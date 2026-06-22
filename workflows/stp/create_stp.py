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

from products.product_types.stp import ServiceTerminationPointInactive, ServiceTerminationPointProvisioning
from products.services.description import description
from workflows.shared import create_summary_form, fetch_for_form
from workflows.stp.shared.forms import (
    available_service_termination_points,
    stp_selector,
    switchingservice_block_for,
)

logger = structlog.get_logger(__name__)


def initial_input_form_generator(product_name: str) -> FormGenerator:
    # Only STPs without a subscription whose switching service is already subscribed, so the
    # switching_service link in the construct step always resolves.
    stps = fetch_for_form(available_service_termination_points)
    stp_by_id = {stp.id: stp for stp in stps}
    ServiceTerminationPointChoice = stp_selector(stps)

    class CreateServiceTerminationPointForm(FormPage):
        model_config = ConfigDict(title=product_name)

        stp_id: ServiceTerminationPointChoice  # type: ignore[valid-type]

    user_input = yield CreateServiceTerminationPointForm
    chosen = stp_by_id[user_input.model_dump()["stp_id"]]

    summary_fields = ["stp_id", "stp_name", "capacity", "label_group"]
    summary_data = {
        "stp_id": chosen.id,
        "stp_name": chosen.name,
        "capacity": chosen.capacity,
        "label_group": chosen.label_group,
    }
    yield from create_summary_form(summary_data, product_name, summary_fields)

    # stp_name defaults to the DDS name (editable later via the modify workflow); the rest comes
    # straight from the chosen DDS service termination point.
    return {
        "customer_id": app_settings.DEFAULT_CUSTOMER_IDENTIFIER,
        "stp_id": chosen.id,
        "stp_name": chosen.name,
        "capacity": chosen.capacity,
        "label_group": chosen.label_group,
        "switching_service_id": chosen.switching_service_id,
    }


@step("Construct Subscription model")
def construct_stp_model(
    product: UUIDstr,
    customer_id: UUIDstr,
    stp_id: str,
    stp_name: str,
    capacity: int,
    label_group: str,
    switching_service_id: str,
) -> State:
    stp = ServiceTerminationPointInactive.from_product_id(
        product_id=product,
        customer_id=customer_id,
        status=SubscriptionLifecycle.INITIAL,
    )
    stp.stp.stp_id = stp_id
    stp.stp.stp_name = stp_name
    stp.stp.capacity = capacity
    stp.stp.label_group = label_group
    stp.stp.switching_service = switchingservice_block_for(switching_service_id)

    stp = ServiceTerminationPointProvisioning.from_other_lifecycle(stp, SubscriptionLifecycle.PROVISIONING)
    stp.description = description(stp)

    return {
        "subscription": stp,
        "subscription_id": stp.subscription_id,
        "subscription_description": stp.description,
    }


additional_steps = begin


@create_workflow(initial_input_form=initial_input_form_generator, additional_steps=additional_steps)
def create_stp() -> StepList:
    return begin >> construct_stp_model >> store_process_subscription()
