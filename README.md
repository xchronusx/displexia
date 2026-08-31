# displexia

Discord bot for the ztechnus.com Plex stack: automatic library invites + media requests, wired to Plex and Seerr (Overseerr/Jellyseerr).

## Features

**#join-plex — Plex access**

- 🎟️ **Get Plex Access** button → private modal asks for their Plex email
- ⌨️ Typing an email in the channel works too — deleted instantly for privacy, result via DM
- 🔍 `/plexinvite email:...` — private reply
- Success = Plex invite email sent + the **plex members** role assigned automatically
- Shares the libraries in `LIBRARIES` (`all` = everything)

**#media-requests — movies & TV (requires the plex members role)**

- 🔎 **Search & Request** button → search modal → pick from a results menu
- ⌨️ Typing a title in the channel triggers the same search
- 🎯 `/request title:...`
- Requests go to Seerr, which routes movies→Radarr / TV→Sonarr with your profiles
- Knows what's already on Plex or already queued, and says so instead of double-requesting

Rate-limited, everything logged (`journalctl -u displexia`).

## Install (fresh, Debian/Ubuntu LXC)

```bash
apt-get update && apt-get install -y git
git clone https://github.com/YOURUSER/displexia /opt/displexia
cd /opt/displexia
cp .env.example .env && nano .env    # fill in tokens/IDs — see comments
bash setup.sh
```

`setup.sh` installs python + venv + deps, runs the plex.tv/link flow if `PLEX_TOKEN` is empty, installs the `displexia` systemd service, and starts it. On first boot the bot posts its button embeds into both channels and syncs the slash commands.

**Migrating from the old `plex-invite-bot` install:** just run `setup.sh` — it detects `/opt/plex-invite-bot`, carries over `.env` values (incl. the Plex token) and `state.json`, and disables the old service.

## Update (the whole point)

Push to GitHub from your dev machine, then on the box:

```bash
bash /opt/displexia/update.sh     # git pull + deps + restart
```

## Config (`.env`, never committed)

| Key | What |
|---|---|
| `DISCORD_TOKEN` | Bot token (Discord dev portal → Bot → Reset Token) |
| `GUILD_ID` / `CHANNEL_ID` / `REQUESTS_CHANNEL_ID` | Server, #join-plex, #media-requests IDs |
| `PLEX_URL` / `PLEX_TOKEN` | Plex server URL + account token (setup.sh can fetch via plex.tv/link) |
| `OVERSEERR_URL` / `OVERSEERR_API_KEY` | Seerr base URL + API key (Settings → General) |
| `ROLE_NAME` | Role granted on successful invite (`plex members`) |
| `REQUESTS_ROLE_NAME` | Role required to request (empty = anyone) |
| `LIBRARIES` | `all` or comma-separated library names |

## Notes

- Discord app needs: Message Content intent ON; permissions View Channels, Send Messages, Embed Links, Read Message History, Manage Messages, Manage Roles.
- The bot's role must sit **above** `plex members` in Server Settings → Roles.
- Invitees must accept the email from Plex; requesters need the role first.
