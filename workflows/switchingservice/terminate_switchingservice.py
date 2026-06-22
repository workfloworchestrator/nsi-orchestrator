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
from orchestrator.core.forms.validators import DisplaySubscription
from orchestrator.core.workflow import StepList, begin, step
from orchestrator.core.workflows.utils import terminate_workflow
from pydantic_forms.types import InputForm, State, UUIDstr

from products.product_types.switchingservice import SwitchingService

logger = structlog.get_logger(__name__)


def terminate_initial_input_form_generator(
    subscription_id: UUIDstr, customer_id: UUIDstr
) -> InputForm:
    temp_subscription_id = subscription_id

    class TerminateSwitchingServiceForm(FormPage):
        subscription_id: DisplaySubscription = temp_subscription_id  # type: ignore[assignment]

    return TerminateSwitchingServiceForm


@step("Terminate switching service subscription")
def terminate_switchingservice_subscription(subscription: SwitchingService) -> State:
    # DDS is read-only, so there is nothing to deprovision; just drop the subscription.
    logger.info(
        "Terminating switching service subscription",
        switching_service_id=subscription.switchingservice.switching_service_id,
    )

    return {}


@terminate_workflow(initial_input_form=terminate_initial_input_form_generator)
def terminate_switchingservice() -> StepList:
    return begin >> terminate_switchingservice_subscription
