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

"""Retry a reservation that failed, with corrected input and without retyping the create form.

A reserve can fail for reasons the user can fix: the path they asked for is not routable, the
requested capacity is not available end to end, or the VLAN is taken somewhere along the way. The
create workflow leaves such a subscription ACTIVE with ``vc.state == FAILED``, which orchestrator-core
cannot retry (the process itself completed), so the only recovery used to be terminate and re-create.

This workflow prefills every create field from the subscription, lets the user change any of them,
terminates the old connection, and reserves again. Terminating first matters twice over: it is what
keeps the aggregator from holding an orphaned reservation, and a FAILED reservation only releases
its VLANs once terminated (see ``vlans_in_use_by_stp``), so abandoning it would strand them for
every other user.
"""

from uuid import uuid4

import structlog
from orchestrator.core.types import SubscriptionLifecycle
from orchestrator.core.workflow import StepList, begin, callback_step, conditional, step
from orchestrator.core.workflows.steps import set_status
from orchestrator.core.workflows.utils import modify_workflow
from pydantic_forms.types import FormGenerator, State, UUIDstr

from products.product_blocks.sap import ServiceAccessPointBlockProvisioning
from products.product_blocks.sdp_constraint import ConstraintType, SdpConstraintBlockProvisioning
from products.product_types.mdp2p import MultiDomainPoint2Point, MultiDomainPoint2PointProvisioning
from products.services.description import description
from settings import settings
from workflows.mdp2p.create_mdp2p import process_reservation_result, reserve_connection
from workflows.mdp2p.shared.forms import (
    CONNECTION_SUMMARY_FIELDS,
    connection_form,
    path_summary,
    sdp_block_for,
    sdp_topology,
    stp_block_for,
)
from workflows.mdp2p.shared.fsm import ConnectionState, apply
from workflows.mdp2p.terminate_mdp2p import terminate_connection
from workflows.shared import create_summary_form, raise_form_validation_error

logger = structlog.get_logger(__name__)

RETRYABLE_STATES = (ConnectionState.CREATED, ConnectionState.FAILED)


def initial_input_form_generator(subscription_id: UUIDstr) -> FormGenerator:
    subscription = MultiDomainPoint2Point.from_subscription(subscription_id)
    vc = subscription.vc
    if vc.state not in RETRYABLE_STATES:
        raise_form_validation_error(
            f"Only a connection that holds no reservation can be retried, and this one is {vc.state}; "
            "release or terminate it instead"
        )

    source, destination = vc.saps
    topology = sdp_topology()
    form = connection_form(
        "Retry reservation",
        topology,
        defaults={
            "circuit_description": vc.circuit_description,
            "service_speed": vc.service_speed,
            "source_stp": source.stp.stp_id,
            "source_vlan": int(source.vlan),
            "destination_stp": destination.stp.stp_id,
            "destination_vlan": int(destination.vlan),
            "include_sdps": [
                str(constraint.sdp.owner_subscription_id)
                for constraint in vc.sdp_constraints
                if constraint.constraint_type == ConstraintType.INCLUDE
            ],
        },
        # This subscription's own failed reservation holds its VLANs until the terminate step runs,
        # so release them here or the user cannot keep the VLAN they already had.
        released_vlans={int(source.vlan), int(destination.vlan)},
    )

    user_input = yield form
    user_input_dict: State = user_input.model_dump()

    summary_input = user_input_dict | {"path": path_summary(topology, user_input_dict["include_sdps"])}
    # A single column, not modify_summary_form's before/after: these are not VC attributes, and the
    # "before" is the reservation that just failed.
    yield from create_summary_form(summary_input, subscription.product.name, CONNECTION_SUMMARY_FIELDS)

    ero = topology.ero(
        str(user_input_dict["source_stp"]), str(user_input_dict["destination_stp"]), user_input_dict["include_sdps"]
    )
    return user_input_dict | {"subscription": subscription, "ero": ero}


@step("Process terminate result")
def process_terminate_result(subscription: MultiDomainPoint2PointProvisioning) -> State:
    """Drop the old connection id; ``update_subscription`` applies the ``retry`` transition."""
    logger.info("terminated the failed connection", connection_id=subscription.vc.connection_id)
    subscription.vc.connection_id = None
    return {"subscription": subscription}


@step("Update subscription")
def update_subscription(
    subscription: MultiDomainPoint2PointProvisioning,
    circuit_description: str,
    service_speed: int,
    source_stp: str,
    source_vlan: int,
    destination_stp: str,
    destination_vlan: int,
    include_sdps: list[str],
) -> State:
    subscription_id = subscription.subscription_id
    vc = subscription.vc
    vc.circuit_description = circuit_description
    vc.service_speed = service_speed
    vc.saps = [
        ServiceAccessPointBlockProvisioning.new(
            subscription_id=subscription_id, vlan=str(source_vlan), stp=stp_block_for(source_stp)
        ),
        ServiceAccessPointBlockProvisioning.new(
            subscription_id=subscription_id, vlan=str(destination_vlan), stp=stp_block_for(destination_stp)
        ),
    ]
    vc.sdp_constraints = [
        SdpConstraintBlockProvisioning.new(
            subscription_id=subscription_id, constraint_type=ConstraintType.INCLUDE, sdp=sdp_block_for(sdp_id)
        )
        for sdp_id in include_sdps
    ]
    # The aggregator dedups on globalReservationId before it reads the criteria, so reusing the old
    # one would hand back the old failed connection and quietly ignore every correction above.
    vc.global_reservation_id = f"urn:uuid:{uuid4()}"
    # The old connection is terminated by now, so the subscription genuinely holds nothing again.
    vc.state = apply(vc.state, "retry")
    subscription.description = description(subscription)
    return {"subscription": subscription}


# A create that never got as far as a reserve has nothing to tear down.
has_connection = conditional(lambda state: bool(state["subscription"]["vc"]["connection_id"]))


@modify_workflow(initial_input_form=initial_input_form_generator)
def retry_reservation() -> StepList:
    return (
        begin
        >> set_status(SubscriptionLifecycle.PROVISIONING)
        >> has_connection(
            callback_step(
                name=f"Terminate the failed connection (timeout {settings.aggregator_callback_timeout} seconds)",
                action_step=terminate_connection,
                validate_step=process_terminate_result,
                timeout=settings.aggregator_callback_timeout,
            )
        )
        >> update_subscription
        >> callback_step(
            name=f"Reserve connection (timeout {settings.aggregator_callback_timeout} seconds)",
            action_step=reserve_connection,
            validate_step=process_reservation_result,
            timeout=settings.aggregator_callback_timeout,
        )
        >> set_status(SubscriptionLifecycle.ACTIVE)
    )
