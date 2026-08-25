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

"""End-to-end tests for the system tasks."""

from __future__ import annotations

import pytest
from orchestrator.core.targets import Target
from orchestrator.core.workflows import get_workflow

from schedules import NSI_SCHEDULES
from services import aggregator_proxy
from services.aggregator_proxy import AggregatorProxyError, AggregatorReservation
from tests.workflows import assert_complete, assert_failed, extract_error, extract_state, run_workflow

TASK = "task_validate_aggregator_against_subscriptions"


def _reservation(connection_id: str, status: str = "RESERVED") -> AggregatorReservation:
    return AggregatorReservation(connection_id=connection_id, description="d", status=status)


@pytest.fixture
def reservations(monkeypatch: pytest.MonkeyPatch) -> list[AggregatorReservation]:
    """Mock the aggregator's reservation list; tests append to the returned list to shape it."""
    listed: list[AggregatorReservation] = []
    monkeypatch.setattr(aggregator_proxy, "list_reservations", lambda: listed)
    return listed


@pytest.mark.parametrize(
    "workflow_name", [s["workflow_name"] for s in NSI_SCHEDULES], ids=[s["name"] for s in NSI_SCHEDULES]
)
def test_scheduled_tasks_never_block_their_own_later_runs(workflow_name: str) -> None:
    """A run_predicate would make the first failure block every subsequent run (see CLAUDE.md)."""
    workflow = get_workflow(workflow_name)

    assert workflow is not None
    assert workflow.target == Target.SYSTEM
    assert workflow.run_predicate is None


def test_reports_nothing_when_every_reservation_has_a_subscription(
    mdp2p_subscription: str, reservations: list[AggregatorReservation]
) -> None:
    reservations.append(_reservation("conn-1"))

    result, _, _ = run_workflow(TASK, [{}])

    assert_complete(result)
    state = extract_state(result)
    assert (state["checked_reservations"], state["checked_subscriptions"]) == (1, 1)


@pytest.mark.parametrize(
    ("extra_reservations", "expected"),
    [
        pytest.param(["conn-orphan"], "reservations without a subscription: ['conn-orphan']", id="aggregator-orphan"),
        pytest.param([], "subscriptions without a live reservation: ['conn-1']", id="subscription-orphan"),
    ],
)
def test_reports_drift_in_both_directions(
    mdp2p_subscription: str,
    reservations: list[AggregatorReservation],
    extra_reservations: list[str],
    expected: str,
) -> None:
    if extra_reservations:
        reservations.append(_reservation("conn-1"))
    reservations.extend(_reservation(cid) for cid in extra_reservations)

    result, _, _ = run_workflow(TASK, [{}])

    assert_failed(result)
    assert expected in str(extract_error(result))


def test_terminated_reservations_are_not_orphans(
    mdp2p_subscription: str, reservations: list[AggregatorReservation]
) -> None:
    """A terminated connection's subscription is terminated too, so it is outside subscribed_values."""
    reservations.extend([_reservation("conn-1"), _reservation("conn-old", status="TERMINATED")])

    result, _, _ = run_workflow(TASK, [{}])

    assert_complete(result)


def test_an_unreachable_aggregator_fails_without_reporting_drift(
    mdp2p_subscription: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed fetch must abort rather than diff against nothing."""

    def _boom() -> list[AggregatorReservation]:
        raise AggregatorProxyError("connection refused")

    monkeypatch.setattr(aggregator_proxy, "list_reservations", _boom)

    result, _, _ = run_workflow(TASK, [{}])

    assert_failed(result)
    error = str(extract_error(result))
    assert "nothing was compared" in error
    assert "without a live reservation" not in error
