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
from orchestrator.core.utils.errors import InconsistentDataError
from orchestrator.core.workflow import StepList, begin, step
from orchestrator.core.workflows.utils import validate_workflow
from pydantic_forms.types import State

from products.product_blocks.sdp_constraint import ConstraintType, SdpConstraintBlock
from products.product_types.mdp2p import MultiDomainPoint2Point
from services import aggregator_proxy
from workflows.mdp2p.shared.fsm import ConnectionState
from workflows.mdp2p.shared.vlans import StpVlan, reservations_vlan_pairs

logger = structlog.get_logger(__name__)

_PATH_HELD_STATES = {ConnectionState.RESERVED, ConnectionState.ACTIVATED}


@step("Validate reservation matches the aggregator")
def validate_reservation(subscription: MultiDomainPoint2Point) -> State:
    """Assert the connection's stored facts still match the aggregator's reservation.

    The description is a local label (editable via the modify workflow) and is deliberately not
    compared; everything that defines the connection at the aggregator is.
    """
    vc = subscription.vc
    reservation = aggregator_proxy.get_reservation(vc.connection_id, with_segments=True)

    if reservation.status != vc.state:
        raise InconsistentDataError(f"Aggregator status {reservation.status} does not match stored state {vc.state}")
    if reservation.global_reservation_id != vc.global_reservation_id:
        raise InconsistentDataError(
            f"Aggregator global reservation id {reservation.global_reservation_id} does not match "
            f"stored {vc.global_reservation_id}"
        )

    if reservation.criteria is None:
        raise InconsistentDataError("Aggregator returned no criteria to validate the connection against")
    p2ps = reservation.criteria.p2ps
    source, destination = vc.saps
    expected_source = f"{source.stp.stp_id}?vlan={source.vlan}"
    expected_destination = f"{destination.stp.stp_id}?vlan={destination.vlan}"
    if p2ps.capacity != vc.service_speed:
        raise InconsistentDataError(f"Aggregator capacity {p2ps.capacity} does not match stored {vc.service_speed}")
    if p2ps.source_stp != expected_source:
        raise InconsistentDataError(f"Aggregator source STP {p2ps.source_stp} does not match stored {expected_source}")
    if p2ps.dest_stp != expected_destination:
        raise InconsistentDataError(
            f"Aggregator destination STP {p2ps.dest_stp} does not match stored {expected_destination}"
        )

    # Only a reserved or activated connection holds its whole path; an earlier or failed one may not.
    pinned = _pinned_sdp_vlans(vc.sdp_constraints) if vc.state in _PATH_HELD_STATES else set()
    if missing := sorted(pinned - reservations_vlan_pairs([reservation])):
        raise InconsistentDataError(
            "Aggregator path does not hold the pinned SDP VLAN on: "
            + ", ".join(f"{stp_id}?vlan={vlan}" for stp_id, vlan in missing)
        )

    return {"subscription": subscription}


def _pinned_sdp_vlans(constraints: list[SdpConstraintBlock]) -> set[StpVlan]:
    """Both STPs of every included SDP the user pinned a VLAN on, with that VLAN."""
    return {
        (stp.stp_id, constraint.vlan)
        for constraint in constraints
        if constraint.constraint_type == ConstraintType.INCLUDE and constraint.vlan is not None
        for stp in constraint.sdp.stps
    }


@validate_workflow()
def validate_mdp2p() -> StepList:
    return begin >> validate_reservation
