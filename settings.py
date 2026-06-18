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

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application-specific settings for the NSI orchestrator."""

    # Base URL of the nsi-dds-proxy REST API (topology data source).
    dds_proxy_base_url: str = "http://localhost:8080"
    dds_proxy_timeout_seconds: float = 30.0

    # Authentication mode against the dds-proxy.
    #
    # When deployed the orchestrator authenticates to the *public* dds-proxy endpoint with
    # mutual TLS: it presents a client certificate + key and verifies the server against a CA
    # bundle. Set DDS_PROXY_MTLS_ENABLED=true and point the three path settings at PEM files.
    dds_proxy_mtls_enabled: bool = False
    dds_proxy_client_cert: str | None = None  # path to the PEM client certificate
    dds_proxy_client_key: str | None = None  # path to the PEM private key
    dds_proxy_ca_bundle: str | None = (
        None  # path to a CA bundle used to verify the server
    )

    # Local-development shortcut, used ONLY when mTLS is disabled. The dds-proxy trusts the
    # edge identity headers; these fake the mTLS auth path (X-Auth-Method is the proxy's
    # MTLS_HEADER, X-Client-DN is the certificate DN it logs). Never used in a deployment.
    dds_proxy_auth_method: str = "x509"
    dds_proxy_client_dn: str = "CN=claude@local.laptop"


settings = Settings()
