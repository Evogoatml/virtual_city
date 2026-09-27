#!/usr/bin/env python3
"""
IPC Server - Unix Domain Socket
Kernel exposes a local socket that agents use to request execution.
"""

import os
import json
import socket
import threading
import time
from typing import Callable, Dict, Any


class IPCServer:
    """
    Unix domain socket server for kernel-agent IPC.
    Runs in its own thread. Agents connect, send JSON requests, receive JSON responses.
    """

    def __init__(self, socket_path: str = "/tmp/paradox_kernel.sock", handler: Callable = None):
        self.socket_path = socket_path
        self.handler = handler
        self.running = False
        self.server = None
        self._thread = None

    def start(self):
        self._cleanup()
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        self.server.listen(5)
        self.running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        while self.running:
            try:
                self.server.settimeout(1.0)
                conn, _ = self.server.accept()
                t = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except OSError:
                break

    def _handle_client(self, conn: socket.socket):
        try:
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            if not data:
                return
            request = json.loads(data.decode().strip())
            # Handle shutdown specially
            if request.get("action") == "shutdown":
                conn.sendall(json.dumps({"status": "ok", "shutting_down": True}).encode() + b"\n")
                conn.close()
                if hasattr(self, "on_shutdown") and self.on_shutdown:
                    self.on_shutdown()
                return
            response = self._process(request)
            conn.sendall(json.dumps(response).encode() + b"\n")
        except Exception as e:
            try:
                conn.sendall(json.dumps({"error": str(e)}).encode() + b"\n")
            except:
                pass
        finally:
            conn.close()

    def _process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if self.handler:
            return self.handler(request)
        return {"error": "No handler registered"}

    def stop(self):
        self.running = False
        if self.server:
            self.server.close()
        self._cleanup()

    def _cleanup(self):
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass


