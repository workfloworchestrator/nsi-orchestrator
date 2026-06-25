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

"""End-to-end tests for the switching service workflows."""

from __future__ import annotations

from orchestrator.core.types import SubscriptionLifecycle

from products.product_types.switchingservice import SwitchingService
from tests.workflows import assert_complete, extract_state, product_id, run_workflow


def test_create_switchingservice(topology_subscription: str) -> None:
    result, _, _ = run_workflow(
        "create_switchingservice",
        [
            {"product": product_id("SwitchingService")},
            {"switching_service_id": "urn:ss1", "switching_service_name": "SS 1"},
            {},
        ],
    )

    assert_complete(result)
    subscription = SwitchingService.from_subscription(extract_state(result)["subscription_id"])
    assert subscription.status == SubscriptionLifecycle.ACTIVE
    assert subscription.switchingservice.switching_service_id == "urn:ss1"
    # The switching service links to the subscribed topology.
    assert subscription.switchingservice.topology.topology_id == "urn:t1"


def test_modify_switchingservice(switchingservice_subscription: str) -> None:
    result, _, _ = run_workflow(
        "modify_switchingservice",
        [{"subscription_id": switchingservice_subscription}, {"switching_service_name": "Renamed"}, {}],
    )

    assert_complete(result)
    subscription = SwitchingService.from_subscription(switchingservice_subscription)
    assert subscription.switchingservice.switching_service_name == "Renamed"


def test_validate_switchingservice(switchingservice_subscription: str) -> None:
    result, _, _ = run_workflow("validate_switchingservice", [{"subscription_id": switchingservice_subscription}])

    assert_complete(result)


def test_terminate_switchingservice(switchingservice_subscription: str) -> None:
    result, _, _ = run_workflow("terminate_switchingservice", [{"subscription_id": switchingservice_subscription}, {}])

    assert_complete(result)
    assert SwitchingService.from_subscription(switchingservice_subscription).status == SubscriptionLifecycle.TERMINATED
