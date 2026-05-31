"""
YourAI AI - Discord Client
=========================
Discord client bot running as a daemon thread with an async-to-thread bridge interface.

Main Responsibilities:
- Listen to whitelisted user mentions and keywords in a designated VIP channel.
- Route private channel conversations to the brain pipeline.
- Post and manage the "Let her Yap!" room activation button views.
- Link Discord accounts to internal dashboard profile keys.

Side Effects:
- Registers and runs a persistent asyncio event loop.
- Performs file operations to cache channel mappings.
- Interacts with the external Discord Gateway and REST API.
"""

import asyncio
import os
import sys
import threading
import time
import json
from queue import Queue
from typing import Optional, Any, TYPE_CHECKING

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

if TYPE_CHECKING:
    import discord

from display import log, log_exception, Fore
from exceptions import YourAIMissingDependencyError, YourAIUnexpectedError
from feedback import FeedbackStore

try:
    from dashboard_client import debug as _dashboard
except Exception as e:
    err = YourAIUnexpectedError(cause=e, module="discord_dashboard_client_import")
    log_exception("DISCORD", err)
    _dashboard = None

from config import (
    DISCORD_TOKEN, DISCORD_VIP_CHANNEL_ID,
    DISCORD_START_CHANNEL_ID, DISCORD_PRIVATE_CATEGORY_ID,
    DISCORD_MOD_ROLE_IDS, DISCORD_PRIVILEGED_ROLE_IDS,
    DISCORD_TRIGGER_KEYWORDS,
    DISCORD_SERVER_STICKERS
)
from discord_channels import load_private_channels, save_private_channels
from discord_media import extract_media_context
from discord_messages import resolve_custom_emojis
from discord_send import DiscordSender
from helpers.platform_links import (
    resolve_discord_id, is_dm_allowed, all_dm_allowed_ids, consume_link_code, link_discord_id
)
from helpers.text_parser import extract_discord_emoji_id


def _log_unexpected(module: str, error: Exception):
    """
    Wraps an unexpected exception in a YourAI error and logs it.
    
    Returns:
        Any: The operation result, or None when no result is produced.
    """
    err = YourAIUnexpectedError(cause=error, module=module)
    log_exception("DISCORD", err)


