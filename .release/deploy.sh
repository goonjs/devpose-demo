#!/usr/bin/env bash
# Demo deploy: pretends to deploy. Create .release/FAIL to simulate a failing deploy.
set -euo pipefail
echo "Deploying $TAG ($RELEASE_SHA)"
if [ -f .release/FAIL ]; then echo "simulated deploy failure" >&2; exit 1; fi
echo "health check: ok"
