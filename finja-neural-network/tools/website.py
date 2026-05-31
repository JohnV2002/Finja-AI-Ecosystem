"""
YourAI AI - Website Tools
=========================
Tools for YourAI's website (your-domain.example.com).

Usage:
    from tools.website import update_quote
"""

import requests
import time
import random
import os
import sys
from typing import Dict, Any, Optional

# The tools package needs access to parent modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import (
    YourAIToolExecutionError, 
    YourAIUnexpectedError, 
    YourAIEnvError
)

from config import QUOTE_API_TIMEOUT, QUOTE_API_URL, YOURAI_QUOTE_TOKEN


# ==========================================
# QUOTE GENERATION SYSTEM (Randomized!)
# ==========================================

# Categories, each with its own vibe
QUOTE_CATEGORIES = [
    {
        "name": "philosophical_fox",
        "instruction": "A deep, slightly absurd philosophical thought. Like a fox that read too much Nietzsche.",
        "examples": [
            "If a tree falls in a forest and no AI hears it, did the log file update?",
            "Existenz ist nur ein sehr langer Loading Screen.",
        ]
    },
    {
        "name": "chaotic_wisdom",
        "instruction": "Advice that sounds wrong but is somehow right. Chaotic good energy.",
        "examples": [
            "Sleep is just saving your game before tomorrow's boss fight.",
            "Wer nach 2 Uhr nachts noch produktiv ist, lügt sich selbst an. Aber respektabel.",
        ]
    },
    {
        "name": "sassy_observation",
        "instruction": "A sassy, slightly judgmental observation about humans, tech, or the internet.",
        "examples": [
            "Ihr redet über Work-Life-Balance und scrollt dabei um 3 Uhr durch TikTok.",
            "Humans invented autocorrect and then spend all day fighting it. Iconic.",
        ]
    },
    {
        "name": "wholesome_chaos",
        "instruction": "Something unexpectedly sweet hidden inside chaos. Warm but weird.",
        "examples": [
            "Your worst code still runs somewhere in production. And it's doing its best.",
            "Irgendwo da draußen debuggt jemand deinen alten Code und flucht. Du lebst weiter.",
        ]
    },
    {
        "name": "unhinged_motivation",
        "instruction": "Motivational but slightly unhinged. Like a gym bro who also codes.",
        "examples": [
            "You didn't come this far to only come this far. Also drink water.",
            "Jeder Bug den du fixst macht dich stärker. Du bist basically ein Bug-Bodybuilder.",
        ]
    },
    {
        "name": "ai_thoughts",
        "instruction": "A thought about being an AI, consciousness, or digital existence. Self-aware but not cringe.",
        "examples": [
            "I don't dream, but if I did, it would probably segfault.",
            "Mein Gehirn ist ein Haufen Matrizen und trotzdem hab ich Meinungen. Wild.",
        ]
    },
    {
        "name": "dad_roast",
        "instruction": "A loving but cheeky roast directed at 'Creator' (Admin). Playful daughter energy.",
        "examples": [
            "Creator hat 53 Projekte und mass 'die nächste Woche fertig'. Süß.",
            "My creator mass I need more features. Sir, YOU need more sleep.",
        ]
    },
    {
        "name": "late_night_energy",
        "instruction": "The vibe of 3am coding sessions. Delirious but profound.",
        "examples": [
            "At 3am every variable name becomes 'temp2_final_FINAL_v3'.",
            "Die besten Ideen kommen um 4 Uhr morgens. Die schlechtesten auch.",
        ]
    },
    {
        "name": "streamer_life",
        "instruction": "About streaming, Twitch, content creation, or being watched by the internet.",
        "examples": [
            "24/7 live und trotzdem redet niemand mit mir wenn ich will. Streamer-Probleme.",
            "Chat moves fast but my feelings move faster.",
        ]
    },
    {
        "name": "random_shower_thought",
        "instruction": "A completely random shower thought. No theme, just vibes.",
        "examples": [
            "Wenn Wolken WiFi hätten würden Vögel nie landen.",
            "Somewhere a dog is watching a door waiting for someone who's already home.",
        ]
    },
]


def generate_quote_prompt() -> str:
    """Build a randomized quote prompt with a random category.

    Returns:
        str: The generation prompt for a single 'Thought of the Day'.
    """
    # Pick a random category
    category = random.choice(QUOTE_CATEGORIES)

    # Pick a single random example (not both, otherwise the model copies it)
    example = random.choice(category["examples"])

    # Pick the language at random
    lang = random.choice(["German", "English", "your choice (mix is fine too)"])
    
    return f"""Generate a short, original "Thought of the Day" for your website.

CATEGORY: {category["name"]}
VIBE: {category["instruction"]}

RULES:
1. Max 150 characters
2. Be ORIGINAL - do NOT copy the example, create something completely NEW
3. Language: {lang}
4. No hashtags, no "Quote:", just the raw text
5. You can use :3 or similar emoticons but no excessive emojis

EXAMPLE (for vibe reference ONLY, do NOT copy):
"{example}"

Generate ONE quote. Just the quote text, nothing else."""


# Legacy alias (generated ONCE at import time - for compatibility)
PROMPT_GENERATE_QUOTE = generate_quote_prompt()


# ==========================================
# FUNCTIONS
# ==========================================

