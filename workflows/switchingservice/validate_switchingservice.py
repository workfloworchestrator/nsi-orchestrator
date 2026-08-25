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

from products.product_types.switchingservice import SwitchingService
from services.dds_proxy import fetch_switching_services

logger = structlog.get_logger(__name__)


@step("Validate switching service against the DDS")
def validate_switchingservice_present_in_dds(subscription: SwitchingService) -> State:
    """Assert the switching service is still advertised by the dds-proxy under the stored topology."""
    switching_service_id = subscription.switchingservice.switching_service_id
    dds_service = next((service for service in fetch_switching_services() if service.id == switching_service_id), None)
    if dds_service is None:
        raise AssertionError(
            f"Switching service {switching_service_id} is no longer present in the dds-proxy "
            "/switching-services endpoint"
        )
    stored_topology_id = subscription.switchingservice.topology.topology_id
    if dds_service.topology_id != stored_topology_id:
        raise AssertionError(
            f"Switching service {switching_service_id} moved topology: stored {stored_topology_id}, "
            f"DDS advertises {dds_service.topology_id}"
        )

    return {"subscription": subscription}


@validate_workflow()
def validate_switchingservice() -> StepList:
    return begin >> validate_switchingservice_present_in_dds
