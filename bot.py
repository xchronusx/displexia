"""displexia — Plex Discord bot: library invites + Seerr media requests.

#join-plex        → Plex library invites (button/modal, typed email, /plexinvite)
#media-requests   → movie & TV requests via Seerr (button/modal, typed title, /request)

Successful invitees get the ROLE_NAME role; requests require REQUESTS_ROLE_NAME.
Branding comes from SERVER_NAME in .env — nothing server-specific is hardcoded.
"""

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

from seerr import SeerrClient, STATUS_LABEL

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ.get("GUILD_ID") or 0)
CHANNEL_ID = int(os.environ.get("CHANNEL_ID") or 0)
CHANNEL_NAME = os.environ.get("CHANNEL_NAME", "join-plex")
REQUESTS_CHANNEL_ID = int(os.environ.get("REQUESTS_CHANNEL_ID") or 0)
PLEX_TOKEN = os.environ.get("PLEX_TOKEN", "").strip()
PLEX_URL = os.environ.get("PLEX_URL", "").strip()
ROLE_NAME = os.environ.get("ROLE_NAME", "plex members")
REQUESTS_ROLE_NAME = os.environ.get("REQUESTS_ROLE_NAME", "").strip()
LIBRARIES = os.environ.get("LIBRARIES", "all").strip()
OVERSEERR_URL = os.environ.get("OVERSEERR_URL", "").strip()
OVERSEERR_API_KEY = os.environ.get("OVERSEERR_API_KEY", "").strip()
SERVER_NAME = os.environ.get("SERVER_NAME", "").strip()
PLEX_NAME = f"{SERVER_NAME} Plex".strip()  # "yourdomain.com Plex" or just "Plex"
# Per-type announcement channels (name like "tv"/"movies" or a channel ID);
# empty = announce in the requests channel.
ANNOUNCE_CHANNEL = {
    "movie": os.environ.get("MOVIES_CHANNEL", "").strip().lstrip("#"),
    "tv": os.environ.get("TV_CHANNEL", "").strip().lstrip("#"),
}
SETUP_TEST = os.environ.get("SETUP_TEST") == "1"

STATE_FILE = BASE_DIR / "state.json"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("displexia")

seerr = SeerrClient(OVERSEERR_URL, OVERSEERR_API_KEY) if OVERSEERR_URL and OVERSEERR_API_KEY else None

# ---------------------------------------------------------------- Plex invites

_account = None
_server = None


def _connect_account():
    global _account
    if _account is None:
        from plexapi.myplex import MyPlexAccount
        _account = MyPlexAccount(token=PLEX_TOKEN)
    return _account


def _connect_server():
    global _server
    if _server is None:
        from plexapi.server import PlexServer
        _server = PlexServer(PLEX_URL, PLEX_TOKEN, timeout=20)
    return _server


def _sections(plex):
    if LIBRARIES.lower() == "all":
        return plex.library.sections()
    wanted = {n.strip().lower() for n in LIBRARIES.split(",") if n.strip()}
    return [s for s in plex.library.sections() if s.title.lower() in wanted]


def invite_email_sync(email: str):
    """Runs in a worker thread. Returns (status, detail).

    status: sent | pending | updated | error
    """
    if not PLEX_TOKEN:
        return ("error", "Plex is not configured yet (missing PLEX_TOKEN). Tell the server admin.")
    email_l = email.lower()
    try:
        acct = _connect_account()
        plex = _connect_server()
        secs = _sections(plex)

        try:
            for inv in acct.pendingInvites(includeSent=True, includeReceived=False):
                if (getattr(inv, "email", "") or "").lower() == email_l or \
                   (getattr(inv, "username", "") or "").lower() == email_l:
                    return ("pending", "An invite for that address is already waiting — "
                                       "check your email (including spam) and accept it.")
        except Exception:
            pass

        friend = None
        for u in acct.users():
            if (u.email or "").lower() == email_l or (u.username or "").lower() == email_l:
                friend = u
                break
        if friend is not None:
            try:
                acct.updateFriend(friend, plex, sections=secs)
                return ("updated", "That account already has access — library share refreshed.")
            except Exception as e:
                log.warning("updateFriend failed for %s: %s", email, e)
                return ("updated", "That account already has access to the server.")

        acct.inviteFriend(email, plex, sections=secs)
        return ("sent", "Invite sent!")
    except Exception as e:
        msg = str(e)
        low = msg.lower()
        if "already" in low and ("shar" in low or "invit" in low or "friend" in low or "exist" in low):
            return ("pending", "Looks like that address was already invited — check your email and accept it.")
        log.exception("Plex invite failed for %s", email)
        return ("error", f"Plex said no: {msg[:300]}")


