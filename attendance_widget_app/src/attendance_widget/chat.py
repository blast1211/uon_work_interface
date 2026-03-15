from __future__ import annotations

import json
import queue
import socket
import struct
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QThread, Signal


@dataclass(slots=True)
class ChatConfig:
    nickname: str
    room: str
    multicast_group: str
    port: int
    system_messages: bool
    avatar_name: str = ""


class LanChatClient(QThread):
    message_received = Signal(dict)
    status_changed = Signal(str)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, config: ChatConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.client_id = str(uuid.uuid4())
        self._outgoing: queue.Queue[dict[str, Any]] = queue.Queue()
        self._running = threading.Event()
        self._running.set()
        self._sock: socket.socket | None = None

    def run(self) -> None:
        try:
            self._sock = self._create_socket()
        except OSError as exc:
            self.error_occurred.emit(f"LAN chat socket error: {exc}")
            self.connection_changed.emit(False)
            return

        self.connection_changed.emit(True)
        self.status_changed.emit(f"채팅방 접속: {self.config.room} / ID: {self.config.nickname}")
        self._queue_system_message("join")
        self._queue_system_message("presence_request")

        while self._running.is_set():
            self._flush_outgoing()
            try:
                payload, address = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break

            message = self._decode_message(payload)
            if message is None:
                continue
            if message.get("room") != self.config.room:
                continue
            if message.get("client_id") == self.client_id:
                continue

            if message.get("type") == "system" and message.get("event") == "presence_request":
                self._queue_system_message("presence", target_client_id=str(message.get("client_id", "")))
                continue

            message["source_address"] = address[0]
            self.message_received.emit(message)

        self._flush_outgoing()
        self._close_socket()
        self.connection_changed.emit(False)

    def stop(self) -> None:
        if self._running.is_set():
            self._queue_system_message("leave")
        self._running.clear()
        self.wait(1500)
        self._close_socket()

    def send_chat(self, text: str) -> None:
        clean_text = text.strip()
        if not clean_text:
            return
        self._outgoing.put(
            {
                "type": "chat",
                "room": self.config.room,
                "sender": self.config.nickname,
                "client_id": self.client_id,
                "timestamp": time.time(),
                "avatar_name": self.config.avatar_name,
                "text": clean_text,
            }
        )

    def _queue_system_message(self, event: str, target_client_id: str = "") -> None:
        self._outgoing.put(
            {
                "type": "system",
                "event": event,
                "room": self.config.room,
                "sender": self.config.nickname,
                "client_id": self.client_id,
                "target_client_id": target_client_id,
                "avatar_name": self.config.avatar_name,
                "timestamp": time.time(),
                "text": "",
            }
        )

    def _flush_outgoing(self) -> None:
        if self._sock is None:
            return
        while True:
            try:
                message = self._outgoing.get_nowait()
            except queue.Empty:
                return
            try:
                payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
                self._sock.sendto(payload, (self.config.multicast_group, self.config.port))
            except OSError as exc:
                self.error_occurred.emit(f"LAN chat send error: {exc}")
                return

    def _create_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", self.config.port))
        except OSError:
            sock.bind((self.config.multicast_group, self.config.port))
        membership = struct.pack("4sL", socket.inet_aton(self.config.multicast_group), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        sock.settimeout(0.2)
        return sock

    def _close_socket(self) -> None:
        if self._sock is None:
            return
        try:
            self._sock.close()
        except OSError:
            pass
        self._sock = None

    @staticmethod
    def _decode_message(payload: bytes) -> dict[str, Any] | None:
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(decoded, dict):
            return None
        return decoded
