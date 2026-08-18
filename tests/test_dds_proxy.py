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

"""Tests for the nsi-dds-proxy REST client."""

from __future__ import annotations

from collections.abc import Callable

import httpx2
import pytest

from services import dds_proxy
from services.dds_proxy import DdsProxyError, DdsTopology, fetch_topologies

TOPOLOGIES_JSON = [
    {
        "id": "urn:a",
        "version": "v1",
        "name": "Topology A",
        "lifetime": {"start": "s", "end": "e"},
    },
    {
        "id": "urn:b",
        "version": "v1",
        "name": "Topology B",
        "lifetime": {"start": "s", "end": "e"},
    },
]


def test_client_kwargs_dev_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """With mTLS disabled the client sends the dds-proxy mTLS-path identity headers."""
    monkeypatch.setattr(dds_proxy.settings, "dds_proxy_mtls_enabled", False)
    monkeypatch.setattr(dds_proxy.settings, "dds_proxy_auth_method", "x509")
    monkeypatch.setattr(dds_proxy.settings, "dds_proxy_client_dn", "CN=test")

    assert dds_proxy._client_kwargs() == {"headers": {"X-Auth-Method": "x509", "X-Client-DN": "CN=test"}}


@pytest.mark.parametrize(
    ("cert", "key", "ca_bundle", "expected_cert", "expected_verify"),
    [
        pytest.param(
            "/c.pem",
            "/k.pem",
            "/ca.pem",
            ("/c.pem", "/k.pem"),
            "/ca.pem",
            id="cert+key+ca",
        ),
        pytest.param("/c.pem", None, None, "/c.pem", True, id="cert-only-system-ca"),
    ],
)
def test_client_kwargs_mtls(
    monkeypatch: pytest.MonkeyPatch,
    cert: str,
    key: str | None,
    ca_bundle: str | None,
    expected_cert: str | tuple[str, str],
    expected_verify: str | bool,
) -> None:
    """With mTLS enabled the client presents a certificate and verifies the server, no headers."""
    monkeypatch.setattr(dds_proxy.settings, "dds_proxy_mtls_enabled", True)
    monkeypatch.setattr(dds_proxy.settings, "dds_proxy_client_cert", cert)
    monkeypatch.setattr(dds_proxy.settings, "dds_proxy_client_key", key)
    monkeypatch.setattr(dds_proxy.settings, "dds_proxy_ca_bundle", ca_bundle)

    kwargs = dds_proxy._client_kwargs()

    assert kwargs["cert"] == expected_cert
    assert kwargs["verify"] == expected_verify
    assert "headers" not in kwargs


def _install_mock_transport(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx2.Request], httpx2.Response]
) -> None:
    """Replace httpx2.Client in the dds_proxy module with one backed by a mock transport."""
    real_client = httpx2.Client  # capture before patching, else the factory recurses

    def factory(**kwargs: object) -> httpx2.Client:
        base_url = kwargs.get("base_url", "")
        assert isinstance(base_url, str)
        return real_client(base_url=base_url, transport=httpx2.MockTransport(handler))

    monkeypatch.setattr(dds_proxy.httpx2, "Client", factory)


def test_fetch_topologies_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/topologies"
        return httpx2.Response(200, json=TOPOLOGIES_JSON)

    _install_mock_transport(monkeypatch, handler)

    result = fetch_topologies()

    assert all(isinstance(topology, DdsTopology) for topology in result)
    assert [(topology.id, topology.name) for topology in result] == [
        ("urn:a", "Topology A"),
        ("urn:b", "Topology B"),
    ]


def test_fetch_topologies_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(502, text="bad gateway")

    _install_mock_transport(monkeypatch, handler)

    with pytest.raises(DdsProxyError):
        fetch_topologies()
