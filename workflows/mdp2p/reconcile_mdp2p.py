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

"""Reconcile a multi domain point-to-point connection's state from the aggregator.

Repairs a subscription whose ``vc.state`` drifted from the aggregator — typically because a callback
was missed after a network problem. It reads ``GET /reservations/{connectionId}`` and, when the
aggregator reports a resting state that differs, updates ``vc.state`` directly: this is a repair to
ground truth, so it deliberately bypasses the FSM transition guard (the result is always a valid
state). Transient aggregator states (RESERVING/ACTIVATING/DEACTIVATING) are left alone — the
connection is mid-transition and a later reconcile settles it.
"""

import structlog
from orchestrator.core.workflow import StepList, begin, step
from orchestrator.core.workflows.utils import reconcile_workflow
from pydantic_forms.types import State

from products.product_types.mdp2p import MultiDomainPoint2Point
from products.services.description import description
from services import aggregator_proxy
from workflows.mdp2p.shared.fsm import ConnectionState

logger = structlog.get_logger(__name__)

# The stable states the aggregator reports and our FSM models; transient ones are left untouched.
RECONCILABLE_STATES = frozenset(
    {ConnectionState.RESERVED, ConnectionState.ACTIVATED, ConnectionState.FAILED, ConnectionState.TERMINATED}
)


def reconciled_state(current_state: str, aggregator_status: str) -> str | None:
    """Return the state to sync to if the aggregator reports a differing stable state, else None."""
    if aggregator_status in RECONCILABLE_STATES and aggregator_status != current_state:
        return aggregator_status
    return None


@step("Reconcile reservation state from the aggregator")
def reconcile_connection_state(subscription: MultiDomainPoint2Point) -> State:
    reservation = aggregator_proxy.get_reservation(subscription.vc.connection_id)
    new_state = reconciled_state(subscription.vc.state, reservation.status)
    if new_state is not None:
        logger.info(
            "reconciling connection state",
            connection_id=subscription.vc.connection_id,
            from_state=subscription.vc.state,
            to_state=new_state,
        )
        subscription.vc.state = new_state
        subscription.description = description(subscription)

    return {"subscription": subscription}


@reconcile_workflow()
def reconcile_mdp2p() -> StepList:
    return begin >> reconcile_connection_state
