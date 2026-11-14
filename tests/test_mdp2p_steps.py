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
import inspect
from collections.abc import Callable
from datetime import datetime, timedelta
from types import ModuleType, SimpleNamespace

import pytest
from orchestrator.core.utils.datetime import nowtz
from orchestrator.core.utils.errors import InconsistentDataError
from orchestrator.core.workflow import Failed, Success, Waiting, make_step_function
from structlog.testing import capture_logs

from products.product_blocks.sdp_constraint import ConstraintType
from services.aggregator_proxy import AggregatorReservation
from tests import held_reservation


def _vc_sub(**vc_fields: object) -> SimpleNamespace:
    return SimpleNamespace(vc=SimpleNamespace(**vc_fields), description="stale")


@pytest.mark.parametrize(
    ("module_name", "func_name", "start_state", "callback_status", "expected_state", "expected_error"),
    [
        pytest.param(
            "create_mdp2p", "process_reservation_result", "CREATED", "RESERVED", "RESERVED", None, id="reserve-ok"
        ),
        pytest.param(
            "create_mdp2p", "process_reservation_result", "CREATED", "FAILED", "FAILED", "boom", id="reserve-failed"
        ),
        pytest.param(
            "provision_mdp2p",
            "process_provision_result",
            "RESERVED",
            "ACTIVATED",
            "ACTIVATED",
            None,
            id="provision-ok",
        ),
        pytest.param(
            "provision_mdp2p", "process_provision_result", "RESERVED", "FAILED", "FAILED", "boom", id="provision-failed"
        ),
        pytest.param(
            "release_mdp2p", "process_release_result", "ACTIVATED", "RESERVED", "RESERVED", None, id="release-ok"
        ),
        pytest.param(
            "release_mdp2p", "process_release_result", "ACTIVATED", "FAILED", "FAILED", "boom", id="release-failed"
        ),
    ],
)
def test_process_step_sets_state_and_refreshes_description(
    module_name: str,
    func_name: str,
    start_state: str,
    callback_status: str,
    expected_state: str,
    expected_error: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure stores the aggregator's lastError, a success clears it, and terminate keeps the last one."""
    module = importlib.import_module(f"workflows.mdp2p.{module_name}")
    monkeypatch.setattr(module, "description", lambda sub: f"desc({sub.vc.state})")
    step = module.__dict__[func_name].__wrapped__

    subscription = _vc_sub(state=start_state, connection_id="c1", last_error="earlier")
    result = step(subscription=subscription, callback_result={"status": callback_status, "lastError": "boom"})

    updated = result["subscription"]
    assert updated.vc.state == expected_state
    assert updated.vc.last_error == expected_error
    assert updated.description == f"desc({expected_state})"


@pytest.mark.parametrize("start_state", ["RESERVED", "FAILED"])
def test_record_terminated_keeps_the_last_error(start_state: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A terminated circuit still shows why it failed."""
    module = importlib.import_module("workflows.mdp2p.terminate_mdp2p")
    monkeypatch.setattr(module, "description", lambda sub: f"desc({sub.vc.state})")

    result = module.record_terminated.__wrapped__(
        subscription=_vc_sub(state=start_state, connection_id="c1", last_error="earlier")
    )

    assert result["subscription"].vc.state == "TERMINATED"
    assert result["subscription"].vc.last_error == "earlier"
    assert result["subscription"].description == "desc(TERMINATED)"


@pytest.mark.parametrize(
    ("aggregator_status", "resend_error", "expected_error"),
    [
        pytest.param("TERMINATED", None, None, id="terminated"),
        # A child that never confirmed: the aggregator is still terminating, whatever the callback said.
        pytest.param("TERMINATING", None, "TERMINATING.*a child did not reply.*sent again", id="still-terminating"),
        pytest.param("RESERVED", None, "RESERVED.*a child did not reply.*sent again", id="terminate-not-taken"),
        # The error an operator reads still names the aggregator's status when the proxy refuses the resend.
        pytest.param(
            "TERMINATING", "failed: 422", "TERMINATING.*a child did not reply.*not accepted.*422", id="refused"
        ),
    ],
)
def test_confirm_terminated(
    aggregator_status: str, resend_error: str | None, expected_error: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the aggregator's own TERMINATED counts; otherwise terminate is sent again and the step waits."""
    module = importlib.import_module("workflows.mdp2p.terminate_mdp2p")
    sent: list[tuple[object, ...]] = []

    def terminate(*args: object) -> None:
        sent.append(args)
        if resend_error:
            raise module.aggregator_proxy.AggregatorProxyError(resend_error)

    monkeypatch.setattr(
        module.aggregator_proxy,
        "get_reservation",
        lambda cid: SimpleNamespace(status=aggregator_status, last_error="a child did not reply"),
    )
    monkeypatch.setattr(module.aggregator_proxy, "terminate", terminate)
    step = inspect.unwrap(module.confirm_terminated)

    if expected_error is None:
        assert step(subscription={"vc": {"connection_id": "c1"}}) == {}
        assert sent == []
    else:
        with pytest.raises(module.TerminateNotConfirmedError, match=expected_error):
            step(subscription={"vc": {"connection_id": "c1"}})
        assert sent == [("c1",)]  # without a callbackURL: nothing awaits one


@pytest.mark.parametrize(
    ("inner", "deadline", "expected"),
    [
        pytest.param(Waiting(RuntimeError("no")), "2999-01-01T00:00:00+00:00", Waiting, id="waits-before-the-deadline"),
        pytest.param(Waiting(RuntimeError("no")), None, Waiting, id="waits-without-a-deadline"),
        pytest.param(Waiting(RuntimeError("no")), "2020-01-01T00:00:00+00:00", Failed, id="fails-past-the-deadline"),
        pytest.param(Success({}), "2020-01-01T00:00:00+00:00", Success, id="success-passes-through"),
    ],
)
def test_fail_after_deadline(inner: Waiting | Success, deadline: str | None, expected: type) -> None:
    """Only a step that is still waiting once the deadline has passed becomes a failure, naming why."""
    module = importlib.import_module("workflows.mdp2p.terminate_mdp2p")
    step = module.fail_after_deadline(make_step_function(lambda _state: inner, "inner"))

    result = step({} if deadline is None else {"terminate_confirm_deadline": deadline})
    carried = str(result.unwrap())

    assert type(result) is expected
    if expected is Failed:
        assert carried == "no; gave up waiting"


def test_process_terminate_result_sets_the_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deadline is ``terminate_confirm_timeout`` after the callback, in the state for every later attempt."""
    module = importlib.import_module("workflows.mdp2p.terminate_mdp2p")
    monkeypatch.setattr(module.settings, "terminate_confirm_timeout", 3600)

    before = nowtz()
    result = module.process_terminate_result.__wrapped__(
        subscription={"vc": {"connection_id": "c1"}}, callback_result={"status": "TERMINATING"}
    )
    after = nowtz()

    deadline = datetime.fromisoformat(result["terminate_confirm_deadline"])
    assert before + timedelta(hours=1) <= deadline <= after + timedelta(hours=1)


@pytest.mark.parametrize(
    ("start_state", "aggregator_status", "expected_state", "expected_error", "logs_left_alone"),
    [
        pytest.param("RESERVED", "FAILED", "FAILED", "aggregator says", False, id="drift-synced"),
        pytest.param("RESERVED", "ACTIVATING", "RESERVED", "earlier", True, id="transient-left-alone"),
        pytest.param("RESERVED", "TERMINATING", "RESERVED", "earlier", True, id="terminating-left-alone"),
        pytest.param("FAILED", "FAILED", "FAILED", "aggregator says", False, id="in-sync-error-backfilled"),
    ],
)
def test_reconcile_connection_state(
    start_state: str,
    aggregator_status: str,
    expected_state: str,
    expected_error: str,
    logs_left_alone: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any stable aggregator status brings its lastError along; a transient one leaves both alone, and says so."""
    module = importlib.import_module("workflows.mdp2p.reconcile_mdp2p")
    monkeypatch.setattr(module, "description", lambda sub: f"desc({sub.vc.state})")
    monkeypatch.setattr(
        module.aggregator_proxy,
        "get_reservation",
        lambda _cid: SimpleNamespace(status=aggregator_status, last_error="aggregator says"),
    )
    step = module.reconcile_connection_state.__wrapped__

    subscription = _vc_sub(state=start_state, connection_id="c1", last_error="earlier")
    with capture_logs() as logs:
        result = step(subscription=subscription)

    assert result["subscription"].vc.state == expected_state
    assert result["subscription"].vc.last_error == expected_error
    left_alone = [log for log in logs if "left alone" in log["event"]]
    assert [(log["connection_id"], log["aggregator_status"], log["stored_state"]) for log in left_alone] == (
        [("c1", aggregator_status, start_state)] if logs_left_alone else []
    )


def _sdp_constraint(vlan: int | None, constraint_type: ConstraintType = ConstraintType.INCLUDE) -> SimpleNamespace:
    """An SDP constraint on the a <-> b SDP, pinned to ``vlan`` when it is not None."""
    stps = [SimpleNamespace(stp_id="urn:a:to-b"), SimpleNamespace(stp_id="urn:b:to-a")]
    return SimpleNamespace(constraint_type=constraint_type, vlan=vlan, sdp=SimpleNamespace(stps=stps))


def _validate_subscription_and_reservation(
    sdp_vlan: int | None = None,
) -> tuple[SimpleNamespace, AggregatorReservation]:
    """A RESERVED connection a -> b over the a <-> b SDP, whose path holds ``sdp_vlan`` (1800 if None)."""
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
            sdp_constraints=[_sdp_constraint(sdp_vlan)],
        )
    )
    path_vlan = 1800 if sdp_vlan is None else sdp_vlan
    reservation = held_reservation(
        "RESERVED", "urn:a?vlan=100", "urn:b?vlan=200", sdps=[("urn:a:to-b", "urn:b:to-a", path_vlan)]
    )
    reservation.global_reservation_id = "urn:uuid:1"
    return subscription, reservation