# ---------------------------------------------------------------- Discord client

intents = discord.Intents.default()
intents.message_content = True


class Displexia(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.invite_cd: dict[int, list[float]] = {}
        self.request_cd: dict[int, list[float]] = {}

    async def setup_hook(self):
        self.add_view(InviteView())
        self.add_view(RequestButtonView())
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)

    async def close(self):
        if seerr:
            await seerr.close()
        await super().close()


bot = Displexia()


def check_cooldown(bucket: dict, user_id: int, limit: int = 3, window: int = 600) -> bool:
    now = time.time()
    hits = [t for t in bucket.get(user_id, []) if now - t < window]
    if len(hits) >= limit:
        bucket[user_id] = hits
        return False
    hits.append(now)
    bucket[user_id] = hits
    return True


async def ensure_role(guild: discord.Guild) -> discord.Role | None:
    role = discord.utils.get(guild.roles, name=ROLE_NAME)
    if role is None:
        try:
            role = await guild.create_role(
                name=ROLE_NAME,
                colour=discord.Colour.from_str("#e5a00d"),
                reason="Created by displexia",
            )
            log.info("Created role %r", ROLE_NAME)
        except discord.Forbidden:
            log.error("No permission to create role %r", ROLE_NAME)
            return None
    return role


async def grant_role(member: discord.Member) -> str:
    if not isinstance(member, discord.Member):
        return ""
    role = await ensure_role(member.guild)
    if role is None or role in member.roles:
        return ""
    try:
        await member.add_roles(role, reason="Plex invite sent")
        return f" You've been given the **{ROLE_NAME}** role."
    except discord.Forbidden:
        log.error("Missing permission to assign %r (check role order)", ROLE_NAME)
        return ""


def requests_role_ok(member: discord.Member) -> bool:
    if not REQUESTS_ROLE_NAME:
        return True
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator:
        return True  # admins are never locked out of requests
    return discord.utils.get(member.roles, name=REQUESTS_ROLE_NAME) is not None


def requests_role_denial() -> str:
    where = f"<#{CHANNEL_ID}>" if CHANNEL_ID else f"#{CHANNEL_NAME}"
    return (f"🔒 You need the **{REQUESTS_ROLE_NAME}** role to request media. "
            f"Grab Plex access in {where} first!")


# ---------------------------------------------------------------- invite flows

RESULT_PREFIX = {"sent": "📬", "pending": "⏳", "updated": "✅", "error": "❌"}


async def run_invite(member: discord.Member, email: str) -> tuple[str, str]:
    email = email.strip()
    if not EMAIL_RE.fullmatch(email):
        return ("error", "That doesn't look like a valid email address — try again.")
    if not check_cooldown(bot.invite_cd, member.id):
        return ("error", "Too many attempts — wait a few minutes and try again.")

    status, detail = await asyncio.to_thread(invite_email_sync, email)
    log.info("invite: discord=%s (%s) email=%s -> %s", member, member.id, email, status)

    role_note = ""
    if status in ("sent", "pending", "updated"):
        role_note = await grant_role(member)

    if status == "sent":
        text = (f"Invite sent to `{email}`! Open the invitation email from Plex "
                f"(check spam too), hit **Accept**, then sign in at <https://app.plex.tv>."
                f"{role_note}")
    else:
        text = f"{detail}{role_note}"
    return (status, f"{RESULT_PREFIX[status]} {text}")


