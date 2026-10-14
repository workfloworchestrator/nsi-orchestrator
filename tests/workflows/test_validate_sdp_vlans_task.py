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

"""End-to-end tests for task_validate_sdp_vlans."""

from __future__ import annotations

import pytest

from products.product_types.stp import ServiceTerminationPoint
from tests.workflows import assert_complete, assert_failed, extract_error, extract_state, run_workflow

TASK = "task_validate_sdp_vlans"


def test_reports_nothing_when_every_sdp_allows_the_same_vlans_on_both_stps(
    path_subscriptions: dict[str, str],
) -> None:
    result, _, _ = run_workflow(TASK, [{}])

    assert_complete(result)
    assert extract_state(result)["checked_sdps"] == 2


@pytest.mark.parametrize(
    ("stp2_vlans", "only_on_a", "only_on_z"),
    [
        pytest.param("2000-2999", "1000-1999", "2000-2999", id="no-overlap"),
        pytest.param("1500-2499", "1000-1499", "2000-2499", id="partial-overlap"),
        pytest.param("1000-1499,1501-1999", "1500", "", id="one-vlan-missing-on-one-end"),
    ],
)
def test_reports_an_sdp_whose_stps_allow_different_vlans(
    sdp_subscription: str, stp_subscriptions: dict[str, str], stp2_vlans: str, only_on_a: str, only_on_z: str
) -> None:
    stp2 = ServiceTerminationPoint.from_subscription(stp_subscriptions["urn:stp2"])
    stp2.stp.label_group = stp2_vlans
    stp2.save()

    result, _, _ = run_workflow(TASK, [{}])

    assert_failed(result)
    state = extract_state(result)
    assert state["class"] == "InconsistentDataError"
    assert "SDP SDP 1" in str(extract_error(result))
    assert state["details"] == {
        "mismatches": [
            {
                "subscription_id": sdp_subscription,
                "sdp_name": "SDP 1",
                "stps": [
                    {"stp_id": "urn:stp1", "vlans": "1000-1999", "only_here": only_on_a},
                    {"stp_id": "urn:stp2", "vlans": stp2_vlans, "only_here": only_on_z},
                ],
            }
        ]
    }
