# Copyright 2026 SURF.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pin the orchestrator-core websocket close races we depend on being handled.

A client that drops an ``/api/ws/events`` connection used to surface as a full
``Exception in ASGI application`` traceback. ``remove_ws`` is fixed in core 5.4.0
(workfloworchestrator/orchestrator-core#1904); ``disconnect`` is fixed by
workfloworchestrator/orchestrator-core#1928 and is marked xfail until that ships.

These test core, not this repo, which is deliberate: they are the condition under which we chose not
to carry a log filter for this (nsi-orchestrator#68). ``xfail(strict=True)`` fails once the case
starts passing, so the upgrade that fixes it forces this file to be updated rather than leaving a
stale assumption in place.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocket
from orchestrator.core.websocket.managers.memory_websocket_manager import MemoryWebsocketManager
from starlette.websockets import WebSocketState

_ALREADY_CLOSED = RuntimeError('Cannot call "send" once a close message has been sent.')


def _dead_ws() -> AsyncMock:
    """A socket whose peer vanished mid-send: starlette closed the app side, the client side lags."""
    ws = AsyncMock(spec=WebSocket)
    ws.client_state = WebSocketState.CONNECTED
    ws.application_state = WebSocketState.DISCONNECTED
    ws.close.side_effect = _ALREADY_CLOSED
    ws.send_text.side_effect = _ALREADY_CLOSED
    return ws


def test_remove_ws_tolerates_already_closed_peer() -> None:
    """Fixed in core 5.4.0; the registry must be cleaned up either way."""
    manager = MemoryWebsocketManager()
    ws = _dead_ws()
    manager.connections_by_pid = {"ch": [ws]}

    asyncio.run(manager.remove_ws(ws, "ch"))

    assert manager.connections_by_pid == {}


@pytest.mark.xfail(strict=True, reason="needs orchestrator-core#1928; drop this mark when it ships")
def test_disconnect_tolerates_already_closed_peer() -> None:
    """The endpoints call disconnect() directly to reject a client, bypassing remove_ws."""
    asyncio.run(MemoryWebsocketManager().disconnect(_dead_ws()))