class EmailModal(discord.ui.Modal, title="Get Plex Access"):
    email = discord.ui.TextInput(label="Your Plex account email",
                                 placeholder="you@example.com", max_length=120)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        _, text = await run_invite(interaction.user, str(self.email.value))
        await interaction.followup.send(text, ephemeral=True)


class InviteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Get Plex Access", style=discord.ButtonStyle.success,
                       emoji="🎟️", custom_id="ztplex:invite")
    async def invite_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmailModal())


@bot.tree.command(name="plexinvite", description=f"Get invited to the {PLEX_NAME} server")
@app_commands.describe(email="The email address of your Plex account")
async def plexinvite(interaction: discord.Interaction, email: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    _, text = await run_invite(interaction.user, email)
    await interaction.followup.send(text, ephemeral=True)


async def handle_invite_message(message: discord.Message):
    match = EMAIL_RE.search(message.content or "")
    if not match:
        return
    email = match.group(0)
    try:
        await message.delete()
    except discord.Forbidden:
        pass

    status, text = await run_invite(message.author, email)

    dm_ok = True
    try:
        await message.author.send(text)
    except discord.Forbidden:
        dm_ok = False

    note = "📬 I removed your message to keep your email private."
    if status == "sent":
        summary = "Your Plex invite is on its way — check your email!"
    elif status in ("pending", "updated"):
        summary = "Check your DMs — that address is already set up or invited."
    else:
        summary = "That didn't work — check your DMs for details." if dm_ok else text
    try:
        await message.channel.send(f"{message.author.mention} {note} {summary}", delete_after=45)
    except discord.Forbidden:
        pass
    await restick(message.channel, "invite_message_id", build_invite_embed(), InviteView())


# ---------------------------------------------------------------- request flows

TYPE_EMOJI = {"movie": "🎬", "tv": "📺"}
TYPE_LABEL = {"movie": "Movie", "tv": "TV Show"}
TYPE_COLOUR = {"movie": "#e5a00d", "tv": "#5865f2"}


def build_media_embed(pick: dict, footer: str | None = None) -> discord.Embed:
    """Info card for a search pick: artwork, title, year, description."""
    title = f"{pick['title']} ({pick['year']})" if pick["year"] else pick["title"]
    e = discord.Embed(
        title=f"{TYPE_EMOJI[pick['media_type']]}  {title}",
        colour=discord.Colour.from_str(TYPE_COLOUR[pick["media_type"]]),
        description=pick.get("overview") or "No description available.",
    )
    if pick.get("poster"):
        e.set_thumbnail(url=pick["poster"])
    if footer:
        e.set_footer(text=footer)
    return e


def build_options(results: list[dict]) -> list[discord.SelectOption]:
    opts = []
    for i, r in enumerate(results):
        label = f"{r['title']} ({r['year']})" if r["year"] else r["title"]
        desc = TYPE_LABEL[r["media_type"]]
        if r["status"] in STATUS_LABEL:
            desc += f" · {STATUS_LABEL[r['status']].split(' ', 1)[1]}"
        opts.append(discord.SelectOption(
            label=label[:100],
            description=desc[:100],
            value=f"{r['media_type']}:{r['tmdb_id']}:{i}",
            emoji=TYPE_EMOJI[r["media_type"]],
        ))
    return opts


class ResultsView(discord.ui.View):
    """Select menu of search results, locked to the requester.

    Everything stays hidden until the request is actually sent: menus are
    ephemeral (button/slash) or self-destruct (typed flow), results go
    privately to the requester, and the only public trace is the
    announcement posted after Seerr accepts the request.
    """

    def __init__(self, requester_id: int, results: list[dict], public: bool = False):
        super().__init__(timeout=180)
        self.requester_id = requester_id
        self.public = public                 # True = menu is a normal channel message
        self.menu_message = None             # set by the caller after sending the menu
        self.results = {f"{r['media_type']}:{r['tmdb_id']}:{i}": r for i, r in enumerate(results)}
        select = discord.ui.Select(placeholder="Pick the title you want…",
                                   options=build_options(results))
        select.callback = self.on_pick
        self.select = select
        self.add_item(select)

    async def on_timeout(self):
        if self.menu_message is None:
            return
        try:
            if self.public:
                await self.menu_message.delete()   # leave no trace in the channel
            else:
                await self.menu_message.edit(
                    content="⌛ Search expired — start a new search.", view=None)
        except discord.HTTPException:
            pass

    async def on_pick(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "That menu belongs to someone else — start your own search.",
                ephemeral=True)
            return
        pick = self.results[self.select.values[0]]
        self.stop()

        if self.public:
            # Typed flow: acknowledge privately, then remove the menu from the channel.
            await interaction.response.defer(ephemeral=True, thinking=True)
            menu = self.menu_message or interaction.message
            if menu is not None:
                try:
                    await menu.delete()
                except discord.HTTPException:
                    pass
        else:
            # Ephemeral menu: swap it for a progress note. This UPDATE_MESSAGE
            # response also makes the menu the interaction's original response,
            # so the edit below reliably lands on it.
            await interaction.response.edit_message(
                content=f"⏳ Requesting **{pick['title']}**…", view=None)

        text, card = await submit_request(interaction.user, pick, interaction.channel)
        try:
            await interaction.edit_original_response(content=text, embed=card, view=None)
        except discord.HTTPException:
            try:
                await interaction.followup.send(
                    text, embed=card or discord.utils.MISSING, ephemeral=True)
            except discord.HTTPException:
                log.warning("Could not deliver request result to %s (%s)",
                            interaction.user, interaction.user.id)


def announce_channel_for(media_type: str, member, fallback_channel):
    """Route the announcement card: #movies / #tv if configured, else requests channel."""
    conf = ANNOUNCE_CHANNEL.get(media_type, "")
    ch = None
    if conf:
        if conf.isdigit():
            ch = bot.get_channel(int(conf))
        else:
            guild = getattr(member, "guild", None)
            if guild:
                ch = discord.utils.get(guild.text_channels, name=conf)
        if ch is None:
            log.warning("Announce channel %r for %s not found — using the requests channel",
                        conf, media_type)
    return ch or bot.get_channel(REQUESTS_CHANNEL_ID) or fallback_channel


async def submit_request(member: discord.Member, pick: dict,
                         channel) -> tuple[str, discord.Embed | None]:
    """Returns (result text, info card embed or None)."""
    label = f"**{pick['title']} ({pick['year']})**" if pick["year"] else f"**{pick['title']}**"
    emoji = TYPE_EMOJI[pick["media_type"]]
    card = build_media_embed(pick)

    if pick["status"] == 5:
        return (f"✅ {label} is already on Plex — go watch it!", card)
    if pick["status"] in (2, 3):
        return (f"⏳ {label} was already requested — it's in the queue.", card)

    try:
        ok, msg = await seerr.request(pick["media_type"], pick["tmdb_id"])
    except Exception as e:
        log.exception("Seerr request errored for %s %s", pick["media_type"], pick["tmdb_id"])
        return (f"❌ Couldn't reach Seerr: {str(e)[:150] or type(e).__name__}", None)
    log.info("request: discord=%s (%s) %s %s -> %s", member, member.id,
             pick["media_type"], pick["title"], "ok" if ok else msg)
    if ok:
        announce_channel = announce_channel_for(pick["media_type"], member, channel)
        try:
            await announce_channel.send(embed=build_media_embed(
                pick, footer=f"Requested by {member.display_name} • added to the download queue"))
        except discord.Forbidden:
            pass
        if getattr(announce_channel, "id", None) == REQUESTS_CHANNEL_ID:
            await restick(announce_channel, "request_message_id",
                          build_request_embed(), RequestButtonView())
        return (f"{emoji} {label} requested! Seerr sent it to the right place — "
                f"it'll appear on Plex once it's downloaded.", card)
    low = (msg or "").lower()
    if "already exists" in low or "already" in low:
        return (f"⏳ {label} was already requested — it's in the queue.", card)
    return (f"❌ Couldn't request {label}: {msg}", card)


async def start_request_search(member: discord.Member, query: str):
    """Returns (error_text, results). error_text set when the flow should stop."""
    if seerr is None:
        return ("❌ Requests aren't configured yet (missing Seerr settings). Tell the admin.", None)
    if not requests_role_ok(member):
        log.info("search denied (missing %r role): %s (%s)", REQUESTS_ROLE_NAME, member, member.id)
        return (requests_role_denial(), None)
    if not check_cooldown(bot.request_cd, member.id, limit=5):
        log.info("search rate-limited: %s (%s)", member, member.id)
        return ("⏳ Too many searches — give it a few minutes.", None)
    query = query.strip()
    if not 2 <= len(query) <= 100:
        return ("Give me a title between 2 and 100 characters.", None)
    try:
        results = await seerr.search(query)
    except Exception as e:
        log.exception("Seerr search failed for %r", query)
        return (f"❌ Seerr search failed: {str(e)[:150]}", None)
    log.info("search: %s (%s) %r -> %d results", member, member.id, query, len(results))
    if not results:
        return (f"🔍 No movies or shows found for **{query}** — check the spelling?", None)
    return (None, results)


class RequestModal(discord.ui.Modal, title="Request a movie or show"):
    query = discord.ui.TextInput(label="Title", placeholder="e.g. Dune Part Two",
                                 max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        err, results = await start_request_search(interaction.user, str(self.query.value))
        if err:
            await interaction.followup.send(err, ephemeral=True)
            return
        view = ResultsView(interaction.user.id, results)
        view.menu_message = await interaction.followup.send(
            f"🔍 Results for **{self.query.value}** — pick one:",
            view=view, ephemeral=True)


class RequestButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Search & Request", style=discord.ButtonStyle.primary,
                       emoji="🔎", custom_id="ztplex:request")
    async def request_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not requests_role_ok(interaction.user):
            await interaction.response.send_message(requests_role_denial(), ephemeral=True)
            return
        await interaction.response.send_modal(RequestModal())


@bot.tree.command(name="request", description="Request a movie or TV show for Plex")
@app_commands.describe(title="What do you want added?")
async def request_cmd(interaction: discord.Interaction, title: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    err, results = await start_request_search(interaction.user, title)
    if err:
        await interaction.followup.send(err, ephemeral=True)
        return
    view = ResultsView(interaction.user.id, results)
    view.menu_message = await interaction.followup.send(
        f"🔍 Results for **{title}** — pick one:", view=view, ephemeral=True)


async def handle_request_message(message: discord.Message):
    content = (message.content or "").strip()
    if not content or content.startswith("/") or EMAIL_RE.search(content):
        return
    # Keep the channel clean: the typed title disappears, the menu self-destructs,
    # and only the post-request announcement is ever left behind.
    try:
        await message.delete()
    except discord.HTTPException:
        pass
    err, results = await start_request_search(message.author, content)
    if err:
        try:
            await message.channel.send(f"{message.author.mention} {err}", delete_after=20)
        except discord.Forbidden:
            pass
    else:
        view = ResultsView(message.author.id, results, public=True)
        try:
            view.menu_message = await message.channel.send(
                f"🔍 {message.author.mention} — results for **{content}**, pick one "
                f"(this menu vanishes once the request is sent):", view=view)
        except discord.Forbidden:
            log.error("Cannot post the results menu in #%s", message.channel)
    await restick(message.channel, "request_message_id",
                  build_request_embed(), RequestButtonView())


# ---------------------------------------------------------------- channel embeds


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state))


