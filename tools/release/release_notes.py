#!/usr/bin/env python3
"""Release helper: next version, bilingual (English + Thai) release notes, and a readiness brief.

    release_notes.py next-version --latest v1.2.3 --bump minor        -> 1.3.0
    release_notes.py readiness --since v1.2.3 [--until HEAD]            -> Markdown brief
    release_notes.py notes --version 1.3.0 --previous v1.2.3 --since v1.2.3 \
        --project "Acme Shop" --repo owner/name --bump minor --out-dir out [--notes-dir .release/notes]
    release_notes.py changelog --file CHANGELOG.md --entry out/RELEASE_NOTES.en.md

Notes are built from Conventional Commit subjects between --since and --until and rendered through
templates/release/release-notes.{en,th}.md. A person or an AI assistant (Claude Desktop, Remote or
CLI) can add a summary, highlights and upgrade notes by writing files into --notes-dir:
    summary.en.md summary.th.md  highlights.en.md highlights.th.md  upgrade.en.md upgrade.th.md
No API key and no network access: this tool never calls an external service. Standard library only.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "..", "..", "templates", "release")
GROUPS = {"feat": "features", "perf": "improvements", "refactor": "improvements", "fix": "fixes",
          "revert": "fixes"}
BUMP_LABEL = {
    "en": {"major": "Major", "minor": "Minor", "patch": "Patch"},
    "th": {"major": "เมเจอร์ (Major)", "minor": "ไมเนอร์ (Minor)", "patch": "แพตช์ (Patch)"},
}
SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
CONVENTIONAL = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<subject>.+)$")

# --- readiness detection -------------------------------------------------------------------------
MIGRATION = re.compile(r"(^|/)(migrations?|db/migrate|alembic|drizzle|prisma/migrations|supabase/migrations)(/|$)|\.sql$")
ENV_EXAMPLE = re.compile(r"(^|/)\.env(\.[\w-]+)?\.(example|sample|template)$")
DEPS = re.compile(r"(^|/)(package\.json|package-lock\.json|bun\.lockb?|yarn\.lock|pnpm-lock\.yaml|requirements[\w.-]*\.txt|"
                  r"pyproject\.toml|poetry\.lock|Pipfile\.lock|go\.mod|go\.sum|Gemfile\.lock|pubspec\.(yaml|lock)|Cargo\.lock|composer\.lock)$")
RUNTIME = re.compile(r"(^|/)(Dockerfile[\w.-]*|docker-compose[\w.-]*\.ya?ml|\.nvmrc|\.node-version|\.tool-versions|"
                     r"[\w.-]+\.tf|cloudbuild[\w.-]*\.ya?ml|app\.ya?ml|Chart\.ya?ml|vercel\.json|firebase\.json)$")
WORKFLOW = re.compile(r"(^|/)\.github/workflows/")
ENV_USE = re.compile(r"(?:process\.env\.|import\.meta\.env\.|os\.environ\[['\"]|os\.getenv\(['\"]|ENV\[['\"])([A-Z][A-Z0-9_]{2,})")
GH_SECRET = re.compile(r"\b(?:secrets|vars)\.([A-Z][A-Z0-9_]+)")
CRON = re.compile(r"^\s*-?\s*cron:\s*['\"]")

READINESS_QUESTIONS = """### Decide before releasing

- [ ] Who approves production, and is it a quiet time for the users?
- [ ] Rollback plan: the previous tag, and is any data or schema change reversible?
- [ ] Anything to do by hand: data backfill, cache purge, DNS or domain, webhook or callback URL, third-party settings, feature flags, scheduled jobs?
- [ ] Does anyone (users, support, partners) need to be told, and in which language?
- [ ] Upgrade notes written for anything above (`.release/notes/upgrade.en.md` and `.th.md`)?

### After the deploy: manual checks on the new environment

