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

from products.product_types.topology import Topology
from services.dds_proxy import fetch_topologies

logger = structlog.get_logger(__name__)


@step("Validate topology is still present in the DDS")
def validate_topology_present_in_dds(subscription: Topology) -> State:
    """Assert the subscription's topology_id is still advertised by the dds-proxy."""
    topology_id = subscription.topology.topology_id
    known_topology_ids = {topology.id for topology in fetch_topologies()}
    if topology_id not in known_topology_ids:
        raise AssertionError(f"Topology {topology_id} is no longer present in the dds-proxy /topologies endpoint")

    return {"subscription": subscription}


@validate_workflow()
def validate_topology() -> StepList:
    return begin >> validate_topology_present_in_dds
