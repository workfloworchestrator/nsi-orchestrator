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

orchestrator-core authenticates the OIDC bearer token (via oauth2-lib); this plugs a single
group check into its ``AuthManager`` for both REST and GraphQL. It is deliberately *not*
per-workflow policy: a request is allowed if and only if the token's groups claim intersects
``allowed_groups``. The gate fails closed — a missing/empty user or an absent/garbled claim
yields no groups and is denied — and only bypasses for local development, where
``OAUTH2_ACTIVE`` is off and there is no authenticated user to check.
"""

from collections.abc import Iterable
from http import HTTPStatus

from fastapi import HTTPException
from httpx import AsyncClient
from oauth2_lib.fastapi import Authorization, GraphqlAuthorization, OIDCAuth, OIDCUserModel, RequestPath
from oauth2_lib.settings import oauth2lib_settings
from starlette.requests import HTTPConnection
from starlette.status import HTTP_401_UNAUTHORIZED


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


class GroupGate(Authorization):
    """REST authorization: allow a request when the token shares a group with ``allowed_groups``."""

    def __init__(self, allowed_groups: Iterable[str], groups_claim: str) -> None:
        self.allowed_groups = set(allowed_groups)
        self.groups_claim = groups_claim

    async def authorize(self, request: HTTPConnection, user: OIDCUserModel) -> bool | None:
        # security.py calls this even with auth off (user is then None): bypass so local
        # development works; once auth is on, enforce and fail closed.
        if not oauth2lib_settings.OAUTH2_ACTIVE:
            return None
        return _is_member(user, self.allowed_groups, self.groups_claim)


class GroupGateGraphql(GraphqlAuthorization):
    """GraphQL authorization: the identical coarse group check as :class:`GroupGate`."""

    def __init__(self, allowed_groups: Iterable[str], groups_claim: str) -> None:
        self.allowed_groups = set(allowed_groups)
        self.groups_claim = groups_claim

    async def authorize(self, request: RequestPath, method: str, user: OIDCUserModel) -> bool | None:
        if not oauth2lib_settings.OAUTH2_ACTIVE:
            return None
        return _is_member(user, self.allowed_groups, self.groups_claim)


class UserinfoOIDCAuth(OIDCAuth):
    """Authenticate a bearer token against the OIDC provider's userinfo endpoint.

    orchestrator-core ships only the abstract ``OIDCAuth`` (its ``userinfo`` raises
    ``NotImplementedError``), so a deployment must supply a concrete one. This validates the token
    by calling the provider's discovered ``userinfo_endpoint`` with it — which works with opaque
    access tokens and needs no resource-server credentials — and returns the claims as the user.
    """

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
