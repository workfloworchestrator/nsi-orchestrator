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

"""Tests for the MDP2P reconcile state mapping."""

from __future__ import annotations

import pytest

from workflows.mdp2p.reconcile_mdp2p import reconciled_state


@pytest.mark.parametrize(
    ("current", "aggregator_status", "expected"),
    [
        pytest.param("RESERVED", "ACTIVATED", "ACTIVATED", id="drifted-after-missed-provision"),
        pytest.param("ACTIVATED", "RESERVED", "RESERVED", id="drifted-after-missed-release"),
        pytest.param("RESERVED", "FAILED", "FAILED", id="drifted-to-failed"),
        pytest.param("RESERVED", "TERMINATED", "TERMINATED", id="drifted-to-terminated"),
        pytest.param("ACTIVATED", "ACTIVATED", None, id="already-in-sync"),
        pytest.param("RESERVED", "RESERVING", None, id="transient-reserving-skipped"),
        pytest.param("RESERVED", "ACTIVATING", None, id="transient-activating-skipped"),
        pytest.param("ACTIVATED", "DEACTIVATING", None, id="transient-deactivating-skipped"),
    ],
)
def test_reconciled_state(current: str, aggregator_status: str, expected: str | None) -> None:
    assert reconciled_state(current, aggregator_status) == expected