- [ ] Health check and startup logs are clean; error rate is not rising (error tracker, logs).
- [ ] Sign in and the 2-3 most important user journeys work end to end on a phone-size screen.
- [ ] Anything that touches money, permissions, personal data or notifications is tested by a person.
- [ ] New or changed screens match the design; empty, loading and error states look right.
- [ ] Lower environments still serve noindex; production serves the right robots rules.
- [ ] Background jobs and integrations ran once (emails, webhooks, scheduled tasks).
- [ ] A person signs off in the release thread, or rolls back.
"""


def next_version(latest, bump):
    m = SEMVER.match(latest or "v0.0.0")
    if not m:
        raise ValueError(f"latest tag '{latest}' is not vMAJOR.MINOR.PATCH")
    major, minor, patch = map(int, m.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError("bump must be patch, minor or major")


def parse_commits(log):
    """log: text with records separated by \\x1e and fields by \\x1f (sha, author, subject, body)."""
    out = []
    for rec in log.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        sha, author, subject, body = (rec.split("\x1f") + ["", "", "", ""])[:4]
        m = CONVENTIONAL.match(subject.strip())
        ctype = m.group("type") if m else "other"
        text = m.group("subject") if m else subject.strip()
        scope = (m.group("scope") if m else None) or ""
        breaking = bool(m and m.group("bang")) or "BREAKING CHANGE" in body
        if ctype == "chore" and scope == "release":
            continue
        out.append({"sha": sha.strip(), "author": author, "type": ctype, "scope": scope,
                    "text": text, "body": body.strip(), "breaking": breaking})
    return out


def group(commits):
    g = {"breaking": [], "features": [], "improvements": [], "fixes": [], "other": []}
    for c in commits:
        line = f"{c['text']} ({c['scope']})" if c["scope"] else c["text"]
        if c["breaking"]:
            g["breaking"].append(line)
        g[GROUPS.get(c["type"], "other")].append(line)
    return g


def bullets(items):
    return "\n".join(f"- {i}" for i in items)


def render(template, values):
    def section(m):
        return m.group(2) if values.get(m.group(1)) else ""
    out = re.sub(r"\{\{#(\w+)\}\}\n?(.*?)\{\{/\1\}\}\n?", section, template, flags=re.S)
    out = re.sub(r"\{\{(\w+)\}\}", lambda m: str(values.get(m.group(1), "")), out)
    return re.sub(r"\n{3,}", "\n\n", out).strip() + "\n"


def load_notes_dir(path, lang):
    """Read optional hand- or assistant-written parts for one language."""
    out = {}
    for key in ("summary", "highlights", "upgrade"):
        f = os.path.join(path, f"{key}.{lang}.md") if path else ""
        if f and os.path.isfile(f):
            out[key] = open(f, encoding="utf-8").read().strip()
    return out


def build_notes(lang, args, groups, contributors, extra=None):
    values = {
        "project": args.project, "version": f"v{args.version}", "previous": args.previous or "-",
        "date": args.date, "bump_label": BUMP_LABEL[lang].get(args.bump, args.bump),
        "compare_url": (f"https://github.com/{args.repo}/compare/{args.previous}...v{args.version}"
                        if args.repo and args.previous else "-"),
        "breaking": bullets(groups["breaking"]), "features": bullets(groups["features"]),
        "improvements": bullets(groups["improvements"]), "fixes": bullets(groups["fixes"]),
        "other": bullets(groups["other"]), "upgrade": "", "contributors": bullets(contributors),
        "summary": "", "highlights": "",
    }
    if groups["breaking"]:
        values["upgrade"] = ("Review the breaking changes above before upgrading." if lang == "en"
                             else "โปรดตรวจสอบการเปลี่ยนแปลงที่ส่งผลกระทบด้านบนก่อนอัปเกรด")
    for key, text in (extra or {}).items():
        if text:
            values[key] = text
    path = os.path.join(TEMPLATES, f"release-notes.{lang}.md")
    return render(open(path, encoding="utf-8").read(), values)


def analyze(files, added_lines, commits):
    """Pure function: what in this release needs a human decision or follow-up."""
    env_names, gh_names, crons = set(), set(), 0
    for path, line in added_lines:
        for m in ENV_USE.finditer(line):
            env_names.add(m.group(1))
        if WORKFLOW.search(path):
            for m in GH_SECRET.finditer(line):
                gh_names.add(m.group(1))
            if CRON.match(line):
                crons += 1
        if ENV_EXAMPLE.search(path):
            m = re.match(r"^\s*([A-Z][A-Z0-9_]+)\s*=", line)
            if m:
                env_names.add(m.group(1))
    gh_names.discard("GITHUB_TOKEN")
    return {
        "migrations": sorted(f for f in files if MIGRATION.search(f)),
        "env_names": sorted(env_names),
        "gh_secrets": sorted(gh_names),
        "deps": sorted(f for f in files if DEPS.search(f)),
        "runtime": sorted(f for f in files if RUNTIME.search(f)),
        "workflows": sorted(f for f in files if WORKFLOW.search(f)),
        "crons": crons,
        "breaking": [c["text"] for c in commits if c["breaking"]],
        "files_changed": len(files),
        "commits": len(commits),
    }


def render_readiness(a, since, until):
    def block(title, items, ask):
        if not items:
            return ""
        shown = "\n".join(f"  - `{i}`" for i in items[:15])
        if len(items) > 15:
            shown += f"\n  - ... and {len(items) - 15} more"
        return f"- [ ] **{title}**\n{shown}\n  - {ask}\n"

    found = "".join([
        block("Database or schema changes", a["migrations"],
              "Backward compatible? Run before or after the deploy? Backup taken? Reversible (down-migration)?"),
        block("New environment variables referenced", a["env_names"],
              "Set in EVERY environment (staging, production) before the deploy; add to the env example file."),
        block("New GitHub secrets or variables referenced", a["gh_secrets"],
              "Create them in the repo or environment before running the workflow."),
        block("Dependency changes", a["deps"], "Lockfile reviewed? Security advisories checked? Runtime still supported?"),
        block("Runtime, container or infrastructure files", a["runtime"], "Does the target environment need a change first?"),
        block("Workflow changes", a["workflows"], "Run the ci-audit before shipping; do new workflows need secrets or permissions?"),
        block("Breaking changes (commit messages)", a["breaking"], "Written up in the upgrade notes (EN and TH)? Who must be told?"),
    ])
    if a["crons"]:
        found += f"- [ ] **{a['crons']} scheduled job(s) added** in workflows\n  - Intended? Scheduled runs use the default branch only.\n"
    out = [f"## Release readiness: `{since or 'start'}..{until}` ({a['commits']} commits, {a['files_changed']} files)\n",
           "### Detected in this release\n",
           found or "_Nothing risky detected automatically. Still answer the questions below._\n",
           READINESS_QUESTIONS]
    if a["migrations"]:
        out.append("**Because of the schema change:** also verify the data after the migration (row counts, a sample of old "
                   "records) and confirm the previous version still works against the new schema.\n")
    return "\n".join(out)


def changed_files_and_added(since, until):
    rng = f"{since}..{until}" if since else until
    if since:
        names = subprocess.run(["git", "diff", "--name-only", rng], capture_output=True, text=True, check=True).stdout.split()
        patch = subprocess.run(["git", "diff", "-U0", "--no-color", rng], capture_output=True, text=True, check=True).stdout
    else:  # no previous tag: everything in the tree counts as new
        empty = subprocess.run(["git", "hash-object", "-t", "tree", "/dev/null"], capture_output=True, text=True, check=True).stdout.strip()
        names = subprocess.run(["git", "diff", "--name-only", empty, until], capture_output=True, text=True, check=True).stdout.split()
        patch = subprocess.run(["git", "diff", "-U0", "--no-color", empty, until], capture_output=True, text=True, check=True).stdout
    added, cur = [], ""
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            added.append((cur, line[1:]))
    return names, added


def prepend_changelog(path, notes_text):
    """Add a release's notes (its '# title' becomes '## title') under the CHANGELOG header."""
    entry = re.sub(r"^# ", "## ", notes_text.strip() + "\n", count=1)
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else "# Changelog\n"
    head, _, rest = old.partition("\n")
    open(path, "w", encoding="utf-8").write(f"{head}\n\n{entry}\n{rest.lstrip(chr(10))}")


