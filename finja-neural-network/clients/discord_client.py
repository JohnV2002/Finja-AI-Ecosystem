"""
YourAI AI - Discord Client
==========================
Discord Bot mit async-thread Bridge für die YourAI Pipeline.

Features:
    - VIP Channel: Antwortet auf @mentions und Keywords
    - Proaktive DMs: Kann whitelisted Usern DMs schicken
    - User Mapping: Discord IDs → YourAI User Keys

Usage:
    from discord_client import bot

    # Im Event Loop (wie Twitch):
    msg = bot.get_next_message()
    if msg:
        process_input(msg["text"], msg["user"], "discord", history)

    # Proaktive DM (von überall aufrufbar):
    bot.send_dm(123456789, "Hey Mama! Papa ist gemein!")

    # Antwort im VIP Channel:
    bot.send_channel(channel_id, "Antwort text")
"""

import threading
import asyncio
import time
import sys, os
import json
from datetime import datetime
from queue import Queue
from typing import Optional, Any, TYPE_CHECKING

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

if TYPE_CHECKING:
    import discord

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError
from feedback import FeedbackStore

try:
    from dashboard_client import debug as _dashboard
except Exception:
    _dashboard = None

from config import (
    DISCORD_TOKEN, DISCORD_VIP_CHANNEL_ID,
    DISCORD_START_CHANNEL_ID, DISCORD_PRIVATE_CATEGORY_ID,
    DISCORD_MOD_ROLE_IDS, DISCORD_PRIVILEGED_ROLE_IDS, DISCORD_CHANNELS_FILE,
    DISCORD_TRIGGER_KEYWORDS, DISCORD_DM_WHITELIST,
    DISCORD_CUSTOM_EMOJIS, DISCORD_SERVER_STICKERS
)

import re as _re

# Regex für Custom Discord Emojis: <:name:id> oder <a:name:id> (animiert)
_CUSTOM_EMOJI_RE = _re.compile(r'<a?:(\w+):(\d+)>')


def _resolve_custom_emojis(text: str) -> str:
    """Wandelt Custom Discord Emojis in lesbare Form um.

    <:awww:123456> → :awww: (cute blushing cat)   (wenn in DISCORD_CUSTOM_EMOJIS)
    <:unknown:789> → :unknown:                      (wenn nicht bekannt)
    """
    def _replace(match):
        name = match.group(1)
        desc = DISCORD_CUSTOM_EMOJIS.get(name)
        if desc:
            return f":{name}: ({desc})"
        return f":{name}:"

    return _CUSTOM_EMOJI_RE.sub(_replace, text)


_COLON_EMOJI_RE = _re.compile(r':(\w+):')
# Tenor/Giphy URL keyword extraction
_TENOR_RE = _re.compile(r'https?://tenor\.com/view/([\w-]+?)(?:-\d+)?$', _re.IGNORECASE)
_GIPHY_RE = _re.compile(r'https?://(?:media\.)?giphy\.com/media/\w+/giphy|https?://giphy\.com/gifs/([\w-]+?)(?:-\w+)?$', _re.IGNORECASE)