def build_invite_embed() -> discord.Embed:
    e = discord.Embed(
        title=f"🎬  {PLEX_NAME} — get access",
        colour=discord.Colour.from_str("#e5a00d"),
        description=(
            f"Movies, TV shows and music, streamed from {PLEX_NAME}.\n\n"
            "**Three ways to get your invite:**\n"
            "🎟️ Click **Get Plex Access** below and enter your Plex email\n"
            "⌨️ Just type your email in this channel (I'll delete it right away)\n"
            "🔍 Use `/plexinvite email:you@example.com`\n\n"
            "You'll get an email from Plex — hit **Accept**, then watch at "
            "[app.plex.tv](https://app.plex.tv) or any Plex app.\n"
            "Don't have a Plex account? Create one first at "
            "[plex.tv/sign-up](https://www.plex.tv/sign-up/) with the same email."
        ),
    )
    e.set_footer(text=f"Invites are sent automatically • You'll get the {ROLE_NAME} role")
    return e


def build_request_embed() -> discord.Embed:
    e = discord.Embed(
        title="🍿  Request movies & TV shows",
        colour=discord.Colour.from_str("#5865f2"),
        description=(
            "Want something added to Plex? Ask here and it goes straight into the "
            "download queue.\n\n"
            "**Three ways to request:**\n"
            "🔎 Click **Search & Request** below\n"
            "⌨️ Just type the title in this channel (e.g. `Dune Part Two`) — "
            "I'll tidy your message away\n"
            "🎯 Use `/request title:...`\n\n"
            "Searching and picking happens privately — nothing shows up here "
            "until your request is actually sent."
        ),
    )
    if REQUESTS_ROLE_NAME:
        e.set_footer(text=f"Requires the {REQUESTS_ROLE_NAME} role — get it in #{CHANNEL_NAME}")
    return e


