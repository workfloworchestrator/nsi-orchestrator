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

"""Shared httpx client authentication for the NSI REST proxies (dds-proxy, aggregator-proxy).

Both proxies trust the same edge identity: real mutual TLS against the public endpoint when
deployed, or the edge identity headers as a local-development shortcut when mTLS is disabled.
"""

from __future__ import annotations

from typing import Any


def client_kwargs(
    *,
    mtls_enabled: bool,
    client_cert: str | None,
    client_key: str | None,
    ca_bundle: str | None,
    auth_method: str,
    client_dn: str,
) -> dict[str, Any]:
    """Build the httpx client arguments for the configured authentication mode."""
    if mtls_enabled:
        cert: str | tuple[str, str] | None = (client_cert, client_key) if client_cert and client_key else client_cert
        return {"cert": cert, "verify": ca_bundle or True}

    # Local dev: fake the proxy's mTLS-path identity headers (X-Auth-Method == its MTLS_HEADER).
    return {"headers": {"X-Auth-Method": auth_method, "X-Client-DN": client_dn}}
