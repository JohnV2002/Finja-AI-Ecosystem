"""
YourAI AI - Custom Exceptions
==============================
Einheitliche Exception-Hierarchie für das gesamte YourAI-Ökosystem.

Alle Exceptions erben von YourAIError und enthalten:
- Klaren Error-Code (für Logs und Dashboard)
- Kontext-Info (welches Modul, welches Model, etc.)
- Menschenlesbare Nachricht

Usage:
    from exceptions import YourAILLMError, YourAIConfigError, ...

    try:
        response = call_openrouter(...)
    except Exception as e:
        raise YourAILLMError("OpenRouter call failed", model="nemotron-49b", cause=e)

Error Codes:
    YOURAI-1xx = Config/Setup Errors (100=Config, 101=Env, 102=Import, 103=Permission, 104=MissingDependency)
    YOURAI-2xx = LLM/Model Errors (200=General, 201=Timeout, 202=Connection, 203=Parse,
                204=EmptyResponse, 205=RateLimit, 206=ModelNotFound, 207=PromptTooLong,
                208=Network, 210=AllTiersFailed)
    YOURAI-3xx = Memory/Embedding Errors (300=General, 301=Embed, 302=Disconnect, 303=Server)
    YOURAI-4xx = Session/Auth Errors (400=General, 401=Corrupt, 402=UserNotFound, 403=InvalidUser,
                404=AdminOnly, 444=NoPrivilege)
    YOURAI-5xx = Tool/External Errors (500=General, 501=NotFound, 502=Execution, 510=Vision)
    YOURAI-6xx = Pipeline/Flow Errors (600=General, 601=Guard, 602=Safety)
    YOURAI-7xx = Website/Web Errors (700=General, 701=Fetch, 702=Parse, 703=Blocked,
                704=Validation, 705=Deploy, 706=Truncated, 707=SaveFailed)
    YOURAI-8xx = System/OS Errors (800=General, 801=ProcessKilled, 802=DiskSpace)
    YOURAI-9xx = Unexpected/Unknown (999=Catch-all)
"""

from typing import Optional


class YourAIError(Exception):
    """
    Basis-Exception für alle YourAI-Fehler.
    
    Attributes:
        code: Error-Code (z.B. "YOURAI-201")
        module: Welches Modul den Fehler ausgelöst hat
        context: Zusätzliche Kontext-Infos (dict)
        cause: Die ursprüngliche Exception (falls vorhanden)
    """
    
    code: str = "YOURAI-900"
    
    def __init__(self, message: str, module: str = "unknown", cause: Optional[Exception] = None, **context):
        self.module = module
        self.context = context
        self.cause = cause
        
        # Baue erweiterte Nachricht
        parts = [message]
        if module != "unknown":
            parts.append(f"[module={module}]")
        if context:
            ctx_str = ", ".join(f"{k}={v}" for k, v in context.items())
            parts.append(f"[{ctx_str}]")
        if cause:
            parts.append(f"(caused by {type(cause).__name__}: {cause})")
        
        self.full_message = " ".join(parts)
        super().__init__(self.full_message)
    
    def short(self) -> str:
        """Kurze Zusammenfassung für Logs."""
        return f"[{self.code}] {self.args[0] if self.args else 'Unknown error'}"
    
    def for_dashboard(self) -> dict:
        """Strukturierte Daten fürs Dashboard."""
        return {
            "code": self.code,
            "message": str(self),
            "module": self.module,
            "context": self.context,
            "cause": f"{type(self.cause).__name__}: {self.cause}" if self.cause else None,
        }


# ==========================================
# 1xx - CONFIG / SETUP ERRORS
# ==========================================

class YourAIConfigError(YourAIError):
    """Fehlende oder ungültige Konfiguration."""
    code = "YOURAI-100"

    def __init__(self, message: str, key: Optional[str] = None, **kwargs):
        module = kwargs.pop("module", "config")
        super().__init__(message, module=module, key=key, **kwargs)


class YourAIEnvError(YourAIConfigError):
    """Fehlende .env Variable."""
    code = "YOURAI-101"
    
    def __init__(self, var_name: str, **kwargs):
        super().__init__(
            f"Missing .env variable: {var_name}", 
            key=var_name, 
            hint=f"Add {var_name}=... to your .env file",
            **kwargs
        )


