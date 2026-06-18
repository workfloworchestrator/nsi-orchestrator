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

import httpx
import structlog
from pydantic import BaseModel, ConfigDict

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


def _client_kwargs() -> dict[str, Any]:
    """Build the httpx client arguments for the configured authentication mode."""
    if settings.dds_proxy_mtls_enabled:
        cert: str | tuple[str, str] | None = (
            (settings.dds_proxy_client_cert, settings.dds_proxy_client_key)
            if settings.dds_proxy_client_cert and settings.dds_proxy_client_key
            else settings.dds_proxy_client_cert
        )
        return {"cert": cert, "verify": settings.dds_proxy_ca_bundle or True}

    # Local dev: fake the dds-proxy mTLS-path identity headers (X-Auth-Method == its MTLS_HEADER).
    return {
        "headers": {
            "X-Auth-Method": settings.dds_proxy_auth_method,
            "X-Client-DN": settings.dds_proxy_client_dn,
        }
    }


def fetch_topologies() -> list[DdsTopology]:
    """Return all topologies known to the dds-proxy.

    Raises:
        DdsProxyError: when the proxy cannot be reached or returns an error response.
    """
    with httpx.Client(
        base_url=settings.dds_proxy_base_url,
        timeout=settings.dds_proxy_timeout_seconds,
        **_client_kwargs(),
    ) as client:
        try:
            response = client.get("/topologies")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "dds-proxy /topologies request failed",
                base_url=settings.dds_proxy_base_url,
                error=str(exc),
            )
            # Suppress the httpx/httpcore exception chain: the cause (e.g. "Connection refused")
            # is already folded into the message, and the chain only adds noise to the logs.
            raise DdsProxyError(
                f"Could not fetch topologies from dds-proxy at {settings.dds_proxy_base_url}: {exc}"
            ) from None

        return [DdsTopology.model_validate(item) for item in response.json()]
