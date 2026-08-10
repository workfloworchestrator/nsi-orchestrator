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

"""Tests for the multi domain point-to-point connection state machine."""

from __future__ import annotations

import pytest
from statemachine.exceptions import TransitionNotAllowed

from workflows.mdp2p.shared.fsm import ConnectionState, apply


@pytest.mark.parametrize(
    ("start", "event", "expected"),
    [
        (ConnectionState.CREATED, "reserve_confirmed", ConnectionState.RESERVED),
        (ConnectionState.CREATED, "reserve_failed", ConnectionState.FAILED),
        (ConnectionState.RESERVED, "provision_confirmed", ConnectionState.ACTIVATED),
        (ConnectionState.RESERVED, "provision_failed", ConnectionState.FAILED),
        (ConnectionState.ACTIVATED, "release_confirmed", ConnectionState.RESERVED),
        (ConnectionState.ACTIVATED, "release_failed", ConnectionState.FAILED),
        (ConnectionState.RESERVED, "terminate", ConnectionState.TERMINATED),
        (ConnectionState.FAILED, "terminate", ConnectionState.TERMINATED),
        (ConnectionState.FAILED, "retry", ConnectionState.CREATED),
        (ConnectionState.CREATED, "retry", ConnectionState.CREATED),
    ],
)
def test_legal_transitions(start: str, event: str, expected: str) -> None:
    assert apply(start, event) == expected


@pytest.mark.parametrize(
    ("start", "event"),
    [
        (ConnectionState.ACTIVATED, "provision_confirmed"),  # already activated
        (ConnectionState.RESERVED, "release_confirmed"),  # not activated
        (ConnectionState.ACTIVATED, "terminate"),  # must be released first
        (ConnectionState.TERMINATED, "reserve_confirmed"),  # terminal state
        (ConnectionState.RESERVED, "retry"),  # holds a reservation; release or terminate it instead
        (ConnectionState.ACTIVATED, "retry"),  # data plane may be up
    ],
)
def test_illegal_transitions_raise(start: str, event: str) -> None:
    with pytest.raises(TransitionNotAllowed):
        apply(start, event)
