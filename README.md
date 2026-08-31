# displexia

Discord bot for a Plex stack: automatic library invites + media requests, wired to [Plex](https://www.plex.tv) and Seerr ([Overseerr](https://overseerr.dev) / [Jellyseerr](https://github.com/fallenbagel/jellyseerr)). Point it at your own servers via `.env` — nothing is hardcoded.

## Features

**Invite channel (default `#join-plex`) — Plex access**

- 🎟️ **Get Plex Access** button → private modal asks for their Plex email
- ⌨️ Typing an email in the channel works too — deleted instantly for privacy, result via DM
- 🔍 `/plexinvite email:...` — private reply
- Success = Plex invite email sent + the `ROLE_NAME` role assigned automatically
- Shares the libraries in `LIBRARIES` (`all` = everything)

**Requests channel — movies & TV (requires `REQUESTS_ROLE_NAME`)**

- 🔎 **Search & Request** button, ⌨️ typing a title in the channel, or 🎯 `/request title:...`
- Searching and picking is fully private: typed titles are deleted, result menus are ephemeral or self-destruct, and nothing appears in the channel until the request is actually sent — then one announcement is posted
- Requests go to Seerr, which routes movies→Radarr / TV→Sonarr with your profiles
- Knows what's already on Plex or already queued, and says so instead of double-requesting

Rate-limited, everything logged (`journalctl -u displexia`).

## Install (fresh, Debian/Ubuntu — bare metal, VM, or LXC)

```bash
apt-get update && apt-get install -y git
git clone https://github.com/<your-user>/displexia /opt/displexia
cd /opt/displexia
cp .env.example .env && nano .env    # fill in tokens/IDs — see comments
bash setup.sh
```

`setup.sh` installs python + venv + deps, runs the [plex.tv/link](https://plex.tv/link) flow if `PLEX_TOKEN` is empty, installs the `displexia` systemd service, and starts it. On first boot the bot posts its button embeds into both channels and syncs the slash commands.

## Update

Push to your repo from your dev machine, then on the box:

```bash
bash /opt/displexia/update.sh     # git pull + deps + restart
```

## Config (`.env`, never committed)

| Key | What |
|---|---|
| `DISCORD_TOKEN` | Bot token — [Discord Developer Portal](https://discord.com/developers/applications) → your app → Bot → Reset Token |
| `GUILD_ID` / `CHANNEL_ID` / `REQUESTS_CHANNEL_ID` | Your server, invite channel, and requests channel IDs (enable Developer Mode, right-click → Copy ID) |
| `PLEX_URL` / `PLEX_TOKEN` | Plex server URL (e.g. `http://192.168.1.10:32400`) + account token (`setup.sh` can fetch it via plex.tv/link) |
| `OVERSEERR_URL` / `OVERSEERR_API_KEY` | Seerr base URL (e.g. `http://192.168.1.11:5055`) + API key (Seerr → Settings → General) |
| `SERVER_NAME` | Branding shown in embeds/commands, e.g. `yourdomain.com` (empty = plain "Plex") |
| `ROLE_NAME` | Role granted on successful invite (default `plex members`) |
| `REQUESTS_ROLE_NAME` | Role required to request (empty = anyone) |
| `LIBRARIES` | `all` or comma-separated library names |

## Discord app setup

1. Create an app at the [Developer Portal](https://discord.com/developers/applications), add a Bot, copy the token.
2. Bot → Privileged Gateway Intents → enable **Message Content Intent**.
3. Invite it with permissions: View Channels, Send Messages, Embed Links, Read Message History, **Manage Messages** (deletes typed emails/titles), **Manage Roles**.
4. Server Settings → Roles: drag the bot's role **above** `ROLE_NAME`.

## Notes

- Requesters need the `REQUESTS_ROLE_NAME` role first; invitees must accept the email from Plex.
- If you're replacing an older install of `plex-invite-bot`, `setup.sh` migrates its `.env`, Plex token, and `state.json` automatically.
