#!/bin/bash
# Pull the latest displexia from git, update deps + CLI + service, restart.
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"
echo "==> git pull"
git pull --ff-only
echo "==> deps"
./venv/bin/pip install --quiet -r requirements.txt
echo "==> refresh CLI + service"
sed "s|__DIR__|$DIR|g" displexia.cli > /usr/local/bin/displexia && chmod +x /usr/local/bin/displexia
sed "s|__DIR__|$DIR|g" displexia.service > /etc/systemd/system/displexia.service
systemctl daemon-reload
echo "==> restart"
systemctl restart displexia
sleep 2
systemctl --no-pager status displexia | head -8
echo "Updated. Logs: displexia logs"