class YourAIImportError(YourAIConfigError):
    """Fehlendes Python-Paket."""
    code = "YOURAI-102"

    def __init__(self, package: str, pip_name: Optional[str] = None, **kwargs):
        pip_cmd = pip_name or package
        super().__init__(
            f"Missing package: {package}",
            key=package,
            hint=f"pip install {pip_cmd}",
            **kwargs
        )


class YourAIPermissionError(YourAIConfigError):
    """Dateizugriff verweigert (read/write auf Config, DB, etc.)."""
    code = "YOURAI-103"

    def __init__(self, filepath: str, operation: str = "access", **kwargs):
        super().__init__(
            f"Permission denied: cannot {operation} '{filepath}'",
            key=filepath,
            operation=operation,
            **kwargs
        )


class YourAIMissingDependencyError(YourAIConfigError):
    """Optionales Package fehlt für ein bestimmtes Feature."""
    code = "YOURAI-104"

    def __init__(self, package: str, feature: str, pip_name: Optional[str] = None, **kwargs):
        pip_cmd = pip_name or package
        super().__init__(
            f"Optional package '{package}' required for {feature}",
            key=package,
            feature=feature,
            hint=f"pip install {pip_cmd}",
            **kwargs
        )


# ==========================================
# 2xx - LLM / MODEL ERRORS
# ==========================================

class YourAILLMError(YourAIError):
    """Allgemeiner LLM-Fehler."""
    code = "YOURAI-200"

    def __init__(self, message: str, model: str = "unknown", tier: Optional[str] = None, **kwargs):
        # Allow callers to override module (default: "llm")
        module = kwargs.pop("module", "llm")
        super().__init__(message, module=module, model=model, tier=tier, **kwargs)


class YourAILLMTimeoutError(YourAILLMError):
    """LLM hat zu lange gebraucht."""
    code = "YOURAI-201"
    
    def __init__(self, model: str, timeout_seconds: float, **kwargs):
        super().__init__(
            f"LLM timeout after {timeout_seconds}s",
            model=model,
            timeout=timeout_seconds,
            **kwargs
        )


class YourAILLMConnectionError(YourAILLMError):
    """Verbindung zum LLM fehlgeschlagen."""
    code = "YOURAI-202"
    
    def __init__(self, model: str, host: Optional[str] = None, **kwargs):
        super().__init__(
            f"Cannot connect to LLM",
            model=model,
            host=host,
            **kwargs
        )


class YourAILLMParseError(YourAILLMError):
    """LLM-Response konnte nicht geparst werden."""
    code = "YOURAI-203"
    
    def __init__(self, model: str, expected: str = "JSON", raw_preview: Optional[str] = None, **kwargs):
        preview = (raw_preview[:80] + "...") if raw_preview and len(raw_preview) > 80 else raw_preview
        super().__init__(
            f"Failed to parse {expected} from LLM response",
            model=model,
            expected_format=expected,
            raw_preview=preview,
            **kwargs
        )


class YourAIEmptyResponseError(YourAILLMError):
    """LLM hat einen leeren String zurückgegeben (Server-seitig kein Output)."""
    code = "YOURAI-204"

    def __init__(self, model: str, node: Optional[str] = None, **kwargs):
        super().__init__(
            f"LLM returned empty response",
            model=model,
            node=node,
            hint="Server might be overloaded or model produced no output",
            **kwargs
        )


class YourAIRateLimitError(YourAILLMError):
    """API Rate Limit erreicht (429 / Too Many Requests)."""
    code = "YOURAI-205"

    def __init__(self, model: str, retry_after: Optional[float] = None, **kwargs):
        msg = f"Rate limit hit"
        if retry_after:
            msg += f" (retry after {retry_after}s)"
        super().__init__(
            msg,
            model=model,
            retry_after=retry_after,
            **kwargs
        )


class YourAIModelNotFoundError(YourAILLMError):
    """Model nicht gefunden (404 von OpenRouter/Ollama)."""
    code = "YOURAI-206"

    def __init__(self, model: str, host: Optional[str] = None, **kwargs):
        super().__init__(
            f"Model not found: {model}",
            model=model,
            host=host,
            hint=f"Check if '{model}' exists on the provider or run 'ollama pull {model}'",
            **kwargs
        )


