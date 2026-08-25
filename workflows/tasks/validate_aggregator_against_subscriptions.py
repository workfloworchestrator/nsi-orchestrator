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

"""Compare the aggregator's live reservations against the MDP2P subscriptions."""

import structlog
from orchestrator.core.workflow import StepList, begin, step
from orchestrator.core.workflows.utils import task
from pydantic_forms.types import State

from services import aggregator_proxy
from services.aggregator_proxy import AggregatorProxyError
from workflows.mdp2p.shared.fsm import ConnectionState
from workflows.shared import subscribed_values

logger = structlog.get_logger(__name__)


@step("Compare aggregator reservations against subscriptions")
def compare_reservations_to_subscriptions() -> State:
    """Assert every live reservation has a subscription and vice versa."""
    try:
        reservations = aggregator_proxy.list_reservations()
    except AggregatorProxyError as exc:
        raise AssertionError(f"Aggregator could not be read, so nothing was compared: {exc}") from None

    # Terminated reservations are excluded: their subscriptions are terminated too.
    live = {r.connection_id for r in reservations if r.status != ConnectionState.TERMINATED}
    subscribed = subscribed_values("MultiDomainPoint2Point", "connection_id")
    reservations_without_subscription = sorted(live - subscribed)
    subscriptions_without_reservation = sorted(subscribed - live)

    if reservations_without_subscription or subscriptions_without_reservation:
        raise AssertionError(
            "Aggregator and subscriptions disagree:\n"
            f"  reservations without a subscription: {reservations_without_subscription}\n"
            f"  subscriptions without a live reservation: {subscriptions_without_reservation}"
        )

    logger.info("aggregator matches subscriptions", reservations=len(live), subscriptions=len(subscribed))
    return {"checked_reservations": len(live), "checked_subscriptions": len(subscribed)}


# No run_predicate: see CLAUDE.md.
@task()
def task_validate_aggregator_against_subscriptions() -> StepList:
    return begin >> compare_reservations_to_subscriptions
