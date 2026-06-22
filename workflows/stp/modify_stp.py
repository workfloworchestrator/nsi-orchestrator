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
from orchestrator.core.types import SubscriptionLifecycle
from orchestrator.core.workflow import StepList, begin, step
from orchestrator.core.workflows.steps import set_status
from orchestrator.core.workflows.utils import modify_workflow
from pydantic_forms.types import FormGenerator, State, UUIDstr
from pydantic_forms.validators import read_only_field

from products.product_types.stp import ServiceTerminationPoint, ServiceTerminationPointProvisioning
from products.services.description import description
from workflows.shared import modify_summary_form

logger = structlog.get_logger(__name__)


def initial_input_form_generator(subscription_id: UUIDstr) -> FormGenerator:
    subscription = ServiceTerminationPoint.from_subscription(subscription_id)
    stp = subscription.stp

    class ModifyServiceTerminationPointForm(FormPage):
        stp_id: read_only_field(stp.stp_id)  # type: ignore[valid-type]
        stp_name: str = stp.stp_name

    user_input = yield ModifyServiceTerminationPointForm
    user_input_dict: State = user_input.model_dump()

    summary_fields = ["stp_id", "stp_name"]
    yield from modify_summary_form(user_input_dict, subscription.stp, summary_fields)

    return user_input_dict | {"subscription": subscription}


@step("Update subscription")
def update_subscription(subscription: ServiceTerminationPointProvisioning, stp_name: str) -> State:
    subscription.stp.stp_name = stp_name
    return {"subscription": subscription}


@step("Update subscription description")
def update_subscription_description(subscription: ServiceTerminationPoint) -> State:
    subscription.description = description(subscription)
    return {"subscription": subscription}


additional_steps = begin


@modify_workflow(initial_input_form=initial_input_form_generator, additional_steps=additional_steps)
def modify_stp() -> StepList:
    return (
        begin
        >> set_status(SubscriptionLifecycle.PROVISIONING)
        >> update_subscription
        >> update_subscription_description
        >> set_status(SubscriptionLifecycle.ACTIVE)
    )
