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
from orchestrator.core.workflow import StepList, begin, step
from orchestrator.core.workflows.utils import validate_workflow
from pydantic_forms.types import State

from products.product_types.mdp2p import MultiDomainPoint2Point
from services import aggregator_proxy

logger = structlog.get_logger(__name__)


@step("Validate reservation matches the aggregator")
def validate_reservation(subscription: MultiDomainPoint2Point) -> State:
    """Assert the connection's stored facts still match the aggregator's reservation.

    The description is a local label (editable via the modify workflow) and is deliberately not
    compared; everything that defines the connection at the aggregator is.
    """
    vc = subscription.vc
    reservation = aggregator_proxy.get_reservation(vc.connection_id)

    if reservation.status != vc.state:
        raise AssertionError(f"Aggregator status {reservation.status} does not match stored state {vc.state}")
    if reservation.global_reservation_id != vc.global_reservation_id:
        raise AssertionError(
            f"Aggregator global reservation id {reservation.global_reservation_id} does not match "
            f"stored {vc.global_reservation_id}"
        )

    if reservation.criteria is None:
        raise AssertionError("Aggregator returned no criteria to validate the connection against")
    p2ps = reservation.criteria.p2ps
    source, destination = vc.saps
    expected_source = f"{source.stp.stp_id}?vlan={source.label}"
    expected_destination = f"{destination.stp.stp_id}?vlan={destination.label}"
    if p2ps.capacity != vc.service_speed:
        raise AssertionError(f"Aggregator capacity {p2ps.capacity} does not match stored {vc.service_speed}")
    if p2ps.source_stp != expected_source:
        raise AssertionError(f"Aggregator source STP {p2ps.source_stp} does not match stored {expected_source}")
    if p2ps.dest_stp != expected_destination:
        raise AssertionError(f"Aggregator destination STP {p2ps.dest_stp} does not match stored {expected_destination}")

    return {"subscription": subscription}


@validate_workflow()
def validate_mdp2p() -> StepList:
    return begin >> validate_reservation
