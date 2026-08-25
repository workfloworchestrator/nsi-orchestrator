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
    dds_proxy_timeout: float = 30.0  # seconds

    # Authentication mode against the dds-proxy.
    #
    # When deployed the orchestrator authenticates to the *public* dds-proxy endpoint with
    # mutual TLS: it presents a client certificate + key and verifies the server against a CA
    # bundle. Set DDS_PROXY_MTLS_ENABLED=true and point the three path settings at PEM files.
    dds_proxy_mtls_enabled: bool = False
    dds_proxy_client_cert: str | None = None  # path to the PEM client certificate
    dds_proxy_client_key: str | None = None  # path to the PEM private key
    dds_proxy_ca_bundle: str | None = None  # path to a CA bundle used to verify the server

    # Local-development shortcut, used ONLY when mTLS is disabled. The dds-proxy trusts the
    # edge identity headers; these fake the mTLS auth path (X-Auth-Method is the proxy's
    # MTLS_HEADER, X-Client-DN is the certificate DN it logs). Never used in a deployment.
    dds_proxy_auth_method: str = "x509"
    dds_proxy_client_dn: str = "CN=claude@local.laptop"

    # Base URL of the nsi-aggregator-proxy REST API (connection reserve/provision/release).
    aggregator_proxy_base_url: str = "http://localhost:8080"
    aggregator_proxy_timeout: float = 30.0  # seconds

    # Authentication against the aggregator-proxy mirrors the dds-proxy: real mTLS when
    # deployed, edge identity headers as a local-development shortcut. See the dds_proxy_*
    # fields above for the meaning of each setting.
    aggregator_proxy_mtls_enabled: bool = False
    aggregator_proxy_client_cert: str | None = None
    aggregator_proxy_client_key: str | None = None
    aggregator_proxy_ca_bundle: str | None = None
    aggregator_proxy_auth_method: str = "x509"
    aggregator_proxy_client_dn: str = "CN=claude@local.laptop"

    # Backstop timeout for the aggregator callback_steps (reserve/provision/release/terminate). Sized
    # above the proxy's own worst case (~480s: NSI_TIMEOUT 180 + DATAPLANE_TIMEOUT 300 in sequential
    # phases) plus the ~30s timeout-sweep granularity, so it only fires when the proxy never reports
    # back at all rather than racing a proxy that is about to deliver a real error.
    aggregator_callback_timeout: int = 540  # seconds

    # NSA URNs exchanged with the aggregator: who is asking (this orchestrator) and which
    # aggregator answers. provider_nsa must match the aggregator-proxy's configured PROVIDER_NSA.
    requester_nsa: str = "urn:ogf:network:example.net:2026:nsa:nsi-orchestrator"
    provider_nsa: str = "urn:ogf:network:example.net:2026:nsa:safnari"

    # Connection ids task_validate_aggregator_against_subscriptions must not report (JSON list).
    ignored_connection_ids: list[str] = []

    # This orchestrator's own externally reachable base URL. The aggregator-proxy POSTs reservation
    # results back to <orchestrator_callback_base_url><callback_route>, so it must be an absolute
    # URL the proxy can reach. Override in every deployment.
    orchestrator_callback_base_url: str = "http://localhost:8080"

    # Access control (auth.py): write_groups grants REST + GraphQL mutations, read_groups grants
    # GraphQL queries only; writers are implicitly readers. The group identifiers are deployment
    # config (JSON lists), and wsgi.py refuses to start with empty write_groups once auth is on.
    read_groups: list[str] = []
    write_groups: list[str] = []
    groups_claim: str = "eduperson_entitlement"

    # Serve the OpenAPI docs endpoints (/api/docs, /api/openapi.json, /api/redoc). Off by default
    # so a deployment never exposes its API schema; set SERVE_API_DOCS=true for local development.
    serve_api_docs: bool = False


settings = Settings()


def _psycopg_dsn(uri: str) -> str:
    """Force the psycopg (v3) driver on a bare postgresql:// DSN; leave any other scheme untouched."""
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg://" + uri.removeprefix("postgresql://")
    return uri


def use_psycopg_driver() -> None:
    """Rewrite DATABASE_URI to the psycopg (v3) driver before orchestrator-core builds the engine.

    A bare ``postgresql://`` DSN makes SQLAlchemy select its default psycopg2 dialect, which this
    image does not ship (it has psycopg v3). Call before init_database / OrchestratorCore.
    """
    from orchestrator.core.settings import SecretPostgresDsn, app_settings

    uri = str(app_settings.DATABASE_URI.get_secret_value())
    fixed = _psycopg_dsn(uri)
    if fixed != uri:
        app_settings.DATABASE_URI = SecretPostgresDsn(fixed)  # type: ignore[arg-type]
