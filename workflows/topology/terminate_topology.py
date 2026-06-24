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

from typing import Annotated

import structlog
from orchestrator.core.forms import FormPage
from orchestrator.core.forms.validators import DisplaySubscription
from orchestrator.core.workflow import StepList, begin, step
from orchestrator.core.workflows.utils import terminate_workflow
from pydantic import Field
from pydantic_forms.types import InputForm, State, UUIDstr

from products.product_types.topology import Topology

logger = structlog.get_logger(__name__)


def terminate_initial_input_form_generator(subscription_id: UUIDstr, customer_id: UUIDstr) -> InputForm:
    SubscriptionId = Annotated[DisplaySubscription, Field(subscription_id)]

    class TerminateTopologyForm(FormPage):
        subscription_id: SubscriptionId

    return TerminateTopologyForm


@step("Terminate topology subscription")
def terminate_topology_subscription(subscription: Topology) -> State:
    # The DDS is the authoritative, read-only source of topologies. Terminating only removes the
    # orchestrator's subscription; there is nothing to deprovision in an external system.
    logger.info(
        "Terminating topology subscription",
        topology_id=subscription.topology.topology_id,
    )

    return {}


@terminate_workflow(initial_input_form=terminate_initial_input_form_generator)
def terminate_topology() -> StepList:
    return begin >> terminate_topology_subscription
