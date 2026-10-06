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
from typing import cast
from unittest.mock import patch

import pytest
from orchestrator.core.forms import FormPage
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


_A = "urn:ogf:network:a.example.net:2025:topology"
_B = "urn:ogf:network:b.example.net:2025:topology"
_C = "urn:ogf:network:c.example.net:2025:topology"
_SDP_AB = "11111111-1111-1111-1111-111111111111"
_SDP_BC = "22222222-2222-2222-2222-222222222222"

# A three-domain chain A <-> B <-> C, with an SDP subscription for each hop. The ends of A <-> B
# advertise overlapping but different ranges, so only 1500-1999 is usable on that SDP.
_PATH_TOPOLOGY = forms.SdpTopology(
    names={_SDP_AB: "A <-> B", _SDP_BC: "B <-> C"},
    stps={_SDP_AB: (f"{_A}:to-b", f"{_B}:to-a"), _SDP_BC: (f"{_B}:to-c", f"{_C}:to-b")},
    label_groups={_SDP_AB: ("1000-1999", "1500-2500"), _SDP_BC: ("2000-2999", "2000-2999")},
)
_EDGE_STPS = [
    SimpleNamespace(stp_id=f"{_A}:customer", stp_name="A edge", label_group="1000-1999"),
    SimpleNamespace(stp_id=f"{_C}:customer", stp_name="C edge", label_group="1000-1999"),
]


def _create_form(monkeypatch: pytest.MonkeyPatch, topology: forms.SdpTopology, stps: list) -> type[FormPage]:
    """The create form, with the topology and STP inventory it would otherwise load from the DB."""
    create = importlib.import_module("workflows.mdp2p.create_mdp2p")
    monkeypatch.setattr(create, "fetch_vlans_in_use", dict)
    monkeypatch.setattr(forms, "subscribed_stps", lambda: stps)
    monkeypatch.setattr(create, "sdp_topology", lambda: topology)
    return cast("type[FormPage]", next(create.initial_input_form_generator("MDP2P")))


def _form_values(**overrides: object) -> dict:
    return {
        "circuit_description": "demo",
        "service_speed": 1000,
        "source_stp": f"{_A}:customer",
        "source_vlan": 1001,
        "destination_stp": f"{_C}:customer",
        "destination_vlan": 1002,
        "include_sdps": [],
        "exclude_sdps": [],
    } | overrides


