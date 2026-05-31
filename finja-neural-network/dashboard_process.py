"""Brain subprocess management for the YourAI dashboard."""

import os
import subprocess
import sys
import time
from typing import Optional

from display import Fore, log, log_exception
from exceptions import YourAIUnexpectedError
from dashboard_runtime import load_runtime_overrides

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_active_model() -> str:
    """Return the active YourAI model name respecting runtime overrides."""
    try:
        import config as _cfg

        overrides = load_runtime_overrides()
        use_openrouter = overrides.get("USE_OPENROUTER", getattr(_cfg, "USE_OPENROUTER", False))
        if use_openrouter:
            return f"☁️ {getattr(_cfg, 'MODEL_YOURAI_OPENROUTER', 'unknown')}"
        return f"🏠 {getattr(_cfg, 'MODEL_YOURAI_LOCAL_PRIMARY', 'unknown')}"
    except Exception as e:
        err = YourAIUnexpectedError(cause=e, module="dashboard_active_model")
        log_exception("DASHBOARD", err)
        return "unknown"


class ProcessManager:
    """Manages brain.py as a child subprocess."""

    BRAIN_SCRIPT = os.path.join(BASE_DIR, "core", "brain.py")

    def __init__(self):
        """Initialize with no running process."""
        self._proc: Optional[subprocess.Popen] = None
        self._started_at: Optional[float] = None

    def start(self) -> bool:
        """Start brain.py as a child process. Returns False if already running."""
        if self.is_running():
            return False
        python_exe = sys.executable
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        kwargs = {"creationflags": creationflags} if sys.platform == "win32" else {"start_new_session": True}
        self._proc = subprocess.Popen(
            [python_exe, self.BRAIN_SCRIPT],
            cwd=BASE_DIR,
            **kwargs,
        )
        self._started_at = time.time()
        log("DASHBOARD", f"▶️ Brain started (PID {self._proc.pid})", Fore.GREEN)
        return True

    def stop(self) -> bool:
        """Stop the brain process and its children. Returns False if not running."""
        if not self.is_running():
            return False
        pid = self._proc.pid
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=10,
                )
            else:
                import signal

                os.killpg(os.getpgid(pid), signal.SIGTERM)
                self._proc.wait(timeout=5)
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="dashboard_brain_stop")
            log_exception("DASHBOARD", err)
            try:
                self._proc.kill()
            except Exception as kill_error:
                kill_err = YourAIUnexpectedError(cause=kill_error, module="dashboard_brain_kill")
                log_exception("DASHBOARD", kill_err)
        log("DASHBOARD", f"⏹️ Brain stopped (PID {pid} + children)", Fore.YELLOW)
        self._proc = None
        self._started_at = None
        return True

    def restart(self) -> bool:
        """Stop the brain process (if running) and start it again."""
        self.stop()
        return self.start()

    def is_running(self) -> bool:
        """Return True if the brain subprocess is alive."""
        return self._proc is not None and self._proc.poll() is None

    def status(self) -> dict:
        """Return a status snapshot: running flag, PID, uptime, and active model."""
        running = self.is_running()
        uptime = int(time.time() - self._started_at) if (running and self._started_at) else None
        return {
            "running": running,
            "pid": self._proc.pid if running else None,
            "uptime_s": uptime,
            "model": get_active_model(),
        }
