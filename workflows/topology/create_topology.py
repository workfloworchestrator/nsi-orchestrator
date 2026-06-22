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
from orchestrator.core.forms import FormPage
from orchestrator.core.settings import app_settings
from orchestrator.core.types import SubscriptionLifecycle
from orchestrator.core.workflow import StepList, begin, step
from orchestrator.core.workflows.steps import store_process_subscription
from orchestrator.core.workflows.utils import create_workflow
from pydantic import ConfigDict
from pydantic_forms.types import FormGenerator, State, UUIDstr

from products.product_types.topology import TopologyInactive, TopologyProvisioning
from products.services.description import description
from workflows.shared import create_summary_form
from workflows.topology.shared.forms import available_topologies, topology_selector

logger = structlog.get_logger(__name__)


def initial_input_form_generator(product_name: str) -> FormGenerator:
    # Offer the topologies known to the dds-proxy that do not yet have a subscription.
    topologies = available_topologies()
    topology_name_by_id = {topology.id: topology.name for topology in topologies}
    TopologyChoice = topology_selector(topologies)

    class CreateTopologyForm(FormPage):
        model_config = ConfigDict(title=product_name)

        topology: TopologyChoice  # type: ignore[valid-type]

    user_input = yield CreateTopologyForm
    topology_id = user_input.model_dump()["topology"]
    # The topology name defaults to the name the topology operator set in the DDS.
    topology_name = topology_name_by_id[topology_id]

    summary_data = {"topology_id": topology_id, "topology_name": topology_name}
    yield from create_summary_form(
        summary_data, product_name, ["topology_id", "topology_name"]
    )

    # No CRM for this orchestrator: use orchestrator-core's configurable default customer
    # (override with the DEFAULT_CUSTOMER_IDENTIFIER env var) instead of asking on the form.
    return {
        "customer_id": app_settings.DEFAULT_CUSTOMER_IDENTIFIER,
        "topology_id": topology_id,
        "topology_name": topology_name,
    }


@step("Construct Subscription model")
def construct_topology_model(
    product: UUIDstr,
    customer_id: UUIDstr,
    topology_id: str,
    topology_name: str,
) -> State:
    topology = TopologyInactive.from_product_id(
        product_id=product,
        customer_id=customer_id,
        status=SubscriptionLifecycle.INITIAL,
    )
    topology.topology.topology_id = topology_id
    topology.topology.topology_name = topology_name

    topology = TopologyProvisioning.from_other_lifecycle(
        topology, SubscriptionLifecycle.PROVISIONING
    )
    topology.description = description(topology)

    return {
        "subscription": topology,
        "subscription_id": topology.subscription_id,  # necessary to be able to use older generic step functions
        "subscription_description": topology.description,
    }


additional_steps = begin


@create_workflow(
    initial_input_form=initial_input_form_generator, additional_steps=additional_steps
)
def create_topology() -> StepList:
    return begin >> construct_topology_model >> store_process_subscription()
