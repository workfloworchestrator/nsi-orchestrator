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

"""Client for the nsi-dds-proxy REST API.

The proxy exposes the NSI topology data discovered from the DDS. The orchestrator drives the
topology create and validate workflows off its ``GET /topologies`` endpoint.

Two authentication modes are supported, selected by ``DDS_PROXY_MTLS_ENABLED``:

* **mTLS (deployed):** present a client certificate + key and verify the server against a CA
  bundle. This is the real authentication used against the public dds-proxy endpoint.
* **dev shortcut (mTLS disabled):** send the identity headers the dds-proxy trusts at its edge,
  faking the mTLS auth path. Only for local development against a port-forwarded proxy.
"""

from __future__ import annotations

from typing import Any

import httpx2
import structlog
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from services.edge_auth import client_kwargs
from settings import settings

logger = structlog.get_logger(__name__)


class DdsProxyError(RuntimeError):
    """Raised when the dds-proxy cannot be reached or returns an error response.

    In local development a connection error almost always means the port-forward to the
    dds-proxy is down.
    """


class DdsTopology(BaseModel):
    """A topology as returned by the dds-proxy ``GET /topologies`` endpoint.

    Only the fields the orchestrator needs are modelled; ``version`` and ``lifetime`` are ignored.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str


class DdsSwitchingService(BaseModel):
    """A switching service from the dds-proxy ``GET /switching-services`` endpoint.

    The proxy serialises with camelCase aliases (``topologyId``); only the needed fields are kept.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    id: str
    topology_id: str


class DdsServiceTerminationPoint(BaseModel):
    """A service termination point from the dds-proxy ``GET /service-termination-points`` endpoint.

    The proxy serialises with camelCase aliases (``labelGroup``, ``switchingServiceId``).
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    id: str
    name: str
    # NML advertises capacity in bit/s and the proxy mirrors it verbatim; everything this
    # orchestrator stores is Mbit/s, so the name carries the unit and bit/s stops here.
    capacity_bits: int = Field(alias="capacity")
    label_group: str
    switching_service_id: str

    @property
    def capacity_mbits(self) -> int:
        return self.capacity_bits // 1_000_000


class DdsServiceDemarcationPoint(BaseModel):
    """A service demarcation point from the dds-proxy ``GET /service-demarcation-points`` endpoint.

    An SDP has no id of its own; it is the pair of STP ids (camelCase ``stpAId`` / ``stpZId``).
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    stp_a_id: str
    stp_z_id: str


def _client_kwargs() -> dict[str, Any]:
    """Build the httpx2 client arguments for the configured authentication mode."""
    return client_kwargs(
        mtls_enabled=settings.dds_proxy_mtls_enabled,
        client_cert=settings.dds_proxy_client_cert,
        client_key=settings.dds_proxy_client_key,
        ca_bundle=settings.dds_proxy_ca_bundle,
        auth_method=settings.dds_proxy_auth_method,
        client_dn=settings.dds_proxy_client_dn,
    )


def _fetch(path: str) -> list[dict[str, Any]]:
    """GET ``path`` from the dds-proxy and return the decoded JSON list.

    Raises:
        DdsProxyError: when the proxy cannot be reached or returns an error response.
    """
    with httpx2.Client(
        base_url=settings.dds_proxy_base_url,
        timeout=settings.dds_proxy_timeout,
        **_client_kwargs(),
    ) as client:
        try:
            response = client.get(path)
            response.raise_for_status()
        except httpx2.HTTPError as exc:
            logger.warning(
                "dds-proxy request failed",
                path=path,
                base_url=settings.dds_proxy_base_url,
                error=str(exc),
            )
            # Suppress the httpx2/httpcore chain: the cause is already folded into the message.
            raise DdsProxyError(
                f"Could not fetch {path} from dds-proxy at {settings.dds_proxy_base_url}: {exc}"
            ) from None

        data: list[dict[str, Any]] = response.json()
        return data


def fetch_topologies() -> list[DdsTopology]:
    """Return all topologies known to the dds-proxy."""
    return [DdsTopology.model_validate(item) for item in _fetch("/topologies")]


def fetch_switching_services() -> list[DdsSwitchingService]:
    """Return all switching services known to the dds-proxy."""
    return [DdsSwitchingService.model_validate(item) for item in _fetch("/switching-services")]


def fetch_service_termination_points() -> list[DdsServiceTerminationPoint]:
    """Return all service termination points known to the dds-proxy."""
    return [DdsServiceTerminationPoint.model_validate(item) for item in _fetch("/service-termination-points")]


def fetch_service_demarcation_points() -> list[DdsServiceDemarcationPoint]:
    """Return all service demarcation points known to the dds-proxy."""
    return [DdsServiceDemarcationPoint.model_validate(item) for item in _fetch("/service-demarcation-points")]
