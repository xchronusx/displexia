#!/bin/bash
# displexia installer (Debian/Ubuntu LXC). Idempotent — safe to re-run.
# Recommended: git clone the repo to /opt/displexia, cd into it, bash setup.sh
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"

echo "==> Installing system packages"
apt-get update -qq
apt-get install -y -qq python3 python3-venv git >/dev/null

# ---- migrate from the old plex-invite-bot install, once ----
if [ -d /opt/plex-invite-bot ] && [ ! -f .env.migrated ]; then
    echo "==> Migrating from /opt/plex-invite-bot"
    [ ! -f .env ] && [ -f /opt/plex-invite-bot/.env ] && cp /opt/plex-invite-bot/.env .env
    # carry the Plex token over if ours is empty
    if [ -f .env ] && grep -q '^PLEX_TOKEN=$' .env && [ -f /opt/plex-invite-bot/.env ]; then
        OLD=$(grep '^PLEX_TOKEN=' /opt/plex-invite-bot/.env | cut -d= -f2-)
        [ -n "$OLD" ] && sed -i "s|^PLEX_TOKEN=$|PLEX_TOKEN=$OLD|" .env
    fi
    # keep the already-posted channel embeds
    [ ! -f state.json ] && [ -f /opt/plex-invite-bot/state.json ] && cp /opt/plex-invite-bot/state.json state.json
    systemctl disable --now plex-invite-bot 2>/dev/null || true
    rm -f /etc/systemd/system/plex-invite-bot.service
    systemctl daemon-reload
    touch .env.migrated
fi

if [ ! -f .env ]; then
    cp .env.example .env
    echo "!! Created .env from .env.example — edit it, then re-run setup.sh"
    exit 1
fi
chmod 600 .env

echo "==> Virtualenv + dependencies"
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt

if grep -q '^PLEX_TOKEN=$' .env; then
    echo "==> No Plex token yet — starting the plex.tv/link flow"
    ./venv/bin/python get_plex_token.py
fi

echo "==> Installing the displexia CLI (/usr/local/bin/displexia)"
sed "s|__DIR__|$DIR|g" displexia.cli > /usr/local/bin/displexia
chmod +x /usr/local/bin/displexia

echo "==> Installing systemd service (displexia)"
sed "s|__DIR__|$DIR|g" displexia.service > /etc/systemd/system/displexia.service
systemctl daemon-reload
systemctl enable --now displexia
systemctl restart displexia

sleep 3
systemctl --no-pager --full status displexia || true
echo
echo "Done. Logs:  journalctl -u displexia -f    Update:  bash update.sh"
