"""
======================================================================
         Finja Canvas – Server
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-canvas / server
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0

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
======================================================================
"""

import http.server

PORT = 8000


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    """Prevents the browser from caching color.csv, so the grid updates live."""

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def address_string(self):
        # No reverse-DNS-lookup per request - this can hang depending on the network.
        # We simply log the raw IP.
        return self.client_address[0]


if __name__ == "__main__":
    # ThreadingHTTPServer instead of simple TCPServer: can serve multiple requests 
    # simultaneously (important because index.html polls every second).
    with http.server.ThreadingHTTPServer(("", PORT), NoCacheHandler) as httpd:
        print(f"Server is running on http://localhost:{PORT} :3 (Ctrl+C to stop)")
        httpd.serve_forever()
