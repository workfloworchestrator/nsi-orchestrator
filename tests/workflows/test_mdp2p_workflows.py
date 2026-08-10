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

"""End-to-end tests for the multi domain point-to-point (callback-driven) workflows."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from orchestrator.core.types import SubscriptionLifecycle

from products.product_types.mdp2p import MultiDomainPoint2Point
from services import aggregator_proxy
from services.aggregator_proxy import AggregatorReservation
from tests.workflows import (
    assert_awaiting_callback,
    assert_complete,
    extract_state,
    product_id,
    resume_callback,
    run_workflow,
)
from tests.workflows.conftest import PATH_STPS

_CREATE_FORM = {
    "circuit_description": "Test VC",
    "service_speed": 1000,
    "source_stp": "urn:stp1",
    "source_vlan": 1500,
    "destination_stp": "urn:stp2",
    "destination_vlan": 2500,
    "allow_stps_in_sdp": True,  # stp1/stp2 are paired in the seed SDP
    "include_sdps": [],
    "exclude_sdps": [],
}


@pytest.fixture
def aggregator(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock the aggregator-proxy so the form and the reserve/provision/etc. steps need no network."""
    from workflows.mdp2p.shared import forms

    # forms.py imported list_reservations by name, so patch its binding (not the module attribute).
    monkeypatch.setattr(forms, "list_reservations", list)
    monkeypatch.setattr(aggregator_proxy, "reserve", lambda **_kwargs: "conn-1")
    monkeypatch.setattr(aggregator_proxy, "provision", lambda _cid, _url: None)
    monkeypatch.setattr(aggregator_proxy, "release", lambda _cid, _url: None)
    monkeypatch.setattr(aggregator_proxy, "terminate", lambda _cid, _url: None)


@pytest.fixture
def mdp2p_subscription(stp_subscriptions: dict[str, str], sdp_subscription: str, aggregator: None) -> str:
    """A RESERVED MDP2P connection (create + the reserve callback)."""
    result, process, step_log = run_workflow(
        "create_mdp2p", [{"product": product_id("MultiDomainPoint2Point")}, _CREATE_FORM, {}]
    )
    assert_awaiting_callback(result)
    result, _ = resume_callback(process, step_log, {"status": "RESERVED", "connectionId": "conn-1"})
    assert_complete(result)
    return str(extract_state(result)["subscription_id"])


def test_create_mdp2p(stp_subscriptions: dict[str, str], sdp_subscription: str, aggregator: None) -> None:
    result, process, step_log = run_workflow(
        "create_mdp2p", [{"product": product_id("MultiDomainPoint2Point")}, _CREATE_FORM, {}]
    )
    assert_awaiting_callback(result)

    result, _ = resume_callback(process, step_log, {"status": "RESERVED", "connectionId": "conn-1"})

    assert_complete(result)
    subscription = MultiDomainPoint2Point.from_subscription(extract_state(result)["subscription_id"])
    assert subscription.status == SubscriptionLifecycle.ACTIVE
    assert subscription.vc.state == "RESERVED"
    assert subscription.vc.connection_id == "conn-1"
    assert {sap.stp.stp_id for sap in subscription.vc.saps} == {"urn:stp1", "urn:stp2"}


def test_create_mdp2p_stores_and_sends_the_ero_in_path_order(
    path_subscriptions: dict[str, str], aggregator: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The user's SDP order must survive the DB round trip and reach the aggregator as an ERO."""
    captured: dict = {}

    def fake_reserve(**kwargs: object) -> str:
        captured.update(kwargs)
        return "conn-1"

    monkeypatch.setattr(aggregator_proxy, "reserve", fake_reserve)

    form = _CREATE_FORM | {
        "source_stp": PATH_STPS["source"],
        "source_vlan": 1001,
        "destination_stp": PATH_STPS["destination"],
        "destination_vlan": 1002,
        "allow_stps_in_sdp": False,
        "include_sdps": [path_subscriptions["A <-> B"], path_subscriptions["B <-> C"]],
    }
    result, process, step_log = run_workflow(
        "create_mdp2p", [{"product": product_id("MultiDomainPoint2Point")}, form, {}]
    )
    assert_awaiting_callback(result)
    result, _ = resume_callback(process, step_log, {"status": "RESERVED", "connectionId": "conn-1"})
    assert_complete(result)

    subscription = MultiDomainPoint2Point.from_subscription(extract_state(result)["subscription_id"])
    constraints = subscription.vc.sdp_constraints
    assert [constraint.sdp.sdp_name for constraint in constraints] == ["A <-> B", "B <-> C"]
    assert {constraint.constraint_type for constraint in constraints} == {"INCLUDE"}

    # One STP per SDP, each the end facing the source, in the order the user chose.
    assert captured["ero"] == [PATH_STPS["a_to_b"], PATH_STPS["b_to_c"]]


@pytest.fixture
def failed_mdp2p_subscription(stp_subscriptions: dict[str, str], sdp_subscription: str, aggregator: None) -> str:
    """An MDP2P whose reserve failed: ACTIVE, in-sync, vc.state == FAILED."""
    result, process, step_log = run_workflow(
        "create_mdp2p", [{"product": product_id("MultiDomainPoint2Point")}, _CREATE_FORM, {}]
    )
    assert_awaiting_callback(result)
    result, _ = resume_callback(
        process, step_log, {"status": "FAILED", "connectionId": "conn-1", "lastError": "no path found"}
    )
    assert_complete(result)
    subscription_id = str(extract_state(result)["subscription_id"])
    assert MultiDomainPoint2Point.from_subscription(subscription_id).vc.state == "FAILED"
    return subscription_id


def test_retry_reservation_terminates_the_old_connection_and_reserves_again(
    failed_mdp2p_subscription: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, object]] = []

    def fake_reserve(**kwargs: object) -> str:
        calls.append(("reserve", kwargs))
        return "conn-2"

    monkeypatch.setattr(aggregator_proxy, "terminate", lambda cid, _url: calls.append(("terminate", cid)))
    monkeypatch.setattr(aggregator_proxy, "reserve", fake_reserve)
    before = MultiDomainPoint2Point.from_subscription(failed_mdp2p_subscription).vc

    form = _CREATE_FORM | {"service_speed": 2000}
    result, process, step_log = run_workflow(
        "retry_reservation", [{"subscription_id": failed_mdp2p_subscription}, form, {}]
    )
    assert_awaiting_callback(result)
    result, step_log = resume_callback(process, step_log, {"status": "TERMINATED"})
    assert_awaiting_callback(result)
    result, _ = resume_callback(process, step_log, {"status": "RESERVED", "connectionId": "conn-2"})
    assert_complete(result)

    assert [name for name, _ in calls] == ["terminate", "reserve"]
    assert calls[0][1] == "conn-1"

    after = MultiDomainPoint2Point.from_subscription(failed_mdp2p_subscription).vc
    assert after.state == "RESERVED"
    assert after.connection_id == "conn-2"
    assert after.service_speed == 2000
    # A fresh id, or the proxy would dedup on the old one and ignore every correction.
    assert after.global_reservation_id != before.global_reservation_id


