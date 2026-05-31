"""
YourAI AI - Twitch Client
========================
Twitch bot running in a daemon thread, interfacing with the Twitch IRC channel to process chat queries.

Main Responsibilities:
- Lazy initialize/reconnect socket connections to Twitch IRC.
- Parse PRIVMSG commands and check trigger prefixes/keywords.
- Queue incoming questions for processing by the central brain.
- Send response yaps back to the Twitch chat room.

Side Effects:
- Opens TCP sockets and maintains TCP communication with IRC servers.
"""

import os
import socket
import sys
import threading
import time
from queue import Queue
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError, YourAINetworkError
from helpers.text_parser import parse_twitch_privmsg

from config import (
    TWITCH_TOKEN, TWITCH_BOT_NICK, TWITCH_CHANNEL,
    TWITCH_SERVER, TWITCH_PORT, TWITCH_SOCKET_TIMEOUT,
    TWITCH_RECV_BUFFER_SIZE
)

# Aliases for shorter code
BOT_NICK = TWITCH_BOT_NICK
CHANNEL = TWITCH_CHANNEL

# Which triggers should AltPersona/YourAI react to?
TRIGGER_PREFIXES = ["!say", "!ask", "!chat", "!yourai"]
TRIGGER_KEYWORDS = ["yourai", f"@{BOT_NICK}"] 


class TwitchBot(threading.Thread):
    """
    Twitch Bot running as a daemon thread with its own connection loop.
    Communicates with the synchronous pipeline via a thread-safe Queue.
    """

    def __init__(self):
        """
        Initializes instance state and cached connection metadata.
        
        Returns:
            Any: The operation result, or None when no result is produced.
        """
        # FIX: daemon=True ensures that the thread dies when the main program ends!
        super().__init__(daemon=True) 
        self.server = TWITCH_SERVER
        self.port = TWITCH_PORT
        self.running = True
        self.connected = False
        self.sock = None
        self.message_queue = Queue() 

    def run(self):
        """Main loop (background)"""
        log("TWITCH", f" Twitch Bot connecting to #{CHANNEL}...", Fore.MAGENTA)
        while self.running:
            try:
                self.connect()
                self.listen()
            except Exception as e:
                # Only log if we actually still want to run
                if self.running:
                    err = YourAIUnexpectedError(cause=e, module="twitch_run")
                    log_exception("TWITCH", err)
                    self.connected = False
                    self.sock = None
                    time.sleep(5)

    def connect(self):
        """Connects to the Twitch IRC server and joins the channel."""
        self.sock = socket.socket()
        self.sock.settimeout(TWITCH_SOCKET_TIMEOUT) # Timeout to prevent hanging indefinitely
        self.sock.connect((self.server, self.port))
        
        self.sock.send(f"PASS {TWITCH_TOKEN}\n".encode('utf-8'))
        self.sock.send(f"NICK {BOT_NICK}\n".encode('utf-8'))
        self.sock.send(f"JOIN #{CHANNEL}\n".encode('utf-8'))
        
        self.connected = True
        log("TWITCH", "Done: Twitch: Connected!", Fore.GREEN)

    def _receive_line(self) -> Optional[str]:
        """Receives a response chunk from the IRC socket."""
        if not self.sock:
            raise YourAINetworkError(
                host=f"{self.server}:{self.port}",
                cause=ConnectionError("Socket lost"),
                module="twitch_client"
            )

        try:
            response = self.sock.recv(TWITCH_RECV_BUFFER_SIZE).decode('utf-8')
            if not response:
                raise YourAINetworkError(
                    host=f"{self.server}:{self.port}",
                    cause=ConnectionAbortedError("Empty response (connection closed by peer)"),
                    module="twitch_client"
                )
            return response
        except socket.timeout:
            return None
        except OSError as e:
            if self.running:
                err = YourAIUnexpectedError(cause=e, module="twitch_recv")
                log_exception("TWITCH", err)
            self.connected = False
            return None

    def _check_twitch_trigger(self, message: str) -> tuple[bool, str]:
        """Checks if a message starts with trigger prefixes or contains trigger keywords."""
        msg_lower = message.lower()
        for prefix in TRIGGER_PREFIXES:
            if msg_lower.startswith(prefix):
                return True, message[len(prefix):].strip()

        for keyword in TRIGGER_KEYWORDS:
            if keyword in msg_lower:
                return True, message

        return False, message

    def _handle_incoming_line(self, line: str):
        """Parses and checks triggers for a single IRC response string."""
        if line.startswith('PING'):
            if self.sock:
                self.sock.send("PONG\n".encode('utf-8'))
            return

        if "PRIVMSG" not in line:
            return

        parsed = parse_twitch_privmsg(line)
        if not parsed:
            return

        user, message = parsed
        if user.lower() == BOT_NICK.lower():
            return

        is_for_altpersona, clean_message = self._check_twitch_trigger(message)
        if is_for_altpersona and clean_message:
            log("TWITCH", f"Message Chat ({user}): {clean_message}", Fore.MAGENTA)
            self.message_queue.put({"user": user, "text": clean_message, "source": "twitch"})

    def listen(self):
        """Listening loop reading bytes from the IRC socket."""
        while self.running and self.connected:
            try:
                response = self._receive_line()
                if not response:
                    continue

                self._handle_incoming_line(response)

            except Exception as e:
                if self.running:
                    from exceptions import YourAIError
                    if isinstance(e, YourAIError):
                        log_exception("TWITCH", e)
                    else:
                        err = YourAIUnexpectedError(cause=e, module="twitch_listen")
                        log_exception("TWITCH", err)
                self.connected = False 

    def send_chat(self, text: str):
        """Sends a text message back to Twitch chat."""
        if self.sock and self.connected:
            try:
                self.sock.send(f"PRIVMSG #{CHANNEL} :{text}\n".encode('utf-8'))
                log("TWITCH", f"Bot Bot -> Chat: {text}", Fore.CYAN)
            except Exception as e:
                err = YourAIUnexpectedError(cause=e, module="twitch_send")
                log_exception("TWITCH", err)
                self.connected = False

    def get_next_message(self) -> Optional[dict]:
        """Fetches the next queued message if available."""
        if not self.message_queue.empty():
            return self.message_queue.get()
        return None
    
    def stop(self):
        """Clean shutdown"""
        self.running = False
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                err = YourAIUnexpectedError(cause=e, module="twitch_stop")
                log_exception("TWITCH", err)


# Global instance
bot = TwitchBot()

if __name__ == "__main__":
    try:
        bot.start()
        while True:
            msg = bot.get_next_message()
            if msg:
                log("TWITCH", f"Test: {msg}", Fore.WHITE)
            time.sleep(0.1)
    except KeyboardInterrupt:
        log("TWITCH", "Stopping Shutting down Twitch Bot...", Fore.YELLOW)
        bot.stop()
