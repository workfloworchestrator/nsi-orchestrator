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
from orchestrator.core.workflows.utils import reconcile_workflow
from pydantic_forms.types import State

from products.product_types.stp import ServiceTerminationPoint
from services.dds_proxy import fetch_service_termination_points

logger = structlog.get_logger(__name__)


@step("Reconcile capacity from the DDS")
def reconcile_capacity(subscription: ServiceTerminationPoint) -> State:
    """Update capacity from the dds-proxy; leave it untouched if the STP is no longer advertised."""
    capacity_by_id = {stp.id: stp.capacity for stp in fetch_service_termination_points()}
    if subscription.stp.stp_id in capacity_by_id:
        subscription.stp.capacity = capacity_by_id[subscription.stp.stp_id]

    return {"subscription": subscription}


@reconcile_workflow()
def reconcile_stp() -> StepList:
    return begin >> reconcile_capacity
