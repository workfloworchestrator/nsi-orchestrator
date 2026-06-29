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

"""Client for the nsi-aggregator-proxy REST API.

The proxy fronts the NSI Aggregator/Safnari connection lifecycle. The orchestrator reserves,
provisions, releases, terminates and queries multi domain point-to-point connections through it.

Reserve/provision/release/terminate are asynchronous: the proxy answers ``202 Accepted`` and later
POSTs the result (the full reservation, with a ``RESERVED`` / ``ACTIVATED`` / ``FAILED`` /
``TERMINATED`` status) to the ``callbackURL`` the orchestrator supplies. The orchestrator drives
these from a ``callback_step``; this client only fires the request and returns.

Authentication mirrors the dds-proxy, selected by ``AGGREGATOR_PROXY_MTLS_ENABLED`` (see
:mod:`services.edge_auth`).
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from services.edge_auth import client_kwargs
from settings import settings

logger = structlog.get_logger(__name__)


class AggregatorProxyError(RuntimeError):
    """Raised when the aggregator-proxy cannot be reached or returns an error response.

    In local development a connection error almost always means the port-forward to the
    aggregator-proxy is down.
    """


class AggregatorP2ps(BaseModel):
    """The point-to-point parameters of a reservation's criteria."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    capacity: int
    source_stp: str = Field(alias="sourceSTP")
    dest_stp: str = Field(alias="destSTP")


class AggregatorCriteria(BaseModel):
    """A reservation's criteria; only the p2ps parameters are modelled."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    p2ps: AggregatorP2ps


class AggregatorReservation(BaseModel):
    """A reservation as returned by ``GET /reservations/{connectionId}`` and in callbacks."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    connection_id: str
    description: str
    status: str
    global_reservation_id: str | None = None
    last_error: str | None = None
    criteria: AggregatorCriteria | None = None


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.aggregator_proxy_base_url,
        timeout=settings.aggregator_proxy_timeout,
        **client_kwargs(
            mtls_enabled=settings.aggregator_proxy_mtls_enabled,
            client_cert=settings.aggregator_proxy_client_cert,
            client_key=settings.aggregator_proxy_client_key,
            ca_bundle=settings.aggregator_proxy_ca_bundle,
            auth_method=settings.aggregator_proxy_auth_method,
            client_dn=settings.aggregator_proxy_client_dn,
        ),
    )


def _request(method: str, path: str, *, json: dict[str, Any] | None = None) -> httpx.Response:
    """Send a request to the aggregator-proxy and return the response, raising on error."""
    with _client() as client:
        try:
            response = client.request(method, path, json=json)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "aggregator-proxy request failed",
                method=method,
                path=path,
                base_url=settings.aggregator_proxy_base_url,
                error=str(exc),
            )
            # Suppress the httpx/httpcore chain: the cause is already folded into the message.
            raise AggregatorProxyError(
                f"{method} {path} on aggregator-proxy at {settings.aggregator_proxy_base_url} failed: {exc}"
            ) from None
        return response


def reserve(
    *,
    global_reservation_id: str,
    description: str,
    capacity: int,
    source_stp: str,
    dest_stp: str,
    callback_url: str,
) -> str:
    """Reserve a connection and return the aggregator-assigned ``connectionId``.

    The ``source_stp`` / ``dest_stp`` strings must already carry their VLAN (``...?vlan=<n>``).
    The final RESERVED/FAILED status arrives later via the callback to ``callback_url``.
    """
    body = {
        "globalReservationId": global_reservation_id,
        "description": description,
        "criteria": {"p2ps": {"capacity": capacity, "sourceSTP": source_stp, "destSTP": dest_stp}},
        "requesterNSA": settings.requester_nsa,
        "providerNSA": settings.provider_nsa,
        "callbackURL": callback_url,
    }
    response = _request("POST", "/reservations", json=body)
    # 202 Accepted carries the new connection at "instance": "/reservations/{connectionId}".
    instance = response.json()["instance"]
    return str(instance).rsplit("/", 1)[-1]


def provision(connection_id: str, callback_url: str) -> None:
    """Provision a RESERVED connection; result (ACTIVATED/FAILED) arrives via the callback."""
    _request("POST", f"/reservations/{connection_id}/provision", json={"callbackURL": callback_url})


def release(connection_id: str, callback_url: str) -> None:
    """Release an ACTIVATED connection; result (RESERVED/FAILED) arrives via the callback."""
    _request("POST", f"/reservations/{connection_id}/release", json={"callbackURL": callback_url})


def terminate(connection_id: str, callback_url: str) -> None:
    """Terminate a RESERVED or FAILED connection; result (TERMINATED) arrives via the callback."""
    _request("DELETE", f"/reservations/{connection_id}", json={"callbackURL": callback_url})


def get_reservation(connection_id: str) -> AggregatorReservation:
    """Return the current reservation detail for ``connection_id``."""
    response = _request("GET", f"/reservations/{connection_id}")
    return AggregatorReservation.model_validate(response.json())


def list_reservations() -> list[AggregatorReservation]:
    """Return all reservations the aggregator knows about."""
    response = _request("GET", "/reservations")
    return [AggregatorReservation.model_validate(item) for item in response.json()["reservations"]]
