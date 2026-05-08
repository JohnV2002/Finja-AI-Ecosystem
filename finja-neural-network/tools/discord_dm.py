"""
YourAI AI - Discord DM Tool
============================
Sendet DMs an whitelisted Discord User.

Usage:
    from tools.discord_dm import send_discord_dm
"""

import os
import sys
from typing import Dict, Any

# Tools-Ordner braucht Zugriff auf Parent-Module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIToolExecutionError, YourAIUnexpectedError

from config import DISCORD_DM_WHITELIST


def send_discord_dm(context: Dict[str, Any], debug: Any = None) -> Dict[str, Any]:
    """
    Sendet eine DM an einen whitelisted Discord User.

    Der Tool Router erkennt den Trigger und ruft dieses Tool auf.
    YourAI generiert die Nachricht, das Tool sendet sie.

    Args:
        context: Dict mit:
            - "question": Original User-Input (z.B. "schreib Mom eine DM dass ich sie lieb hab")
            - "user_name": Wer hat den Befehl gegeben
            - "dm_target": Target User Key aus Whitelist (z.B. "Mom", "Bendy")
            - "dm_message": Die zu sendende Nachricht (generiert von YourAI)

    Returns:
        {"success": bool, "result": str, "error": str|None}
    """
    if debug is None:
        class DummyDebug:
            def __getattr__(self, name):
                return lambda *args, **kwargs: None
        debug = DummyDebug()

    debug.node_start("discord_dm", input_data="Sending Discord DM")

    # Target aus Context oder aus der Frage extrahieren
    target_key = context.get("dm_target")
    dm_message = context.get("dm_message")

    if not target_key:
        # Versuche Target aus der Frage zu erkennen
        question = context.get("question", "").lower()
        for discord_id, user_key in DISCORD_DM_WHITELIST.items():
            if user_key.lower() in question:
                target_key = user_key
                break

    if not target_key:
        log("DISCORD", "⚠️ DM Tool: Kein Target erkannt", Fore.YELLOW)
        debug.node_end("discord_dm")
        return {
            "success": False,
            "result": None,
            "error": "Kein DM-Ziel erkannt. Sag mir WEM ich schreiben soll!",
            "needs_generation": False
        }

    # Discord ID für den Target finden
    target_discord_id = None
    for discord_id, user_key in DISCORD_DM_WHITELIST.items():
        if user_key.lower() == target_key.lower():
            target_discord_id = int(discord_id)
            break

    if not target_discord_id:
        log("DISCORD", f"🚫 DM Tool: '{target_key}' nicht in Whitelist!", Fore.RED)
        debug.node_end("discord_dm")
        return {
            "success": False,
            "result": None,
            "error": f"'{target_key}' ist nicht in meiner DM-Whitelist! Ich darf nur an bestimmte Leute schreiben.",
            "needs_generation": False
        }

    if not dm_message:
        # YourAI muss erst die Nachricht generieren
        log("DISCORD", f"📝 DM Tool: Brauche Message für {target_key}", Fore.YELLOW)
        debug.node_end("discord_dm")
        return {
            "success": False,
            "result": None,
            "error": None,
            "needs_generation": True,
            "dm_target": target_key,
            "generation_prompt": f"Write a Discord DM message to {target_key}. Context: {context.get('question', '')}"
        }

    # Discord Bot holen und DM senden
    try:
        import discord_client
        bot = discord_client.bot

        if not bot.connected:
            log("DISCORD", "⚠️ DM Tool: Bot nicht verbunden!", Fore.YELLOW)
            debug.node_end("discord_dm")
            return {
                "success": False,
                "result": None,
                "error": "Discord Bot ist nicht verbunden! Kann keine DM senden."
            }

        bot.send_dm(target_discord_id, dm_message)

        log("DISCORD", f"📩 DM an {target_key} gesendet: {dm_message[:50]}...", Fore.GREEN)
        debug.info("discord_dm", f"DM sent to {target_key}: {dm_message[:50]}...")
        debug.node_end("discord_dm")

        return {
            "success": True,
            "result": f"DM an {target_key} gesendet! Message: \"{dm_message[:100]}\"",
            "error": None,
            "dm_target": target_key,
            "dm_message": dm_message
        }

    except ImportError as e:
        from exceptions import YourAIImportError
        err = YourAIImportError("discord_client", module="discord_dm", cause=e)
        log_exception("DISCORD", err)
        debug.node_end("discord_dm")
        return {
            "success": False,
            "result": None,
            "error": "Discord Client nicht geladen (USE_DISCORD ist aus?)"
        }

    except Exception as e:
        err = YourAIToolExecutionError("Fehler beim Senden der DM", tool_name="discord_dm", cause=e)
        log_exception("DISCORD", err)
        debug.error("discord_dm", err.short(), exception=e)
        debug.node_end("discord_dm")
        return {
            "success": False,
            "result": None,
            "error": f"Fehler beim Senden: {e}"
        }
