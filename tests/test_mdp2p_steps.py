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

"""Unit tests for the MDP2P workflow step functions.

These call each step's raw (``__wrapped__``) function with a stubbed subscription and a mocked
aggregator, so they exercise the step logic without a database. The subscription description service
is monkeypatched per module to avoid singledispatch on a real lifecycle model.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from types import SimpleNamespace

import pytest


def _vc_sub(**vc_fields: object) -> SimpleNamespace:
    return SimpleNamespace(vc=SimpleNamespace(**vc_fields), description="stale")


@pytest.mark.parametrize(
    ("module_name", "func_name", "start_state", "callback_status", "expected_state"),
    [
        pytest.param("create_mdp2p", "process_reservation_result", "CREATED", "RESERVED", "RESERVED", id="reserve-ok"),
        pytest.param("create_mdp2p", "process_reservation_result", "CREATED", "FAILED", "FAILED", id="reserve-failed"),
        pytest.param(
            "provision_mdp2p", "process_provision_result", "RESERVED", "ACTIVATED", "ACTIVATED", id="provision-ok"
        ),
        pytest.param(
            "provision_mdp2p", "process_provision_result", "RESERVED", "FAILED", "FAILED", id="provision-failed"
        ),
        pytest.param("release_mdp2p", "process_release_result", "ACTIVATED", "RESERVED", "RESERVED", id="release-ok"),
        pytest.param("release_mdp2p", "process_release_result", "ACTIVATED", "FAILED", "FAILED", id="release-failed"),
        pytest.param(
            "terminate_mdp2p",
            "process_terminate_result",
            "RESERVED",
            "TERMINATED",
            "TERMINATED",
            id="terminate-reserved",
        ),
        pytest.param(
            "terminate_mdp2p", "process_terminate_result", "FAILED", "TERMINATED", "TERMINATED", id="terminate-failed"
        ),
    ],
)
def test_process_step_sets_state_and_refreshes_description(
    module_name: str,
    func_name: str,
    start_state: str,
    callback_status: str,
    expected_state: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module(f"workflows.mdp2p.{module_name}")
    monkeypatch.setattr(module, "description", lambda sub: f"desc({sub.vc.state})")
    step = module.__dict__[func_name].__wrapped__

    subscription = _vc_sub(state=start_state, connection_id="c1")
    result = step(subscription=subscription, callback_result={"status": callback_status, "lastError": "boom"})

    updated = result["subscription"]
    assert updated.vc.state == expected_state
    assert updated.description == f"desc({expected_state})"


@pytest.mark.parametrize(
    ("start_state", "aggregator_status", "expected_state"),
    [
        pytest.param("RESERVED", "ACTIVATED", "ACTIVATED", id="drift-synced"),
        pytest.param("RESERVED", "ACTIVATING", "RESERVED", id="transient-left-alone"),
        pytest.param("ACTIVATED", "ACTIVATED", "ACTIVATED", id="already-in-sync"),
    ],
)
def test_reconcile_connection_state(
    start_state: str, aggregator_status: str, expected_state: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("workflows.mdp2p.reconcile_mdp2p")
    monkeypatch.setattr(module, "description", lambda sub: f"desc({sub.vc.state})")
    monkeypatch.setattr(
        module.aggregator_proxy, "get_reservation", lambda _cid: SimpleNamespace(status=aggregator_status)
    )
    step = module.reconcile_connection_state.__wrapped__

    subscription = _vc_sub(state=start_state, connection_id="c1")
    result = step(subscription=subscription)

    assert result["subscription"].vc.state == expected_state


def _validate_subscription_and_reservation() -> tuple[SimpleNamespace, SimpleNamespace]:
    subscription = SimpleNamespace(
        vc=SimpleNamespace(
            connection_id="c1",
            state="RESERVED",
            global_reservation_id="urn:uuid:1",
            service_speed=1000,
            saps=[
                SimpleNamespace(stp=SimpleNamespace(stp_id="urn:a"), vlan="100"),
                SimpleNamespace(stp=SimpleNamespace(stp_id="urn:b"), vlan="200"),
            ],
        )
    )
    reservation = SimpleNamespace(
        status="RESERVED",
        global_reservation_id="urn:uuid:1",
        criteria=SimpleNamespace(
            p2ps=SimpleNamespace(capacity=1000, source_stp="urn:a?vlan=100", dest_stp="urn:b?vlan=200")
        ),
    )
    return subscription, reservation


def test_validate_reservation_passes_when_matching(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("workflows.mdp2p.validate_mdp2p")
    subscription, reservation = _validate_subscription_and_reservation()
    monkeypatch.setattr(module.aggregator_proxy, "get_reservation", lambda _cid: reservation)

    assert module.validate_reservation.__wrapped__(subscription=subscription)["subscription"] is subscription


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda r: setattr(r, "status", "ACTIVATED"), id="status"),
        pytest.param(lambda r: setattr(r, "global_reservation_id", "urn:uuid:other"), id="global-reservation-id"),
        pytest.param(lambda r: setattr(r.criteria.p2ps, "capacity", 999), id="capacity"),
        pytest.param(lambda r: setattr(r.criteria.p2ps, "source_stp", "urn:a?vlan=999"), id="source-vlan"),
        pytest.param(lambda r: setattr(r.criteria.p2ps, "dest_stp", "urn:c?vlan=200"), id="dest-stp"),
    ],
)
def test_validate_reservation_raises_on_mismatch(
    mutate: Callable[[SimpleNamespace], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("workflows.mdp2p.validate_mdp2p")
    subscription, reservation = _validate_subscription_and_reservation()
    mutate(reservation)
    monkeypatch.setattr(module.aggregator_proxy, "get_reservation", lambda _cid: reservation)

    with pytest.raises(AssertionError):
        module.validate_reservation.__wrapped__(subscription=subscription)
