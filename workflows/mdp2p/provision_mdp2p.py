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

"""Provision a multi domain point-to-point connection: RESERVED -> ACTIVATED (or FAILED)."""

from typing import Annotated
from uuid import UUID

import structlog
from orchestrator.core.forms import FormPage
from orchestrator.core.forms.validators import DisplaySubscription
from orchestrator.core.types import SubscriptionLifecycle
from orchestrator.core.workflow import StepList, begin, callback_step, step
from orchestrator.core.workflows.steps import set_status
from orchestrator.core.workflows.utils import modify_workflow
from pydantic import ConfigDict, Field
from pydantic_forms.types import FormGenerator, State, UUIDstr

from products.product_types.mdp2p import MultiDomainPoint2Point, MultiDomainPoint2PointProvisioning
from products.services.description import description
from services import aggregator_proxy
from settings import settings
from workflows.mdp2p.shared.fsm import ConnectionState, apply
from workflows.shared import raise_form_validation_error

logger = structlog.get_logger(__name__)


def initial_input_form_generator(subscription_id: UUIDstr) -> FormGenerator:
    subscription = MultiDomainPoint2Point.from_subscription(subscription_id)
    if subscription.vc.state != ConnectionState.RESERVED:
        raise_form_validation_error(f"Connection must be RESERVED to provision, not {subscription.vc.state}")
    SubscriptionId = Annotated[DisplaySubscription, Field(UUID(subscription_id))]

    class ProvisionMultiDomainPoint2PointForm(FormPage):
        model_config = ConfigDict(title="Provision connection")

        subscription_id: SubscriptionId

    yield ProvisionMultiDomainPoint2PointForm
    return {"subscription": subscription}


@step("Provision connection with the aggregator")
def provision_connection(subscription: MultiDomainPoint2PointProvisioning, callback_route: str) -> State:
    connection_id = subscription.vc.connection_id
    assert connection_id is not None  # set at reserve time; required on the active subscription
    aggregator_proxy.provision(connection_id, f"{settings.orchestrator_callback_base_url}{callback_route}")
    return {"subscription": subscription}


@step("Process provision result")
def process_provision_result(subscription: MultiDomainPoint2PointProvisioning, callback_result: dict) -> State:
    status = callback_result["status"]
    if status != ConnectionState.ACTIVATED:
        logger.warning(
            "provision failed",
            connection_id=subscription.vc.connection_id,
            last_error=callback_result.get("lastError"),
        )
    event = "provision_confirmed" if status == ConnectionState.ACTIVATED else "provision_failed"
    subscription.vc.state = apply(subscription.vc.state, event)
    subscription.description = description(subscription)
    return {"subscription": subscription}


@modify_workflow(initial_input_form=initial_input_form_generator)
def provision_mdp2p() -> StepList:
    return (
        begin
        >> set_status(SubscriptionLifecycle.PROVISIONING)
        >> callback_step(
            name="Provision connection",
            action_step=provision_connection,
            validate_step=process_provision_result,
        )
        >> set_status(SubscriptionLifecycle.ACTIVE)
    )
