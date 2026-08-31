#!/bin/bash
# Pull the latest displexia from git, update deps, restart the service.
set -e
cd "$(dirname "$0")"
echo "==> git pull"
git pull --ff-only
echo "==> deps"
./venv/bin/pip install --quiet -r requirements.txt
echo "==> restart"
systemctl restart displexia
sleep 2
systemctl --no-pager status displexia | head -8
echo "Updated. Logs: journalctl -u displexia -f"
