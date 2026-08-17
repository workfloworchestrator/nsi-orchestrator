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

"""Coarse, in-process authorization gate: allow only members of configured groups.

orchestrator-core authenticates the OIDC bearer token (via oauth2-lib); this plugs a group check
into its ``AuthManager`` for both REST and GraphQL. It is deliberately *not* per-workflow policy,
only two tiers: ``write_groups`` for the REST API and the GraphQL mutations, ``read_groups`` (plus
the writers) for the GraphQL queries. The gate fails closed — a missing/empty user or an
absent/garbled claim yields no groups and is denied — and only bypasses for local development,
where ``OAUTH2_ACTIVE`` is off and there is no authenticated user to check.
"""

import re
from collections.abc import Iterable
from http import HTTPStatus

from fastapi import HTTPException
from httpx2 import AsyncClient
from oauth2_lib.fastapi import Authorization, GraphqlAuthorization, OIDCAuth, OIDCUserModel, RequestPath
from oauth2_lib.settings import oauth2lib_settings
from starlette.requests import HTTPConnection, Request
from starlette.status import HTTP_401_UNAUTHORIZED

# The awaiting-process callback route, authenticated by its own path token rather than OIDC.
_CALLBACK_PATH = re.compile(r"/processes/[^/]+/callback/[^/]+")

# oauth2-lib's discriminator: "QUERY" for query fields, "POST" for mutation fields — not an HTTP
# verb, and not the field name (that is the request path). Anything else falls through to writers.
_GRAPHQL_QUERY = "QUERY"


def _token_groups(user: OIDCUserModel | None, claim: str) -> set[str]:
    """Return the groups carried in ``claim``, normalised to a set of strings.

    Providers usually put group membership in a multivalued claim (e.g. ``eduperson_entitlement``),
    but a single value can arrive as a bare string; a missing/None user or any other shape yields
    no groups.
    """
    raw = user.get(claim) if user else None
    match raw:
        case str():
            return {raw}
        case list() | tuple() | set():
            return {str(value) for value in raw}
        case _:
            return set()


def _is_member(user: OIDCUserModel | None, allowed: set[str], claim: str) -> bool:
    return bool(allowed & _token_groups(user, claim))


class NamedEmailUserModel(OIDCUserModel):
    """Identify the user as ``Full Name <email>``.

    orchestrator-core stores a process's ``created_by`` from ``resolve_user_name()``, which takes
    ``OIDCUserModel.name`` — the full name only. A property shadows the base class' claim lookup via
    ``__getattr__``, so appending the email here is enough to widen the field, with the plain name
    (or the email, or ``sub``) as fallback when the token lacks a claim.
    """

    @property
    def name(self) -> str:
        full_name, email = str(self.get("name", "")), str(self.get("email", ""))
        if full_name and email:
            return f"{full_name} <{email}>"
        return full_name or email or str(self.get("sub", ""))


class GroupGate(Authorization):
    """REST and websocket authorization: the whole API is a write surface, so writers only."""

    def __init__(self, write_groups: Iterable[str], groups_claim: str) -> None:
        self.write_groups = set(write_groups)
        self.groups_claim = groups_claim

    async def authorize(self, request: HTTPConnection, user: OIDCUserModel) -> bool | None:
        # security.py calls this even with auth off (user is then None): bypass so local
        # development works; once auth is on, enforce and fail closed.
        if not oauth2lib_settings.OAUTH2_ACTIVE:
            return None
        # The aggregator callback authenticates by its path token, not a group (see
        # UserinfoOIDCAuth.is_bypassable_request), so skip the group gate for it too.
        if _CALLBACK_PATH.search(request.url.path):
            return None
        return _is_member(user, self.write_groups, self.groups_claim)


class GroupGateGraphql(GraphqlAuthorization):
    """GraphQL authorization: readers may query, only writers may mutate.

    The field being resolved is in ``request``, which this coarse gate ignores, so a reader gets the
    whole query surface.
    """

    def __init__(self, read_groups: Iterable[str], write_groups: Iterable[str], groups_claim: str) -> None:
        self.write_groups = set(write_groups)
        self.read_groups = set(read_groups) | self.write_groups
        self.groups_claim = groups_claim

    async def authorize(self, request: RequestPath, method: str, user: OIDCUserModel) -> bool | None:
        if not oauth2lib_settings.OAUTH2_ACTIVE:
            return None
        allowed = self.read_groups if method == _GRAPHQL_QUERY else self.write_groups
        return _is_member(user, allowed, self.groups_claim)


class UserinfoOIDCAuth(OIDCAuth):
    """Authenticate a bearer token against the OIDC provider's userinfo endpoint.

    orchestrator-core ships only the abstract ``OIDCAuth`` (its ``userinfo`` raises
    ``NotImplementedError``), so a deployment must supply a concrete one. This validates the token
    by calling the provider's discovered ``userinfo_endpoint`` with it — which works with opaque
    access tokens and needs no resource-server credentials — and returns the claims as the user.
    """

    @staticmethod
    async def is_bypassable_request(request: Request) -> bool:
        """Skip OIDC on the aggregator callback route.

        The awaiting-process callback (``/api/processes/{id}/callback/{token}``) is
        machine-to-machine: the aggregator-proxy carries no OIDC bearer, and orchestrator-core
        authenticates it by the unguessable per-process token in the path instead.
        """
        return bool(_CALLBACK_PATH.search(request.url.path))

    async def userinfo(self, async_request: AsyncClient, token: str) -> OIDCUserModel:
        # authenticate() calls check_openid_config() first, so openid_config is populated here.
        if self.openid_config is None:
            raise HTTPException(status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail="OIDC config not loaded")
        response = await async_request.get(
            self.openid_config.userinfo_endpoint,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != HTTPStatus.OK:
            raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
        return self.user_model_cls(response.json())
