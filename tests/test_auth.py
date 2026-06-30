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
from typing import cast

import pytest
from _pytest.monkeypatch import MonkeyPatch
from oauth2_lib.fastapi import OIDCUserModel
from oauth2_lib.settings import oauth2lib_settings
from starlette.requests import HTTPConnection

from auth import GroupGate, GroupGateGraphql

OPERATOR = "urn:example:group:operators"
OTHER = "urn:example:group:other"
CLAIM = "eduperson_entitlement"


def _conn() -> HTTPConnection:
    return HTTPConnection({"type": "http", "headers": []})


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
