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


@step("Validate service termination point is still present in the DDS")
def validate_stp_present_in_dds(subscription: ServiceTerminationPoint) -> State:
    """Assert the subscription's stp_id is still advertised by the dds-proxy."""
    stp_id = subscription.stp.stp_id
    known_ids = {stp.id for stp in fetch_service_termination_points()}
    if stp_id not in known_ids:
        raise AssertionError(
            f"Service termination point {stp_id} is no longer present in the dds-proxy "
            "/service-termination-points endpoint"
        )

    return {"subscription": subscription}


@validate_workflow()
def validate_stp() -> StepList:
    return begin >> validate_stp_present_in_dds