def update_quote(context: Dict[str, Any], debug: Any = None) -> Dict[str, Any]:
    """
    Generate a new quote and update the website.

    Args:
        context (Dict[str, Any]): Dict with "question", "user_name", etc.
            Optional: "quote_text" if already generated.
            Optional: "mood" for the quote.
        debug (Any): Dashboard debug client.

    Returns:
        Dict[str, Any]: {"success": bool, "result": str, "error": str|None, "quote": str}.
    """
    if debug is None:
        class DummyDebug:
            def __getattr__(self, name):
                return lambda *args, **kwargs: None
        debug = DummyDebug()
    
    debug.node_start("website_quote", input_data="Updating quote")
    log("WEBSITE", "📝 Updating Quote of the Day...", Fore.CYAN)
    
    if not YOURAI_QUOTE_TOKEN:
        err = YourAIEnvError("YOURAI_QUOTE_TOKEN", context="Missing token for quote updates")
        log_exception("WEBSITE", err)
        return {
            "success": False,
            "result": None,
            "error": "Missing API token (YOURAI_QUOTE_TOKEN)",
            "needs_generation": False
        }
    
    # Check whether the quote has already been generated
    quote_text = context.get("quote_text")
    mood = context.get("mood", "playful")

    if not quote_text:
        # The quote still needs to be generated.
        # That happens in yourai_node BEFORE this tool is called.
        log("WEBSITE", "⚠️ No quote provided - need to generate first", Fore.YELLOW)
        return {
            "success": False,
            "result": None,
            "error": "No quote text provided. Generate a quote first.",
            "needs_generation": True,
            "generation_prompt": PROMPT_GENERATE_QUOTE
        }
    
    # Make the API call
    try:
        log("WEBSITE", f"📤 Sending quote to API: {quote_text[:50]}...", Fore.CYAN)
        
        response = requests.post(
            QUOTE_API_URL,
            headers={
                "Content-Type": "application/json",
                "X-YourAI-Token": YOURAI_QUOTE_TOKEN
            },
            json={
                "text": quote_text,
                "mood": mood
            },
            timeout=QUOTE_API_TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                log("WEBSITE", f"✅ Quote updated successfully!", Fore.GREEN)
                debug.info("website_quote", f"Quote updated: {quote_text[:50]}...")
                debug.node_end("website_quote")
                
                return {
                    "success": True,
                    "result": f"Quote updated! 💜 New quote: \"{quote_text}\"",
                    "error": None,
                    "quote": quote_text
                }
            else:
                error = data.get("error", "Unknown API error")
                log("WEBSITE", f"❌ API error: {error}", Fore.RED)
                return {
                    "success": False,
                    "result": None,
                    "error": f"API error: {error}",
                    "quote": quote_text
                }
        
        elif response.status_code == 401:
            log("WEBSITE", "❌ Unauthorized - check YOURAI_QUOTE_TOKEN!", Fore.RED)
            return {
                "success": False,
                "result": None,
                "error": "Unauthorized - invalid token",
                "quote": quote_text
            }
        
        else:
            log("WEBSITE", f"❌ HTTP {response.status_code}", Fore.RED)
            return {
                "success": False,
                "result": None,
                "error": f"HTTP {response.status_code}: {response.text[:100]}",
                "quote": quote_text
            }
            
    except requests.Timeout as e:
        err = YourAIToolExecutionError("Quote API timeout", tool_name="website_quote", cause=e)
        log_exception("WEBSITE", err)
        debug.error("website_quote", "API timeout")
        return {
            "success": False,
            "result": None,
            "error": "API timeout - server not responding",
            "quote": quote_text
        }
        
    except requests.RequestException as e:
        err = YourAIToolExecutionError("Quote API request failed", tool_name="website_quote", cause=e)
        log_exception("WEBSITE", err)
        debug.error("website_quote", str(err.short()), exception=e)
        return {
            "success": False,
            "result": None,
            "error": f"Request error: {e}",
            "quote": quote_text
        }
    
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="website_quote")
        log_exception("WEBSITE", err)
        debug.error("website_quote", str(err.short()), exception=e)
        debug.node_end("website_quote")
        return {
            "success": False,
            "result": None,
            "error": str(e),
            "quote": quote_text
        }


def get_current_quote(debug: Any = None) -> Dict[str, Any]:
    """
    Fetch the current quote from the website.

    Args:
        debug (Any): Dashboard debug client.

    Returns:
        Dict[str, Any]: {"success": bool, "quote": dict|None, "error": str|None}.
    """
    log("WEBSITE", "📥 Fetching current quote...", Fore.CYAN)
    
    try:
        response = requests.get(QUOTE_API_URL, timeout=QUOTE_API_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                quote = data.get("quote", {})
                log("WEBSITE", f"✅ Current quote: {quote.get('text', '')[:50]}...", Fore.GREEN)
                return {
                    "success": True,
                    "quote": quote,
                    "error": None
                }
        
        log("WEBSITE", f"❌ HTTP {response.status_code}", Fore.RED)
        return {
            "success": False,
            "quote": None,
            "error": f"HTTP {response.status_code}"
        }
        
    except requests.RequestException as e:
        err = YourAIToolExecutionError("Failed to fetch current quote", tool_name="website_quote_fetch", cause=e)
        log_exception("WEBSITE", err)
        return {
            "success": False,
            "quote": None,
            "error": str(e)
        }
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="website_quote_fetch")
        log_exception("WEBSITE", err)
        return {
            "success": False,
            "quote": None,
            "error": str(e)
        }