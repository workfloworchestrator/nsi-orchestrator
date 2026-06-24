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

from products.product_types.mdp2p import MultiDomainPoint2Point, MultiDomainPoint2PointProvisioning
from products.services.description import description
from workflows.shared import modify_summary_form

logger = structlog.get_logger(__name__)


def initial_input_form_generator(subscription_id: UUIDstr) -> FormGenerator:
    subscription = MultiDomainPoint2Point.from_subscription(subscription_id)

    class ModifyMultiDomainPoint2PointForm(FormPage):
        circuit_description: str = subscription.vc.circuit_description

    user_input = yield ModifyMultiDomainPoint2PointForm
    user_input_dict: State = user_input.model_dump()

    summary_fields = ["circuit_description"]
    yield from modify_summary_form(user_input_dict, subscription.vc, summary_fields)

    return user_input_dict | {"subscription": subscription}


@step("Update subscription")
def update_subscription(subscription: MultiDomainPoint2PointProvisioning, circuit_description: str) -> State:
    # Local label only; the description sent to the aggregator at reserve time is not changed.
    subscription.vc.circuit_description = circuit_description
    return {"subscription": subscription}


@step("Update subscription description")
def update_subscription_description(subscription: MultiDomainPoint2Point) -> State:
    subscription.description = description(subscription)
    return {"subscription": subscription}


@modify_workflow(initial_input_form=initial_input_form_generator)
def modify_mdp2p() -> StepList:
    return (
        begin
        >> set_status(SubscriptionLifecycle.PROVISIONING)
        >> update_subscription
        >> update_subscription_description
        >> set_status(SubscriptionLifecycle.ACTIVE)
    )
