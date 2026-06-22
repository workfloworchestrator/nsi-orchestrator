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

from products.product_types.switchingservice import (
    SwitchingServiceInactive,
    SwitchingServiceProvisioning,
)
from products.services.description import description
from workflows.shared import create_summary_form
from workflows.switchingservice.shared.forms import (
    available_switching_services,
    switchingservice_selector,
    topology_block_for,
)

logger = structlog.get_logger(__name__)


def initial_input_form_generator(product_name: str) -> FormGenerator:
    # Only services without a subscription whose topology is already subscribed, so the topology
    # link in the construct step always resolves.
    services = available_switching_services()
    topology_id_by_id = {service.id: service.topology_id for service in services}
    SwitchingServiceChoice = switchingservice_selector(services)

    class CreateSwitchingServiceForm(FormPage):
        model_config = ConfigDict(title=product_name)

        switching_service_id: SwitchingServiceChoice  # type: ignore[valid-type]
        switching_service_name: str

    user_input = yield CreateSwitchingServiceForm
    user_input_dict = user_input.model_dump()
    switching_service_id = user_input_dict["switching_service_id"]

    summary_fields = ["switching_service_id", "switching_service_name"]
    yield from create_summary_form(user_input_dict, product_name, summary_fields)

    return {
        "customer_id": app_settings.DEFAULT_CUSTOMER_IDENTIFIER,
        "switching_service_id": switching_service_id,
        "switching_service_name": user_input_dict["switching_service_name"],
        "topology_id": topology_id_by_id[switching_service_id],
    }


@step("Construct Subscription model")
def construct_switchingservice_model(
    product: UUIDstr,
    customer_id: UUIDstr,
    switching_service_id: str,
    switching_service_name: str,
    topology_id: str,
) -> State:
    switchingservice = SwitchingServiceInactive.from_product_id(
        product_id=product,
        customer_id=customer_id,
        status=SubscriptionLifecycle.INITIAL,
    )
    switchingservice.switchingservice.switching_service_id = switching_service_id
    switchingservice.switchingservice.switching_service_name = switching_service_name
    switchingservice.switchingservice.topology = topology_block_for(topology_id)

    switchingservice = SwitchingServiceProvisioning.from_other_lifecycle(
        switchingservice, SubscriptionLifecycle.PROVISIONING
    )
    switchingservice.description = description(switchingservice)

    return {
        "subscription": switchingservice,
        "subscription_id": switchingservice.subscription_id,
        "subscription_description": switchingservice.description,
    }


additional_steps = begin


@create_workflow(
    initial_input_form=initial_input_form_generator, additional_steps=additional_steps
)
def create_switchingservice() -> StepList:
    return begin >> construct_switchingservice_model >> store_process_subscription()
