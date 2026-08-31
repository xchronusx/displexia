# displexia

```
██████╗ ██╗███████╗██████╗ ██╗     ███████╗██╗  ██╗██╗ █████╗
██╔══██╗██║██╔════╝██╔══██╗██║     ██╔════╝╚██╗██╔╝██║██╔══██╗
██║  ██║██║███████╗██████╔╝██║     █████╗   ╚███╔╝ ██║███████║
██║  ██║██║╚════██║██╔═══╝ ██║     ██╔══╝   ██╔██╗ ██║██╔══██║
██████╔╝██║███████║██║     ███████╗███████╗██╔╝ ██╗██║██║  ██║
╚═════╝ ╚═╝╚══════╝╚═╝     ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝╚═╝  ╚═╝
```

**The Discord front door for your Plex server.** Automatic library invites + media requests, wired to [Plex](https://www.plex.tv) and Seerr ([Overseerr](https://overseerr.dev) / [Jellyseerr](https://github.com/fallenbagel/jellyseerr)). Point it at your own servers via `.env` — nothing is hardcoded. MIT licensed, one-command install, one-command updates.

## Features

**Invite channel (default `#join-plex`) — Plex access**

- 🎟️ **Get Plex Access** button → private modal asks for their Plex email
- ⌨️ Typing an email in the channel works too — deleted instantly for privacy, result via DM
- 🔍 `/plexinvite email:...` — private reply
- Success = Plex invite email sent + the `ROLE_NAME` role assigned automatically
- Shares the libraries in `LIBRARIES` (`all` = everything)

**Requests channel — movies & TV (requires `REQUESTS_ROLE_NAME`)**

- 🔎 **Search & Request** button, ⌨️ typing a title in the channel, or 🎯 `/request title:...`
- Fully private flow: typed titles are deleted, result menus are ephemeral or self-destruct — nothing shows until a request is actually sent
- Announcements are rich info cards (poster, title, year, description), routed per type to `#movies` / `#tv`
- When the download lands, the card turns **green**: *"Requested by X • Available to watch on plex.yourdomain.com now"* (polled from Seerr every 5 min, survives restarts)
- Knows what's already on Plex or queued, and says so instead of double-requesting
- The button embeds re-post themselves so they always sit at the bottom of their channel

**Ops**

- 📊 Every interaction is counted per user — `displexia stats` prints the report
- 🛡️ Rate-limited, admins bypass the request role gate, everything logged
- 🔁 `displexia update` pulls, installs, restarts

## Install (fresh, Debian/Ubuntu — bare metal, VM, or LXC)

```bash
apt-get update && apt-get install -y git
git clone https://github.com/xchronusx/displexia /opt/displexia
cd /opt/displexia
cp .env.example .env && nano .env    # fill in tokens/IDs — see comments
bash setup.sh
```

`setup.sh` installs python + venv + deps, runs the [plex.tv/link](https://plex.tv/link) flow if `PLEX_TOKEN` is empty, installs the systemd service and the `displexia` CLI, and starts the bot. On first boot it posts its button embeds and syncs the slash commands.

## The `displexia` CLI

```
displexia update     pull the latest code, install deps, restart the bot
displexia stats      usage report — every button press, search, request, per user
displexia logs       follow the live bot logs
displexia status     systemd service status
displexia restart    restart the bot
```

`displexia stats` looks like this:

```
  EVENT                            COUNT
  ─────────────────────────────────────
  🎟  Get Plex Access button          12
  🔎  Search & Request button         34
  🔍  Searches run                    41
  👆  Titles picked from menu         29
  📥  Requests sent to Seerr          24
  🟢  Cards flipped to available      19

  USER          BUTTONS  SEARCHES  PICKS  REQUESTS  INVITES   LAST SEEN
  ─────────────────────────────────────────────────────────────────────
  GOD                21        28     22        19        1   2h ago
```

## Config (`.env`, never committed)

| Key | What |
|---|---|
| `DISCORD_TOKEN` | Bot token — [Discord Developer Portal](https://discord.com/developers/applications) → your app → Bot → Reset Token |
| `GUILD_ID` / `CHANNEL_ID` / `REQUESTS_CHANNEL_ID` | Your server, invite channel, and requests channel IDs (enable Developer Mode, right-click → Copy ID) |
| `PLEX_URL` / `PLEX_TOKEN` | Plex server URL (e.g. `http://192.168.1.10:32400`) + account token (`setup.sh` can fetch it via plex.tv/link) |
| `OVERSEERR_URL` / `OVERSEERR_API_KEY` | Seerr base URL (e.g. `http://192.168.1.11:5055`) + API key (Seerr → Settings → General) |
| `MOVIES_CHANNEL` / `TV_CHANNEL` | Where announcement cards go, per type — channel name (`movies`, `tv`) or ID; empty = the requests channel |
| `PLEX_LINK` | Shown on green "available" cards, e.g. `plex.yourdomain.com` (empty = "Plex") |
| `SERVER_NAME` | Branding shown in embeds/commands, e.g. `yourdomain.com` (empty = plain "Plex") |
| `ROLE_NAME` | Role granted on successful invite (default `plex members`) |
| `REQUESTS_ROLE_NAME` | Role required to request (empty = anyone; admins always allowed) |
| `LIBRARIES` | `all` or comma-separated library names |

## Discord app setup

1. Create an app at the [Developer Portal](https://discord.com/developers/applications), add a Bot, copy the token.
2. Bot → Privileged Gateway Intents → enable **Message Content Intent**.
3. Invite it with permissions: View Channels, Send Messages, Embed Links, Read Message History, **Manage Messages** (deletes typed emails/titles), **Manage Roles**.
4. Server Settings → Roles: drag the bot's role **above** `ROLE_NAME`.

## Project layout

```
bot.py             the Discord bot (invites, requests, cards, watcher, sticky embeds)
seerr.py           tiny async Overseerr/Jellyseerr API client
stats.py           usage counters + the `displexia stats` report
get_plex_token.py  plex.tv/link token helper (used by setup.sh)
setup.sh           installer: deps, token flow, systemd service, CLI
update.sh          what `displexia update` runs
displexia.cli      the /usr/local/bin/displexia command
displexia.service  systemd unit template
```

Runtime files `state.json` (sticky embeds + availability watches) and `stats.json` (usage counters) live next to the code and are gitignored, as is `.env`.

## License

[MIT](LICENSE) — take it, run it, share it with every Plex admin you know.
