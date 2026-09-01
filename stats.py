"""displexia usage stats — every interaction counted, per user and in total.

Import side: `bump(event, user)` from the bot.
CLI side:    `displexia stats` (or `python3 stats.py`) prints the report.
"""

import json
import time
from pathlib import Path

__version__ = "2.0.0"

BANNER = r"""
██████╗ ██╗███████╗██████╗ ██╗     ███████╗██╗  ██╗██╗ █████╗
██╔══██╗██║██╔════╝██╔══██╗██║     ██╔════╝╚██╗██╔╝██║██╔══██╗
██║  ██║██║███████╗██████╔╝██║     █████╗   ╚███╔╝ ██║███████║
██║  ██║██║╚════██║██╔═══╝ ██║     ██╔══╝   ██╔██╗ ██║██╔══██║
██████╔╝██║███████║██║     ███████╗███████╗██╔╝ ██╗██║██║  ██║
╚═════╝ ╚═╝╚══════╝╚═╝     ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝╚═╝  ╚═╝"""

STATS_FILE = Path(__file__).resolve().parent / "stats.json"

# event key -> label shown in the report (order = report order)
EVENT_LABELS = {
    "invite_button":     "🎟  Get Plex Access button",
    "request_button":    "🔎  Search & Request button",
    "cmd_plexinvite":    "⌨️  /plexinvite command",
    "cmd_request":       "⌨️  /request command",
    "typed_email":       "📧  Emails typed in channel",
    "typed_request":     "💬  Titles typed in channel",
    "search":            "🔍  Searches run",
    "pick":              "👆  Titles picked from menu",
    "request_ok":        "📥  Requests sent to Seerr",
    "request_fail":      "❌  Requests failed",
    "already_on_plex":   "✅  Already on Plex",
    "already_requested": "⏳  Already in the queue",
    "invite_sent":       "📬  Plex invites sent",
    "invite_pending":    "⏳  Invites already pending",
    "invite_updated":    "🔄  Library shares refreshed",
    "invite_error":      "❌  Invite errors",
    "became_available":  "🟢  Cards flipped to available",
    "cmd_mystatus":      "📈  /mystatus checks",
    "new_on_plex":       "🆕  New-on-Plex announcements",
    "revoked":           "🔐  Plex shares auto-revoked",
}


def _load() -> dict:
    try:
        return json.loads(STATS_FILE.read_text())
    except Exception:
        return {}


def _save(data: dict):
    try:
        STATS_FILE.write_text(json.dumps(data))
    except Exception:
        pass  # stats must never break the bot


def bump(event: str, user=None):
    """Count one occurrence of `event`, optionally attributed to a Discord user."""
    data = _load()
    data.setdefault("since", time.time())
    totals = data.setdefault("totals", {})
    totals[event] = totals.get(event, 0) + 1
    if user is not None:
        users = data.setdefault("users", {})
        u = users.setdefault(str(user.id), {"events": {}})
        u["name"] = getattr(user, "display_name", None) or str(user)
        u["last"] = time.time()
        u["events"][event] = u["events"].get(event, 0) + 1
    _save(data)


# ---------------------------------------------------------------- report

def _ago(ts: float) -> str:
    d = max(0, int(time.time() - ts))
    for unit, secs in (("d", 86400), ("h", 3600), ("m", 60)):
        if d >= secs:
            return f"{d // secs}{unit} ago"
    return "just now"


def _user_cols(ev: dict) -> tuple[int, int, int, int, int]:
    buttons = ev.get("invite_button", 0) + ev.get("request_button", 0)
    searches = ev.get("search", 0)
    picks = ev.get("pick", 0)
    requests = ev.get("request_ok", 0)
    invites = ev.get("invite_sent", 0) + ev.get("invite_updated", 0)
    return (buttons, searches, picks, requests, invites)


def report() -> str:
    data = _load()
    out = [BANNER, f"  v{__version__} — usage report"]
    if not data.get("totals"):
        out.append("\n  Nothing counted yet — go push some buttons.\n")
        return "\n".join(out)

    since = data.get("since")
    if since:
        days = max(1, round((time.time() - since) / 86400))
        out[-1] += f" · since {time.strftime('%Y-%m-%d', time.localtime(since))} ({days}d)"
    out.append("")

    width = max(len(label) for label in EVENT_LABELS.values()) + 2
    out.append(f"  {'EVENT':<{width}}COUNT")
    out.append(f"  {'─' * width}─────")
    totals = data["totals"]
    for key, label in EVENT_LABELS.items():
        if totals.get(key):
            out.append(f"  {label:<{width}}{totals[key]:>5}")
    for key, n in sorted(totals.items()):          # anything not in the label map
        if key not in EVENT_LABELS:
            out.append(f"  {key:<{width}}{n:>5}")

    users = data.get("users", {})
    if users:
        out.append("")
        name_w = max(12, max(len(u.get("name", "?")) for u in users.values()) + 2)
        out.append(f"  {'USER':<{name_w}}{'BUTTONS':>8}{'SEARCHES':>10}{'PICKS':>7}"
                   f"{'REQUESTS':>10}{'INVITES':>9}   LAST SEEN")
        out.append(f"  {'─' * (name_w + 44 + 11)}")
        ranked = sorted(users.values(),
                        key=lambda u: -sum(_user_cols(u.get("events", {}))))
        for u in ranked:
            b, s, p, r, i = _user_cols(u.get("events", {}))
            out.append(f"  {u.get('name', '?'):<{name_w}}{b:>8}{s:>10}{p:>7}"
                       f"{r:>10}{i:>9}   {_ago(u.get('last', 0))}")
    out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    print(report())