_sticky_lock = asyncio.Lock()


async def restick(channel: discord.TextChannel, state_key: str,
                  embed: discord.Embed, view: discord.ui.View):
    """Keep the button embed pinned to the bottom: if anything was posted after
    it, delete it and re-post it as the newest message."""
    async with _sticky_lock:
        state = load_state()
        old_id = state.get(state_key)
        if old_id and channel.last_message_id == old_id:
            return
        if old_id:
            try:
                old = await channel.fetch_message(old_id)
                await old.delete()
            except discord.HTTPException:
                pass
        try:
            msg = await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            log.error("Cannot re-post the button embed in #%s", channel)
            return
        state = load_state()
        state[state_key] = msg.id
        save_state(state)


async def ensure_channel_message(channel: discord.TextChannel, state_key: str,
                                 embed: discord.Embed, view: discord.ui.View):
    state = load_state()
    msg_id = state.get(state_key)
    if msg_id:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=embed, view=view)
            return
        except (discord.NotFound, discord.Forbidden):
            pass
    msg = await channel.send(embed=embed, view=view)
    state = load_state()
    state[state_key] = msg.id
    save_state(state)
    log.info("Posted %s in #%s", state_key, channel.name)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return
    if CHANNEL_ID and message.channel.id == CHANNEL_ID:
        await handle_invite_message(message)
    elif not CHANNEL_ID and message.channel.name == CHANNEL_NAME:
        await handle_invite_message(message)
    elif REQUESTS_CHANNEL_ID and message.channel.id == REQUESTS_CHANNEL_ID:
        await handle_request_message(message)