async def _extract_media_context(message) -> tuple:
    """Extrahiert Sticker, GIFs, Bild-Attachments und Text-Dateien aus einer Discord Nachricht.

    Returns: Beschreibungs-String oder "" wenn nichts gefunden.
    """
    parts = []

    # Sticker - mit Beschreibung wenn bekannt
    if message.stickers:
        for sticker in message.stickers:
            desc = DISCORD_SERVER_STICKERS.get(sticker.name)
            if desc:
                parts.append(f"(Sticker: {sticker.name} - {desc})")
            else:
                parts.append(f"(Sticker: {sticker.name})")

    # GIF/Bild Embeds (Tenor, Giphy, etc.)
    if message.embeds:
        for embed in message.embeds:
            url = embed.url or embed.thumbnail.url if embed.thumbnail else ""
            if not url:
                continue
            # Tenor
            tenor_match = _TENOR_RE.search(url)
            if tenor_match:
                keywords = tenor_match.group(1).replace("-", " ")
                parts.append(f"(GIF: {keywords})")
                continue
            # Giphy
            giphy_match = _GIPHY_RE.search(url)
            if giphy_match and giphy_match.group(1):
                keywords = giphy_match.group(1).replace("-", " ")
                parts.append(f"(GIF: {keywords})")
                continue
            # Generic GIF embed
            if embed.type == "gifv" or (url and ".gif" in url.lower()):
                parts.append("(GIF sent)")

    # Bild-Attachments (URLs für Vision) + Text-Dateien
    image_urls = []
    TEXT_EXTENSIONS = {".py", ".md", ".txt", ".json", ".js", ".ts", ".css", ".html", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".log", ".csv"}
    MAX_TEXT_FILE_SIZE = 50_000  # 50KB max - gegen Riesen-Dateien

    if message.attachments:
        for att in message.attachments:
            ct = att.content_type or ""
            filename = att.filename or ""
            ext = filename[filename.rfind("."):].lower() if "." in filename else ""

            if ct.startswith("image/"):
                image_urls.append(att.url)
                parts.append(f"(Image: {filename})")
            elif ct.startswith("video/"):
                parts.append(f"(Video: {filename})")
            elif ext in TEXT_EXTENSIONS or ct.startswith("text/"):
                # Text-Datei: Inhalt direkt herunterladen
                if att.size and att.size > MAX_TEXT_FILE_SIZE:
                    parts.append(f"(File: {filename} - zu groß: {att.size // 1000}KB)")
                else:
                    try:
                        # att.read() ist async und gibt bytes zurück
                        file_bytes = await att.read()
                        if file_bytes:
                            file_text = file_bytes.decode("utf-8", errors="replace")
                            parts.append(f"(File: {filename})\n```\n{file_text[:10000]}\n```")
                        else:
                            parts.append(f"(File: {filename} - konnte nicht gelesen werden)")
                    except Exception as e:
                        parts.append(f"(File: {filename} - Fehler: {e})")

    return " ".join(parts), image_urls