def _install_reservation(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, reservation: AggregatorReservation
) -> None:
    def get_reservation(_cid: str, *, with_segments: bool = False) -> AggregatorReservation:
        assert with_segments, "the pinned SDP VLANs are only in the segments"
        return reservation

    monkeypatch.setattr(module.aggregator_proxy, "get_reservation", get_reservation)


@pytest.mark.parametrize("sdp_vlan", [pytest.param(None, id="unpinned"), pytest.param(1800, id="pinned")])
def test_validate_reservation_passes_when_matching(sdp_vlan: int | None, monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("workflows.mdp2p.validate_mdp2p")
    subscription, reservation = _validate_subscription_and_reservation(sdp_vlan)
    _install_reservation(monkeypatch, module, reservation)

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
    mutate: Callable[[AggregatorReservation], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("workflows.mdp2p.validate_mdp2p")
    subscription, reservation = _validate_subscription_and_reservation()
    mutate(reservation)
    _install_reservation(monkeypatch, module, reservation)

    with pytest.raises(InconsistentDataError):
        module.validate_reservation.__wrapped__(subscription=subscription)


@pytest.mark.parametrize(
    ("state", "segments", "raises"),
    [
        pytest.param("RESERVED", [("urn:a:to-b", "urn:b:to-a", 1801)], True, id="other-vlan-on-the-sdp"),
        pytest.param("ACTIVATED", [("urn:a:to-b", "urn:b:to-a", 1801)], True, id="activated-other-vlan"),
        pytest.param("RESERVED", [], True, id="path-without-the-sdp"),
        pytest.param("FAILED", [], False, id="failed-holds-no-path"),
    ],
)
def test_validate_reservation_checks_a_pinned_sdp_vlan(
    state: str, segments: list[tuple[str, str, int]], raises: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("workflows.mdp2p.validate_mdp2p")
    subscription, _ = _validate_subscription_and_reservation(sdp_vlan=1800)
    subscription.vc.state = state
    reservation = held_reservation(state, "urn:a?vlan=100", "urn:b?vlan=200", sdps=segments)
    reservation.global_reservation_id = "urn:uuid:1"
    _install_reservation(monkeypatch, module, reservation)

    if raises:
        with pytest.raises(InconsistentDataError, match=r"pinned SDP VLAN on: urn:a:to-b\?vlan=1800, urn:b:to-a"):
            module.validate_reservation.__wrapped__(subscription=subscription)
    else:
        module.validate_reservation.__wrapped__(subscription=subscription)


def test_validate_reservation_ignores_an_excluded_sdp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only an included SDP is on the path; an excluded one carries no VLAN to hold."""
    module = importlib.import_module("workflows.mdp2p.validate_mdp2p")
    subscription, reservation = _validate_subscription_and_reservation()
    subscription.vc.sdp_constraints = [_sdp_constraint(1900, ConstraintType.EXCLUDE)]
    _install_reservation(monkeypatch, module, reservation)

    module.validate_reservation.__wrapped__(subscription=subscription)
