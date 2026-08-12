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

import structlog
from orchestrator.core.workflow import StepList, begin, step
from orchestrator.core.workflows.utils import validate_workflow
from pydantic_forms.types import State

from products.product_types.stp import ServiceTerminationPoint
from services.dds_proxy import fetch_service_termination_points

logger = structlog.get_logger(__name__)


@step("Validate service termination point against the DDS")
def validate_stp_present_in_dds(subscription: ServiceTerminationPoint) -> State:
    """Assert the STP is still advertised by the dds-proxy with the stored capacity and VLAN range.

    capacity and label_group are DDS-derived; drift means a reconcile is needed (reconcile_stp repairs
    them). stp_name is operator-editable via modify, so it is deliberately not validated.
    """
    stp_id = subscription.stp.stp_id
    dds_stp = next((stp for stp in fetch_service_termination_points() if stp.id == stp_id), None)
    if dds_stp is None:
        raise AssertionError(
            f"Service termination point {stp_id} is no longer present in the dds-proxy "
            "/service-termination-points endpoint"
        )
    if dds_stp.capacity_mbits != subscription.stp.capacity:
        raise AssertionError(
            f"Service termination point {stp_id} capacity drifted: stored {subscription.stp.capacity} Mbit/s, "
            f"DDS advertises {dds_stp.capacity_mbits} Mbit/s; reconcile to repair"
        )
    if dds_stp.label_group != subscription.stp.label_group:
        raise AssertionError(
            f"Service termination point {stp_id} VLAN range drifted: stored {subscription.stp.label_group}, "
            f"DDS advertises {dds_stp.label_group}; reconcile to repair"
        )

    return {"subscription": subscription}


@validate_workflow()
def validate_stp() -> StepList:
    return begin >> validate_stp_present_in_dds
