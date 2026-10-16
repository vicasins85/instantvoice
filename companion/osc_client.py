"""Talks to the VoiceCast plugin over OSC (UDP localhost)."""
from __future__ import annotations

import json
import socket
import threading

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient


class PluginLink:
    def __init__(self, host: str = "127.0.0.1", port: int = 9001, reply_port: int = 9002):
        self.client = SimpleUDPClient(host, port)
        self.host = host
        self.reply_port = reply_port

    def preset(self, params: dict):
        self.client.send_message("/vc/preset", json.dumps(params))

    def nudge(self, param: str, delta: float):
        self.client.send_message("/vc/nudge", [param, float(delta)])

    def bypass(self, on: bool = True):
        self.client.send_message("/vc/bypass", 1 if on else 0)

    def mute(self, on: bool):
        self.client.send_message("/vc/mute", 1 if on else 0)

    def ping(self, timeout: float = 1.0) -> bool:
        """True if a plugin instance answered /vc/pong."""
        got = threading.Event()
        dispatcher = Dispatcher()
        dispatcher.map("/vc/pong", lambda *_: got.set())
        try:
            server = BlockingOSCUDPServer((self.host, self.reply_port), dispatcher)
        except OSError:
            return False
        server.timeout = timeout
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        self.client.send_message("/vc/ping", [])
        thread.join(timeout + 0.2)
        server.server_close()
        return got.is_set()


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True
