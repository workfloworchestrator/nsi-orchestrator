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

"""End-to-end tests for the service demarcation point workflows."""

from __future__ import annotations

from orchestrator.core.types import SubscriptionLifecycle

from products.product_types.sdp import ServiceDemarcationPoint
from tests.workflows import assert_complete, extract_state, product_id, run_workflow


def test_create_sdp(stp_subscriptions: dict[str, str]) -> None:
    result, _, _ = run_workflow(
        "create_sdp",
        [
            {"product": product_id("ServiceDemarcationPoint")},
            {"service_demarcation_point": "urn:stp1|urn:stp2", "sdp_name": "SDP 1"},
            {},
        ],
    )

    assert_complete(result)
    subscription = ServiceDemarcationPoint.from_subscription(extract_state(result)["subscription_id"])
    assert subscription.status == SubscriptionLifecycle.ACTIVE
    assert subscription.sdp.sdp_name == "SDP 1"
    # The SDP links the two subscribed STP blocks.
    assert {stp.stp_id for stp in subscription.sdp.stps} == {"urn:stp1", "urn:stp2"}


def test_modify_sdp(sdp_subscription: str) -> None:
    result, _, _ = run_workflow("modify_sdp", [{"subscription_id": sdp_subscription}, {"sdp_name": "Renamed"}, {}])

    assert_complete(result)
    assert ServiceDemarcationPoint.from_subscription(sdp_subscription).sdp.sdp_name == "Renamed"


def test_validate_sdp(sdp_subscription: str) -> None:
    result, _, _ = run_workflow("validate_sdp", [{"subscription_id": sdp_subscription}])

    assert_complete(result)


def test_terminate_sdp(sdp_subscription: str) -> None:
    result, _, _ = run_workflow("terminate_sdp", [{"subscription_id": sdp_subscription}, {}])

    assert_complete(result)
    assert ServiceDemarcationPoint.from_subscription(sdp_subscription).status == SubscriptionLifecycle.TERMINATED
