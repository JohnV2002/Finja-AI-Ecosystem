"""
YourAI AI - Home Assistant Integration
=======================================
API-Client für Home Assistant Smart Home Steuerung.
Admin-Only: Nur Creator darf das Smart Home steuern.

Endpoints:
    GET  /api/states                      → Alle Entity-States
    GET  /api/states/{entity_id}          → Einzelner State
    POST /api/services/{domain}/{service} → Service aufrufen (on/off/toggle/etc.)
    GET  /api/config                      → HA Konfiguration (Areas etc.)

Usage:
    from tools.home_assistant import ha_devices, ha_state, ha_turn_on, ha_turn_off
"""

import logging
import time
import re
import requests
from typing import Dict, Any, Optional, List

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIToolExecutionError
from config import HOMEASSISTANT_URL, HOMEASSISTANT_TOKEN, HOMEASSISTANT_TIMEOUT

logger = logging.getLogger("yourai.tools.home_assistant")

# ==========================================
# API HELPERS
# ==========================================

def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {HOMEASSISTANT_TOKEN}",
        "Content-Type": "application/json",
    }


def _api_get(endpoint: str) -> Any:
    """GET Request an Home Assistant API."""
    url = f"{HOMEASSISTANT_URL}/api/{endpoint}"
    response = requests.get(url, headers=_headers(), timeout=HOMEASSISTANT_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _api_post(endpoint: str, data: Optional[Dict] = None) -> Any:
    """POST Request an Home Assistant API."""
    url = f"{HOMEASSISTANT_URL}/api/{endpoint}"
    response = requests.post(url, headers=_headers(), json=data or {}, timeout=HOMEASSISTANT_TIMEOUT)
    response.raise_for_status()
    return response.json()


# ==========================================
# FRIENDLY NAMES & FILTERING
# ==========================================

# Domains die für YourAI relevant sind (keine internen/system entities)
_CONTROLLABLE_DOMAINS = {
    "light", "switch", "fan", "cover", "climate", "media_player",
    "vacuum", "lock", "scene", "script", "automation", "input_boolean",
}

_SENSOR_DOMAINS = {
    "sensor", "binary_sensor", "weather",
}

_RELEVANT_DOMAINS = _CONTROLLABLE_DOMAINS | _SENSOR_DOMAINS


def _friendly_state(entity: Dict) -> str:
    """Kompakte Darstellung eines Entity-States."""
    eid = entity.get("entity_id", "?")
    state = entity.get("state", "unknown")
    name = entity.get("attributes", {}).get("friendly_name", eid)
    domain = eid.split(".")[0] if "." in eid else "?"

    extra = []
    attrs = entity.get("attributes", {})

    if domain == "light" and state == "on":
        if "brightness" in attrs:
            pct = round(attrs["brightness"] / 255 * 100)
            extra.append(f"{pct}%")
        if "color_temp_kelvin" in attrs:
            extra.append(f"{attrs['color_temp_kelvin']}K")
    elif domain == "climate":
        if "current_temperature" in attrs:
            extra.append(f"{attrs['current_temperature']}°C")
        if "temperature" in attrs:
            extra.append(f"target {attrs['temperature']}°C")
    elif domain == "sensor":
        unit = attrs.get("unit_of_measurement", "")
        if unit:
            extra.append(f"{state} {unit}")
            return f"{name}: {' | '.join(extra)}"
    elif domain == "weather":
        if "temperature" in attrs:
            extra.append(f"{attrs['temperature']}°C")

    extra_str = f" ({', '.join(extra)})" if extra else ""
    return f"{name}: {state}{extra_str}"


# ==========================================
# MAIN FUNCTIONS
# ==========================================

def ha_devices(debug: Any = None) -> Dict[str, Any]:
    """
    Listet alle steuerbaren Geräte mit aktuellem Status.

    Returns:
        {"success": bool, "devices": [...], "message": str}
    """
    log("HOME", "🏠 Loading devices...", Fore.CYAN)

    if not HOMEASSISTANT_TOKEN:
        return {"success": False, "message": "Home Assistant token not configured"}

    try:
        start_time = time.time()
        states = _api_get("states")
        duration_ms = int((time.time() - start_time) * 1000)

        # Nach Domain gruppieren
        by_domain: Dict[str, List[str]] = {}
        for entity in states:
            eid = entity.get("entity_id", "")
            domain = eid.split(".")[0] if "." in eid else None
            if domain not in _RELEVANT_DOMAINS:
                continue
            if entity.get("state") == "unavailable":
                continue

            friendly = _friendly_state(entity)
            by_domain.setdefault(domain, []).append(friendly)

        # Formatieren
        lines = []
        domain_labels = {
            "light": "💡 Lichter", "switch": "🔌 Schalter", "fan": "🌀 Lüfter",
            "cover": "🪟 Rollos/Abdeckungen", "climate": "🌡️ Klima",
            "media_player": "📺 Media Player", "vacuum": "🤖 Staubsauger",
            "lock": "🔒 Schlösser", "scene": "🎬 Szenen", "script": "📜 Scripts",
            "automation": "⚙️ Automationen", "input_boolean": "🔘 Eingänge",
            "sensor": "📊 Sensoren", "binary_sensor": "📡 Binär-Sensoren",
            "weather": "🌤️ Wetter",
        }
        for domain in sorted(by_domain.keys()):
            label = domain_labels.get(domain, domain)
            lines.append(f"\n{label}:")
            for dev in sorted(by_domain[domain]):
                lines.append(f"  - {dev}")

        total = sum(len(v) for v in by_domain.values())
        message = f"🏠 {total} Geräte gefunden ({duration_ms}ms):" + "\n".join(lines)

        log("HOME", f"✅ {total} devices ({duration_ms}ms)", Fore.GREEN)
        return {"success": True, "devices": by_domain, "total": total, "message": message, "duration_ms": duration_ms}

    except requests.exceptions.Timeout:
        log("HOME", f"❌ Timeout ({HOMEASSISTANT_TIMEOUT}s)", Fore.RED)
        return {"success": False, "message": f"Home Assistant timeout ({HOMEASSISTANT_TIMEOUT}s)"}
    except requests.exceptions.ConnectionError:
        log("HOME", "❌ Not reachable", Fore.RED)
        return {"success": False, "message": "Home Assistant not reachable"}
    except Exception as e:
        err = YourAIToolExecutionError("HA devices error", tool_name="ha_devices", cause=e)
        log_exception("HOME", err)
        return {"success": False, "message": f"HA error: {e}"}


def ha_state(entity_id: str, debug: Any = None) -> Dict[str, Any]:
    """
    Holt den Status eines einzelnen Entity.
    """
    log("HOME", f"🏠 Getting state: {entity_id}", Fore.CYAN)

    if not HOMEASSISTANT_TOKEN:
        return {"success": False, "message": "Home Assistant token not configured"}

    try:
        entity = _api_get(f"states/{entity_id}")
        friendly = _friendly_state(entity)
        attrs = entity.get("attributes", {})

        message = f"🏠 {friendly}"
        log("HOME", f"✅ {friendly}", Fore.GREEN)
        return {"success": True, "entity_id": entity_id, "state": entity.get("state"), "attributes": attrs, "message": message}

    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return {"success": False, "message": f"Entity '{entity_id}' nicht gefunden"}
        return {"success": False, "message": f"HA HTTP error: {e.response.status_code if e.response else '?'}"}
    except Exception as e:
        err = YourAIToolExecutionError("HA state error", tool_name="ha_state", cause=e)
        log_exception("HOME", err)
        return {"success": False, "message": f"HA error: {e}"}


def ha_call_service(domain: str, service: str, entity_id: str, data: Optional[Dict] = None, debug: Any = None) -> Dict[str, Any]:
    """
    Ruft einen Home Assistant Service auf.

    Args:
        domain: z.B. "light", "switch", "climate"
        service: z.B. "turn_on", "turn_off", "toggle"
        entity_id: z.B. "light.wohnzimmer"
        data: Zusätzliche Daten (brightness, temperature, etc.)
    """
    log("HOME", f"🏠 Calling {domain}.{service} on {entity_id}", Fore.CYAN)

    if not HOMEASSISTANT_TOKEN:
        return {"success": False, "message": "Home Assistant token not configured"}

    try:
        payload = {"entity_id": entity_id}
        if data:
            payload.update(data)

        result = _api_post(f"services/{domain}/{service}", payload)

        name = entity_id
        # Try to get friendly name from result
        if isinstance(result, list) and result:
            name = result[0].get("attributes", {}).get("friendly_name", entity_id)

        message = f"✅ {name}: {service.replace('_', ' ')}"
        if data:
            extras = [f"{k}={v}" for k, v in data.items()]
            message += f" ({', '.join(extras)})"

        log("HOME", message, Fore.GREEN)
        return {"success": True, "entity_id": entity_id, "service": f"{domain}.{service}", "message": message}

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        log("HOME", f"❌ HTTP {status}", Fore.RED)
        return {"success": False, "message": f"HA service call failed: HTTP {status}"}
    except Exception as e:
        err = YourAIToolExecutionError(f"HA service call error ({domain}.{service})", tool_name="ha_call_service", cause=e)
        log_exception("HOME", err)
        return {"success": False, "message": f"HA error: {e}"}


def ha_turn_on(entity_id: str, **kwargs) -> Dict[str, Any]:
    """Schaltet ein Gerät ein. Optional: brightness (0-255), color_temp_kelvin, etc."""
    domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
    data = {}
    if "brightness" in kwargs:
        # Accept percentage (0-100), convert to HA (0-255)
        val = kwargs["brightness"]
        if isinstance(val, (int, float)) and val <= 100:
            data["brightness"] = round(val * 255 / 100)
        else:
            data["brightness"] = int(val)
    if "color_temp_kelvin" in kwargs:
        data["color_temp_kelvin"] = int(kwargs["color_temp_kelvin"])
    if "temperature" in kwargs:
        data["temperature"] = float(kwargs["temperature"])
    return ha_call_service(domain, "turn_on", entity_id, data if data else None)


def ha_turn_off(entity_id: str) -> Dict[str, Any]:
    """Schaltet ein Gerät aus."""
    domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
    return ha_call_service(domain, "turn_off", entity_id)


def ha_toggle(entity_id: str) -> Dict[str, Any]:
    """Toggled ein Gerät."""
    domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
    return ha_call_service(domain, "toggle", entity_id)


def ha_scenes(debug: Any = None) -> Dict[str, Any]:
    """Listet alle verfügbaren Szenen."""
    log("HOME", "🏠 Loading scenes...", Fore.CYAN)

    if not HOMEASSISTANT_TOKEN:
        return {"success": False, "message": "Home Assistant token not configured"}

    try:
        states = _api_get("states")
        scenes = []
        for entity in states:
            eid = entity.get("entity_id", "")
            if eid.startswith("scene."):
                name = entity.get("attributes", {}).get("friendly_name", eid)
                scenes.append({"entity_id": eid, "name": name})

        if scenes:
            scene_list = "\n".join(f"  - {s['name']} ({s['entity_id']})" for s in sorted(scenes, key=lambda x: x["name"]))
            message = f"🎬 {len(scenes)} Szenen:\n{scene_list}"
        else:
            message = "🎬 Keine Szenen vorhanden"

        log("HOME", f"✅ {len(scenes)} scenes", Fore.GREEN)
        return {"success": True, "scenes": scenes, "message": message}

    except Exception as e:
        err = YourAIToolExecutionError("HA scenes error", tool_name="ha_scenes", cause=e)
        log_exception("HOME", err)
        return {"success": False, "message": f"HA error: {e}"}


def ha_activate_scene(scene_entity_id: str) -> Dict[str, Any]:
    """Aktiviert eine Szene."""
    if not scene_entity_id.startswith("scene."):
        scene_entity_id = f"scene.{scene_entity_id}"
    return ha_call_service("scene", "turn_on", scene_entity_id)


# ==========================================
# COMMAND PARSER (für [HOME:command] Tags)
# ==========================================

def execute_home_command(cmd: str, debug: Any = None) -> Dict[str, Any]:
    """
    Parst und führt einen [HOME:command] Tag aus.

    Supported commands:
        devices                       → Liste aller Geräte
        status <entity_id>            → Status eines Geräts
        on <entity_id>                → Einschalten
        on <entity_id> brightness=80  → Einschalten mit Helligkeit
        off <entity_id>               → Ausschalten
        toggle <entity_id>            → Umschalten
        scenes                        → Alle Szenen listen
        scene <name>                  → Szene aktivieren
    """
    cmd = cmd.strip()
    cmd_lower = cmd.lower()

    log("HOME", f"🏠 Executing: [HOME:{cmd}]", Fore.MAGENTA)

    try:
        if cmd_lower == "devices":
            return ha_devices(debug)

        elif cmd_lower == "scenes":
            return ha_scenes(debug)

        elif cmd_lower.startswith("scene "):
            scene_name = cmd[6:].strip()
            return ha_activate_scene(scene_name)

        elif cmd_lower.startswith("status "):
            entity_id = cmd[7:].strip()
            return ha_state(entity_id, debug)

        elif cmd_lower.startswith("on "):
            parts = cmd[3:].strip()
            # Parse optional key=value params
            entity_id, kwargs = _parse_entity_and_params(parts)
            return ha_turn_on(entity_id, **kwargs)

        elif cmd_lower.startswith("off "):
            entity_id = cmd[4:].strip()
            return ha_turn_off(entity_id)

        elif cmd_lower.startswith("toggle "):
            entity_id = cmd[7:].strip()
            return ha_toggle(entity_id)

        else:
            return {"success": False, "message": f"Unknown HOME command: {cmd}"}

    except Exception as e:
        err = YourAIToolExecutionError(f"HA command error: {cmd}", tool_name="execute_home_command", cause=e)
        log_exception("HOME", err)
        return {"success": False, "message": f"HA command error: {e}"}


def _parse_entity_and_params(text: str) -> tuple:
    """Parst 'entity_id key=value key2=value2' → (entity_id, {key: value})."""
    parts = text.split()
    if not parts:
        return text, {}

    entity_id = parts[0]
    kwargs = {}
    for part in parts[1:]:
        if "=" in part:
            k, _, v = part.partition("=")
            try:
                kwargs[k] = float(v) if "." in v else int(v)
            except ValueError:
                kwargs[k] = v

    return entity_id, kwargs


def format_result_for_prompt(result: Dict[str, Any]) -> str:
    """Formatiert HA-Ergebnis kompakt für YourAIs Prompt-Kontext."""
    return result.get("message", "No result")
