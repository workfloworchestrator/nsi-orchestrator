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

"""Release a multi domain point-to-point connection: ACTIVATED -> RESERVED (or FAILED)."""

from typing import Annotated

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
    if subscription.vc.state != ConnectionState.ACTIVATED:
        raise_form_validation_error(f"Connection must be ACTIVATED to release, not {subscription.vc.state}")
    SubscriptionId = Annotated[DisplaySubscription, Field(subscription_id)]

    class ReleaseMultiDomainPoint2PointForm(FormPage):
        model_config = ConfigDict(title="Release connection")

        subscription_id: SubscriptionId

    yield ReleaseMultiDomainPoint2PointForm
    return {"subscription": subscription}


@step("Release connection with the aggregator")
def release_connection(subscription: MultiDomainPoint2PointProvisioning, callback_route: str) -> State:
    connection_id = subscription.vc.connection_id
    assert connection_id is not None  # set at reserve time; required on the active subscription
    aggregator_proxy.release(connection_id, f"{settings.orchestrator_callback_base_url}{callback_route}")
    return {"subscription": subscription}


@step("Process release result")
def process_release_result(subscription: MultiDomainPoint2PointProvisioning, callback_result: dict) -> State:
    status = callback_result["status"]
    if status != ConnectionState.RESERVED:
        logger.warning(
            "release failed",
            connection_id=subscription.vc.connection_id,
            last_error=callback_result.get("lastError"),
        )
    event = "release_confirmed" if status == ConnectionState.RESERVED else "release_failed"
    subscription.vc.state = apply(subscription.vc.state, event)
    subscription.description = description(subscription)
    return {"subscription": subscription}


@modify_workflow(initial_input_form=initial_input_form_generator)
def release_mdp2p() -> StepList:
    return (
        begin
        >> set_status(SubscriptionLifecycle.PROVISIONING)
        >> callback_step(
            name="Release connection",
            action_step=release_connection,
            validate_step=process_release_result,
        )
        >> set_status(SubscriptionLifecycle.ACTIVE)
    )
