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

"""End-to-end tests for task_validate_upas_against_vlans, over the A <-> B <-> C chain."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import pytest

from services import aggregator_proxy
from services.aggregator_proxy import AggregatorProxyError, AggregatorReservation, Upa, UpaReservation
from tests import held_reservation
from tests.workflows import assert_complete, assert_failed, extract_error, extract_state, run_workflow
from tests.workflows.conftest import PATH_STPS
from workflows.mdp2p.shared.ero import network_of
from workflows.tasks import validate_upas_against_vlans

TASK = "task_validate_upas_against_vlans"
SUBSCRIPTION_ID = UUID("5e1f0b8c-0000-4000-8000-000000000001")
UNKNOWN = "held by a uPA but not in use by the orchestrator"
LOST = "in use by the orchestrator but not held by any uPA"
FAILED_ONLY = "held only by a FAILED aggregator reservation, already released by the uPA"
OUTSIDE_RANGE = "held outside the STP's current DDS range"
SOURCE, A_TO_B, DESTINATION = PATH_STPS["source"], PATH_STPS["a_to_b"], PATH_STPS["destination"]
# One uPA per domain of the chain, each serving its own network.
NETWORKS = {name: network_of(PATH_STPS[stp]) for name, stp in (("a", "source"), ("b", "b_to_a"), ("c", "destination"))}
UPAS = {
    name: Upa(nsa_id=f"urn:ogf:network:{name}.example.net:2025:nsa:upa", network_ids=[n])
    for name, n in NETWORKS.items()
}


def _upa_reservation(
    source_stp: str | None,
    dest_stp: str | None,
    *,
    connection_id: str = "upa-conn",
    global_reservation_id: str | None = None,
    lifecycle_state: str = "Created",
    reservation_state: str = "ReserveStart",
) -> UpaReservation:
    return UpaReservation.model_validate(
        {
            "connectionId": connection_id,
            "globalReservationId": global_reservation_id,
            "reservationState": reservation_state,
            "lifecycleState": lifecycle_state,
            "sourceSTP": source_stp,
            "destSTP": dest_stp,
        }
    )


def _segment(stp_a: str, stp_z: str, vlan: int) -> UpaReservation:
    return _upa_reservation(f"{stp_a}?vlan={vlan}", f"{stp_z}?vlan={vlan}", connection_id=f"child-{stp_a}")


def _healthy_upas() -> dict[str, list[UpaReservation]]:
    """The uPA view of a healthy A -> C connection on VLAN 1500 end to end, crossing both SDPs."""
    return {
        "a": [_segment(SOURCE, A_TO_B, 1500)],
        "b": [_segment(PATH_STPS["b_to_a"], PATH_STPS["b_to_c"], 1500)],
        "c": [_segment(PATH_STPS["c_to_b"], DESTINATION, 1500)],
    }


HEALTHY_AGGREGATOR = held_reservation(
    "ACTIVATED",
    f"{SOURCE}?vlan=1500",
    f"{DESTINATION}?vlan=1500",
    sdps=[(A_TO_B, PATH_STPS["b_to_a"], 1500), (PATH_STPS["b_to_c"], PATH_STPS["c_to_b"], 1500)],
)


@dataclass
class Proxies:
    """What the mocked aggregator-proxy returns; a test edits it to shape the scenario."""

    aggregator: list[AggregatorReservation] = field(default_factory=lambda: [HEALTHY_AGGREGATOR])
    upas: dict[str, list[UpaReservation]] = field(default_factory=_healthy_upas)
    peered: list[str] = field(default_factory=lambda: list(UPAS))

    def list_upas(self) -> list[Upa]:
        return [UPAS[name] for name in self.peered]

    def list_upa_reservations(self, nsa_id: str) -> list[UpaReservation]:
        return next(self.upas[name] for name, upa in UPAS.items() if upa.nsa_id == nsa_id)


@pytest.fixture
def proxies(path_subscriptions: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Proxies:
    state = Proxies()
    monkeypatch.setattr(aggregator_proxy, "list_upas", state.list_upas)
    monkeypatch.setattr(aggregator_proxy, "list_reservations", lambda **_kwargs: state.aggregator)
    monkeypatch.setattr(aggregator_proxy, "list_upa_reservations", state.list_upa_reservations)
    return state


def _drift() -> tuple[str, dict[str, list[dict[str, str | None]]]]:
    """Run the task, expect drift, and return its message and its structured findings per section.

    Run it once per test: a failed step rolls back the test's transaction, seed subscriptions included.
    """
    result, _, _ = run_workflow(TASK, [{}])
    assert_failed(result)
    state = extract_state(result)
    assert state["class"] == "InconsistentDataError"
    return str(extract_error(result)), state["details"]


def test_reports_nothing_when_upas_and_orchestrator_agree(proxies: Proxies) -> None:
    result, _, _ = run_workflow(TASK, [{}])

    assert_complete(result)
    state = extract_state(result)
    assert state["checked_upas"] == sorted(upa.nsa_id for upa in UPAS.values())
    assert (state["checked_vlans"], state["unchecked_stps"]) == (6, [])


@pytest.mark.parametrize(
    "reservation",
    [
        pytest.param(_upa_reservation(f"{SOURCE}?vlan=1501", None, lifecycle_state="Terminated"), id="terminated"),
        pytest.param(_upa_reservation(f"{SOURCE}?vlan=1501", None, lifecycle_state="Failed"), id="lifecycle-failed"),
        pytest.param(
            _upa_reservation(f"{SOURCE}?vlan=1501", None, lifecycle_state="PassedEndTime"), id="passed-end-time"
        ),
        pytest.param(
            _upa_reservation(f"{SOURCE}?vlan=1501", None, reservation_state="ReserveTimeout"), id="reserve-timeout"
        ),
        pytest.param(
            _upa_reservation(f"{SOURCE}?vlan=1501", None, reservation_state="ReserveFailed"), id="reserve-failed"
        ),
        pytest.param(_upa_reservation(None, None), id="no-stps"),
        pytest.param(
            _upa_reservation("urn:ogf:network:a.example.net:2025:topology:unsubscribed?vlan=1500", None),
            id="stp-without-subscription",
        ),
    ],
)
def test_upa_reservations_outside_the_comparison_are_ignored(proxies: Proxies, reservation: UpaReservation) -> None:
    """Released VLANs, reservations without STPs, and STPs this orchestrator does not administer."""
    proxies.upas["a"].append(reservation)

    assert_complete(run_workflow(TASK, [{}])[0])


def test_names_the_upa_reservation_holding_an_unknown_vlan(proxies: Proxies) -> None:
    proxies.upas["a"].append(
        _upa_reservation(
            f"{SOURCE}?vlan=1777-1779",
            f"{A_TO_B}?vlan=1777",
            connection_id="upa-orphan",
            global_reservation_id="urn:uuid:g",
        )
    )

    message, details = _drift()

    ids = {
        "side": "uPA",
        "connection_id": "upa-orphan",
        "child_connection_id": None,
        "global_reservation_id": "urn:uuid:g",
        "subscription_id": None,
    }
    assert details[UNKNOWN] == [
        {"stp_id": SOURCE, "vlans": "1777-1779", **ids},
        {"stp_id": A_TO_B, "vlans": "1777", **ids},
    ]
    assert message.startswith(
        "uPA VLANs and the orchestrator disagree:\n"
        f"    {UNKNOWN}:\n"
        f"        {SOURCE}: VLAN 1777-1779\n"
        "            uPA connection upa-orphan\n"
        "            global reservation urn:uuid:g\n"
        f"        {A_TO_B}: VLAN 1777\n"
    )
    assert LOST not in message


def test_names_the_aggregator_connection_and_the_child_a_upa_lost(proxies: Proxies) -> None:
    """The child id is what the uPA would report the segment as, so it names exactly what is missing."""
    proxies.upas["c"] = []

    message, details = _drift()

    assert {(f["stp_id"], f["side"], f["connection_id"], f["child_connection_id"]) for f in details[LOST]} == {
        (PATH_STPS["c_to_b"], "aggregator", HEALTHY_AGGREGATOR.connection_id, f"{HEALTHY_AGGREGATOR.connection_id}-1"),
        (DESTINATION, "aggregator", HEALTHY_AGGREGATOR.connection_id, None),
    }
    assert f"child {HEALTHY_AGGREGATOR.connection_id}-1" in message
    assert UNKNOWN not in message


@pytest.mark.parametrize(
    ("subscriptions", "expected_id", "expected_text"),
    [
        pytest.param(
            {HEALTHY_AGGREGATOR.connection_id: SUBSCRIPTION_ID},
            str(SUBSCRIPTION_ID),
            f"subscription {SUBSCRIPTION_ID}",
            id="with-subscription",
        ),
        pytest.param({}, None, "no subscription", id="without-subscription"),
    ],
)
def test_names_the_subscription_of_an_aggregator_reservation(
    proxies: Proxies,
    monkeypatch: pytest.MonkeyPatch,
    subscriptions: dict[str, UUID],
    expected_id: str | None,
    expected_text: str,
) -> None:
    proxies.upas["c"] = []
    monkeypatch.setattr(validate_upas_against_vlans, "subscription_ids_for_values", lambda *_args: subscriptions)

    message, details = _drift()

    assert {f["subscription_id"] for f in details[LOST]} == {expected_id}
    assert expected_text in message


def test_a_path_end_is_named_once_by_the_segment_holding_it(proxies: Proxies) -> None:
    """A path's end is also its first segment's outer end; only the line naming the child is kept."""
    with_end_segments = held_reservation(
        "ACTIVATED",
        f"{SOURCE}?vlan=1500",
        f"{DESTINATION}?vlan=1500",
        connection_id="ends",
        sdps=[(SOURCE, A_TO_B, 1500), (PATH_STPS["c_to_b"], DESTINATION, 1500)],
    )
    proxies.aggregator = [with_end_segments]
    proxies.upas = {"a": [], "b": [], "c": []}

    _, details = _drift()

    source_lines = [f for f in details[LOST] if f["stp_id"] == SOURCE]
    assert [(f["connection_id"], f["child_connection_id"]) for f in source_lines] == [("ends", "ends-0")]


def test_a_vlan_held_twice_names_both_holders(proxies: Proxies) -> None:
    proxies.upas["a"] += [
        _upa_reservation(f"{SOURCE}?vlan=1777", None, connection_id="first"),
        _upa_reservation(f"{SOURCE}?vlan=1777", None, connection_id="second"),
    ]

    _, details = _drift()

    assert sorted(f["connection_id"] or "" for f in details[UNKNOWN]) == ["first", "second"]


def test_reports_a_failed_reservation_released_by_the_upa_separately(proxies: Proxies) -> None:
    failed = held_reservation("FAILED", f"{SOURCE}?vlan=1600", f"{DESTINATION}?vlan=1600", connection_id="failed")
    proxies.aggregator = [failed, HEALTHY_AGGREGATOR]

    message, _ = _drift()

    assert FAILED_ONLY in message
    assert f"{SOURCE}: VLAN 1600" in message
    assert LOST not in message


@pytest.mark.parametrize(
    ("upa_reservations", "aggregator_reservations"),
    [
        pytest.param([_upa_reservation(f"{SOURCE}?vlan=3000", None)], [], id="held-by-a-upa"),
        pytest.param(
            [],
            [held_reservation("ACTIVATED", f"{SOURCE}?vlan=3000", f"{DESTINATION}?vlan=1500", connection_id="old")],
            id="in-use-by-the-orchestrator",
        ),
    ],
)
def test_reports_a_vlan_outside_the_current_dds_range_on_its_own(
    proxies: Proxies,
    upa_reservations: list[UpaReservation],
    aggregator_reservations: list[AggregatorReservation],
) -> None:
    """A range change leaves reservations outside the new range; they are not in the other sections."""
    proxies.upas["a"].extend(upa_reservations)
    proxies.aggregator.extend(aggregator_reservations)

    message, _ = _drift()

    assert OUTSIDE_RANGE in message
    assert f"{SOURCE}: VLAN 3000" in message
    assert UNKNOWN not in message
    assert LOST not in message


def test_a_failed_reservation_still_held_by_its_upa_is_fine(proxies: Proxies) -> None:
    proxies.aggregator = [held_reservation("FAILED", f"{SOURCE}?vlan=1600", f"{A_TO_B}?vlan=1600")]
    proxies.upas = {"a": [_segment(SOURCE, A_TO_B, 1600)], "b": [], "c": []}

    assert_complete(run_workflow(TASK, [{}])[0])


def test_stps_no_peered_upa_serves_are_left_unchecked(proxies: Proxies) -> None:
    proxies.peered = ["a", "b"]

    result, _, _ = run_workflow(TASK, [{}])

    assert_complete(result)
    state = extract_state(result)
    assert state["checked_upas"] == [UPAS["a"].nsa_id, UPAS["b"].nsa_id]
    assert state["unchecked_stps"] == sorted([PATH_STPS["c_to_b"], DESTINATION])


@pytest.mark.parametrize("function", ["list_upas", "list_reservations", "list_upa_reservations"])
def test_an_unreachable_proxy_fails_without_comparing(
    proxies: Proxies, monkeypatch: pytest.MonkeyPatch, function: str
) -> None:
    """An outage is plain ``failed``, not drift."""

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AggregatorProxyError("connection refused")

    monkeypatch.setattr(aggregator_proxy, function, _boom)

    result, _, _ = run_workflow(TASK, [{}])

    assert_failed(result)
    assert extract_state(result)["class"] == "AggregatorProxyError"
