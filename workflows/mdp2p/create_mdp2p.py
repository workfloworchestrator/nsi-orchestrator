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
from orchestrator.core.settings import app_settings
from orchestrator.core.types import SubscriptionLifecycle
from orchestrator.core.workflow import StepList, begin, callback_step, step
from orchestrator.core.workflows.steps import store_process_subscription
from orchestrator.core.workflows.utils import create_workflow
from pydantic_forms.types import FormGenerator, State, UUIDstr

from products.product_blocks.sap import ServiceAccessPointBlockInactive
from products.product_blocks.sdp_constraint import ConstraintType, SdpConstraintBlockInactive
from products.product_types.mdp2p import MultiDomainPoint2PointInactive, MultiDomainPoint2PointProvisioning
from products.services.description import description
from services import aggregator_proxy
from settings import settings
from workflows.mdp2p.shared.forms import (
    CONNECTION_SUMMARY_FIELDS,
    connection_form,
    path_summary,
    sdp_block_for,
    sdp_topology,
    stp_block_for,
)
from workflows.mdp2p.shared.fsm import ConnectionState, apply
from workflows.shared import create_summary_form

logger = structlog.get_logger(__name__)


def initial_input_form_generator(product_name: str) -> FormGenerator:
    topology = sdp_topology()

    user_input = yield connection_form(product_name, topology)
    user_input_dict: State = user_input.model_dump()

    summary_input = user_input_dict | {"path": path_summary(topology, user_input_dict["include_sdps"])}
    yield from create_summary_form(summary_input, product_name, CONNECTION_SUMMARY_FIELDS)

    # Derived here, not in reserve_connection: the topology is already loaded and the form has just
    # validated this exact order, so recomputing at step time would re-query and could disagree.
    ero = topology.ero(
        str(user_input_dict["source_stp"]), str(user_input_dict["destination_stp"]), user_input_dict["include_sdps"]
    )
    return {"customer_id": app_settings.DEFAULT_CUSTOMER_IDENTIFIER, "ero": ero} | user_input_dict


@step("Construct Subscription model")
def construct_mdp2p_model(
    product: UUIDstr,
    customer_id: UUIDstr,
    circuit_description: str,
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
    vc.circuit_description = circuit_description
    vc.service_speed = service_speed
    vc.state = ConnectionState.CREATED
    # The orchestrator generates the global reservation id; the aggregator assigns the connection id.
    vc.global_reservation_id = f"urn:uuid:{uuid4()}"
    vc.saps = [
        ServiceAccessPointBlockInactive.new(
            subscription_id=subscription_id, vlan=str(source_vlan), stp=stp_block_for(source_stp)
        ),
        ServiceAccessPointBlockInactive.new(
            subscription_id=subscription_id, vlan=str(destination_vlan), stp=stp_block_for(destination_stp)
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
def reserve_connection(subscription: MultiDomainPoint2PointProvisioning, callback_route: str, ero: list[str]) -> State:
    vc = subscription.vc
    source, destination = vc.saps
    connection_id = aggregator_proxy.reserve(
        global_reservation_id=vc.global_reservation_id,
        description=vc.circuit_description,
        capacity=vc.service_speed,
        source_stp=f"{source.stp.stp_id}?vlan={source.vlan}",
        dest_stp=f"{destination.stp.stp_id}?vlan={destination.vlan}",
        callback_url=f"{settings.orchestrator_callback_base_url}{callback_route}",
        ero=ero,
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
    subscription.description = description(subscription)
    return {"subscription": subscription}


@create_workflow(initial_input_form=initial_input_form_generator)
def create_mdp2p() -> StepList:
    return (
        begin
        >> construct_mdp2p_model
        >> store_process_subscription()
        >> callback_step(
            name=f"Reserve connection (timeout {settings.aggregator_callback_timeout} seconds)",
            action_step=reserve_connection,
            validate_step=process_reservation_result,
            timeout=settings.aggregator_callback_timeout,
        )
    )