class YourAIPromptTooLongError(YourAILLMError):
    """Prompt/Context übersteigt das Context Window des Models."""
    code = "YOURAI-207"

    def __init__(self, model: str, prompt_tokens: Optional[int] = None,
                 max_tokens: Optional[int] = None, **kwargs):
        parts = [f"Prompt too long for {model}"]
        if prompt_tokens and max_tokens:
            parts.append(f"({prompt_tokens}/{max_tokens} tokens)")
        super().__init__(
            " ".join(parts),
            model=model,
            prompt_tokens=prompt_tokens,
            max_tokens=max_tokens,
            hint="Reduce context size or use a model with larger context window",
            **kwargs
        )


class YourAINetworkError(YourAILLMError):
    """Netzwerk-Fehler (DNS, SSL, OpenRouter/Ollama nicht erreichbar)."""
    code = "YOURAI-208"

    def __init__(self, host: str, cause: Optional[Exception] = None, **kwargs):
        super().__init__(
            f"Network error: cannot reach {host}",
            model="n/a",
            host=host,
            cause=cause,
            **kwargs
        )


class YourAIAllTiersFailedError(YourAILLMError):
    """Alle LLM-Tiers sind fehlgeschlagen (OpenRouter + lokal)."""
    code = "YOURAI-210"

    def __init__(self, tiers_tried: Optional[list] = None, **kwargs):
        tiers = tiers_tried or ["unknown"]
        super().__init__(
            f"All {len(tiers)} LLM tiers failed: {', '.join(tiers)}",
            model="all",
            tiers=tiers,
            **kwargs
        )


# ==========================================
# 3xx - MEMORY / EMBEDDING ERRORS
# ==========================================

class YourAIMemoryError(YourAIError):
    """Allgemeiner Memory-Fehler."""
    code = "YOURAI-300"

    def __init__(self, message: str, **kwargs):
        module = kwargs.pop("module", "hippocampus")
        super().__init__(message, module=module, **kwargs)


class YourAIEmbedError(YourAIMemoryError):
    """Embedding-Berechnung fehlgeschlagen."""
    code = "YOURAI-301"
    
    def __init__(self, message: str = "Embedding failed", model: Optional[str] = None, 
                 attempt: Optional[int] = None, max_attempts: Optional[int] = None, **kwargs):
        super().__init__(
            message, model=model, attempt=attempt, max_attempts=max_attempts, **kwargs
        )


class YourAIEmbedDisconnectError(YourAIEmbedError):
    """Server hat die Embedding-Verbindung getrennt."""
    code = "YOURAI-302"
    
    def __init__(self, message: str = "Embedding server disconnected", 
                 server_url: Optional[str] = None, 
                 reconnect_attempts: Optional[int] = None, **kwargs):
        super().__init__(
            message, server_url=server_url, 
            reconnect_attempts=reconnect_attempts, **kwargs
        )


class YourAIMemoryServerError(YourAIMemoryError):
    """Memory-Server nicht erreichbar."""
    code = "YOURAI-303"
    
    def __init__(self, url: Optional[str] = None, status: Optional[int] = None, **kwargs):
        super().__init__(
            f"Memory server error (status={status})",
            url=url, status=status, **kwargs
        )


# ==========================================
# 4xx - SESSION / AUTH ERRORS
# ==========================================

class YourAISessionError(YourAIError):
    """Allgemeiner Session-Fehler."""
    code = "YOURAI-400"

    def __init__(self, message: str, **kwargs):
        module = kwargs.pop("module", "session")
        super().__init__(message, module=module, **kwargs)


class YourAISessionCorruptError(YourAISessionError):
    """Session-Datei ist korrupt."""
    code = "YOURAI-401"
    
    def __init__(self, filepath: Optional[str] = None, **kwargs):
        super().__init__(
            f"Session file corrupted",
            filepath=filepath,
            hint="Delete user_sessions.json to reset",
            **kwargs
        )


class YourAIUserNotFoundError(YourAISessionError):
    """User nicht gefunden."""
    code = "YOURAI-402"

    def __init__(self, user_key: str, **kwargs):
        super().__init__(f"User not found: {user_key}", user_key=user_key, **kwargs)


class YourAIInvalidUserError(YourAISessionError):
    """User-Key ungültig oder existiert nicht in der Config."""
    code = "YOURAI-403"

    def __init__(self, user_key: str, reason: Optional[str] = None, **kwargs):
        msg = f"Invalid user key: {user_key}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg, user_key=user_key, **kwargs)


