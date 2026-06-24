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

"""Tests for the multi domain point-to-point form helpers."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic_forms.exceptions import FormValidationError

from services.aggregator_proxy import AggregatorReservation
from workflows.mdp2p.shared import forms
from workflows.mdp2p.shared.forms import (
    available_vlan_ranges,
    stp_selector,
    vlan_in_label_group,
    vlans_in_use_by_stp,
)


@pytest.mark.parametrize(
    ("vlan", "label_group", "expected"),
    [
        pytest.param(1500, "1000-1999", True, id="in-single-range"),
        pytest.param(1000, "1000-1999", True, id="low-boundary"),
        pytest.param(1999, "1000-1999", True, id="high-boundary"),
        pytest.param(999, "1000-1999", False, id="below-range"),
        pytest.param(2000, "1000-1999", False, id="above-range"),
        pytest.param(250, "100,200-300", True, id="in-second-of-multi"),
        pytest.param(100, "100,200-300", True, id="single-value-member"),
        pytest.param(150, "100,200-300", False, id="gap-between-ranges"),
        pytest.param(42, "", False, id="empty-label-group-allows-nothing"),
    ],
)
def test_vlan_in_label_group(vlan: int, label_group: str, expected: bool) -> None:
    assert vlan_in_label_group(vlan, label_group) is expected


def test_stp_selector_labels_show_free_vlan_range_and_sdp_marker() -> None:
    stps = [
        SimpleNamespace(stp_id="urn:ogf:network:x", stp_name="Port X", label_group="1000-1999"),
        SimpleNamespace(stp_id="urn:ogf:network:y", stp_name="Port Y", label_group="2000-2999"),
    ]
    # stp_selector only reads stp_id/stp_name/label_group, so duck-typed stubs stand in for STP blocks.
    choice = stp_selector(
        stps,  # type: ignore[arg-type]
        used_in_sdp={"urn:ogf:network:x"},
        in_use_by_stp={"urn:ogf:network:x": {1500}},
    )

    members = choice.__members__
    # Keyed by stp id, so the construct step can resolve the block.
    assert set(members) == {"urn:ogf:network:x", "urn:ogf:network:y"}
    # The label shows the free VLAN range (1500 is in use, so removed) and marks the in-SDP STP.
    assert members["urn:ogf:network:x"].label == "Port X (VLAN 1000-1499,1501-1999, in SDP)"
    assert members["urn:ogf:network:y"].label == "Port Y (VLAN 2000-2999)"


@pytest.mark.parametrize(
    ("label_group", "in_use", "expected"),
    [
        pytest.param("1000-1999", set(), "1000-1999", id="nothing-in-use"),
        pytest.param("1000-1999", {1500}, "1000-1499,1501-1999", id="one-in-use-splits-range"),
        pytest.param("1000-1002", {1001}, "1000,1002", id="single-gap"),
        pytest.param("100,200-202", {201}, "100,200,202", id="multi-range-source"),
        pytest.param("1000-1002", {1000, 1001, 1002}, "none available", id="all-in-use"),
    ],
)
def test_available_vlan_ranges(label_group: str, in_use: set[int], expected: str) -> None:
    assert available_vlan_ranges(label_group, in_use) == expected


_SUB_ID = "11111111-1111-1111-1111-111111111111"
_CUST_ID = "22222222-2222-2222-2222-222222222222"

# (module, a state the action is allowed from, a state it must be rejected from)
_MDP2P_ACTION_FORMS = [
    pytest.param("provision_mdp2p", "RESERVED", "ACTIVATED", id="provision"),
    pytest.param("release_mdp2p", "ACTIVATED", "RESERVED", id="release"),
    pytest.param("terminate_mdp2p", "RESERVED", "ACTIVATED", id="terminate"),
]


def _patch_state(monkeypatch: pytest.MonkeyPatch, module: object, state: str) -> None:
    monkeypatch.setattr(
        module.MultiDomainPoint2Point,  # type: ignore[attr-defined]
        "from_subscription",
        staticmethod(lambda _sid: SimpleNamespace(vc=SimpleNamespace(state=state))),
    )


def _build_form(module: object) -> object:
    # terminate returns the form directly; provision/release yield it from a generator.
    if hasattr(module, "terminate_initial_input_form_generator"):
        return module.terminate_initial_input_form_generator(_SUB_ID, _CUST_ID)
    return next(module.initial_input_form_generator(_SUB_ID))  # type: ignore[attr-defined]


@pytest.mark.parametrize(("module_name", "valid_state", "wrong_state"), _MDP2P_ACTION_FORMS)
def test_mdp2p_action_form_builds_in_valid_state(
    module_name: str, valid_state: str, wrong_state: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module(f"workflows.mdp2p.{module_name}")
    _patch_state(monkeypatch, module, valid_state)
    assert "subscription_id" in _build_form(module).model_fields  # type: ignore[attr-defined]


@pytest.mark.parametrize(("module_name", "valid_state", "wrong_state"), _MDP2P_ACTION_FORMS)
def test_mdp2p_action_form_gate_rejects_wrong_state(
    module_name: str, valid_state: str, wrong_state: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module(f"workflows.mdp2p.{module_name}")
    _patch_state(monkeypatch, module, wrong_state)
    with pytest.raises(FormValidationError):
        _build_form(module)


def test_vlans_in_use_by_stp_holds_failed_but_releases_terminated() -> None:
    def reservation(status: str, source_vlan: int, dest_vlan: int) -> AggregatorReservation:
        return AggregatorReservation.model_validate(
            {
                "connectionId": "c",
                "description": "d",
                "status": status,
                "criteria": {
                    "p2ps": {
                        "capacity": 1000,
                        "sourceSTP": f"urn:a?vlan={source_vlan}",
                        "destSTP": f"urn:b?vlan={dest_vlan}",
                    }
                },
            }
        )

    reservations = [
        reservation("RESERVED", 1500, 2500),
        reservation("FAILED", 1600, 2600),  # FAILED still holds its VLANs
        reservation("TERMINATED", 1700, 2700),  # TERMINATED has released them
    ]
    with patch.object(forms, "list_reservations", return_value=reservations):
        in_use = vlans_in_use_by_stp()

    assert in_use == {"urn:a": {1500, 1600}, "urn:b": {2500, 2600}}
