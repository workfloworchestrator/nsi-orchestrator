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

"""Tests for the nsi-aggregator-proxy REST client."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from services import aggregator_proxy
from services.aggregator_proxy import AggregatorProxyError, get_reservation, list_reservations, reserve

RESERVATION_JSON = {
    "globalReservationId": "urn:uuid:1234",
    "connectionId": "conn-1",
    "description": "demo",
    "criteria": {
        "version": 1,
        "p2ps": {
            "capacity": 1000,
            "sourceSTP": "urn:ogf:network:a?vlan=100",
            "destSTP": "urn:ogf:network:b?vlan=200",
        },
    },
    "status": "RESERVED",
    "lastError": None,
}


def _install_mock_transport(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    """Replace httpx.Client in the aggregator_proxy module with one backed by a mock transport."""
    real_client = httpx.Client  # capture before patching, else the factory recurses

    def factory(**kwargs: object) -> httpx.Client:
        base_url = kwargs.get("base_url", "")
        assert isinstance(base_url, str)
        return real_client(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(aggregator_proxy.httpx, "Client", factory)


def test_reserve_sends_request_and_returns_connection_id(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/reservations"
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(202, json={"instance": "/reservations/conn-42"})

    _install_mock_transport(monkeypatch, handler)

    connection_id = reserve(
        global_reservation_id="urn:uuid:abc",
        description="demo",
        capacity=1000,
        source_stp="urn:ogf:network:a?vlan=100",
        dest_stp="urn:ogf:network:b?vlan=200",
        callback_url="http://orchestrator/api/processes/1/callback/tok",
    )

    assert connection_id == "conn-42"
    assert captured["globalReservationId"] == "urn:uuid:abc"
    assert captured["criteria"]["p2ps"] == {
        "capacity": 1000,
        "sourceSTP": "urn:ogf:network:a?vlan=100",
        "destSTP": "urn:ogf:network:b?vlan=200",
    }
    assert captured["callbackURL"] == "http://orchestrator/api/processes/1/callback/tok"
    assert "requesterNSA" in captured
    assert "providerNSA" in captured


def test_get_reservation_parses_stp_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/reservations/conn-1"
        return httpx.Response(200, json=RESERVATION_JSON)

    _install_mock_transport(monkeypatch, handler)

    reservation = get_reservation("conn-1")

    assert reservation.connection_id == "conn-1"
    assert reservation.status == "RESERVED"
    assert reservation.criteria is not None
    assert reservation.criteria.p2ps.source_stp == "urn:ogf:network:a?vlan=100"
    assert reservation.criteria.p2ps.dest_stp == "urn:ogf:network:b?vlan=200"


def test_list_reservations_parses_each_item(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/reservations"
        return httpx.Response(200, json={"reservations": [RESERVATION_JSON, RESERVATION_JSON]})

    _install_mock_transport(monkeypatch, handler)

    reservations = list_reservations()

    assert [r.connection_id for r in reservations] == ["conn-1", "conn-1"]
    assert all(
        r.criteria is not None and r.criteria.p2ps.source_stp == "urn:ogf:network:a?vlan=100" for r in reservations
    )


def test_request_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, text="must be RESERVED to provision")

    _install_mock_transport(monkeypatch, handler)

    with pytest.raises(AggregatorProxyError):
        get_reservation("conn-1")