class DiscordBot(threading.Thread):
    """
    Discord Bot as a daemon thread with its own asyncio event loop.

    Communicates with the sync pipeline via a thread-safe Queue.
    """

    def __init__(self):
        """
        Initializes instance state and cached connection metadata.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        super().__init__(daemon=True, name="discord-bot")
        self.message_queue = Queue()
        self.running = True
        self.connected = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client: Optional["discord.Client"] = None
        # Emoji Cache: name -> "<:name:id>" (populated in on_ready)
        self._server_emojis: dict[str, str] = {}
        # Sticker Cache: name -> sticker object (populated in on_ready)
        self._server_stickers: dict[str, Any] = {}
        # Feedback System
        self._feedback_enabled = True
        self._pending_tracking_id: Optional[str] = None
        # Views and Command Tree (set in _setup_events)
        self._private_view_class = None
        self._delete_view_class = None
        self._cmd_tree = None
        self.start_channel_id = DISCORD_START_CHANNEL_ID
        self._sender = DiscordSender(self)
        # Subconscious: Timestamp of the last incoming message (for boredom calculation)
        self.last_message_time: Optional[float] = None

    # ==========================================
    # PRIVATE CHANNEL MAP (discord_channels.json)
    # ==========================================

    def _load_private_channels(self) -> dict:
        """Loads the discord_user_id -> {channel_id, username} map from disk."""
        return load_private_channels()

    def _save_private_channels(self, channels: dict):
        """Saves the private channel map to disk."""
        save_private_channels(channels)

    def run(self):
        """Thread entry point: Creates event loop and starts the bot."""
        try:
            import discord
        except ImportError as e:
            err = YourAIMissingDependencyError("discord", feature="Discord client", pip_name="discord.py", cause=e)
            log_exception("DISCORD", err)
            log("DISCORD", "discord.py not installed! -> pip install discord.py", Fore.RED)
            return

        log("DISCORD", " Discord Bot starting...", Fore.BLUE)

        while self.running:
            try:
                # Create new event loop for this thread
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)

                # Discord Client Setup
                intents = discord.Intents.default()
                intents.message_content = True   # Privileged Intent - must be enabled in the Dev Portal!
                intents.emojis_and_stickers = True  # Emoji cache for web dashboard

                self._client = discord.Client(intents=intents)
                self._setup_events()

                # Blocks until the bot disconnects or stops
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
        """Register Discord slash commands, views, and gateway event handlers."""
        assert self._client is not None, "Client must be initialized before setup_events"

        import discord as _disc

        client = self._client
        self._register_slash_commands(client, _disc)
        self._delete_view_class = self._build_delete_data_view_class(_disc)
        self._private_view_class = self._build_private_channel_view_class(client, _disc)
        self._register_gateway_events(client)

    def _register_slash_commands(self, client: Any, disc: Any) -> None:
        """Register Discord slash commands on the command tree."""
        tree = disc.app_commands.CommandTree(client)

        @tree.command(name="link", description="Link your Discord account with the YourAI dashboard")
        async def link_cmd(interaction, code: str):
            """Link a Discord account to a dashboard user key."""
            user_key = consume_link_code(code)
            if not user_key:
                await interaction.response.send_message(
                    "Error: Code invalid or expired. Generate a new code in the dashboard.",
                    ephemeral=True,
                )
                return

            discord_id = str(interaction.user.id)
            link_discord_id(user_key, discord_id, dm_allowed=False)
            log("DISCORD", f"Discord linked: {interaction.user.display_name} -> {user_key}", Fore.GREEN)
            await interaction.response.send_message(
                f"Linked! Your Discord account is now connected with **{user_key}**.\n"
                f"YourAI knows you here as well!",
                ephemeral=True,
            )

        @tree.command(name="dsgvo_delete", description="Delete all of your YourAI data (GDPR Art. 17)")
        async def dsgvo_delete_cmd(interaction):
            """Ask for confirmation before queueing Discord data deletion."""
            await self._send_slash_delete_confirmation(interaction, disc)

        self._cmd_tree = tree

    async def _send_slash_delete_confirmation(self, interaction: Any, disc: Any) -> None:
        """Send the slash-command delete-data confirmation view."""
        discord_id = str(interaction.user.id)
        channel_id = interaction.channel_id or 0
        confirm_view = disc.ui.View(timeout=60)

        async def _confirm(btn_interaction):
            """Queue confirmed data deletion from a slash-command interaction."""
            self.message_queue.put({
                "action": "delete_discord_data",
                "channel_id": channel_id,
                "discord_id": discord_id,
            })
            log("DISCORD", f"GDPR/DSGVO deletion via /dsgvo_delete: {interaction.user.display_name} ({discord_id})", Fore.YELLOW)
            await btn_interaction.response.edit_message(
                content="Your data is being deleted. Goodbye, memories.",
                view=None,
            )

        async def _cancel(btn_interaction):
            """Cancel a slash-command data deletion request."""
            await btn_interaction.response.edit_message(
                content="Canceled - your data remains intact.",
                view=None,
            )

        yes_btn = disc.ui.Button(label="Yes, delete everything", style=disc.ButtonStyle.danger)
        no_btn = disc.ui.Button(label="Cancel", style=disc.ButtonStyle.secondary)
        yes_btn.callback = _confirm
        no_btn.callback = _cancel
        confirm_view.add_item(yes_btn)
        confirm_view.add_item(no_btn)
        await interaction.response.send_message(
            "Warning **Really delete all data?**\n"
            "This removes your diary, links, and channel data - irrevocably.",
            view=confirm_view,
            ephemeral=True,
        )

    def _build_delete_data_view_class(self, disc: Any):
        """Build the persistent delete-data view class."""
        bot = self

        class _DeleteConfirmView(disc.ui.View):
            """Temporary Discord view that confirms or cancels data deletion."""

            def __init__(self, channel_id: int, discord_id: str):
                """Initialize confirmation metadata."""
                super().__init__(timeout=60)
                self.channel_id = channel_id
                self.discord_id = discord_id

            @disc.ui.button(label="Yes, delete everything", style=disc.ButtonStyle.danger)
            async def confirm(self_view, interaction, button):
                """Queue the confirmed private-channel data deletion request."""
                bot.message_queue.put({
                    "action": "delete_discord_data",
                    "channel_id": self_view.channel_id,
                    "discord_id": self_view.discord_id,
                })
                log("DISCORD", f"Data deletion requested: channel={self_view.channel_id}", Fore.YELLOW)
                await interaction.response.edit_message(
                    content="Your data is being deleted. Goodbye, memories.",
                    view=None,
                )

            @disc.ui.button(label="Cancel", style=disc.ButtonStyle.secondary)
            async def cancel(self_view, interaction, button):
                """Cancel a private-channel data deletion interaction."""
                await interaction.response.edit_message(content="Okay, nothing happened! ", view=None)

        class _DeleteDataView(disc.ui.View):
            """Persistent Discord view that starts the delete-data confirmation flow."""

            def __init__(self):
                """Initialize the persistent delete-data view."""
                super().__init__(timeout=None)

            @disc.ui.button(
                label="Delete my data",
                style=disc.ButtonStyle.danger,
                custom_id="yourai_delete_data_v1",
            )
            async def on_delete_click(self_view, interaction, button):
                """Show the delete-data confirmation dialog."""
                confirm_view = _DeleteConfirmView(
                    channel_id=interaction.channel_id,
                    discord_id=str(interaction.user.id),
                )
                await interaction.response.send_message(
                    "Warning **Really delete all data?**\n"
                    "This removes your entire YourAI memory for this channel - irrevocably.",
                    view=confirm_view,
                    ephemeral=True,
                )

        return _DeleteDataView

    def _build_private_channel_view_class(self, client: Any, disc: Any):
        """Build the persistent private-channel creation view class."""
        bot = self

        class _PrivateChannelView(disc.ui.View):
            """Persistent Discord view that creates private user channels."""

            def __init__(self):
                """Initialize the persistent private-channel view."""
                super().__init__(timeout=None)

            @disc.ui.button(
                label="Let her Yap!",
                style=disc.ButtonStyle.primary,
                custom_id="yourai_private_ch_v1",
            )
            async def on_yap_click(self_view, interaction, button):
                """Create or reuse a private Discord channel for the requesting user."""
                await bot._handle_private_channel_request(client, disc, interaction)

        return _PrivateChannelView

    async def _handle_private_channel_request(self, client: Any, disc: Any, interaction: Any) -> None:
        """Create a private channel for a Discord user when needed."""
        user_id_str = str(interaction.user.id)
        channels = self._load_private_channels()
        existing = channels.get(user_id_str)
        if existing:
            await interaction.response.send_message(
                f"You already have a private channel: <#{existing['channel_id']}>",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            new_ch = await self._create_private_channel(client, disc, interaction)
            channels[user_id_str] = {
                "channel_id": new_ch.id,
                "username": interaction.user.display_name,
                "created": datetime.now().isoformat(),
            }
            self._save_private_channels(channels)
            await self._send_private_channel_welcome(new_ch, interaction)
        except Exception as e:
            _log_unexpected("discord_private_channel_create", e)
            log("DISCORD", f"Error: Channel creation failed: {e}", Fore.RED)
            await interaction.followup.send("Oops! Something went wrong. Try again.", ephemeral=True)

    async def _create_private_channel(self, client: Any, disc: Any, interaction: Any) -> Any:
        """Create the Discord private channel with configured overwrites."""
        guild = interaction.guild
        category = guild.get_channel(DISCORD_PRIVATE_CATEGORY_ID)
        overwrites = self._private_channel_overwrites(client, disc, guild, interaction.user)
        safe_name = interaction.user.display_name.lower().replace(" ", "-")[:20]
        return await guild.create_text_channel(
            name=f"yourai-{safe_name}",
            category=category,
            overwrites=overwrites,
        )

    def _private_channel_overwrites(self, client: Any, disc: Any, guild: Any, user: Any) -> dict:
        """Build permission overwrites for a private channel."""
        overwrites = {
            guild.default_role: disc.PermissionOverwrite(view_channel=False),
            user: disc.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            client.user: disc.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        mod_role_ids = list(DISCORD_MOD_ROLE_IDS) + list(DISCORD_PRIVILEGED_ROLE_IDS)
        for role_id in mod_role_ids:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = disc.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )
        return overwrites

    async def _send_private_channel_welcome(self, channel: Any, interaction: Any) -> None:
        """Send the welcome text into a newly created private channel."""
        safe_name = interaction.user.display_name.lower().replace(" ", "-")[:20]
        await channel.send(
            f"Hey {interaction.user.mention}!\n"
            f"Welcome to your private YourAI channel!\n"
            f"Just start writing - only you, me, and the mods see this here.\n\n"
            f"Do you have a dashboard account? Link it with `/link <code>` "
            f"(generate code in the dashboard). Otherwise you remain anonymous - also okay.",
            view=self._delete_view_class(),
        )
        await interaction.followup.send(f"Your channel is ready: {channel.mention}", ephemeral=True)
        log("DISCORD", f"Private channel created: yourai-{safe_name} for {interaction.user.display_name}", Fore.GREEN)
        if _dashboard:
            _dashboard.info("discord", f"New private channel: yourai-{safe_name}", f"User: {interaction.user.display_name} ({interaction.user.id})")

    def _register_gateway_events(self, client: Any) -> None:
        """Register Discord gateway event callbacks."""

        @client.event
        async def on_ready():
            """Initialize caches and persistent views after gateway connection."""
            await self._on_ready(client)

        @client.event
        async def on_disconnect():
            """Update connection state after a gateway disconnect."""
            self._on_disconnect()

        @client.event
        async def on_resumed():
            """Update connection state after Discord resumes the gateway session."""
            self._on_resumed()

        @client.event
        async def on_raw_reaction_add(payload):
            """Record feedback reactions on YourAI messages."""
            self._on_raw_reaction_add(client, payload)

        @client.event
        async def on_message(message):
            """Route incoming Discord messages into the YourAI queue."""
            await self._on_message(client, message)

    async def _on_ready(self, client: Any) -> None:
        """Initialize Discord caches and persistent views after connection."""
        self.connected = True
        log("DISCORD", f"Discord connected as {client.user.name}.", Fore.GREEN)
        log("DISCORD", f"    VIP Channel ID: {DISCORD_VIP_CHANNEL_ID}", Fore.BLUE)
        log("DISCORD", f"    Start Channel: {DISCORD_START_CHANNEL_ID}", Fore.BLUE)
        log("DISCORD", f"   DM-allowed: {len(all_dm_allowed_ids())} Discord IDs", Fore.BLUE)

        client.add_view(self._private_view_class())
        client.add_view(self._delete_view_class())
        await self._sync_slash_commands(client)
        self._cache_server_media(client)
        await self._write_emoji_map_async()

        channels_loaded = len(self._load_private_channels())
        log("DISCORD", f"   Private channels loaded: {channels_loaded}", Fore.BLUE)
        if _dashboard:
            _dashboard.info("discord", f"Discord connected as {client.user.name}", f"VIP Channel: {DISCORD_VIP_CHANNEL_ID}\nStart Channel: {DISCORD_START_CHANNEL_ID}\nDM-allowed: {len(all_dm_allowed_ids())} IDs\nPrivate Channels: {channels_loaded}")

    async def _sync_slash_commands(self, client: Any) -> None:
        """Sync slash commands for all connected guilds."""
        synced_count = 0
        for guild in client.guilds:
            try:
                self._cmd_tree.copy_global_to(guild=guild)
                await self._cmd_tree.sync(guild=guild)
                synced_count += 1
            except Exception as e:
                _log_unexpected("discord_slash_sync", e)
                log("DISCORD", f"   Warning Sync failed for {guild.name}: {e}", Fore.YELLOW)
        log("DISCORD", f"    Slash commands synced for {synced_count}/{len(client.guilds)} servers", Fore.BLUE)

    def _cache_server_media(self, client: Any) -> None:
        """Cache server emojis and stickers for outgoing messages."""
        self._server_emojis.clear()
        self._server_stickers.clear()
        for guild in client.guilds:
            for emoji in guild.emojis:
                prefix = "a" if emoji.animated else ""
                self._server_emojis[emoji.name] = f"<{prefix}:{emoji.name}:{emoji.id}>"
            for sticker in guild.stickers:
                self._server_stickers[sticker.name.lower()] = sticker
        log("DISCORD", f"    Server Emojis loaded: {len(self._server_emojis)}", Fore.BLUE)
        log("DISCORD", f"   Server stickers loaded: {len(self._server_stickers)}", Fore.BLUE)

    async def _write_emoji_map_async(self) -> None:
        """Write emoji-map JSON without blocking the event loop."""
        emoji_ids = {}
        for emoji_name, emoji_format in self._server_emojis.items():
            emoji_id = extract_discord_emoji_id(emoji_format)
            if emoji_id:
                emoji_ids[emoji_name] = {"id": emoji_id, "animated": emoji_format.startswith("<a:")}
        emap_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "emoji_map.json")
        try:
            await asyncio.to_thread(self._write_emoji_map_file, emap_path, emoji_ids)
            log("DISCORD", f"    emoji_map.json written: {len(emoji_ids)} Emojis", Fore.BLUE)
        except Exception as e:
            _log_unexpected("discord_emoji_map_write", e)
            log("DISCORD", f"   Warning emoji_map.json error: {e}", Fore.YELLOW)

    @staticmethod
    def _write_emoji_map_file(path: str, emoji_ids: dict) -> None:
        """Write emoji map JSON from a worker thread."""
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(emoji_ids, handle)

    def _on_disconnect(self) -> None:
        """Update connection state after a Discord gateway disconnect."""
        if self.connected:
            log("DISCORD", "Warning Discord: Connection lost...", Fore.YELLOW)
            self.connected = False

    def _on_resumed(self) -> None:
        """Update connection state after Discord resumes the gateway session."""
        self.connected = True
        log("DISCORD", "Discord connection restored.", Fore.GREEN)

    def _on_raw_reaction_add(self, client: Any, payload: Any) -> None:
        """Record feedback reactions on bot messages."""
        if not self._feedback_enabled or payload.user_id == client.user.id:
            return
        emoji = str(payload.emoji)
        if emoji not in ("\U0001f44d", "\U0001f44e"):
            return
        rating = "up" if emoji == "\U0001f44d" else "down"
        success = FeedbackStore().rate_by_message(payload.message_id, rating)
        if success:
            log("FEEDBACK", f"{'Up' if rating == 'up' else 'Down'} Discord feedback from user {payload.user_id}", Fore.CYAN)

    async def _on_message(self, client: Any, message: Any) -> None:
        """Route incoming Discord DMs and channel messages into the queue."""
        import discord as _discord

        if message.author == client.user:
            return
        if isinstance(message.channel, _discord.DMChannel):
            await self._handle_dm_message(message)
            return
        await self._handle_channel_message(client, message)

    async def _handle_dm_message(self, message: Any) -> None:
        """Handle a Discord direct message."""
        discord_id = str(message.author.id)
        display_name = message.author.display_name
        if not is_dm_allowed(discord_id):
            log("DISCORD", f"Blocked DM from non-allowed user ignored: {display_name} ({discord_id})", Fore.YELLOW)
            return

        msg_data = await self._message_payload(message, source="discord_dm", user_key=resolve_discord_id(discord_id))
        if not msg_data:
            return
        log("DISCORD", f"DM ({display_name}/{msg_data.get('user_key') or 'anon'}): {msg_data['text']}", Fore.BLUE)
        self._queue_discord_message(msg_data)

    async def _handle_channel_message(self, client: Any, message: Any) -> None:
        """Handle VIP and private Discord channel messages."""
        private_ch_map = self._private_channel_user_map()
        is_vip = message.channel.id == DISCORD_VIP_CHANNEL_ID
        is_private = message.channel.id in private_ch_map
        if not is_vip and not is_private:
            return

        payload = await self._message_payload(message, source="discord_private" if is_private else "discord")
        if not payload:
            return
        if is_vip:
            self._queue_vip_message(client, message, payload)
        else:
            self._queue_private_message(message, payload)

    def _private_channel_user_map(self) -> dict:
        """Return channel_id -> discord_user_id for known private channels."""
        private_channels = self._load_private_channels()
        return {v["channel_id"]: k for k, v in private_channels.items()}

    async def _message_payload(self, message: Any, source: str, user_key: Optional[str] = None) -> Optional[dict]:
        """Build queue payload data from a Discord message."""
        clean_text = resolve_custom_emojis(message.content).strip()
        media_context, image_urls, text_attachments = await extract_media_context(message, DISCORD_SERVER_STICKERS)
        if media_context:
            clean_text = f"{clean_text} {media_context}".strip()
        if not clean_text and not text_attachments and not image_urls:
            return None

        discord_id = str(message.author.id)
        msg_data = {
            "user": message.author.display_name,
            "discord_id": discord_id,
            "user_key": user_key if user_key is not None else resolve_discord_id(discord_id),
            "text": clean_text,
            "source": source,
            "channel_id": message.channel.id,
        }
        if image_urls:
            msg_data["image_urls"] = image_urls
        if text_attachments:
            msg_data["text_attachments"] = text_attachments
        return msg_data

    def _queue_vip_message(self, client: Any, message: Any, payload: dict) -> None:
        """Queue a VIP-channel message when it mentions or triggers YourAI."""
        if not self._is_vip_triggered(client, message):
            return
        payload["text"] = self._strip_bot_mention(client, payload["text"]).strip()
        if not payload["text"] and not payload.get("text_attachments") and not payload.get("image_urls"):
            return
        log("DISCORD", f"VIP ({message.author.display_name}): {payload['text'][:60]}", Fore.BLUE)
        self._queue_discord_message(payload)

    def _queue_private_message(self, message: Any, payload: dict) -> None:
        """Queue a private-channel message."""
        log("DISCORD", f"Private ({message.author.display_name}/{payload.get('user_key') or 'anon'}): {payload['text'][:60]}", Fore.BLUE)
        self._queue_discord_message(payload)

    def _queue_discord_message(self, payload: dict) -> None:
        """Update activity state and enqueue a Discord message payload."""
        self.last_message_time = time.time()
        self.message_queue.put(payload)
        if payload.get("image_urls"):
            log("DISCORD", f"   {len(payload['image_urls'])} image(s) for Vision", Fore.CYAN)
        if payload.get("text_attachments"):
            log("DISCORD", f"   Text file(s): {len(payload['text_attachments'])}", Fore.CYAN)

    def _is_vip_triggered(self, client: Any, message: Any) -> bool:
        """Return True when a VIP message should trigger YourAI."""
        if client.user in message.mentions:
            return True
        msg_lower = message.content.lower()
        return any(keyword in msg_lower for keyword in DISCORD_TRIGGER_KEYWORDS)

    @staticmethod
    def _strip_bot_mention(client: Any, text: str) -> str:
        """Remove the bot mention from message text."""
        return text.replace(f"<@{client.user.id}>", "").strip()

    # ==========================================
    # SYNC API (callable from anywhere)
    # ==========================================

    def get_next_message(self) -> Optional[dict]:
        """Fetches the next message from the queue (non-blocking)."""
        if not self.message_queue.empty():
            return self.message_queue.get()
        return None

    def _resolve_outgoing_emojis(self, text: str) -> str:
        """Converts :emoji_name: into <:emoji_name:id> for Discord."""
        return self._sender._resolve_outgoing_emojis(text)

    def send_channel(self, channel_id: int, text: str):
        """Sends a message to a Discord channel (sync wrapper)."""
        return self._sender.send_channel(channel_id, text)

    def send_dm(self, discord_user_id: int, text: str):
        """Sends a DM to a user (sync wrapper)."""
        return self._sender.send_dm(discord_user_id, text)

    def send_sticker(self, channel_id: int, sticker_name: str):
        """Sends a server sticker to a channel or DM."""
        return self._sender.send_sticker(channel_id, sticker_name)

    def send_sticker_dm(self, discord_user_id: int, sticker_name: str):
        """Sends a server sticker as DM."""
        return self._sender.send_sticker_dm(discord_user_id, sticker_name)

    def send_channel_image(self, channel_id: int, image_url: str, prompt: str = "") -> bool:
        """Downloads an image from URL and posts it as attachment to a Discord channel."""
        return self._sender.send_channel_image(channel_id, image_url, prompt)

    def get_emoji_map(self) -> dict:
        """Returns {emoji_name: cdn_url} from the on_ready emoji cache."""
        return self._sender.get_emoji_map()

    def post_start_message(self, text: str = "Wanna talk to YourAI in private? \U0001f98a\nClick the button below to get your own cozy little channel!"):
        """
        Posts the private channel start message with the button widget.

        Args:
            text (str, optional): The prompt message.
        """
        return self._sender.post_start_message(text)

    def stop(self):
        """Safely stops the Discord bot and closes the connection loop."""
        self.running = False
        self.connected = False
        if self._loop and self._client:
            try:
                asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
            except Exception as e:
                _log_unexpected("discord_stop", e)


# Global instance
bot = DiscordBot()


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("DISCORD_TOKEN is not configured in the environment variables!")
        print("1. Go to https://discord.com/developers/applications")
        print("2. Navigate to your Application -> Bot -> copy the Token")
        print("3. Set DISCORD_TOKEN=your_token in .env")
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