def _split_message(text: str, max_len: int = 1900) -> list:
    """Splittet lange Nachrichten für Discords 2000-Char-Limit."""
    text = text.strip()
    if not text:
        return []

    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Versuche an einem Zeilenumbruch zu splitten
        split_at = text.rfind("\n", 0, max_len)
        if split_at <= 0:
            # Kein Zeilenumbruch? Dann am letzten Leerzeichen
            split_at = text.rfind(" ", 0, max_len)
        if split_at <= 0:
            # Gar nichts? Hart schneiden
            split_at = max_len

        chunk = text[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        text = text[split_at:].lstrip()

    return chunks


class DiscordBot(threading.Thread):
    """
    Discord Bot als Daemon Thread mit eigenem asyncio Event Loop.

    Kommuniziert mit der sync Pipeline über eine thread-safe Queue.
    Gleiche Architektur wie TwitchBot, aber async statt raw socket.
    """

    def __init__(self):
        super().__init__(daemon=True, name="discord-bot")
        self.message_queue = Queue()
        self.running = True
        self.connected = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client: Optional["discord.Client"] = None
        # Emoji Cache: name → "<:name:id>" (gefüllt bei on_ready)
        self._server_emojis: dict[str, str] = {}
        # Sticker Cache: name → sticker object (gefüllt bei on_ready)
        self._server_stickers: dict[str, Any] = {}
        # Feedback System
        self._feedback_enabled = True
        self._pending_tracking_id: Optional[str] = None
        # Private Channel Button View (wird in _setup_events gesetzt)
        self._private_view_class = None

    # ==========================================
    # PRIVATE CHANNEL MAP (discord_channels.json)
    # ==========================================

    def _load_private_channels(self) -> dict:
        """Lädt discord_user_id → {channel_id, username} Map."""
        if os.path.exists(DISCORD_CHANNELS_FILE):
            try:
                with open(DISCORD_CHANNELS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log("DISCORD", f"⚠️ discord_channels.json lesen fehlgeschlagen: {e}", Fore.YELLOW)
        return {}

    def _save_private_channels(self, channels: dict):
        """Speichert die Channel Map."""
        try:
            with open(DISCORD_CHANNELS_FILE, "w", encoding="utf-8") as f:
                json.dump(channels, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log("DISCORD", f"⚠️ discord_channels.json speichern fehlgeschlagen: {e}", Fore.YELLOW)

    def run(self):
        """Thread Entry Point: Erstellt Event Loop und startet den Bot."""
        try:
            import discord
        except ImportError:
            log("DISCORD", "discord.py nicht installiert! → pip install discord.py", Fore.RED)
            return

        log("DISCORD", "🔵 Discord Bot startet...", Fore.BLUE)

        while self.running:
            try:
                # Neuen Event Loop für diesen Thread erstellen
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)

                # Discord Client Setup
                intents = discord.Intents.default()
                intents.message_content = True   # Privileged Intent - muss im Dev Portal an sein!
                intents.emojis_and_stickers = True  # Emoji-Cache für Web-Dashboard

                self._client = discord.Client(intents=intents)
                self._setup_events()

                # Blockiert bis der Bot disconnected oder stoppt
                self._loop.run_until_complete(self._client.start(DISCORD_TOKEN))

            except Exception as e:
                if self.running:
                    err = YourAIUnexpectedError(cause=e, module="discord_run")
                    log_exception("DISCORD", err)
                    self.connected = False
                    self._client = None
                    time.sleep(5)  # Reconnect Backoff
            finally:
                if self._loop and not self._loop.is_closed():
                    self._loop.close()

    def _setup_events(self):
        """Registriert die Discord Event Handler."""
        assert self._client is not None, "Client must be initialized before setup_events"
        client = self._client
        bot = self  # Referenz für Closures

        import discord as _disc

        # ── Persistent Button View (überlebt Bot-Restarts) ──────────
        class _PrivateChannelView(_disc.ui.View):
            def __init__(self):
                super().__init__(timeout=None)

            @_disc.ui.button(
                label="🦊 Let her Yap!",
                style=_disc.ButtonStyle.primary,
                custom_id="yourai_private_ch_v1"
            )
            async def on_yap_click(self_view, interaction: _disc.Interaction, button: _disc.ui.Button):
                user_id_str = str(interaction.user.id)
                channels = bot._load_private_channels()

                # Schon einen Channel?
                if user_id_str in channels:
                    ch_id = channels[user_id_str]["channel_id"]
                    await interaction.response.send_message(
                        f"Du hast schon einen privaten Channel! → <#{ch_id}> 🦊",
                        ephemeral=True
                    )
                    return

                await interaction.response.defer(ephemeral=True)
                try:
                    guild = interaction.guild
                    category = guild.get_channel(DISCORD_PRIVATE_CATEGORY_ID)

                    overwrites = {
                        guild.default_role: _disc.PermissionOverwrite(view_channel=False),
                        interaction.user: _disc.PermissionOverwrite(
                            view_channel=True, send_messages=True, read_message_history=True
                        ),
                        client.user: _disc.PermissionOverwrite(
                            view_channel=True, send_messages=True, read_message_history=True
                        ),
                    }
                    # Mod roles — from config (DISCORD_MOD_ROLE_IDS + DISCORD_PRIVILEGED_ROLE_IDS env vars)
                    mod_role_ids = list(DISCORD_MOD_ROLE_IDS) + list(DISCORD_PRIVILEGED_ROLE_IDS)
                    for role_id in mod_role_ids:
                        role = guild.get_role(role_id)
                        if role:
                            overwrites[role] = _disc.PermissionOverwrite(
                                view_channel=True, send_messages=True, read_message_history=True
                            )

                    safe_name = interaction.user.display_name.lower().replace(" ", "-")[:20]
                    new_ch = await guild.create_text_channel(
                        name=f"🦊-{safe_name}",
                        category=category,
                        overwrites=overwrites,
                    )

                    channels[user_id_str] = {
                        "channel_id": new_ch.id,
                        "username": interaction.user.display_name,
                        "created": datetime.now().isoformat(),
                    }
                    bot._save_private_channels(channels)

                    await new_ch.send(
                        f"Hey {interaction.user.mention}! 🦊\n"
                        f"Willkommen in deinem privaten YourAI-Channel!\n"
                        f"Schreib einfach los — nur du, ich und die Mods sehen das hier."
                    )
                    await interaction.followup.send(
                        f"✅ Dein Channel ist fertig: {new_ch.mention}", ephemeral=True
                    )
                    log("DISCORD", f"✅ Privater Channel erstellt: 🦊-{safe_name} für {interaction.user.display_name}", Fore.GREEN)
                    if _dashboard:
                        _dashboard.info("discord", f"✅ Neuer privater Channel: 🦊-{safe_name}", f"User: {interaction.user.display_name} ({user_id_str})")

                except Exception as e:
                    log("DISCORD", f"❌ Channel-Erstellung fehlgeschlagen: {e}", Fore.RED)
                    await interaction.followup.send("Upsi! Da ist was schiefgelaufen. Probier's nochmal! 🙈", ephemeral=True)

        bot._private_view_class = _PrivateChannelView

        @client.event
        async def on_ready():
            self.connected = True
            log("DISCORD", f"✅ Discord: Verbunden als {client.user.name}!", Fore.GREEN)  # type: ignore[union-attr]
            log("DISCORD", f"   📌 VIP Channel ID: {DISCORD_VIP_CHANNEL_ID}", Fore.BLUE)
            log("DISCORD", f"   🦊 Start Channel: {DISCORD_START_CHANNEL_ID}", Fore.BLUE)
            log("DISCORD", f"   📋 DM Whitelist: {len(DISCORD_DM_WHITELIST)} User", Fore.BLUE)

            # Persistent Button View registrieren (überlebt Restarts)
            client.add_view(_PrivateChannelView())

            # Server-Emojis cachen für ausgehende Nachrichten
            self._server_emojis.clear()
            self._server_stickers.clear()
            for guild in client.guilds:
                for emoji in guild.emojis:
                    prefix = "a" if emoji.animated else ""
                    self._server_emojis[emoji.name] = f"<{prefix}:{emoji.name}:{emoji.id}>"
                for sticker in guild.stickers:
                    self._server_stickers[sticker.name.lower()] = sticker
            log("DISCORD", f"   😸 Server Emojis geladen: {len(self._server_emojis)}", Fore.BLUE)
            log("DISCORD", f"   🎨 Server Sticker geladen: {len(self._server_stickers)}", Fore.BLUE)

            # Emoji-Map für Dashboard als JSON schreiben (dashboard_server ist eigener Prozess)
            import re as _re_eid
            _emoji_ids = {}
            for _ename, _efmt in self._server_emojis.items():
                _m = _re_eid.search(r':(\d+)>', _efmt)
                if _m:
                    _animated = _efmt.startswith("<a:")
                    _emoji_ids[_ename] = {"id": _m.group(1), "animated": _animated}
            _emap_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "emoji_map.json")
            try:
                with open(_emap_path, "w") as _f:
                    json.dump(_emoji_ids, _f)
                log("DISCORD", f"   🌐 emoji_map.json geschrieben: {len(_emoji_ids)} Emojis", Fore.BLUE)
            except Exception as _e:
                log("DISCORD", f"   ⚠️ emoji_map.json Fehler: {_e}", Fore.YELLOW)
            channels_loaded = len(self._load_private_channels())
            log("DISCORD", f"   🔒 Private Channels geladen: {channels_loaded}", Fore.BLUE)
            if _dashboard:
                _dashboard.info("discord", f"✅ Discord verbunden als {client.user.name}", f"📌 VIP Channel: {DISCORD_VIP_CHANNEL_ID}\n🦊 Start Channel: {DISCORD_START_CHANNEL_ID}\n📋 DM Whitelist: {len(DISCORD_DM_WHITELIST)} User\n🔒 Private Channels: {channels_loaded}")

        @client.event
        async def on_disconnect():
            if self.connected:
                log("DISCORD", "⚠️ Discord: Verbindung verloren...", Fore.YELLOW)
                self.connected = False

        @client.event
        async def on_resumed():
            self.connected = True
            log("DISCORD", "🔌 Discord: Verbindung wiederhergestellt!", Fore.GREEN)

        @client.event
        async def on_raw_reaction_add(payload):
            """Feedback: User klickt 👍 oder 👎 auf YourAI's Nachricht."""
            if not self._feedback_enabled:
                return
            # Nur Reactions auf Bot-Nachrichten zählen
            if payload.user_id == client.user.id:  # type: ignore[union-attr]
                return  # Eigene Reactions ignorieren
            emoji = str(payload.emoji)
            if emoji not in ("\U0001f44d", "\U0001f44e"):  # 👍 👎
                return
            rating = "up" if emoji == "\U0001f44d" else "down"
            fb = FeedbackStore()
            success = fb.rate_by_message(payload.message_id, rating)
            if success:
                log("FEEDBACK", f"{'👍' if rating == 'up' else '👎'} Discord Feedback von User {payload.user_id}", Fore.CYAN)

        @client.event
        async def on_message(message):
            import discord as _discord

            # Eigene Nachrichten ignorieren
            if message.author == client.user:
                return

            discord_id = str(message.author.id)
            display_name = message.author.display_name

            # ===== DM von Whitelisted User =====
            if isinstance(message.channel, _discord.DMChannel):
                if discord_id not in DISCORD_DM_WHITELIST:
                    log("DISCORD", f"🚫 DM von unbekanntem User ignoriert: {display_name} ({discord_id})", Fore.YELLOW)
                    return

                clean_text = _resolve_custom_emojis(message.content).strip()
                media_context, image_urls = await _extract_media_context(message)

                # Sticker/GIF ohne Text? Trotzdem verarbeiten!
                if not clean_text and not media_context:
                    return

                if media_context:
                    clean_text = f"{clean_text} {media_context}".strip()

                whitelist_name = DISCORD_DM_WHITELIST[discord_id]
                log("DISCORD", f"📩 DM ({display_name}/{whitelist_name}): {clean_text}", Fore.BLUE)

                msg_data = {
                    "user": display_name,
                    "discord_id": discord_id,
                    "text": clean_text,
                    "source": "discord_dm",
                    "channel_id": message.channel.id,
                }
                # Vision in DMs: Bild-URLs mitgeben
                if image_urls:
                    msg_data["image_urls"] = image_urls
                    log("DISCORD", f"   🖼️ {len(image_urls)} Bild(er) für Vision", Fore.CYAN)

                self.message_queue.put(msg_data)
                return

            # ===== Channel-Routing =====
            private_channels = self._load_private_channels()
            private_ch_map = {v["channel_id"]: k for k, v in private_channels.items()}  # channel_id → discord_user_id

            is_vip     = message.channel.id == DISCORD_VIP_CHANNEL_ID
            is_private = message.channel.id in private_ch_map

            if not is_vip and not is_private:
                return  # Unbekannter Channel → ignorieren

            clean_text = _resolve_custom_emojis(message.content)
            media_context, image_urls = await _extract_media_context(message)
            if media_context:
                clean_text = f"{clean_text} {media_context}".strip()

            # ── VIP Channel: nur auf @mention oder Keyword reagieren ──
            if is_vip:
                is_triggered = False
                if client.user in message.mentions:  # type: ignore[union-attr]
                    is_triggered = True
                    clean_text = clean_text.replace(f'<@{client.user.id}>', '').strip()  # type: ignore[union-attr]
                if not is_triggered:
                    msg_lower = message.content.lower()
                    for keyword in DISCORD_TRIGGER_KEYWORDS:
                        if keyword in msg_lower:
                            is_triggered = True
                            break
                if is_triggered and clean_text.strip():
                    log("DISCORD", f"💬 VIP ({display_name}): {clean_text.strip()[:60]}", Fore.BLUE)
                    self.message_queue.put({
                        "user": display_name,
                        "discord_id": discord_id,
                        "text": clean_text.strip(),
                        "source": "discord",
                        "channel_id": message.channel.id,
                    })

            # ── Privater Channel: immer antworten (kein Trigger nötig) ──
            elif is_private:
                if not clean_text.strip():
                    return
                log("DISCORD", f"🔒 Privat ({display_name}): {clean_text.strip()[:60]}", Fore.BLUE)
                msg_data = {
                    "user": display_name,
                    "discord_id": discord_id,
                    "text": clean_text.strip(),
                    "source": "discord_private",  # ← Privacy: brain weiß das ist vertraulich
                    "channel_id": message.channel.id,
                }
                if image_urls:
                    msg_data["image_urls"] = image_urls
                self.message_queue.put(msg_data)

    # ==========================================
    # SYNC API (aufrufbar von überall)
    # ==========================================

    def get_next_message(self) -> Optional[dict]:
        """Holt die nächste Nachricht aus der Queue (non-blocking)."""
        if not self.message_queue.empty():
            return self.message_queue.get()
        return None

    def _resolve_outgoing_emojis(self, text: str) -> str:
        """Wandelt :emoji_name: in <:emoji_name:id> für Discord um."""
        if not self._server_emojis:
            return text

        def _replace(match):
            name = match.group(1)
            if name in self._server_emojis:
                return self._server_emojis[name]
            return match.group(0)  # unbekannt → :name: lassen

        return _COLON_EMOJI_RE.sub(_replace, text)

    def send_channel(self, channel_id: int, text: str):
        """Sendet eine Nachricht in einen Discord Channel (sync wrapper)."""
        if not self._loop or not self._client or not self.connected:
            log("DISCORD", "⚠️ Kann nicht senden - Bot nicht verbunden", Fore.YELLOW)
            return

        text = self._resolve_outgoing_emojis(text)

        async def _do_send():
            assert self._client is not None
            channel = self._client.get_channel(channel_id)
            if not channel or not hasattr(channel, "send"):
                log("DISCORD", f"⚠️ Channel {channel_id} nicht gefunden", Fore.YELLOW)
                return None
            chunks = _split_message(text)
            if not chunks:
                log("DISCORD", f"⚠️ Leere Nachricht, nichts zu senden", Fore.YELLOW)
                return None
            last_msg = None
            for chunk in chunks:
                last_msg = await channel.send(chunk)  # type: ignore[union-attr]
            # Feedback Reactions auf die letzte Nachricht
            if last_msg and self._feedback_enabled:
                try:
                    await last_msg.add_reaction("\U0001f44d")  # 👍
                    await last_msg.add_reaction("\U0001f44e")  # 👎
                except Exception:
                    pass  # Reaction fehlgeschlagen, nicht schlimm
            return last_msg

        try:
            future = asyncio.run_coroutine_threadsafe(_do_send(), self._loop)
            result = future.result(timeout=30)
            # Link message to tracking_id for feedback
            if result and hasattr(self, '_pending_tracking_id') and self._pending_tracking_id:
                fb = FeedbackStore()
                fb.link_discord_message(result.id, self._pending_tracking_id)
                self._pending_tracking_id = None
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="discord_send_channel")
            log_exception("DISCORD", err)
            log("DISCORD", f"❌ send_channel failed: {type(e).__name__}: {e}", Fore.RED)

    def send_dm(self, discord_user_id: int, text: str):
        """
        Sendet eine DM an einen User (sync wrapper).

        SAFETY: Nur an User in DISCORD_DM_WHITELIST!

        Usage:
            from discord_client import bot
            bot.send_dm(123456789, "Hey Mama!")
        """
        # Safety Check: Nur whitelisted User!
        user_id_str = str(discord_user_id)
        if user_id_str not in DISCORD_DM_WHITELIST:
            log("DISCORD", f"🚫 DM an {discord_user_id} blockiert - nicht in Whitelist!", Fore.RED)
            return

        if not self._loop or not self._client or not self.connected:
            log("DISCORD", "⚠️ Kann keine DM senden - Bot nicht verbunden", Fore.YELLOW)
            return

        text = self._resolve_outgoing_emojis(text)

        async def _do_send():
            assert self._client is not None
            user = await self._client.fetch_user(discord_user_id)
            if not user:
                log("DISCORD", f"⚠️ User {discord_user_id} nicht gefunden", Fore.YELLOW)
                return None

            chunks = _split_message(text)
            if not chunks:
                log("DISCORD", f"⚠️ Leere DM, nichts zu senden", Fore.YELLOW)
                return None
            last_msg = None
            for chunk in chunks:
                last_msg = await user.send(chunk)

            whitelist_name = DISCORD_DM_WHITELIST.get(user_id_str, "unknown")
            log("DISCORD", f"📩 DM gesendet an {user.display_name} ({whitelist_name})", Fore.GREEN)

            # Feedback Reactions auf DMs
            if last_msg and self._feedback_enabled:
                try:
                    await last_msg.add_reaction("\U0001f44d")  # 👍
                    await last_msg.add_reaction("\U0001f44e")  # 👎
                except Exception:
                    pass
            return last_msg

        try:
            future = asyncio.run_coroutine_threadsafe(_do_send(), self._loop)
            result = future.result(timeout=30)
            if result and hasattr(self, '_pending_tracking_id') and self._pending_tracking_id:
                fb = FeedbackStore()
                fb.link_discord_message(result.id, self._pending_tracking_id)
                self._pending_tracking_id = None
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="discord_send_dm")
            log_exception("DISCORD", err)
            log("DISCORD", f"❌ send_dm failed: {type(e).__name__}: {e}", Fore.RED)

    def send_sticker(self, channel_id: int, sticker_name: str):
        """Sendet einen Server-Sticker in einen Channel oder DM."""
        if not self._loop or not self._client or not self.connected:
            log("DISCORD", "⚠️ Kann keinen Sticker senden - Bot nicht verbunden", Fore.YELLOW)
            return False

        sticker = self._server_stickers.get(sticker_name.lower())
        if not sticker:
            log("DISCORD", f"⚠️ Sticker '{sticker_name}' nicht auf dem Server gefunden", Fore.YELLOW)
            return False

        async def _do_send():
            assert self._client is not None
            channel = self._client.get_channel(channel_id)
            if channel and hasattr(channel, "send"):
                await channel.send(stickers=[sticker])  # type: ignore[arg-type, union-attr]
            else:
                log("DISCORD", f"⚠️ Channel {channel_id} nicht gefunden für Sticker", Fore.YELLOW)

        try:
            future = asyncio.run_coroutine_threadsafe(_do_send(), self._loop)
            future.result(timeout=10)
            log("DISCORD", f"🎨 Sticker gesendet: {sticker_name}", Fore.GREEN)
            return True
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="discord_send_sticker")
            log_exception("DISCORD", err)
            return False

    def send_sticker_dm(self, discord_user_id: int, sticker_name: str):
        """Sendet einen Server-Sticker als DM."""
        user_id_str = str(discord_user_id)
        if user_id_str not in DISCORD_DM_WHITELIST:
            log("DISCORD", f"🚫 Sticker-DM an {discord_user_id} blockiert - nicht in Whitelist!", Fore.RED)
            return False

        if not self._loop or not self._client or not self.connected:
            return False

        sticker = self._server_stickers.get(sticker_name.lower())
        if not sticker:
            log("DISCORD", f"⚠️ Sticker '{sticker_name}' nicht auf dem Server gefunden", Fore.YELLOW)
            return False

        async def _do_send():
            assert self._client is not None
            user = await self._client.fetch_user(discord_user_id)
            if user:
                await user.send(stickers=[sticker])  # type: ignore[arg-type]

        try:
            future = asyncio.run_coroutine_threadsafe(_do_send(), self._loop)
            future.result(timeout=10)
            whitelist_name = DISCORD_DM_WHITELIST.get(user_id_str, "unknown")
            log("DISCORD", f"🎨 Sticker-DM gesendet an {whitelist_name}: {sticker_name}", Fore.GREEN)
            return True
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="discord_send_sticker_dm")
            log_exception("DISCORD", err)
            return False

    def send_channel_image(self, channel_id: int, image_url: str, prompt: str = "") -> bool:
        """Downloads an image from URL and posts it as attachment to a Discord channel."""
        if not self._loop or not self._client or not self.connected:
            log("DISCORD", "⚠️ Kann kein Bild senden - Bot nicht verbunden", Fore.YELLOW)
            return False

        async def _do_send():
            import io
            import base64 as _b64
            import requests as _req
            import discord as _disc
            assert self._client is not None
            channel = self._client.get_channel(channel_id)
            if not channel or not hasattr(channel, "send"):
                log("DISCORD", f"⚠️ Channel {channel_id} nicht gefunden für Image", Fore.YELLOW)
                return False
            try:
                if image_url.startswith("data:"):
                    # base64 data URI → decode directly
                    _, encoded = image_url.split(",", 1)
                    img_bytes = _b64.b64decode(encoded)
                else:
                    img_bytes = _req.get(image_url, timeout=30).content
                file = _disc.File(io.BytesIO(img_bytes), filename="yourai_art.png")
                caption = "🎨 Here you go!"
                if prompt:
                    caption += f'\n*"{prompt[:150]}"*'
                await channel.send(caption, file=file)
                log("DISCORD", f"🎨 Bild gesendet in Channel {channel_id}", Fore.GREEN)
                return True
            except Exception as e:
                log("DISCORD", f"❌ Bild-Senden fehlgeschlagen: {e}", Fore.RED)
                return False

        try:
            future = asyncio.run_coroutine_threadsafe(_do_send(), self._loop)
            return future.result(timeout=45)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="discord_send_channel_image")
            log_exception("DISCORD", err)
            return False

    def get_emoji_map(self) -> dict:
        """Returns {emoji_name: cdn_url} from the on_ready emoji cache."""
        import re as _re
        result = {}
        for name, discord_fmt in self._server_emojis.items():
            # Format: "<:name:id>" or "<a:name:id>"
            m = _re.search(r':(\d+)>', discord_fmt)
            if m:
                result[name] = m.group(1)  # just the ID, URL built in API endpoint
        return result

    def post_start_message(self, text: str = "Wanna talk to YourAI in private? 🦊\nClick the button below to get your own cozy little channel!"):
        """
        Postet die 'Let her Yap!' Button-Nachricht in den Start-Channel.

        Muss einmalig aufgerufen werden, wenn der Bot läuft.
        Danach reagiert der Button persistent (überlebt Restarts).

        Usage:
            from discord_client import bot
            bot.post_start_message()
        """
        if not self._loop or not self._client or not self.connected:
            log("DISCORD", "⚠️ Kann Start-Message nicht posten - Bot nicht verbunden", Fore.YELLOW)
            return False
        if not self._private_view_class:
            log("DISCORD", "⚠️ _PrivateChannelView nicht initialisiert", Fore.YELLOW)
            return False

        async def _do_post():
            assert self._client is not None
            channel = self._client.get_channel(DISCORD_START_CHANNEL_ID)
            if not channel or not hasattr(channel, "send"):
                log("DISCORD", f"⚠️ Start-Channel {DISCORD_START_CHANNEL_ID} nicht gefunden", Fore.YELLOW)
                return False
            await channel.send(text, view=self._private_view_class())  # type: ignore[union-attr]
            log("DISCORD", f"✅ Start-Message gepostet in Channel {DISCORD_START_CHANNEL_ID}", Fore.GREEN)
            return True

        try:
            future = asyncio.run_coroutine_threadsafe(_do_post(), self._loop)
            return future.result(timeout=10)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="discord_post_start_message")
            log_exception("DISCORD", err)
            return False

    def stop(self):
        """Sauberes Beenden."""
        self.running = False
        self.connected = False
        if self._loop and self._client:
            try:
                asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
            except Exception:
                pass


# Globale Instanz
bot = DiscordBot()


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("DISCORD_TOKEN nicht in .env gesetzt!")
        print("1. https://discord.com/developers/applications")
        print("2. New Application → Bot → Token kopieren")
        print("3. DISCORD_TOKEN=dein_token in .env")
    else:
        print("Starting Discord bot standalone...")
        bot.start()
        try:
            while True:
                msg = bot.get_next_message()
                if msg:
                    print(f"Message: {msg}")
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopping...")
            bot.stop()