@pytest.mark.parametrize("state", ["RESERVED", "ACTIVATED"])
def test_retry_reservation_refuses_a_live_connection(mdp2p_subscription: str, state: str) -> None:
    """Retrying tears the connection down, so it must be unreachable while one is actually held."""
    from pydantic_forms.exceptions import FormValidationError

    from workflows.mdp2p import retry_reservation

    subscription = MultiDomainPoint2Point.from_subscription(mdp2p_subscription)
    subscription.vc.state = state
    subscription.save()

    with pytest.raises(FormValidationError, match="holds no reservation"):
        next(retry_reservation.initial_input_form_generator(mdp2p_subscription))


def test_provision_mdp2p(mdp2p_subscription: str) -> None:
    result, process, step_log = run_workflow("provision_mdp2p", [{"subscription_id": mdp2p_subscription}, {}])
    assert_awaiting_callback(result)

    result, _ = resume_callback(process, step_log, {"status": "ACTIVATED"})

    assert_complete(result)
    assert MultiDomainPoint2Point.from_subscription(mdp2p_subscription).vc.state == "ACTIVATED"


@pytest.fixture
def activated_mdp2p_subscription(mdp2p_subscription: str) -> str:
    result, process, step_log = run_workflow("provision_mdp2p", [{"subscription_id": mdp2p_subscription}, {}])
    result, _ = resume_callback(process, step_log, {"status": "ACTIVATED"})
    assert_complete(result)
    return mdp2p_subscription


def test_release_mdp2p(activated_mdp2p_subscription: str) -> None:
    result, process, step_log = run_workflow("release_mdp2p", [{"subscription_id": activated_mdp2p_subscription}, {}])
    assert_awaiting_callback(result)

    result, _ = resume_callback(process, step_log, {"status": "RESERVED"})

    assert_complete(result)
    assert MultiDomainPoint2Point.from_subscription(activated_mdp2p_subscription).vc.state == "RESERVED"


def test_modify_mdp2p(mdp2p_subscription: str) -> None:
    result, _, _ = run_workflow(
        "modify_mdp2p", [{"subscription_id": mdp2p_subscription}, {"circuit_description": "Renamed VC"}, {}]
    )

    assert_complete(result)
    assert MultiDomainPoint2Point.from_subscription(mdp2p_subscription).vc.circuit_description == "Renamed VC"


def test_validate_mdp2p(mdp2p_subscription: str, monkeypatch: pytest.MonkeyPatch) -> None:
    vc = MultiDomainPoint2Point.from_subscription(mdp2p_subscription).vc
    reservation = AggregatorReservation.model_validate(
        {
            "connectionId": "conn-1",
            "description": vc.circuit_description,
            "status": "RESERVED",
            "globalReservationId": vc.global_reservation_id,
            "criteria": {
                "p2ps": {"capacity": 1000, "sourceSTP": "urn:stp1?vlan=1500", "destSTP": "urn:stp2?vlan=2500"}
            },
        }
    )
    monkeypatch.setattr(aggregator_proxy, "get_reservation", lambda _cid: reservation)

    result, _, _ = run_workflow("validate_mdp2p", [{"subscription_id": mdp2p_subscription}])

    assert_complete(result)


def test_terminate_mdp2p(mdp2p_subscription: str) -> None:
    result, process, step_log = run_workflow("terminate_mdp2p", [{"subscription_id": mdp2p_subscription}, {}])
    assert_awaiting_callback(result)

    result, _ = resume_callback(process, step_log, {"status": "TERMINATED"})

    assert_complete(result)
    subscription = MultiDomainPoint2Point.from_subscription(mdp2p_subscription)
    assert subscription.vc.state == "TERMINATED"
    assert subscription.status == SubscriptionLifecycle.TERMINATED


def test_reconcile_mdp2p_syncs_state(mdp2p_subscription: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # The aggregator reports the connection drifted to ACTIVATED (a missed provision callback).
    monkeypatch.setattr(aggregator_proxy, "get_reservation", lambda _cid: SimpleNamespace(status="ACTIVATED"))

    result, _, _ = run_workflow("reconcile_mdp2p", [{"subscription_id": mdp2p_subscription}])

    assert_complete(result)
    assert MultiDomainPoint2Point.from_subscription(mdp2p_subscription).vc.state == "ACTIVATED"
