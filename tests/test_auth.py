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

"""Tests for the coarse operators-group authorization gate (auth.py)."""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from types import SimpleNamespace
from typing import cast

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi import HTTPException
from httpx import AsyncClient
from oauth2_lib.fastapi import OIDCConfig, OIDCUserModel
from oauth2_lib.settings import oauth2lib_settings
from starlette.requests import HTTPConnection, Request
from starlette.status import HTTP_401_UNAUTHORIZED

from auth import GroupGate, GroupGateGraphql, UserinfoOIDCAuth

OPERATOR = "urn:example:group:operators"
OTHER = "urn:example:group:other"
CALLBACK_PATH = "/api/processes/1d1b00ca-9c22-456a-abf2-60024def0764/callback/nMo_Hjo1"
CLAIM = "eduperson_entitlement"


def _conn(path: str = "/api/subscriptions") -> HTTPConnection:
    return HTTPConnection({"type": "http", "headers": [], "path": path})


@pytest.mark.parametrize(
    ("oauth2_active", "user", "expected"),
    [
        pytest.param(False, OIDCUserModel({CLAIM: [OTHER]}), None, id="auth-off-bypasses"),
        pytest.param(True, OIDCUserModel({CLAIM: [OPERATOR]}), True, id="operator-in-list"),
        pytest.param(True, OIDCUserModel({CLAIM: OPERATOR}), True, id="operator-as-bare-string"),
        pytest.param(True, OIDCUserModel({CLAIM: [OTHER, OPERATOR]}), True, id="operator-among-many"),
        pytest.param(True, OIDCUserModel({CLAIM: [OTHER]}), False, id="non-operator-denied"),
        pytest.param(True, OIDCUserModel({CLAIM: []}), False, id="empty-claim-denied"),
        pytest.param(True, OIDCUserModel(), False, id="missing-claim-denied"),
        pytest.param(True, cast(OIDCUserModel, None), False, id="no-user-fails-closed"),
    ],
)
def test_group_gate_rest(
    monkeypatch: MonkeyPatch, oauth2_active: bool, user: OIDCUserModel, expected: bool | None
) -> None:
    monkeypatch.setattr(oauth2lib_settings, "OAUTH2_ACTIVE", oauth2_active)
    gate = GroupGate([OPERATOR], CLAIM)
    assert asyncio.run(gate.authorize(_conn(), user)) is expected


@pytest.mark.parametrize(
    "user",
    [OIDCUserModel({CLAIM: [OTHER]}), cast(OIDCUserModel, None)],
    ids=["non-operator", "no-user"],
)
def test_group_gate_bypasses_callback_route(monkeypatch: MonkeyPatch, user: OIDCUserModel) -> None:
    monkeypatch.setattr(oauth2lib_settings, "OAUTH2_ACTIVE", True)
    gate = GroupGate([OPERATOR], CLAIM)
    assert asyncio.run(gate.authorize(_conn(CALLBACK_PATH), user)) is None


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        pytest.param(CALLBACK_PATH, True, id="callback-bypassed"),
        pytest.param(CALLBACK_PATH + "/progress", True, id="callback-progress-bypassed"),
        pytest.param("/api/processes/1d1b00ca/resume", False, id="resume-not-bypassed"),
        pytest.param("/api/subscriptions", False, id="other-not-bypassed"),
    ],
)
def test_is_bypassable_request(path: str, expected: bool) -> None:
    request = Request({"type": "http", "headers": [], "path": path})
    assert asyncio.run(_userinfo_auth().is_bypassable_request(request)) is expected


@pytest.mark.parametrize(
    ("oauth2_active", "user", "expected"),
    [
        pytest.param(False, OIDCUserModel({CLAIM: [OTHER]}), None, id="auth-off-bypasses"),
        pytest.param(True, OIDCUserModel({CLAIM: [OPERATOR]}), True, id="operator-allowed"),
        pytest.param(True, OIDCUserModel({CLAIM: [OTHER]}), False, id="non-operator-denied"),
        pytest.param(True, cast(OIDCUserModel, None), False, id="no-user-fails-closed"),
    ],
)
def test_group_gate_graphql(
    monkeypatch: MonkeyPatch, oauth2_active: bool, user: OIDCUserModel, expected: bool | None
) -> None:
    monkeypatch.setattr(oauth2lib_settings, "OAUTH2_ACTIVE", oauth2_active)
    gate = GroupGateGraphql([OPERATOR], CLAIM)
    assert asyncio.run(gate.authorize("/api/graphql", "QUERY", user)) is expected


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def get(self, url: str, headers: dict[str, str] | None = None) -> _FakeResponse:
        return self._response


def _userinfo_auth(with_config: bool = True) -> UserinfoOIDCAuth:
    auth = UserinfoOIDCAuth(
        openid_url="https://op",
        openid_config_url="https://op/.well-known/openid-configuration",
        resource_server_id="",
        resource_server_secret="",
        oidc_user_model_cls=OIDCUserModel,
    )
    if with_config:
        auth.openid_config = cast(OIDCConfig, SimpleNamespace(userinfo_endpoint="https://op/userinfo"))
    return auth


def test_userinfo_returns_claims_on_200() -> None:
    auth = _userinfo_auth()
    client = cast(AsyncClient, _FakeClient(_FakeResponse(HTTPStatus.OK, {"sub": "u", CLAIM: [OPERATOR]})))
    user = asyncio.run(auth.userinfo(client, "token"))
    assert user.get(CLAIM) == [OPERATOR]


def test_userinfo_raises_401_on_non_200() -> None:
    auth = _userinfo_auth()
    client = cast(AsyncClient, _FakeClient(_FakeResponse(HTTPStatus.UNAUTHORIZED, {})))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.userinfo(client, "token"))
    assert exc.value.status_code == HTTP_401_UNAUTHORIZED


def test_userinfo_raises_503_without_openid_config() -> None:
    auth = _userinfo_auth(with_config=False)
    client = cast(AsyncClient, _FakeClient(_FakeResponse(HTTPStatus.OK, {})))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.userinfo(client, "token"))
    assert exc.value.status_code == HTTPStatus.SERVICE_UNAVAILABLE
