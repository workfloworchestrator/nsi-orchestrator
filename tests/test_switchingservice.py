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

"""Tests for the switching service client model, form helpers and description."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from products.product_types.switchingservice import SwitchingServiceProvisioning
from products.services.description import description
from services.dds_proxy import DdsSwitchingService
from workflows.switchingservice.shared import forms


def test_dds_switchingservice_parses_camelcase_topology_id() -> None:
    service = DdsSwitchingService.model_validate(
        {
            "id": "ss-1",
            "encoding": "e",
            "labelSwapping": True,
            "labelType": "l",
            "topologyId": "topo-1",
        }
    )

    assert (service.id, service.topology_id) == ("ss-1", "topo-1")


def test_switchingservice_selector_keys_and_labels_by_id() -> None:
    enum = forms.switchingservice_selector([DdsSwitchingService(id="a", topology_id="t1")])

    assert {member.value: member.label for member in enum} == {"a": "a"}


def test_available_switching_services_excludes_subscribed_and_requires_subscribed_topology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_subscribed(product_type: str, resource_type: str) -> set[str]:
        return {"ss-x"} if product_type == "SwitchingService" else {"topo-1"}

    monkeypatch.setattr(forms, "subscribed_values", fake_subscribed)
    monkeypatch.setattr(
        forms,
        "fetch_switching_services",
        lambda: [
            DdsSwitchingService(id="ss-x", topology_id="topo-1"),  # already subscribed
            DdsSwitchingService(id="ss-y", topology_id="topo-1"),  # topology subscribed -> offered
            DdsSwitchingService(id="ss-z", topology_id="topo-2"),  # topology not subscribed
        ],
    )

    assert [service.id for service in forms.available_switching_services()] == ["ss-y"]


def test_switchingservice_description_uses_product_name_and_service_name() -> None:
    switchingservice_description = description.dispatch(SwitchingServiceProvisioning)
    stub = SimpleNamespace(
        product=SimpleNamespace(name="switchingservice"),
        switchingservice=SimpleNamespace(switching_service_name="Core SS"),
    )

    assert switchingservice_description(stub) == "switchingservice Core SS"
