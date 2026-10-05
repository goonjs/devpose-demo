import os
import tempfile
import unittest

import release_notes as rn


def rec(subject, body="", author="Ann", email="ann@example.com"):
    return f"abc\x1f{author}\x1f{email}\x1f{subject}\x1f{body}\x1e"


class VersionTests(unittest.TestCase):
    def test_bumps(self):
        self.assertEqual(rn.next_version("v1.2.3", "patch"), "1.2.4")
        self.assertEqual(rn.next_version("v1.2.3", "minor"), "1.3.0")
        self.assertEqual(rn.next_version("1.2.3", "major"), "2.0.0")
        self.assertEqual(rn.next_version("", "minor"), "0.1.0")

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            rn.next_version("release-7", "patch")
        with self.assertRaises(ValueError):
            rn.next_version("v1.0.0", "huge")


class NotesTests(unittest.TestCase):
    log = (rec("feat(cart): add coupons") + rec("fix(api): handle empty basket") +
           rec("perf: cache prices") + rec("docs: update readme") +
           rec("feat!: drop v1 api", "BREAKING CHANGE: v1 removed", "Bo") +
           rec("chore(release): v1.0.0") + rec("plain message"))

    def test_parse_and_group(self):
        cs = rn.parse_commits(self.log)
        self.assertEqual(len(cs), 6)  # release commit skipped
        g = rn.group(cs)
        self.assertEqual(g["features"], ["add coupons (cart)", "drop v1 api"])
        self.assertEqual(g["fixes"], ["handle empty basket (api)"])
        self.assertEqual(g["improvements"], ["cache prices"])
        self.assertEqual(g["breaking"], ["drop v1 api"])
        self.assertEqual(g["other"], ["update readme", "plain message"])

    def test_render_omits_empty_sections_in_both_languages(self):
        class A:  # minimal args
            project, version, previous, date, bump, repo = "Acme", "1.1.0", "v1.0.0", "2026-10-05", "minor", "o/r"
        g = rn.group(rn.parse_commits(rec("fix: one bug")))
        en = rn.build_notes("en", A, g, ["Ann"], None)
        th = rn.build_notes("th", A, g, ["Ann"], None)
        self.assertIn("## Fixes", en)
        self.assertNotIn("## New", en)
        self.assertNotIn("Breaking", en)
        self.assertIn("## การแก้ไขข้อผิดพลาด", th)
        self.assertNotIn("## สิ่งใหม่", th)
        self.assertIn("https://github.com/o/r/compare/v1.0.0...v1.1.0", en)
        self.assertIn("ไมเนอร์", th)

    def test_notes_dir_fills_summary_highlights_upgrade(self):
        class A:
            project, version, previous, date, bump, repo = "Acme", "1.1.0", "v1.0.0", "2026-10-05", "minor", ""
        with tempfile.TemporaryDirectory() as d:
            for name, text in {"summary.en.md": "S", "highlights.en.md": "- H1", "upgrade.en.md": "Run migrations first",
                               "summary.th.md": "สรุป", "highlights.th.md": "- ข้อ1"}.items():
                open(os.path.join(d, name), "w", encoding="utf-8").write(text)
            g = rn.group(rn.parse_commits(rec("feat: x")))
            en = rn.build_notes("en", A, g, [], rn.load_notes_dir(d, "en"))
            th = rn.build_notes("th", A, g, [], rn.load_notes_dir(d, "th"))
            self.assertIn("## Highlights\n\n- H1", en)
            self.assertIn("## Upgrade notes\n\nRun migrations first", en)
            self.assertIn("## ไฮไลต์\n\n- ข้อ1", th)
            self.assertNotIn("หมายเหตุสำหรับการอัปเกรด", th)  # no upgrade.th.md -> section omitted

    def test_missing_notes_dir_is_fine(self):
        self.assertEqual(rn.load_notes_dir("", "en"), {})
        self.assertEqual(rn.load_notes_dir("/nonexistent", "th"), {})


class ReadinessTests(unittest.TestCase):
    files = ["db/migrations/001_add.sql", "package.json", "Dockerfile", ".env.example",
             ".github/workflows/ci.yml", "src/app.ts", "README.md"]
    added = [("src/app.ts", "const k = process.env.PAYMENT_API_KEY;"),
             (".env.example", "PAYMENT_API_KEY=changeme"),
             (".github/workflows/ci.yml", "  token: ${{ secrets.DEPLOY_TOKEN }}"),
             (".github/workflows/ci.yml", "  token: ${{ secrets.GITHUB_TOKEN }}"),
             (".github/workflows/ci.yml", "    - cron: '0 3 * * *'")]

    def test_analyze_detects_each_kind(self):
        commits = rn.parse_commits(rec("feat!: new api", "BREAKING CHANGE: x"))
        a = rn.analyze(self.files, self.added, commits)
        self.assertEqual(a["migrations"], ["db/migrations/001_add.sql"])
        self.assertEqual(a["env_names"], ["PAYMENT_API_KEY"])
        self.assertEqual(a["gh_secrets"], ["DEPLOY_TOKEN"])  # GITHUB_TOKEN ignored
        self.assertEqual(a["deps"], ["package.json"])
        self.assertEqual(a["runtime"], ["Dockerfile"])
        self.assertEqual(a["crons"], 1)
        self.assertEqual(a["breaking"], ["new api"])

    def test_test_files_are_ignored(self):
        added = [("tools/release/test_release_notes.py", "x = process.env.FAKE_TEST_KEY"),
                 ("test/app.test.js", "process.env.ANOTHER_FAKE"),
                 ("src/app.js", "process.env.REAL_KEY")]
        self.assertEqual(rn.analyze(["src/app.js"], added, [])["env_names"], ["REAL_KEY"])

    def test_commits_keep_the_author_email(self):
        cs = rn.parse_commits(rec("fix: a", author="Chalat", email="C@Example.com"))
        self.assertEqual(cs[0]["email"], "c@example.com")

    def test_render_always_has_questions_and_manual_checks(self):
        quiet = rn.render_readiness(rn.analyze(["README.md"], [], []), "v1.0.0", "HEAD")
        self.assertIn("Nothing risky detected", quiet)
        self.assertIn("Decide before releasing", quiet)
        self.assertIn("After the deploy: manual checks", quiet)
        loud = rn.render_readiness(rn.analyze(self.files, self.added, []), "v1.0.0", "HEAD")
        self.assertIn("Database or schema changes", loud)
        self.assertIn("Because of the schema change", loud)
        self.assertIn("`PAYMENT_API_KEY`", loud)


class ChangelogTests(unittest.TestCase):
    def test_prepend_keeps_header_and_older_entries(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "CHANGELOG.md")
            open(p, "w").write("# Changelog\n\n## Acme v1.0.0\n\n- old\n")
            rn.prepend_changelog(p, "# Acme v1.1.0\n\n- new\n")
            txt = open(p).read()
            self.assertTrue(txt.startswith("# Changelog"))
            self.assertLess(txt.index("Acme v1.1.0"), txt.index("Acme v1.0.0"))
            self.assertIn("## Acme v1.1.0", txt)

    def test_creates_changelog_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "CHANGELOG.md")
            rn.prepend_changelog(p, "# Acme v0.1.0\n\n- first\n")
            self.assertTrue(open(p).read().startswith("# Changelog"))


if __name__ == "__main__":
    unittest.main()
