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

from uuid import uuid4

import structlog
from orchestrator.core.forms import FormPage
from orchestrator.core.settings import app_settings
from orchestrator.core.types import SubscriptionLifecycle
from orchestrator.core.workflow import StepList, begin, callback_step, step
from orchestrator.core.workflows.steps import store_process_subscription
from orchestrator.core.workflows.utils import create_workflow
from pydantic import ConfigDict, model_validator
from pydantic_forms.types import FormGenerator, State, UUIDstr
from pydantic_forms.validators import Divider, choice_list

from products.product_blocks.sap import ServiceAccessPointBlockInactive
from products.product_blocks.sdp_constraint import ConstraintType, SdpConstraintBlockInactive
from products.product_types.mdp2p import MultiDomainPoint2PointInactive, MultiDomainPoint2PointProvisioning
from products.services.description import description
from services import aggregator_proxy
from settings import settings
from workflows.mdp2p.shared.forms import (
    Vlan,
    sdp_block_for,
    sdp_selector,
    stp_block_for,
    stp_selector,
    stps_used_in_sdp,
    subscribed_sdp_options,
    subscribed_stps,
)
from workflows.mdp2p.shared.fsm import ConnectionState, apply
from workflows.shared import create_summary_form

logger = structlog.get_logger(__name__)


def initial_input_form_generator(product_name: str) -> FormGenerator:
    used_in_sdp = stps_used_in_sdp()
    ServiceTerminationPointChoice = stp_selector(subscribed_stps(), used_in_sdp)
    ServiceDemarcationPointChoice = sdp_selector(subscribed_sdp_options())

    class CreateMultiDomainPoint2PointForm(FormPage):
        model_config = ConfigDict(title=product_name)

        description: str
        service_speed: int

        endpoints: Divider

        source_stp: ServiceTerminationPointChoice  # type: ignore[valid-type]
        source_vlan: Vlan
        destination_stp: ServiceTerminationPointChoice  # type: ignore[valid-type]
        destination_vlan: Vlan
        # STPs that are part of an SDP are shown but only selectable when this is ticked.
        allow_stps_in_sdp: bool = False

        path_constraints: Divider

        include_sdps: choice_list(ServiceDemarcationPointChoice, unique_items=True) = []  # type: ignore[valid-type]
        exclude_sdps: choice_list(ServiceDemarcationPointChoice, unique_items=True) = []  # type: ignore[valid-type]

        @model_validator(mode="after")
        def _check_endpoints(self) -> "CreateMultiDomainPoint2PointForm":
            if str(self.source_stp) == str(self.destination_stp):
                raise ValueError("Source and destination STP must be different")
            if not self.allow_stps_in_sdp and {str(self.source_stp), str(self.destination_stp)} & used_in_sdp:
                raise ValueError("A selected STP is part of an SDP; tick 'allow stps in sdp' to use it anyway")
            if set(self.include_sdps) & set(self.exclude_sdps):
                raise ValueError("An SDP cannot be both included and excluded")
            return self

    user_input = yield CreateMultiDomainPoint2PointForm
    user_input_dict = user_input.model_dump()

    summary_fields = [
        "description",
        "service_speed",
        "source_stp",
        "source_vlan",
        "destination_stp",
        "destination_vlan",
    ]
    yield from create_summary_form(user_input_dict, product_name, summary_fields)

    return {
        "customer_id": app_settings.DEFAULT_CUSTOMER_IDENTIFIER,
        "vc_description": user_input_dict["description"],
        "service_speed": user_input_dict["service_speed"],
        "source_stp": user_input_dict["source_stp"],
        "source_vlan": user_input_dict["source_vlan"],
        "destination_stp": user_input_dict["destination_stp"],
        "destination_vlan": user_input_dict["destination_vlan"],
        "include_sdps": user_input_dict["include_sdps"],
        "exclude_sdps": user_input_dict["exclude_sdps"],
    }


@step("Construct Subscription model")
def construct_mdp2p_model(
    product: UUIDstr,
    customer_id: UUIDstr,
    vc_description: str,
    service_speed: int,
    source_stp: str,
    source_vlan: int,
    destination_stp: str,
    destination_vlan: int,
    include_sdps: list[str],
    exclude_sdps: list[str],
) -> State:
    mdp2p = MultiDomainPoint2PointInactive.from_product_id(
        product_id=product,
        customer_id=customer_id,
        status=SubscriptionLifecycle.INITIAL,
    )
    subscription_id = mdp2p.subscription_id

    vc = mdp2p.vc
    vc.description = vc_description
    vc.service_speed = service_speed
    vc.state = ConnectionState.CREATED
    # The orchestrator generates the global reservation id; the aggregator assigns the connection id.
    vc.global_reservation_id = f"urn:uuid:{uuid4()}"
    vc.saps = [
        ServiceAccessPointBlockInactive.new(
            subscription_id=subscription_id, label=str(source_vlan), stp=stp_block_for(source_stp)
        ),
        ServiceAccessPointBlockInactive.new(
            subscription_id=subscription_id, label=str(destination_vlan), stp=stp_block_for(destination_stp)
        ),
    ]
    vc.sdp_constraints = [
        SdpConstraintBlockInactive.new(
            subscription_id=subscription_id, constraint_type=ConstraintType.INCLUDE, sdp=sdp_block_for(sdp_id)
        )
        for sdp_id in include_sdps
    ] + [
        SdpConstraintBlockInactive.new(
            subscription_id=subscription_id, constraint_type=ConstraintType.EXCLUDE, sdp=sdp_block_for(sdp_id)
        )
        for sdp_id in exclude_sdps
    ]

    mdp2p = MultiDomainPoint2PointProvisioning.from_other_lifecycle(mdp2p, SubscriptionLifecycle.PROVISIONING)
    mdp2p.description = description(mdp2p)

    return {
        "subscription": mdp2p,
        "subscription_id": mdp2p.subscription_id,  # necessary to be able to use older generic step functions
        "subscription_description": mdp2p.description,
    }


@step("Reserve connection with the aggregator")
def reserve_connection(subscription: MultiDomainPoint2PointProvisioning, callback_route: str) -> State:
    vc = subscription.vc
    source, destination = vc.saps
    connection_id = aggregator_proxy.reserve(
        global_reservation_id=vc.global_reservation_id,
        description=vc.description,
        capacity=vc.service_speed,
        source_stp=f"{source.stp.stp_id}?vlan={source.label}",
        dest_stp=f"{destination.stp.stp_id}?vlan={destination.label}",
        callback_url=f"{settings.orchestrator_callback_base_url}{callback_route}",
    )
    vc.connection_id = connection_id
    return {"subscription": subscription}


@step("Process reservation result")
def process_reservation_result(subscription: MultiDomainPoint2PointProvisioning, callback_result: dict) -> State:
    status = callback_result["status"]
    if status != ConnectionState.RESERVED:
        logger.warning(
            "reservation failed",
            connection_id=subscription.vc.connection_id,
            last_error=callback_result.get("lastError"),
        )
    event = "reserve_confirmed" if status == ConnectionState.RESERVED else "reserve_failed"
    subscription.vc.state = apply(subscription.vc.state, event)
    return {"subscription": subscription}


@create_workflow(initial_input_form=initial_input_form_generator)
def create_mdp2p() -> StepList:
    return (
        begin
        >> construct_mdp2p_model
        >> store_process_subscription()
        >> callback_step(
            name="Reserve connection",
            action_step=reserve_connection,
            validate_step=process_reservation_result,
        )
    )
