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

import logging
from pathlib import Path
from typing import Any

from graphql.validation import NoSchemaIntrospectionCustomRule
from oauth2_lib.fastapi import OIDCUserModel
from oauth2_lib.settings import oauth2lib_settings
from orchestrator.core import OrchestratorCore
from orchestrator.core.graphql import Mutation, Query
from orchestrator.core.graphql.schema import get_extensions
from orchestrator.core.settings import app_settings
from strawberry.extensions import AddValidationRules

import products  # noqa: F401  Registers subscription models in SUBSCRIPTION_MODEL_REGISTRY
import workflows  # noqa: F401  Registers the topology workflow instances
from auth import GroupGate, GroupGateGraphql, UserinfoOIDCAuth
from log_filters import HealthCheckAccessFilter
from settings import settings, use_psycopg_driver

# Fail fast rather than boot silently open. orchestrator-core's GraphQL layer skips the
# authorization check entirely when OAUTH2_AUTHORIZATION_ACTIVE is off, so wherever authentication
# is enabled both flags must be on and a group must be configured for the gate to bite.
if oauth2lib_settings.OAUTH2_ACTIVE:
    if not oauth2lib_settings.OAUTH2_AUTHORIZATION_ACTIVE:
        raise RuntimeError("OAUTH2_AUTHORIZATION_ACTIVE must be true when OAUTH2_ACTIVE is true")
    if not settings.allowed_groups:
        raise RuntimeError("ALLOWED_GROUPS must be set when OAUTH2_ACTIVE is true")

# Serve our project translations from ./translations unless overridden via TRANSLATIONS_DIR.
if app_settings.TRANSLATIONS_DIR is None:
    app_settings.TRANSLATIONS_DIR = Path("translations")

# Drop the GraphiQL playground; the API is internet-facing with only the in-app gate in front.
app_settings.SERVE_GRAPHQL_UI = None

# Disable the OpenAPI docs endpoints unless explicitly enabled for local development, so a
# deployment does not expose its REST API schema.
# FastAPI accepts None for these to disable the endpoints, though orchestrator-core types them str.
docs: dict[str, Any] = {} if settings.serve_api_docs else {"docs_url": None, "openapi_url": None, "redoc_url": None}
use_psycopg_driver()
app = OrchestratorCore(base_settings=app_settings, **docs)

# OrchestratorCore ran initialise_logging above; add the filter afterwards so it survives. The health
# probe fires every few seconds and would otherwise dominate the access log.
logging.getLogger("uvicorn.access").addFilter(HealthCheckAccessFilter())

# Authenticate bearer tokens via the OIDC provider's userinfo endpoint (orchestrator-core ships
# only the abstract OIDCAuth), then restrict access to members of allowed_groups on REST + GraphQL.
app.register_authentication(
    UserinfoOIDCAuth(
        openid_url=oauth2lib_settings.OIDC_BASE_URL,
        openid_config_url=oauth2lib_settings.OIDC_CONF_URL,
        resource_server_id=oauth2lib_settings.OAUTH2_RESOURCE_SERVER_ID,
        resource_server_secret=oauth2lib_settings.OAUTH2_RESOURCE_SERVER_SECRET,
        oidc_user_model_cls=OIDCUserModel,
    )
)
app.register_authorization(GroupGate(settings.allowed_groups, settings.groups_claim))
app.register_graphql_authorization(GroupGateGraphql(settings.allowed_groups, settings.groups_claim))

# Keep orchestrator-core's default GraphQL extensions and additionally forbid schema introspection.
extensions = [*get_extensions(Mutation, Query), AddValidationRules([NoSchemaIntrospectionCustomRule])]
app.register_graphql(extensions=extensions)
