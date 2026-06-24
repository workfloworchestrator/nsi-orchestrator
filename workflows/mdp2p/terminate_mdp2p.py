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
from orchestrator.core.workflow import StepList, begin, callback_step, step
from orchestrator.core.workflows.utils import terminate_workflow
from pydantic import Field
from pydantic_forms.types import InputForm, State, UUIDstr

from products.product_types.mdp2p import MultiDomainPoint2Point
from services import aggregator_proxy
from settings import settings
from workflows.mdp2p.shared.fsm import ConnectionState, apply

logger = structlog.get_logger(__name__)


def terminate_initial_input_form_generator(subscription_id: UUIDstr, customer_id: UUIDstr) -> InputForm:
    SubscriptionId = Annotated[DisplaySubscription, Field(subscription_id)]

    class TerminateMultiDomainPoint2PointForm(FormPage):
        subscription_id: SubscriptionId

    return TerminateMultiDomainPoint2PointForm


@step("Check connection can be terminated")
def check_terminable(subscription: MultiDomainPoint2Point) -> State:
    if subscription.vc.state not in (ConnectionState.RESERVED, ConnectionState.FAILED):
        raise ValueError(
            f"Connection must be RESERVED or FAILED to terminate, not {subscription.vc.state}; release it first"
        )
    return {"subscription": subscription}


@step("Terminate connection with the aggregator")
def terminate_connection(subscription: MultiDomainPoint2Point, callback_route: str) -> State:
    aggregator_proxy.terminate(
        subscription.vc.connection_id, f"{settings.orchestrator_callback_base_url}{callback_route}"
    )
    return {"subscription": subscription}


@step("Process terminate result")
def process_terminate_result(subscription: MultiDomainPoint2Point, callback_result: dict) -> State:
    subscription.vc.state = apply(subscription.vc.state, "terminate")
    return {"subscription": subscription}


@terminate_workflow(initial_input_form=terminate_initial_input_form_generator)
def terminate_mdp2p() -> StepList:
    return (
        begin
        >> check_terminable
        >> callback_step(
            name="Terminate connection",
            action_step=terminate_connection,
            validate_step=process_terminate_result,
        )
    )
