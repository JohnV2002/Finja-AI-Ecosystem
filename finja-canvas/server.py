"""
======================================================================
         Finja Canvas – Server
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-canvas / server
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.2.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
 Description:
----------------------------------------------------------------------
  Simple HTTP Server to serve the canvas frontend without caching.

 Changes (1.2.0):
  Reports to the Analytics Collector (lifecycle, CPU, RAM, errors) when
  ANALYTICS_ENABLED is set, and has the owner-only /diagnostics/probe route
  (CANVAS_PROBE_TOKEN; FINJA-516) for Flare's onboarding test.

 Changes (1.1.0):
  Serves the canvas while Recraft Vector motifs are painted.
======================================================================
"""

import http.server
import logging
import os
import secrets
import urllib.parse
from pathlib import Path

from analytics_sender import AnalyticsConfig, AnalyticsSender
from canvas_stats import average_motif_pixels
from core.exceptions import AnalyticsDeliveryError, CanvasDiagnosticsProbeError

LOGGER = logging.getLogger("finja_canvas")
PROJECT_ROOT = Path(__file__).resolve().parent


def _report_analytics_problem(problem):
    error = AnalyticsDeliveryError(str(problem.get("message") or "analytics delivery failed"),
                                   reason=problem.get("reason"), retry=problem.get("retry"))
    LOGGER.warning("%s %s context=%s", error.code, error, error.context)


_analytics_config, _analytics_problem = AnalyticsConfig.from_environment(PROJECT_ROOT, version="1.2.0")
analytics = AnalyticsSender(_analytics_config, root=PROJECT_ROOT, on_failure=_report_analytics_problem)

PORT = 8000


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    """Prevents the browser from caching color.csv, so the grid updates live."""

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def do_GET(self):
        if self.path.startswith("/diagnostics/probe"):
            self._probe()
            return
        super().do_GET()

    def _probe(self):
        """Owner-only: runs the canvas statistics with no finished motif (the onboarding pilot's real bug)."""
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        expected = os.getenv("CANVAS_PROBE_TOKEN", "")
        supplied = (query.get("token") or [""])[0]
        if not expected or not secrets.compare_digest(supplied, expected):
            self.send_error(404, "Not found")
            return
        try:
            try:
                value = average_motif_pixels([])
            except ZeroDivisionError as exc:
                raise CanvasDiagnosticsProbeError("Diagnostics probe hit a real bug",
                                                  probe="average_motif_pixels") from exc
        except CanvasDiagnosticsProbeError as error:
            LOGGER.error("%s %s context=%s", error.code, error, error.context)
            analytics.record_exception(error)
            self._send_json(500, '{"error": {"code": "%s"}}' % error.code)
            return
        self._send_json(200, '{"probe": "average_motif_pixels", "value": %s}' % value)

    def _send_json(self, status, text):
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def address_string(self):
        # No reverse-DNS-lookup per request - this can hang depending on the network.
        # We simply log the raw IP.
        return self.client_address[0]


if __name__ == "__main__":
    # ThreadingHTTPServer instead of simple TCPServer: can serve multiple requests 
    # simultaneously (important because index.html polls every second).
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if _analytics_problem:
        _report_analytics_problem({"message": "analytics stays off", "reason": _analytics_problem})
    analytics.start()  # lifecycle, CPU and RAM come from the long-running server process
    try:
        with http.server.ThreadingHTTPServer(("", PORT), NoCacheHandler) as httpd:
            print(f"Server is running on http://localhost:{PORT} :3 (Ctrl+C to stop)")
            httpd.serve_forever()
    finally:
        analytics.stop()