@bot.event
async def on_ready():
    log.info("Logged in as %s (%s)", bot.user, bot.user.id)

    if seerr is None:
        log.warning("Seerr is NOT configured (OVERSEERR_URL / OVERSEERR_API_KEY "
                    "missing from .env) — media requests are disabled!")
    if not REQUESTS_CHANNEL_ID:
        log.warning("REQUESTS_CHANNEL_ID missing from .env — typed requests and "
                    "the requests embed are disabled.")

    invite_channel = bot.get_channel(CHANNEL_ID) if CHANNEL_ID else None
    if invite_channel is None:
        for g in bot.guilds:
            invite_channel = discord.utils.get(g.text_channels, name=CHANNEL_NAME)
            if invite_channel:
                break
    if invite_channel:
        await ensure_channel_message(invite_channel, "invite_message_id",
                                     build_invite_embed(), InviteView())
        await ensure_role(invite_channel.guild)
    else:
        log.error("Could not find the invite channel (#%s)", CHANNEL_NAME)

    if REQUESTS_CHANNEL_ID:
        req_channel = bot.get_channel(REQUESTS_CHANNEL_ID)
        if req_channel:
            await ensure_channel_message(req_channel, "request_message_id",
                                         build_request_embed(), RequestButtonView())
        else:
            log.error("Could not find the requests channel (%s)", REQUESTS_CHANNEL_ID)

    if SETUP_TEST:
        log.info("SETUP_TEST complete — closing.")
        await bot.close()


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
