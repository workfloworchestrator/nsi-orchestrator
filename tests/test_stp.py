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

"""Tests for the service termination point client model, form helpers and description."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from products.product_types.stp import ServiceTerminationPointProvisioning
from products.services.description import description
from services.dds_proxy import DdsServiceTerminationPoint
from workflows.stp.shared import forms


def test_dds_stp_parses_camelcase_aliases() -> None:
    stp = DdsServiceTerminationPoint.model_validate(
        {"id": "stp-1", "name": "STP 1", "capacity": 100, "labelGroup": "vlan", "switchingServiceId": "ss-1"}
    )

    assert (stp.id, stp.name, stp.capacity, stp.label_group, stp.switching_service_id) == (
        "stp-1",
        "STP 1",
        100,
        "vlan",
        "ss-1",
    )


def test_stp_selector_keys_by_id_labels_by_name_and_id() -> None:
    enum = forms.stp_selector(
        [DdsServiceTerminationPoint(id="a", name="A", capacity=1, label_group="g", switching_service_id="s")]
    )

    assert {member.value: member.label for member in enum} == {"a": "A (a)"}


def test_available_service_termination_points_excludes_subscribed_and_requires_switching_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_subscribed(product_type: str, resource_type: str) -> set[str]:
        return {"stp-x"} if product_type == "ServiceTerminationPoint" else {"ss-1"}

    def stp(id_: str, ss_id: str) -> DdsServiceTerminationPoint:
        return DdsServiceTerminationPoint(id=id_, name=id_, capacity=1, label_group="g", switching_service_id=ss_id)

    monkeypatch.setattr(forms, "subscribed_values", fake_subscribed)
    monkeypatch.setattr(
        forms,
        "fetch_service_termination_points",
        lambda: [stp("stp-x", "ss-1"), stp("stp-y", "ss-1"), stp("stp-z", "ss-2")],
    )

    assert [s.id for s in forms.available_service_termination_points()] == ["stp-y"]


def test_stp_description_uses_product_name_and_stp_name() -> None:
    stp_description = description.dispatch(ServiceTerminationPointProvisioning)
    stub = SimpleNamespace(product=SimpleNamespace(tag="STP"), stp=SimpleNamespace(stp_name="Core STP"))

    assert stp_description(stub) == "STP Core STP"
