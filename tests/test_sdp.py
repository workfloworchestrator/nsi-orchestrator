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

"""Tests for the service demarcation point client model, form helpers and description."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from products.product_types.sdp import ServiceDemarcationPointProvisioning
from products.services.description import description
from services.dds_proxy import DdsServiceDemarcationPoint
from workflows.sdp.shared import forms


def test_dds_sdp_parses_camelcase_stp_pair() -> None:
    sdp = DdsServiceDemarcationPoint.model_validate({"stpAId": "urn:a", "stpZId": "urn:z"})

    assert (sdp.stp_a_id, sdp.stp_z_id) == ("urn:a", "urn:z")


def test_sdp_selector_keys_by_pair_and_strips_urn_in_label() -> None:
    enum = forms.sdp_selector([DdsServiceDemarcationPoint(stp_a_id="urn:ogf:network:a", stp_z_id="urn:ogf:network:z")])

    assert {member.value: member.label for member in enum} == {"urn:ogf:network:a|urn:ogf:network:z": "a <-> z"}


def test_available_service_demarcation_points_excludes_subscribed_pairs_and_requires_both_stps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(forms, "subscribed_sdp_pairs", lambda: {frozenset({"a1", "z1"})})
    monkeypatch.setattr(forms, "subscribed_values", lambda _product, _resource: {"a1", "z1", "a2", "z2"})
    monkeypatch.setattr(
        forms,
        "fetch_service_demarcation_points",
        lambda: [
            DdsServiceDemarcationPoint(stp_a_id="a1", stp_z_id="z1"),  # pair already subscribed
            DdsServiceDemarcationPoint(stp_a_id="a2", stp_z_id="z2"),  # free pair, both STPs subscribed -> offered
            DdsServiceDemarcationPoint(stp_a_id="a2", stp_z_id="z3"),  # z3 STP not subscribed
        ],
    )

    available = forms.available_service_demarcation_points()

    assert [(sdp.stp_a_id, sdp.stp_z_id) for sdp in available] == [("a2", "z2")]


def test_sdp_description_uses_product_name_and_sdp_name() -> None:
    sdp_description = description.dispatch(ServiceDemarcationPointProvisioning)
    stub = SimpleNamespace(product=SimpleNamespace(tag="SDP"), sdp=SimpleNamespace(sdp_name="Border SDP"))

    assert sdp_description(stub) == "SDP Border SDP"
