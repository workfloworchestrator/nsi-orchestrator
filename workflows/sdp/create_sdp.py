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

from products.product_types.sdp import ServiceDemarcationPointInactive, ServiceDemarcationPointProvisioning
from products.services.description import description
from workflows.shared import create_summary_form, fetch_for_form
from workflows.sdp.shared.forms import available_service_demarcation_points, sdp_selector, stp_block_for

logger = structlog.get_logger(__name__)


def initial_input_form_generator(product_name: str) -> FormGenerator:
    sdps = fetch_for_form(available_service_demarcation_points)
    sdp_by_key = {f"{sdp.stp_a_id}|{sdp.stp_z_id}": sdp for sdp in sdps}
    ServiceDemarcationPointChoice = sdp_selector(sdps)

    class CreateServiceDemarcationPointForm(FormPage):
        model_config = ConfigDict(title=product_name)

        service_demarcation_point: ServiceDemarcationPointChoice  # type: ignore[valid-type]
        sdp_name: str

    user_input = yield CreateServiceDemarcationPointForm
    user_input_dict = user_input.model_dump()
    chosen = sdp_by_key[user_input_dict["service_demarcation_point"]]

    summary_fields = ["sdp_name", "stp_a_id", "stp_z_id"]
    summary_data = {
        "sdp_name": user_input_dict["sdp_name"],
        "stp_a_id": chosen.stp_a_id,
        "stp_z_id": chosen.stp_z_id,
    }
    yield from create_summary_form(summary_data, product_name, summary_fields)

    return {
        "customer_id": app_settings.DEFAULT_CUSTOMER_IDENTIFIER,
        "sdp_name": user_input_dict["sdp_name"],
        "stp_a_id": chosen.stp_a_id,
        "stp_z_id": chosen.stp_z_id,
    }


@step("Construct Subscription model")
def construct_sdp_model(
    product: UUIDstr,
    customer_id: UUIDstr,
    sdp_name: str,
    stp_a_id: str,
    stp_z_id: str,
) -> State:
    sdp = ServiceDemarcationPointInactive.from_product_id(
        product_id=product,
        customer_id=customer_id,
        status=SubscriptionLifecycle.INITIAL,
    )
    sdp.sdp.sdp_name = sdp_name
    # The two STP subscriptions exist (the form only offers SDPs whose STPs are subscribed).
    sdp.sdp.stps = [stp_block_for(stp_a_id), stp_block_for(stp_z_id)]

    sdp = ServiceDemarcationPointProvisioning.from_other_lifecycle(sdp, SubscriptionLifecycle.PROVISIONING)
    sdp.description = description(sdp)

    return {
        "subscription": sdp,
        "subscription_id": sdp.subscription_id,
        "subscription_description": sdp.description,
    }


additional_steps = begin


@create_workflow(initial_input_form=initial_input_form_generator, additional_steps=additional_steps)
def create_sdp() -> StepList:
    return begin >> construct_sdp_model >> store_process_subscription()
