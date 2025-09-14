#!/usr/bin/env python3

"""
======================================================================
                Finja's Brain & Knowledge Core - Spotify
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: JohnV2002 (J. Apps / Sodakiller1)
  Version: 1.0.0 (Spotify Modul)

----------------------------------------------------------------------

  Copyright (c) 2025 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import os, urllib.parse, http.server, socketserver, threading, webbrowser, requests, json
PORT=53682; REDIRECT=f"http://localhost:{PORT}/callback"
SCOPES="user-read-currently-playing user-read-playback-state"
cid=os.getenv("SPOTIFY_CLIENT_ID","").strip(); cs=os.getenv("SPOTIFY_CLIENT_SECRET","").strip()
def auth_url():
    q=dict(client_id=cid,response_type="code",redirect_uri=REDIRECT,scope=SCOPES,state="soda",show_dialog="true")
    return "https://accounts.spotify.com/authorize?"+urllib.parse.urlencode(q)
def exchange(code):
    r=requests.post("https://accounts.spotify.com/api/token",data={"grant_type":"authorization_code","code":code,"redirect_uri":REDIRECT,"client_id":cid,"client_secret":cs},timeout=15); r.raise_for_status(); return r.json()
class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/callback"):
            qs=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); code=qs.get("code",[None])[0]
            if not code: self.send_response(400); self.end_headers(); self.wfile.write(b"missing code"); return
            try:
                js=exchange(code); rt=js.get("refresh_token","")
                self.send_response(200); self.end_headers(); self.wfile.write(("REFRESH_TOKEN:\n"+rt).encode())
                print("\n[REFRESH_TOKEN]\n",rt,"\n")
            except Exception as e:
                self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())
            threading.Thread(target=self.server.shutdown,daemon=True).start()
        else: self.send_response(404); self.end_headers(); self.wfile.write(b"Not Found")
print("Open and approve:", auth_url()); 
try: webbrowser.open(auth_url())
except: pass
with socketserver.TCPServer(("127.0.0.1",PORT),H) as s:
    print("Waiting on",REDIRECT,"..."); s.serve_forever()
