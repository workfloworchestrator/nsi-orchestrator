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

"""End-to-end tests for the topology workflows."""

from __future__ import annotations

import pytest
from orchestrator.core.types import SubscriptionLifecycle

from products.product_types.topology import Topology
from services.dds_proxy import DdsTopology
from tests.workflows import assert_complete, extract_state, product_id, run_workflow


@pytest.fixture
def _dds_topologies(monkeypatch: pytest.MonkeyPatch) -> None:
    from workflows.topology.shared import forms

    monkeypatch.setattr(forms, "fetch_topologies", lambda: [DdsTopology(id="urn:t1", name="Topo 1")])


def test_create_topology(_dds_topologies: None) -> None:
    result, _, _ = run_workflow(
        "create_topology", [{"product": product_id("Topology")}, {"topology": "urn:t1"}, {}]
    )

    assert_complete(result)
    subscription = Topology.from_subscription(extract_state(result)["subscription_id"])
    assert subscription.status == SubscriptionLifecycle.ACTIVE
    assert subscription.topology.topology_id == "urn:t1"
    assert subscription.topology.topology_name == "Topo 1"