@pytest.mark.parametrize("field", ["include_sdps", "exclude_sdps"])
def test_create_form_sdp_constraints_carry_an_empty_array_default(field: str, monkeypatch: pytest.MonkeyPatch) -> None:
    form = _create_form(monkeypatch, _PATH_TOPOLOGY, _EDGE_STPS)

    # A default_factory would leave "default" out of the schema, and the UI then submits the untouched
    # field as undefined instead of an empty array, failing client-side validation.
    assert form.model_json_schema()["properties"][field]["default"] == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        pytest.param({"include_sdps": [_SDP_AB, _SDP_BC]}, None, id="sdps-in-path-order"),
        pytest.param(
            {"exclude_sdps": [_SDP_AB]},
            "not yet supported by the aggregator",
            id="exclusion-is-dropped-by-safnari-so-must-be-refused",
        ),
        pytest.param(
            {"include_sdps": [_SDP_BC, _SDP_AB]},
            "cannot be traversed in this order",
            id="B-C-before-A-B-doubles-back",
        ),
    ],
)
def test_create_form_path_constraints(overrides: dict, message: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    form = _create_form(monkeypatch, _PATH_TOPOLOGY, _EDGE_STPS)
    if message is None:
        assert form(**_form_values(**overrides)) is not None
    else:
        with pytest.raises(ValueError, match=message):
            form(**_form_values(**overrides))


def _reservation(
    status: str, source_vlan: int, dest_vlan: int, connection_id: str = "c", segments: list[dict] | None = None
) -> AggregatorReservation:
    return AggregatorReservation.model_validate(
        {
            "connectionId": connection_id,
            "description": "d",
            "status": status,
            "criteria": {
                "p2ps": {
                    "capacity": 1000,
                    "sourceSTP": f"urn:a?vlan={source_vlan}",
                    "destSTP": f"urn:b?vlan={dest_vlan}",
                }
            },
            "segments": segments,
        }
    )


def test_vlans_in_use_by_stp_holds_failed_but_releases_terminated() -> None:
    reservations = [
        _reservation("RESERVED", 1500, 2500),
        _reservation("FAILED", 1600, 2600),  # FAILED still holds its VLANs
        _reservation("TERMINATED", 1700, 2700),  # TERMINATED has released them
    ]
    with patch.object(forms, "list_reservations", return_value=reservations) as listed:
        in_use = vlans_in_use_by_stp()

    assert in_use == {"urn:a": {1500, 1600}, "urn:b": {2500, 2600}}
    listed.assert_called_once_with(with_segments=True)


def test_vlans_in_use_by_stp_includes_the_sdps_along_each_path() -> None:
    # A two-domain path: the segments add the SDP between them, at both ends, on its own VLAN.
    segments: list[dict] = [
        {"order": 0, "sourceSTP": "urn:a?vlan=1500", "destSTP": "urn:a:to-b?vlan=1800"},
        {"order": 1, "sourceSTP": "urn:b:to-a?vlan=1800", "destSTP": "urn:b?vlan=2500"},
        {"order": 2, "sourceSTP": None, "destSTP": None},  # a segment the aggregator reports without STPs
    ]
    reservation = _reservation("RESERVED", 1500, 2500, segments=segments)
    with patch.object(forms, "list_reservations", return_value=[reservation]):
        in_use = vlans_in_use_by_stp()

    assert in_use == {"urn:a": {1500}, "urn:a:to-b": {1800}, "urn:b:to-a": {1800}, "urn:b": {2500}}


def test_vlans_in_use_by_stp_leaves_out_the_released_connection() -> None:
    segments = [{"order": 0, "sourceSTP": "urn:a:to-b?vlan=1800", "destSTP": "urn:b:to-a?vlan=1800"}]
    reservations = [
        _reservation("FAILED", 1500, 2500, connection_id="retried", segments=segments),
        _reservation("RESERVED", 1600, 2600, connection_id="other"),
    ]
    with patch.object(forms, "list_reservations", return_value=reservations):
        in_use = vlans_in_use_by_stp(released_connection_id="retried")

    assert in_use == {"urn:a": {1600}, "urn:b": {2600}}


@pytest.mark.parametrize(
    ("sdp_id", "expected"),
    [
        pytest.param(_SDP_AB, "1500-1999", id="overlap-of-different-ranges"),
        pytest.param(_SDP_BC, "2000-2999", id="identical-ranges"),
    ],
)
def test_common_vlans_is_what_both_ends_allow(sdp_id: str, expected: str) -> None:
    assert _PATH_TOPOLOGY.common_vlans(sdp_id) == expected


@pytest.mark.parametrize(
    ("sdp_vlans", "expected"),
    [
        pytest.param(None, [f"{_A}:to-b", f"{_B}:to-c"], id="no-vlans-leaves-the-choice-to-the-pce"),
        pytest.param([None, None], [f"{_A}:to-b", f"{_B}:to-c"], id="all-empty"),
        pytest.param([1700, None], [f"{_A}:to-b?vlan=1700", f"{_B}:to-c"], id="first-pinned"),
        pytest.param([1700, 2100], [f"{_A}:to-b?vlan=1700", f"{_B}:to-c?vlan=2100"], id="both-pinned"),
    ],
)
def test_ero_pins_the_vlan_on_the_source_facing_stp(sdp_vlans: list[int | None] | None, expected: list[str]) -> None:
    source, destination = f"{_A}:customer", f"{_C}:customer"
    assert _PATH_TOPOLOGY.ero(source, destination, [_SDP_AB, _SDP_BC], sdp_vlans) == expected


@pytest.mark.parametrize(
    ("sdp_vlans", "expected"),
    [
        pytest.param(None, "A <-> B, B <-> C", id="no-vlans"),
        pytest.param([1700, None], "A <-> B (VLAN 1700), B <-> C", id="one-pinned"),
    ],
)
def test_path_summary_shows_pinned_vlans(sdp_vlans: list[int | None] | None, expected: str) -> None:
    assert forms.path_summary(_PATH_TOPOLOGY, [_SDP_AB, _SDP_BC], sdp_vlans) == expected


# 1600 is held on the A end of A <-> B, 2100 on the C end of B <-> C, 1700 on an unrelated STP.
_IN_USE = {f"{_A}:to-b": {1600}, f"{_C}:to-b": {2100}, f"{_A}:customer": {1700}}


@pytest.mark.parametrize(
    ("values", "message"),
    [
        pytest.param({}, None, id="all-optional"),
        pytest.param({"sdp_vlan_1": 1500, "sdp_vlan_2": 2999}, None, id="range-boundaries"),
        pytest.param({"sdp_vlan_1": 1200}, r"both ends of the SDP allow \(1500-1999\)", id="only-one-end-allows-it"),
        pytest.param({"sdp_vlan_2": 1999}, r"both ends of the SDP allow \(2000-2999\)", id="outside-both-ends"),
        pytest.param({"sdp_vlan_1": 4095}, "less than or equal to 4094", id="not-a-vlan"),
        pytest.param({"sdp_vlan_1": 1600}, "already in use on the SDP", id="in-use-on-the-near-end"),
        pytest.param({"sdp_vlan_2": 2100}, "already in use on the SDP", id="in-use-on-the-far-end"),
        pytest.param({"sdp_vlan_1": 1700}, None, id="in-use-elsewhere-only"),
    ],
)
def test_sdp_vlan_form_validates_against_the_sdp(values: dict, message: str | None) -> None:
    form = forms.sdp_vlan_form(_PATH_TOPOLOGY, [_SDP_AB, _SDP_BC], {}, _IN_USE)
    if message is None:
        assert form(**values) is not None
    else:
        with pytest.raises(ValueError, match=message):
            form(**values)


def test_sdp_vlan_form_titles_each_field_with_its_sdp_and_prefills_by_sdp() -> None:
    # Path order B <-> C then A <-> B: the prefill must follow the SDP, not the position.
    form = forms.sdp_vlan_form(_PATH_TOPOLOGY, [_SDP_BC, _SDP_AB], {_SDP_AB: 1700}, _IN_USE)
    properties = form.model_json_schema()["properties"]

    assert properties["sdp_vlan_1"]["title"] == "VLAN on B <-> C"
    assert properties["sdp_vlan_1"]["default"] is None
    assert properties["sdp_vlan_2"]["title"] == "VLAN on A <-> B"
    assert properties["sdp_vlan_2"]["default"] == 1700
    # The description lists what is still free: the common range minus what either end holds.
    assert "free: 2000-2099,2101-2999" in properties["sdp_vlan_1"]["description"]
    assert "free: 1500-1599,1601-1999" in properties["sdp_vlan_2"]["description"]


def test_sdp_vlan_input_skips_the_page_without_included_sdps() -> None:
    generator = forms.sdp_vlan_input(_PATH_TOPOLOGY, [], {})
    with pytest.raises(StopIteration) as stop:
        next(generator)
    assert stop.value.value == []


def test_sdp_vlan_input_returns_the_vlans_in_path_order() -> None:
    generator = forms.sdp_vlan_input(_PATH_TOPOLOGY, [_SDP_AB, _SDP_BC], {})
    form = next(generator)
    with pytest.raises(StopIteration) as stop:
        generator.send(form.model_validate({"sdp_vlan_2": 2100}))
    assert stop.value.value == [None, 2100]
