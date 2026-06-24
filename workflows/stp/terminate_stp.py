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

from products.product_types.stp import ServiceTerminationPoint

logger = structlog.get_logger(__name__)


def terminate_initial_input_form_generator(subscription_id: UUIDstr, customer_id: UUIDstr) -> InputForm:
    SubscriptionId = Annotated[DisplaySubscription, Field(subscription_id)]

    class TerminateServiceTerminationPointForm(FormPage):
        subscription_id: SubscriptionId

    return TerminateServiceTerminationPointForm


@step("Terminate service termination point subscription")
def terminate_stp_subscription(subscription: ServiceTerminationPoint) -> State:
    # DDS is read-only, so there is nothing to deprovision; just drop the subscription.
    logger.info("Terminating service termination point subscription", stp_id=subscription.stp.stp_id)

    return {}


@terminate_workflow(initial_input_form=terminate_initial_input_form_generator)
def terminate_stp() -> StepList:
    return begin >> terminate_stp_subscription
