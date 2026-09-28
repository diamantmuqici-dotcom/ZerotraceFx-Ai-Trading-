"""Remote control API (aiohttp) for the ZeroTrace Android companion app.

Security: every request must carry ``Authorization: Bearer <REMOTE_API_TOKEN>``.
The server refuses to start without a token of at least 16 characters.
Comparison is constant-time. Only expose on a trusted LAN/VPN.
"""
from __future__ import annotations

import asyncio
import hmac
import threading
from typing import Any, Callable, Optional

from aiohttp import web

from core.state import RuntimeState
from utils.logging_setup import get_logger

logger = get_logger("app")

MIN_TOKEN_LEN = 16


def build_app(
    state: RuntimeState,
    token: str,
    on_pause: Optional[Callable[[bool], None]] = None,
    on_close_all: Optional[Callable[[], dict]] = None,
    ai_summary: Optional[Callable[[], dict[str, Any]]] = None,
) -> web.Application:
    """Create the aiohttp application with auth middleware and routes."""
    if len(token or "") < MIN_TOKEN_LEN:
        raise ValueError(f"REMOTE_API_TOKEN must be at least {MIN_TOKEN_LEN} characters")
    expected = f"Bearer {token}".encode()

    @web.middleware
    async def auth(request: web.Request, handler):  # type: ignore[no-untyped-def]
        if request.method == "OPTIONS":
            return web.Response(status=204, headers=_cors())
        supplied = request.headers.get("Authorization", "").encode()
        if not hmac.compare_digest(supplied, expected):
            return web.json_response({"error": "unauthorized"}, status=401, headers=_cors())
        response = await handler(request)
        response.headers.update(_cors())
        return response

    async def status(_: web.Request) -> web.Response:
        return web.json_response(state.snapshot())

    async def ai(_: web.Request) -> web.Response:
        return web.json_response(ai_summary() if ai_summary else {})

    async def pause(request: web.Request) -> web.Response:
        body = await _json(request)
        paused = bool(body.get("paused", True))
        state.update(paused=paused)
        if on_pause:
            on_pause(paused)
        return web.json_response({"paused": paused})

    async def close_all(_: web.Request) -> web.Response:
        if on_close_all is None:
            return web.json_response({"error": "not available"}, status=501)
        result = await asyncio.get_running_loop().run_in_executor(None, on_close_all)
        return web.json_response(result)

    app = web.Application(middlewares=[auth])
    app.router.add_get("/api/status", status)
    app.router.add_get("/api/ai", ai)
    app.router.add_post("/api/pause", pause)
    app.router.add_post("/api/close_all", close_all)
    return app


def _cors() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }


async def _json(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def start_in_thread(app: web.Application, host: str, port: int) -> threading.Thread:
    """Serve the app on a daemon thread with its own event loop."""

    def _serve() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        loop.run_until_complete(web.TCPSite(runner, host, port).start())
        logger.info("Remote API listening on %s:%d", host, port)
        loop.run_forever()

    thread = threading.Thread(target=_serve, daemon=True, name="remote-api")
    thread.start()
    return thread
