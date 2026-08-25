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

"""End-to-end tests for the service termination point workflows."""

from __future__ import annotations

import pytest
from orchestrator.core.types import SubscriptionLifecycle

from products.product_types.stp import ServiceTerminationPoint
from services import dds_proxy
from tests.workflows import assert_complete, assert_failed, extract_error, extract_state, product_id, run_workflow


def test_create_stp(switchingservice_subscription: str) -> None:
    result, _, _ = run_workflow(
        "create_stp", [{"product": product_id("ServiceTerminationPoint")}, {"stp_id": "urn:stp1"}, {}]
    )

    assert_complete(result)
    subscription = ServiceTerminationPoint.from_subscription(extract_state(result)["subscription_id"])
    assert subscription.status == SubscriptionLifecycle.ACTIVE
    assert subscription.stp.stp_id == "urn:stp1"
    assert subscription.stp.capacity == 1000
    # The STP links to the subscribed switching service.
    assert subscription.stp.switching_service.switching_service_id == "urn:ss1"


def test_modify_stp(stp_subscriptions: dict[str, str]) -> None:
    subscription_id = stp_subscriptions["urn:stp1"]
    result, _, _ = run_workflow("modify_stp", [{"subscription_id": subscription_id}, {"stp_name": "Renamed"}, {}])

    assert_complete(result)
    assert ServiceTerminationPoint.from_subscription(subscription_id).stp.stp_name == "Renamed"


def test_validate_stp(stp_subscriptions: dict[str, str]) -> None:
    result, _, _ = run_workflow("validate_stp", [{"subscription_id": stp_subscriptions["urn:stp1"]}])

    assert_complete(result)


def test_terminate_stp(stp_subscriptions: dict[str, str]) -> None:
    subscription_id = stp_subscriptions["urn:stp1"]
    result, _, _ = run_workflow("terminate_stp", [{"subscription_id": subscription_id}, {}])

    assert_complete(result)
    assert ServiceTerminationPoint.from_subscription(subscription_id).status == SubscriptionLifecycle.TERMINATED


def test_reconcile_stp_syncs_dds_attributes(stp_subscriptions: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    subscription_id = stp_subscriptions["urn:stp1"]
    # The DDS now advertises a different capacity and VLAN range for the STP.
    monkeypatch.setattr(
        dds_proxy,
        "_fetch",
        lambda _path: [
            {
                "id": "urn:stp1",
                "name": "STP 1",
                "capacity": 5_000_000_000,
                "labelGroup": "3000-3999",
                "switchingServiceId": "urn:ss1",
            }
        ],
    )
    result, _, _ = run_workflow("reconcile_stp", [{"subscription_id": subscription_id}])

    assert_complete(result)
    stp = ServiceTerminationPoint.from_subscription(subscription_id).stp
    assert stp.capacity == 5000
    assert stp.label_group == "3000-3999"


def test_validate_stp_detects_switching_service_drift(
    stp_subscriptions: dict[str, str], dds: dict[str, list[dict[str, object]]]
) -> None:
    """The parent switching service is DDS-derived, so re-parenting is drift."""
    dds["/service-termination-points"][0]["switchingServiceId"] = "urn:other-ss"

    result, _, _ = run_workflow("validate_stp", [{"subscription_id": stp_subscriptions["urn:stp1"]}])

    assert_failed(result)
    assert "moved switching service" in str(extract_error(result))


def test_validate_stp_ignores_a_renamed_subscription(stp_subscriptions: dict[str, str]) -> None:
    """A renamed subscription is a deliberate local divergence, never a validation failure."""
    subscription_id = stp_subscriptions["urn:stp1"]
    modified, _, _ = run_workflow("modify_stp", [{"subscription_id": subscription_id}, {"stp_name": "Local label"}, {}])
    assert_complete(modified)

    result, _, _ = run_workflow("validate_stp", [{"subscription_id": subscription_id}])

    assert_complete(result)
