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

# (module path, validate step, dds fetch name, a subscription whose id is "present")
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
    pytest.param(
        "workflows.stp.validate_stp",
        "validate_stp_present_in_dds",
        "fetch_service_termination_points",
        SimpleNamespace(stp=SimpleNamespace(stp_id="present")),
        id="stp",
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


@pytest.mark.parametrize(
    ("advertised_id", "expected_capacity"),
    [
        pytest.param("x", 4000, id="advertised-capacity-applied"),
        pytest.param("other", 1000, id="not-advertised-left-unchanged"),
    ],
)
def test_reconcile_stp_capacity(advertised_id: str, expected_capacity: int, monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("workflows.stp.reconcile_stp")
    monkeypatch.setattr(
        module, "fetch_service_termination_points", lambda: [SimpleNamespace(id=advertised_id, capacity=4000)]
    )

    subscription = SimpleNamespace(stp=SimpleNamespace(stp_id="x", capacity=1000))
    result = module.reconcile_capacity.__wrapped__(subscription=subscription)

    assert result["subscription"].stp.capacity == expected_capacity
