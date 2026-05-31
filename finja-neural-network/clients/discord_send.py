"""
YourAI AI - Discord Sender
=========================
Synchronous send API wrapper mapping calls into the Discord bot's asyncio event loop.

Main Responsibilities:
- Marshal synchronous payload calls (messages, stickers, images, DMs) into async tasks.
- Resolve outgoing emojis using cached server dictionary maps.
- Handle delivery verification, rate limit recovery warnings, and feedback tracking links.

Side Effects:
- Submits asynchronous messages and reactions to external Discord API.
"""

from typing import Any
import asyncio
import base64
import io
from typing import Optional

import _paths  # noqa: F401

from display import Fore, log, log_exception
from exceptions import YourAIUnexpectedError
from feedback import FeedbackStore
from helpers.platform_links import is_dm_allowed, resolve_discord_id
from helpers.text_parser import extract_discord_emoji_id

from discord_messages import resolve_outgoing_emojis, split_message


def _log_unexpected(module: str, error: Exception):
    """
    Wraps an unexpected exception in a YourAI error and logs it.
    
    Returns:
        Any: The operation result, or None when no result is produced.
    """
    err = YourAIUnexpectedError(cause=error, module=module)
    log_exception("DISCORD", err)


class DiscordSender:
    """
    Send helper that interfaces with the Discord bot's event loop.
    Allows synchronous thread execution mapping to asynchronous loop tasks.
    """

    def __init__(self, bot):
        """
        Initializes instance state and cached connection metadata.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        self.bot = bot

    def _ready(self) -> bool:
        """
        Checks whether the Discord client and event loop are ready to send.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        return bool(self.bot._loop and self.bot._client and self.bot.connected)

    def _resolve_outgoing_emojis(self, text: str) -> str:
        """
        Maps outgoing emoji shortcodes to cached Discord custom emoji markup.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        return resolve_outgoing_emojis(text, self.bot._server_emojis)

    def _link_feedback(self, result):
        """
        Links a sent Discord message to the pending feedback tracking ID.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        tracking_id = getattr(self.bot, "_pending_tracking_id", None)
        if result and tracking_id:
            fb = FeedbackStore()
            fb.link_discord_message(result.id, tracking_id)
            self.bot._pending_tracking_id = None

    def send_channel(self, channel_id: int, text: str):
        """
        Sends a text message to a Discord channel.

        Args:
            channel_id (int): The target Discord channel ID.
            text (str): Message text to send.
        """
        if not self._ready():
            log("DISCORD", "Cannot send - Bot not connected", Fore.YELLOW)
            return

        text = self._resolve_outgoing_emojis(text)

        async def _do_send():
            """
            Executes the asynchronous Discord send operation.
            
            Returns:
                Any: The operation result, or None when no result is produced.
            """
            client = self.bot._client
            assert client is not None
            channel = client.get_channel(channel_id)
            if not channel or not hasattr(channel, "send"):
                log("DISCORD", f"Channel {channel_id} not found", Fore.YELLOW)
                return None
            chunks = split_message(text)
            if not chunks:
                log("DISCORD", "Empty message, nothing to send", Fore.YELLOW)
                return None
            last_msg = None
            for chunk in chunks:
                last_msg = await channel.send(chunk)  # type: ignore[union-attr]
            if last_msg and self.bot._feedback_enabled:
                try:
                    await last_msg.add_reaction("\U0001f44d")
                    await last_msg.add_reaction("\U0001f44e")
                except Exception as e:
                    _log_unexpected("discord_feedback_reaction_channel", e)
            return last_msg

        try:
            future = asyncio.run_coroutine_threadsafe(_do_send(), self.bot._loop)
            result = future.result(timeout=30)
            self._link_feedback(result)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="discord_send_channel")
            log_exception("DISCORD", err)
            log("DISCORD", f"send_channel failed: {type(e).__name__}: {e}", Fore.RED)

    async def _execute_dm_send(self, user, text: str, user_id_str: str) -> Optional[Any]:
        """
        Sends prepared DM chunks and attaches feedback reactions.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        chunks = split_message(text)
        if not chunks:
            log("DISCORD", "Empty DM, nothing to send", Fore.YELLOW)
            return None
        last_msg = None
        for chunk in chunks:
            last_msg = await user.send(chunk)

        user_key = resolve_discord_id(user_id_str) or "anon"
        log("DISCORD", f"DM sent to {user.display_name} ({user_key})", Fore.GREEN)

        if last_msg and self.bot._feedback_enabled:
            try:
                await last_msg.add_reaction("\U0001f44d")
                await last_msg.add_reaction("\U0001f44e")
            except Exception as e:
                _log_unexpected("discord_feedback_reaction_dm", e)
        return last_msg

    def send_dm(self, discord_user_id: int, text: str):
        """
        Sends a private message to a whitelisted Discord user.

        Args:
            discord_user_id (int): The target user ID.
            text (str): Message text to send.
        """
        user_id_str = str(discord_user_id)
        if not is_dm_allowed(user_id_str):
            log("DISCORD", f"DM to {discord_user_id} blocked - dm_allowed=false!", Fore.RED)
            return

        if not self._ready():
            log("DISCORD", "Cannot send DM - Bot not connected", Fore.YELLOW)
            return

        text = self._resolve_outgoing_emojis(text)

        async def _do_send():
            """
            Executes the asynchronous Discord send operation.
            
            Returns:
                Any: The operation result, or None when no result is produced.
            """
            client = self.bot._client
            assert client is not None
            user = await client.fetch_user(discord_user_id)
            if not user:
                log("DISCORD", f"User {discord_user_id} not found", Fore.YELLOW)
                return None
            return await self._execute_dm_send(user, text, user_id_str)

        try:
            future = asyncio.run_coroutine_threadsafe(_do_send(), self.bot._loop)
            result = future.result(timeout=30)
            self._link_feedback(result)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="discord_send_dm")
            log_exception("DISCORD", err)
            log("DISCORD", f"send_dm failed: {type(e).__name__}: {e}", Fore.RED)

    def send_sticker(self, channel_id: int, sticker_name: str) -> bool:
        """
        Sends a guild-specific sticker to a channel.

        Args:
            channel_id (int): Target channel ID.
            sticker_name (str): Case-insensitive sticker name.

        Returns:
            bool: True on success, False on failure.
        """
        if not self._ready():
            log("DISCORD", "Cannot send sticker - Bot not connected", Fore.YELLOW)
            return False

        sticker = self.bot._server_stickers.get(sticker_name.lower())
        if not sticker:
            log("DISCORD", f"Sticker '{sticker_name}' not found on server", Fore.YELLOW)
            return False

        async def _do_send():
            """
            Executes the asynchronous Discord send operation.
            
            Returns:
                Any: The operation result, or None when no result is produced.
            """
            client = self.bot._client
            assert client is not None
            channel = client.get_channel(channel_id)
            if channel and hasattr(channel, "send"):
                await channel.send(stickers=[sticker])  # type: ignore[arg-type, union-attr]
            else:
                log("DISCORD", f"Channel {channel_id} not found for sticker", Fore.YELLOW)

        try:
            future = asyncio.run_coroutine_threadsafe(_do_send(), self.bot._loop)
            future.result(timeout=10)
            log("DISCORD", f"Sticker sent: {sticker_name}", Fore.GREEN)
            return True
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="discord_send_sticker")
            log_exception("DISCORD", err)
            return False

    def send_sticker_dm(self, discord_user_id: int, sticker_name: str) -> bool:
        """
        Sends a guild sticker as a private DM.

        Args:
            discord_user_id (int): Target user ID.
            sticker_name (str): Sticker name.

        Returns:
            bool: True on success, False on failure.
        """
        user_id_str = str(discord_user_id)
        if not is_dm_allowed(user_id_str):
            log("DISCORD", f"Sticker DM to {discord_user_id} blocked - dm_allowed=false!", Fore.RED)
            return False

        if not self._ready():
            return False

        sticker = self.bot._server_stickers.get(sticker_name.lower())
        if not sticker:
            log("DISCORD", f"Sticker '{sticker_name}' not found on server", Fore.YELLOW)
            return False

        async def _do_send():
            """
            Executes the asynchronous Discord send operation.
            
            Returns:
                Any: The operation result, or None when no result is produced.
            """
            client = self.bot._client
            assert client is not None
            user = await client.fetch_user(discord_user_id)
            if user:
                await user.send(stickers=[sticker])  # type: ignore[arg-type]

        try:
            future = asyncio.run_coroutine_threadsafe(_do_send(), self.bot._loop)
            future.result(timeout=10)
            user_key = resolve_discord_id(user_id_str) or "anon"
            log("DISCORD", f"Sticker DM sent to {user_key}: {sticker_name}", Fore.GREEN)
            return True
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="discord_send_sticker_dm")
            log_exception("DISCORD", err)
            return False

    def send_channel_image(self, channel_id: int, image_url: str, prompt: str = "") -> bool:
        """
        Downloads a visual asset (data URI or URL) and uploads it as an attachment.

        Args:
            channel_id (int): Target channel ID.
            image_url (str): Target URL or inline base64 string.
            prompt (str, optional): Generation prompt description.

        Returns:
            bool: True on success, False on failure.
        """
        if not self._ready():
            log("DISCORD", "Cannot send image - Bot not connected", Fore.YELLOW)
            return False

        async def _do_send():
            """
            Executes the asynchronous Discord send operation.
            
            Returns:
                Any: The operation result, or None when no result is produced.
            """
            import discord as _disc
            import aiohttp as _aio

            client = self.bot._client
            assert client is not None
            channel = client.get_channel(channel_id)
            if not channel or not hasattr(channel, "send"):
                log("DISCORD", f"Channel {channel_id} not found for image", Fore.YELLOW)
                return False
            try:
                if image_url.startswith("data:"):
                    _, encoded = image_url.split(",", 1)
                    img_bytes = base64.b64decode(encoded)
                else:
                    async with _aio.ClientSession() as session:
                        async with session.get(image_url, timeout=30) as resp:
                            img_bytes = await resp.read()
                file = _disc.File(io.BytesIO(img_bytes), filename="yourai_art.png")
                caption = "Here you go!"
                if prompt:
                    caption += f'\n*"{prompt[:150]}"*'
                await channel.send(caption, file=file)
                log("DISCORD", f"Image sent in channel {channel_id}", Fore.GREEN)
                return True
            except Exception as e:
                _log_unexpected("discord_send_channel_image_inner", e)
                log("DISCORD", f"Image sending failed: {e}", Fore.RED)
                return False

        try:
            future = asyncio.run_coroutine_threadsafe(_do_send(), self.bot._loop)
            return future.result(timeout=45)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="discord_send_channel_image")
            log_exception("DISCORD", err)
            return False

    def get_emoji_map(self) -> dict:
        """
        Resolves a cache map matching emoji names to their unique custom Discord formats.

        Returns:
            dict: A name -> id dictionary mappings.
        """
        result = {}
        for name, discord_fmt in self.bot._server_emojis.items():
            emoji_id = extract_discord_emoji_id(discord_fmt)
            if emoji_id:
                result[name] = emoji_id
        return result

    def post_start_message(self, text: str) -> bool:
        """
        Posts the persistent private-channel start yapping button inside the lobby room.

        Args:
            text (str): Room message label.

        Returns:
            bool: True on success, False on failure.
        """
        if not self._ready():
            log("DISCORD", "Cannot post start message - Bot not connected", Fore.YELLOW)
            return False
        if not self.bot._private_view_class:
            log("DISCORD", "_PrivateChannelView not initialized", Fore.YELLOW)
            return False

        async def _do_post():
            """
            Posts the private-channel start message with its persistent view.
            
            Returns:
                Any: The operation result, or None when no result is produced.
            """
            client = self.bot._client
            assert client is not None
            channel = client.get_channel(self.bot.start_channel_id)
            if not channel or not hasattr(channel, "send"):
                log("DISCORD", f"Start channel {self.bot.start_channel_id} not found", Fore.YELLOW)
                return False
            await channel.send(text, view=self.bot._private_view_class())  # type: ignore[union-attr]
            log("DISCORD", f"Start message posted in channel {self.bot.start_channel_id}", Fore.GREEN)
            return True

        try:
            future = asyncio.run_coroutine_threadsafe(_do_post(), self.bot._loop)
            return future.result(timeout=10)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="discord_post_start_message")
            log_exception("DISCORD", err)
            return False