class YourAINoPrivilegeError(YourAISessionError):
    """User hat keine Berechtigung für eine Admin-Only Aktion."""
    code = "YOURAI-444"

    def __init__(self, user_id: str, action: str, **kwargs):
        super().__init__(
            f"No privilege: '{user_id}' cannot {action}",
            user_id=user_id,
            action=action,
            **kwargs
        )


class YourAITokenExpiredError(YourAISessionError):
    """Session oder API-Token ist abgelaufen."""
    code = "YOURAI-405"

    def __init__(self, user_id: str, **kwargs):
        super().__init__(
            f"Token expired for user: '{user_id}'",
            user_id=user_id,
            hint="User needs to re-authenticate",
            **kwargs
        )


# ==========================================
# 5xx - TOOL / EXTERNAL ERRORS
# ==========================================

class YourAIToolError(YourAIError):
    """Allgemeiner Tool-Fehler."""
    code = "YOURAI-500"

    def __init__(self, message: str, tool_name: Optional[str] = None, **kwargs):
        module = kwargs.pop("module", "tools")
        super().__init__(message, module=module, tool_name=tool_name, **kwargs)


class YourAIToolNotFoundError(YourAIToolError):
    """Tool nicht gefunden."""
    code = "YOURAI-501"


class YourAIToolExecutionError(YourAIToolError):
    """Tool-Ausführung fehlgeschlagen."""
    code = "YOURAI-502"


class YourAIToolTimeoutError(YourAIToolError):
    """Tool-Ausführung hat zu lange gedauert."""
    code = "YOURAI-503"

    def __init__(self, tool_name: str, timeout_seconds: float, **kwargs):
        super().__init__(
            f"Tool '{tool_name}' timed out after {timeout_seconds}s",
            tool_name=tool_name,
            timeout=timeout_seconds,
            **kwargs
        )


class YourAIVisionError(YourAIError):
    """Vision/Screenshot-Fehler."""
    code = "YOURAI-510"

    def __init__(self, message: str, **kwargs):
        module = kwargs.pop("module", "vision")
        super().__init__(message, module=module, **kwargs)


# ==========================================
# 6xx - PIPELINE / FLOW ERRORS
# ==========================================

class YourAIPipelineError(YourAIError):
    """Fehler in der LangGraph-Pipeline."""
    code = "YOURAI-600"

    def __init__(self, message: str, node: Optional[str] = None, **kwargs):
        module = kwargs.pop("module", "pipeline")
        super().__init__(message, module=module, node=node, **kwargs)


class YourAIGuardError(YourAIPipelineError):
    """Autonomy Guard Fehler."""
    code = "YOURAI-601"
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, node="autonomy_guard", **kwargs)


class YourAISafetyError(YourAIPipelineError):
    """Granite Safety Filter Fehler."""
    code = "YOURAI-602"
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, node="granite", **kwargs)


# ==========================================
# 7xx - WEBSITE / WEB ERRORS
# ==========================================

class YourAIWebError(YourAIError):
    """Allgemeiner Website/Web-Fehler."""
    code = "YOURAI-700"

    def __init__(self, message: str, url: Optional[str] = None, **kwargs):
        module = kwargs.pop("module", "web")
        super().__init__(message, module=module, url=url, **kwargs)


class YourAIWebFetchError(YourAIWebError):
    """Website konnte nicht abgerufen werden (z.B. 404, 500)."""
    code = "YOURAI-701"

    def __init__(self, url: str, status_code: Optional[int] = None, **kwargs):
        super().__init__(
            f"Failed to fetch URL: {url} (status={status_code})",
            url=url,
            status_code=status_code,
            **kwargs
        )


class YourAIWebParseError(YourAIWebError):
    """Fehler beim Parsen von HTML oder Extrahieren von Content."""
    code = "YOURAI-702"


class YourAIWebBlockError(YourAIWebError):
    """Zugriff verweigert (Captcha, Cloudflare, 403 Forbidden)."""
    code = "YOURAI-703"
    
    def __init__(self, url: str, block_reason: str = "Cloudflare/Captcha", **kwargs):
        super().__init__(
            f"Access blocked for URL: {url} ({block_reason})",
            url=url,
            block_reason=block_reason,
            hint="Might need proxy, stealth mode or user agent rotation",
            **kwargs
        )


