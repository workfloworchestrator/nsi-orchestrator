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

from products.product_types.switchingservice import (
    SwitchingService,
    SwitchingServiceProvisioning,
)
from products.services.description import description
from workflows.shared import modify_summary_form

logger = structlog.get_logger(__name__)


def initial_input_form_generator(subscription_id: UUIDstr) -> FormGenerator:
    subscription = SwitchingService.from_subscription(subscription_id)
    switchingservice = subscription.switchingservice

    class ModifySwitchingServiceForm(FormPage):
        switching_service_id: read_only_field(switchingservice.switching_service_id)  # type: ignore[valid-type]
        switching_service_name: str = switchingservice.switching_service_name

    user_input = yield ModifySwitchingServiceForm
    user_input_dict: State = user_input.model_dump()

    summary_fields = ["switching_service_id", "switching_service_name"]
    yield from modify_summary_form(user_input_dict, subscription.switchingservice, summary_fields)

    return user_input_dict | {"subscription": subscription}


@step("Update subscription")
def update_subscription(subscription: SwitchingServiceProvisioning, switching_service_name: str) -> State:
    subscription.switchingservice.switching_service_name = switching_service_name
    return {"subscription": subscription}


@step("Update subscription description")
def update_subscription_description(subscription: SwitchingService) -> State:
    subscription.description = description(subscription)
    return {"subscription": subscription}


additional_steps = begin


@modify_workflow(initial_input_form=initial_input_form_generator, additional_steps=additional_steps)
def modify_switchingservice() -> StepList:
    return (
        begin
        >> set_status(SubscriptionLifecycle.PROVISIONING)
        >> update_subscription
        >> update_subscription_description
        >> set_status(SubscriptionLifecycle.ACTIVE)
    )
