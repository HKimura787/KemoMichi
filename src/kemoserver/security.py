"""Who may connect, and which folders they may see (plan §7.2)."""

from __future__ import annotations

import base64
import hmac
import ipaddress
import os
import string
from dataclasses import dataclass, field
from pathlib import Path

from starlette.types import ASGIApp, Receive, Scope, Send


def is_loopback(host: str) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    password: str = ""
    roots: list[Path] = field(default_factory=list)
    open_path: Path | None = None

    @property
    def server_mode(self) -> bool:
        return not is_loopback(self.host)

    def check(self) -> None:
        """Refuse unsafe combinations before the server starts."""
        if self.server_mode and not self.password:
            raise SystemExit("Refusing to listen on a network address without a password. "
                             "Pass --password (or set KEMOMICHI_PASSWORD), or use --host 127.0.0.1.")
        if self.server_mode and not self.roots:
            raise SystemExit("In server mode, pass --root for each folder people may open.")

    def allowed(self, path: Path) -> bool:
        if not self.roots:
            return True
        resolved = path.resolve()
        return any(resolved == r or r in resolved.parents for r in self.roots)

    def start_folders(self) -> list[dict]:
        if self.roots:
            return [{"name": str(r), "path": str(r)} for r in self.roots]
        places = [{"name": "~", "path": str(Path.home())}]
        if os.name == "nt":
            for letter in string.ascii_uppercase:
                drive = Path(f"{letter}:\\")
                if drive.exists():
                    places.append({"name": f"{letter}:", "path": str(drive)})
        else:
            for mount in ("/Volumes", "/media", "/mnt"):
                if Path(mount).is_dir():
                    places.append({"name": mount, "path": mount})
            places.append({"name": "/", "path": "/"})
        return places


class BasicAuthMiddleware:
    """One shared password, HTTP Basic, for HTTP and WebSocket alike. Loopback peers are exempt."""

    def __init__(self, app: ASGIApp, password: str):
        self.app = app
        self.password = password.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or not self.password:
            await self.app(scope, receive, send)
            return
        client = scope.get("client") or ("", 0)
        if is_loopback(client[0]):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"")
        if auth.startswith(b"Basic "):
            try:
                _user, _, given = base64.b64decode(auth[6:]).partition(b":")
            except ValueError:
                given = b""
            if hmac.compare_digest(given, self.password):
                await self.app(scope, receive, send)
                return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4401})
            return
        await send({"type": "http.response.start", "status": 401, "headers": [
            (b"www-authenticate", b'Basic realm="KemoMichi"'), (b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"Password required"})