class YourAIWebValidationError(YourAIWebError):
    """Website-Content Validation fehlgeschlagen (HTML/CSS/JS)."""
    code = "YOURAI-704"

    def __init__(self, file_type: str, errors: list, **kwargs):
        errors_str = "; ".join(errors[:5])
        super().__init__(
            f"{file_type} validation failed: {errors_str}",
            file_type=file_type,
            error_count=len(errors),
            errors=errors_str,
            **kwargs
        )


class YourAIWebDeployError(YourAIWebError):
    """Website-Deploy an den Webserver fehlgeschlagen."""
    code = "YOURAI-705"

    def __init__(self, status_code: Optional[int] = None, 
                 deploy_url: Optional[str] = None, **kwargs):
        msg = f"Deploy failed"
        if status_code:
            msg += f" (HTTP {status_code})"
        super().__init__(
            msg,
            url=deploy_url,
            status_code=status_code,
            **kwargs
        )


class YourAIWebTruncatedError(YourAIWebError):
    """LLM Code-Expert hat Output abgeschnitten (zu wenig Output für Input)."""
    code = "YOURAI-706"

    def __init__(self, file_type: str, input_chars: int, output_chars: int, **kwargs):
        ratio = output_chars / max(input_chars, 1)
        super().__init__(
            f"Code expert truncated {file_type}: {input_chars} chars in → {output_chars} chars out ({ratio:.0%})",
            file_type=file_type,
            input_chars=input_chars,
            output_chars=output_chars,
            ratio=f"{ratio:.0%}",
            hint="Model ran out of tokens. Try smaller changes or a model with larger output window.",
            **kwargs
        )


class YourAIWebSaveError(YourAIWebError):
    """Lokales Speichern einer Website-Datei fehlgeschlagen."""
    code = "YOURAI-707"

    def __init__(self, filepath: str, file_type: str = "unknown", **kwargs):
        super().__init__(
            f"Failed to save {file_type} to local path: {filepath}",
            url=filepath,
            file_type=file_type,
            **kwargs
        )


# ==========================================
# 8xx - SYSTEM / OS ERRORS
# ==========================================

class YourAISystemError(YourAIError):
    """Allgemeiner System- oder Betriebssystem-Fehler."""
    code = "YOURAI-800"

    def __init__(self, message: str, **kwargs):
        module = kwargs.pop("module", "system")
        super().__init__(message, module=module, **kwargs)


class YourAIProcessKillError(YourAISystemError):
    """Ein Hintergrundprozess wurde unerwartet beendet (z.B. OOM)."""
    code = "YOURAI-801"
    
    def __init__(self, process_name: str, exit_code: Optional[int] = None, **kwargs):
        super().__init__(
            f"Process killed: {process_name} (exit={exit_code})",
            process_name=process_name,
            exit_code=exit_code,
            **kwargs
        )


class YourAIDiskSpaceError(YourAISystemError):
    """Nicht genug Festplattenspeicher."""
    code = "YOURAI-802"

    def __init__(self, path: str, required_mb: Optional[float] = None, **kwargs):
        msg = f"Not enough disk space for path: '{path}'"
        if required_mb:
            msg += f" (required: {required_mb}MB)"
        super().__init__(
            msg,
            path=path,
            required_mb=required_mb,
            **kwargs
        )


class YourAIMaintenanceError(YourAISystemError):
    """Server ist im Wartungsmodus — Anfrage abgelehnt."""
    code = "YOURAI-803"

    def __init__(self, user_id: Optional[str] = None, **kwargs):
        msg = "Server is in maintenance mode"
        if user_id:
            msg += f" (blocked user: {user_id})"
        super().__init__(msg, user_id=user_id, hint="Try again later", **kwargs)


class YourAIUploadError(YourAISystemError):
    """Datei-Upload fehlgeschlagen."""
    code = "YOURAI-804"

    def __init__(self, reason: str, filename: Optional[str] = None, **kwargs):
        msg = f"Upload failed: {reason}"
        if filename:
            msg += f" (file: {filename})"
        super().__init__(msg, filename=filename, **kwargs)


# ==========================================
# 9xx - UNEXPECTED
# ==========================================

class YourAIUnexpectedError(YourAIError):
    """Unerwarteter Fehler (Catch-all)."""
    code = "YOURAI-999"
    
    def __init__(self, cause: Exception, module: str = "unknown", **kwargs):
        super().__init__(
            f"Unexpected {type(cause).__name__}",
            module=module,
            cause=cause,
            **kwargs
        )