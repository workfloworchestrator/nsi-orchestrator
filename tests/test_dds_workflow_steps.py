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

"""Unit tests for the dds-proxy-backed validate and reconcile step functions.

Each step's raw (``__wrapped__``) function is called with a stubbed subscription and a monkeypatched
dds-proxy fetch, so the assert/update logic is exercised without a database.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

# Presence-only validators (module path, validate step, dds fetch name, a subscription whose id is
# "present"). STP is not here: it also validates capacity/label_group, so it has dedicated tests below.
_ID_VALIDATORS = [
    pytest.param(
        "workflows.topology.validate_topology",
        "validate_topology_present_in_dds",
        "fetch_topologies",
        SimpleNamespace(topology=SimpleNamespace(topology_id="present")),
        id="topology",
    ),
    pytest.param(
        "workflows.switchingservice.validate_switchingservice",
        "validate_switchingservice_present_in_dds",
        "fetch_switching_services",
        SimpleNamespace(switchingservice=SimpleNamespace(switching_service_id="present")),
        id="switchingservice",
    ),
]


@pytest.mark.parametrize(("module_path", "func_name", "fetch_name", "subscription"), _ID_VALIDATORS)
def test_validate_present_in_dds_passes_when_advertised(
    module_path: str, func_name: str, fetch_name: str, subscription: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module(module_path)
    monkeypatch.setattr(module, fetch_name, lambda: [SimpleNamespace(id="present")])

    assert module.__dict__[func_name].__wrapped__(subscription=subscription)["subscription"] is subscription


@pytest.mark.parametrize(("module_path", "func_name", "fetch_name", "subscription"), _ID_VALIDATORS)
def test_validate_present_in_dds_raises_when_gone(
    module_path: str, func_name: str, fetch_name: str, subscription: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module(module_path)
    monkeypatch.setattr(module, fetch_name, lambda: [SimpleNamespace(id="something-else")])

    with pytest.raises(AssertionError):
        module.__dict__[func_name].__wrapped__(subscription=subscription)


def _sdp_subscription() -> SimpleNamespace:
    return SimpleNamespace(sdp=SimpleNamespace(stps=[SimpleNamespace(stp_id="a"), SimpleNamespace(stp_id="b")]))


def test_validate_sdp_passes_when_pair_present(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("workflows.sdp.validate_sdp")
    # The pair is order-independent (a frozenset), so b<->a still matches.
    monkeypatch.setattr(
        module, "fetch_service_demarcation_points", lambda: [SimpleNamespace(stp_a_id="b", stp_z_id="a")]
    )

    subscription = _sdp_subscription()
    assert module.validate_sdp_present_in_dds.__wrapped__(subscription=subscription)["subscription"] is subscription


def test_validate_sdp_raises_when_pair_gone(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("workflows.sdp.validate_sdp")
    monkeypatch.setattr(
        module, "fetch_service_demarcation_points", lambda: [SimpleNamespace(stp_a_id="a", stp_z_id="c")]
    )

    with pytest.raises(AssertionError):
        module.validate_sdp_present_in_dds.__wrapped__(subscription=_sdp_subscription())


def _dds_stp(capacity: int = 1000, label_group: str = "1000-1999") -> SimpleNamespace:
    return SimpleNamespace(id="urn:stp1", capacity=capacity, label_group=label_group)


def _stp_subscription() -> SimpleNamespace:
    return SimpleNamespace(stp=SimpleNamespace(stp_id="urn:stp1", capacity=1000, label_group="1000-1999"))


def test_validate_stp_passes_when_attributes_match(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("workflows.stp.validate_stp")
    monkeypatch.setattr(module, "fetch_service_termination_points", lambda: [_dds_stp()])

    subscription = _stp_subscription()
    assert module.validate_stp_present_in_dds.__wrapped__(subscription=subscription)["subscription"] is subscription


@pytest.mark.parametrize(
    "advertised",
    [
        pytest.param([], id="no-longer-advertised"),
        pytest.param([_dds_stp(capacity=5000)], id="capacity-drift"),
        pytest.param([_dds_stp(label_group="3000-3999")], id="vlan-range-drift"),
    ],
)
def test_validate_stp_raises_on_drift(advertised: list[SimpleNamespace], monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("workflows.stp.validate_stp")
    monkeypatch.setattr(module, "fetch_service_termination_points", lambda: advertised)

    with pytest.raises(AssertionError):
        module.validate_stp_present_in_dds.__wrapped__(subscription=_stp_subscription())


@pytest.mark.parametrize(
    ("advertised_id", "expected_capacity", "expected_label_group"),
    [
        pytest.param("x", 4000, "2000-2999", id="advertised-attributes-applied"),
        pytest.param("other", 1000, "1000-1999", id="not-advertised-left-unchanged"),
    ],
)
def test_reconcile_stp_dds_attributes(
    advertised_id: str, expected_capacity: int, expected_label_group: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("workflows.stp.reconcile_stp")
    monkeypatch.setattr(
        module,
        "fetch_service_termination_points",
        lambda: [SimpleNamespace(id=advertised_id, capacity=4000, label_group="2000-2999")],
    )

    subscription = SimpleNamespace(stp=SimpleNamespace(stp_id="x", capacity=1000, label_group="1000-1999"))
    result = module.reconcile_dds_attributes.__wrapped__(subscription=subscription)

    assert result["subscription"].stp.capacity == expected_capacity
    assert result["subscription"].stp.label_group == expected_label_group