def git_log(since, until):
    rng = f"{since}..{until}" if since else until
    r = subprocess.run(["git", "log", rng, "--no-merges", "--format=%H%x1f%an%x1f%s%x1f%b%x1e"],
                       capture_output=True, text=True, check=True)
    return r.stdout


def cmd_notes(args):
    commits = parse_commits(git_log(args.since, args.until))
    if not commits:
        sys.exit("No commits since the previous release; nothing to release.")
    authors = sorted({c["author"] for c in commits if c["author"]})
    groups = group(commits)
    os.makedirs(args.out_dir, exist_ok=True)
    langs = [x for x in args.order.split(",") if x in ("en", "th")]
    bodies, used = {}, set()
    for lang in langs:
        extra = load_notes_dir(args.notes_dir, lang)
        used.update(extra)
        bodies[lang] = build_notes(lang, args, groups, authors, extra)
        open(os.path.join(args.out_dir, f"RELEASE_NOTES.{lang}.md"), "w", encoding="utf-8").write(bodies[lang])
    combined = "\n---\n\n".join(bodies[l] for l in langs)
    open(os.path.join(args.out_dir, "RELEASE_NOTES.md"), "w", encoding="utf-8").write(combined)
    print(f"{len(commits)} commit(s); extra notes used: {', '.join(sorted(used)) or 'none'}; wrote {args.out_dir}/RELEASE_NOTES*.md")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    nv = sub.add_parser("next-version")
    nv.add_argument("--latest", default="v0.0.0")
    nv.add_argument("--bump", required=True, choices=["patch", "minor", "major"])
    r = sub.add_parser("readiness", help="what in this release needs a decision or manual follow-up")
    r.add_argument("--since", default="")
    r.add_argument("--until", default="HEAD")
    n = sub.add_parser("notes")
    n.add_argument("--version", required=True)
    n.add_argument("--previous", default="")
    n.add_argument("--since", default="", help="tag or ref to start after (blank = whole history)")
    n.add_argument("--until", default="HEAD")
    n.add_argument("--project", required=True)
    n.add_argument("--repo", default="", help="owner/name, for the compare link")
    n.add_argument("--bump", default="patch")
    n.add_argument("--date", default=datetime.date.today().isoformat())
    n.add_argument("--order", default="en,th", help="languages in the combined file, e.g. th,en")
    n.add_argument("--notes-dir", default="", help="folder with optional summary/highlights/upgrade .en/.th.md")
    n.add_argument("--out-dir", required=True)
    c = sub.add_parser("changelog", help="prepend a notes file to CHANGELOG.md")
    c.add_argument("--file", default="CHANGELOG.md")
    c.add_argument("--entry", required=True, help="notes file, e.g. RELEASE_NOTES.en.md")
    a = ap.parse_args()
    if a.cmd == "next-version":
        print(next_version(a.latest, a.bump))
    elif a.cmd == "readiness":
        files, added = changed_files_and_added(a.since, a.until)
        commits = parse_commits(git_log(a.since, a.until))
        print(render_readiness(analyze(files, added, commits), a.since, a.until))
    elif a.cmd == "changelog":
        prepend_changelog(a.file, open(a.entry, encoding="utf-8").read())
    else:
        cmd_notes(a)


if __name__ == "__main__":
    main()
