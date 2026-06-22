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

from products.product_types.sdp import ServiceDemarcationPoint
from services.dds_proxy import fetch_service_demarcation_points

logger = structlog.get_logger(__name__)


@step("Validate service demarcation point is still present in the DDS")
def validate_sdp_present_in_dds(subscription: ServiceDemarcationPoint) -> State:
    """Assert the subscription's STP pair is still advertised by the dds-proxy."""
    pair = frozenset(stp.stp_id for stp in subscription.sdp.stps)
    known_pairs = {frozenset((sdp.stp_a_id, sdp.stp_z_id)) for sdp in fetch_service_demarcation_points()}
    if pair not in known_pairs:
        raise AssertionError(
            f"Service demarcation point {sorted(pair)} is no longer present in the dds-proxy "
            "/service-demarcation-points endpoint"
        )

    return {"subscription": subscription}


@validate_workflow()
def validate_sdp() -> StepList:
    return begin >> validate_sdp_present_in_dds
