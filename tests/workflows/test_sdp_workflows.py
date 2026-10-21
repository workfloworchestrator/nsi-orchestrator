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

import pytest
from orchestrator.core.types import SubscriptionLifecycle

from products.product_types.sdp import ServiceDemarcationPoint
from products.product_types.stp import ServiceTerminationPoint
from tests.workflows import assert_complete, assert_failed, extract_error, extract_state, product_id, run_workflow


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


def _set_stp2_vlans(stp_subscriptions: dict[str, str], vlans: str) -> None:
    stp2 = ServiceTerminationPoint.from_subscription(stp_subscriptions["urn:stp2"])
    stp2.stp.label_group = vlans
    stp2.save()


def test_validate_sdp(sdp_subscription: str, stp_subscriptions: dict[str, str]) -> None:
    _set_stp2_vlans(stp_subscriptions, "1000-1999")

    result, _, _ = run_workflow("validate_sdp", [{"subscription_id": sdp_subscription}])

    assert_complete(result)


@pytest.mark.parametrize(
    ("stp2_vlans", "only_on_a", "only_on_z"),
    [
        pytest.param("2000-2999", "1000-1999", "2000-2999", id="no-overlap"),
        pytest.param("1500-2499", "1000-1499", "2000-2499", id="partial-overlap"),
        pytest.param("1000-1499,1501-1999", "1500", "", id="one-vlan-missing-on-one-end"),
    ],
)
def test_validate_sdp_reports_stps_allowing_different_vlans(
    sdp_subscription: str, stp_subscriptions: dict[str, str], stp2_vlans: str, only_on_a: str, only_on_z: str
) -> None:
    _set_stp2_vlans(stp_subscriptions, stp2_vlans)

    result, _, _ = run_workflow("validate_sdp", [{"subscription_id": sdp_subscription}])

    assert_failed(result)
    state = extract_state(result)
    assert state["class"] == "InconsistentDataError"
    assert "urn:stp1: VLAN 1000-1999" in str(extract_error(result))
    assert state["details"] == {
        "stps": [
            {"stp_id": "urn:stp1", "vlans": "1000-1999", "only_here": only_on_a},
            {"stp_id": "urn:stp2", "vlans": stp2_vlans, "only_here": only_on_z},
        ]
    }


def test_terminate_sdp(sdp_subscription: str) -> None:
    result, _, _ = run_workflow("terminate_sdp", [{"subscription_id": sdp_subscription}, {}])

    assert_complete(result)
    assert ServiceDemarcationPoint.from_subscription(sdp_subscription).status == SubscriptionLifecycle.TERMINATED
