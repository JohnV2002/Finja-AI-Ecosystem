import socket
import threading
import time
import re
import sys, os
from queue import Queue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError

from config import (
    TWITCH_TOKEN, TWITCH_BOT_NICK, TWITCH_CHANNEL,
    TWITCH_SERVER, TWITCH_PORT, TWITCH_SOCKET_TIMEOUT,
    TWITCH_RECV_BUFFER_SIZE
)

# Aliases für kürzeren Code
BOT_NICK = TWITCH_BOT_NICK
CHANNEL = TWITCH_CHANNEL

# Auf welche Trigger soll AltPersona/YourAI reagieren?
TRIGGER_PREFIXES = ["!say", "!ask", "!chat", "!yourai"]
TRIGGER_KEYWORDS = ["yourai", f"@{BOT_NICK}"] 

class TwitchBot(threading.Thread):
    def __init__(self):
        # FIX: daemon=True sorgt dafür, dass der Thread stirbt, wenn das Hauptprogramm endet!
        super().__init__(daemon=True) 
        self.server = TWITCH_SERVER
        self.port = TWITCH_PORT
        self.running = True
        self.connected = False
        self.sock = None
        self.message_queue = Queue() 

    def run(self):
        """Haupt-Loop (Hintergrund)"""
        log("TWITCH", f"🟣 Twitch Bot verbindet mit #{CHANNEL}...", Fore.MAGENTA)
        while self.running:
            try:
                self.connect()
                self.listen()
            except Exception as e:
                # Nur loggen, wenn wir eigentlich noch laufen wollen
                if self.running:
                    err = YourAIUnexpectedError(cause=e, module="twitch_run")
                    log_exception("TWITCH", err)
                    self.connected = False
                    self.sock = None
                    time.sleep(5)

    def connect(self):
        self.sock = socket.socket()
        self.sock.settimeout(TWITCH_SOCKET_TIMEOUT) # Timeout damit er nicht ewig hängt
        self.sock.connect((self.server, self.port))
        
        self.sock.send(f"PASS {TWITCH_TOKEN}\n".encode('utf-8'))
        self.sock.send(f"NICK {BOT_NICK}\n".encode('utf-8'))
        self.sock.send(f"JOIN #{CHANNEL}\n".encode('utf-8'))
        
        self.connected = True
        log("TWITCH", "✅ Twitch: Verbunden!", Fore.GREEN)

    def listen(self):
        while self.running and self.connected:
            try:
                if not self.sock: raise Exception("Socket lost")

                # Blockiert hier, bis Daten kommen oder Timeout
                try:
                    response = self.sock.recv(TWITCH_RECV_BUFFER_SIZE).decode('utf-8')
                except socket.timeout:
                    continue # Einfach weiter machen
                except OSError:
                    break # Socket geschlossen (beim Beenden)
                
                if not response: raise Exception("Empty response")

                if response.startswith('PING'):
                    if self.sock: self.sock.send("PONG\n".encode('utf-8'))
                    continue
                
                if "PRIVMSG" in response:
                    match = re.search(r":(\w+)!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :(.*)", response)
                    if match:
                        user = match.group(1)
                        message = match.group(2).strip()
                        
                        if user.lower() == BOT_NICK.lower(): continue

                        is_for_altpersona = False
                        clean_message = message
                        
                        for prefix in TRIGGER_PREFIXES:
                            if message.lower().startswith(prefix):
                                is_for_altpersona = True
                                clean_message = message[len(prefix):].strip()
                                break
                        
                        if not is_for_altpersona:
                            for keyword in TRIGGER_KEYWORDS:
                                if keyword in message.lower():
                                    is_for_altpersona = True
                                    break
                        
                        if is_for_altpersona and clean_message:
                            log("TWITCH", f"💬 Chat ({user}): {clean_message}", Fore.MAGENTA)
                            self.message_queue.put({"user": user, "text": clean_message, "source": "twitch"})
                        
            except Exception as e:
                if self.running:
                    err = YourAIUnexpectedError(cause=e, module="twitch_listen")
                    log_exception("TWITCH", err)
                self.connected = False 

    def send_chat(self, text):
        if self.sock and self.connected:
            try:
                self.sock.send(f"PRIVMSG #{CHANNEL} :{text}\n".encode('utf-8'))
                log("TWITCH", f"🤖 Bot -> Chat: {text}", Fore.CYAN)
            except Exception as e:
                err = YourAIUnexpectedError(cause=e, module="twitch_send")
                log_exception("TWITCH", err)
                self.connected = False

    def get_next_message(self):
        if not self.message_queue.empty():
            return self.message_queue.get()
        return None
    
    def stop(self):
        """Sauberes Beenden"""
        self.running = False
        self.connected = False
        if self.sock:
            try: self.sock.close()
            except: pass

# Globale Instanz
bot = TwitchBot()

if __name__ == "__main__":
    try:
        bot.start()
        while True:
            msg = bot.get_next_message()
            if msg: log("TWITCH", f"Test: {msg}", Fore.WHITE)
            time.sleep(0.1)
    except KeyboardInterrupt:
        log("TWITCH", "🛑 Beende Twitch Bot...", Fore.YELLOW)
        bot.stop()