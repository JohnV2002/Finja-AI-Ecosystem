"""
Debug Server Entrypoint
=======================
Starts the dashboard server through uvicorn for local debugging.

Main Responsibilities:
- Load project paths.
- Import the dashboard FastAPI app.
- Run uvicorn on the dashboard port.

Side Effects:
- Starts a long-running HTTP server.
- Writes startup and error logs.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

import uvicorn
import traceback

try:
    from dashboard_server import app
    print("🚀 Attempting to start uvicorn on port 8051...")
    uvicorn.run(app, host="0.0.0.0", port=8051)
except Exception as e:
    from exceptions import YourAISystemError
    from display import log_exception
    err = YourAISystemError(cause=e, module="debug_server")
    log_exception("SYSTEM", err)
    sys.exit(1)
