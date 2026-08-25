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


def _topology_subscription() -> SimpleNamespace:
    return SimpleNamespace(topology=SimpleNamespace(topology_id="present"))


def test_validate_topology_passes_when_advertised(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("workflows.topology.validate_topology")
    monkeypatch.setattr(module, "fetch_topologies", lambda: [SimpleNamespace(id="present")])

    subscription = _topology_subscription()
    result = module.validate_topology_present_in_dds.__wrapped__(subscription=subscription)
    assert result["subscription"] is subscription


@pytest.mark.parametrize(
    "advertised",
    [
        pytest.param([], id="nothing-advertised"),
        pytest.param([SimpleNamespace(id="something-else")], id="no-longer-advertised"),
    ],
)
def test_validate_topology_raises_when_gone(advertised: list[SimpleNamespace], monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("workflows.topology.validate_topology")
    monkeypatch.setattr(module, "fetch_topologies", lambda: advertised)

    with pytest.raises(AssertionError):
        module.validate_topology_present_in_dds.__wrapped__(subscription=_topology_subscription())


def _dds_switching_service(topology_id: str = "urn:t1") -> SimpleNamespace:
    return SimpleNamespace(id="present", topology_id=topology_id)


def _switchingservice_subscription() -> SimpleNamespace:
    return SimpleNamespace(
        switchingservice=SimpleNamespace(switching_service_id="present", topology=SimpleNamespace(topology_id="urn:t1"))
    )


def test_validate_switchingservice_passes_when_parent_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("workflows.switchingservice.validate_switchingservice")
    monkeypatch.setattr(module, "fetch_switching_services", lambda: [_dds_switching_service()])

    subscription = _switchingservice_subscription()
    result = module.validate_switchingservice_present_in_dds.__wrapped__(subscription=subscription)
    assert result["subscription"] is subscription


@pytest.mark.parametrize(
    "advertised",
    [
        pytest.param([], id="no-longer-advertised"),
        pytest.param([_dds_switching_service(topology_id="urn:other")], id="topology-drift"),
    ],
)
def test_validate_switchingservice_raises_on_drift(
    advertised: list[SimpleNamespace], monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("workflows.switchingservice.validate_switchingservice")
    monkeypatch.setattr(module, "fetch_switching_services", lambda: advertised)

    with pytest.raises(AssertionError):
        module.validate_switchingservice_present_in_dds.__wrapped__(subscription=_switchingservice_subscription())


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


def _dds_stp(
    capacity_mbits: int = 1000, label_group: str = "1000-1999", switching_service_id: str = "urn:ss1"
) -> SimpleNamespace:
    return SimpleNamespace(
        id="urn:stp1",
        capacity_mbits=capacity_mbits,
        label_group=label_group,
        switching_service_id=switching_service_id,
    )


def _stp_subscription() -> SimpleNamespace:
    return SimpleNamespace(
        stp=SimpleNamespace(
            stp_id="urn:stp1",
            capacity=1000,
            label_group="1000-1999",
            switching_service=SimpleNamespace(switching_service_id="urn:ss1"),
        )
    )


def test_validate_stp_passes_when_attributes_match(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("workflows.stp.validate_stp")
    monkeypatch.setattr(module, "fetch_service_termination_points", lambda: [_dds_stp()])

    subscription = _stp_subscription()
    assert module.validate_stp_present_in_dds.__wrapped__(subscription=subscription)["subscription"] is subscription


@pytest.mark.parametrize(
    "advertised",
    [
        pytest.param([], id="no-longer-advertised"),
        pytest.param([_dds_stp(capacity_mbits=5000)], id="capacity-drift"),
        pytest.param([_dds_stp(label_group="3000-3999")], id="vlan-range-drift"),
        pytest.param([_dds_stp(switching_service_id="urn:other-ss")], id="switching-service-drift"),
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
        lambda: [SimpleNamespace(id=advertised_id, capacity_mbits=4000, label_group="2000-2999")],
    )

    subscription = SimpleNamespace(stp=SimpleNamespace(stp_id="x", capacity=1000, label_group="1000-1999"))
    result = module.reconcile_dds_attributes.__wrapped__(subscription=subscription)

    assert result["subscription"].stp.capacity == expected_capacity
    assert result["subscription"].stp.label_group == expected_label_group
