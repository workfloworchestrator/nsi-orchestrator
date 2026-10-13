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

"""Compare the VLANs every uPA holds against the VLANs this orchestrator thinks are in use."""

from __future__ import annotations

from itertools import chain

import structlog
from orchestrator.core.utils.errors import InconsistentDataError
from orchestrator.core.workflow import StepList, begin, step
from orchestrator.core.workflows.utils import task
from pydantic_forms.types import State

from services import aggregator_proxy
from services.aggregator_proxy import AggregatorReservation, Upa, UpaReservation
from workflows.mdp2p.shared.ero import network_of
from workflows.mdp2p.shared.fsm import ConnectionState
from workflows.mdp2p.shared.vlans import (
    StpVlan,
    collapse_ranges,
    group_by_stp,
    held_reservations,
    reservations_vlan_pairs,
    subscribed_stps,
    upa_vlan_pairs,
    vlan_set,
)

logger = structlog.get_logger(__name__)


def _fetch() -> tuple[list[Upa], list[AggregatorReservation], list[UpaReservation]]:
    """The aggregator's uPAs, its reservations, and every reservation those uPAs hold.

    An ``AggregatorProxyError`` is left to propagate: an outage ends the run as ``failed``, not as
    the ``inconsistent_data`` that drift gets, and nothing is compared.
    """
    upas = aggregator_proxy.list_upas()
    aggregator_reservations = aggregator_proxy.list_reservations(with_segments=True)
    upa_reservations = list(chain.from_iterable(aggregator_proxy.list_upa_reservations(u.nsa_id) for u in upas))
    return upas, aggregator_reservations, upa_reservations


def _scope(upas: list[Upa]) -> tuple[dict[str, set[int]], list[str]]:
    """The subscribed STPs a queried uPA serves, with their DDS VLAN range, and those no queried uPA serves."""
    served = set(chain.from_iterable(upa.network_ids for upa in upas))
    stps = subscribed_stps()
    ranges = {stp.stp_id: vlan_set(stp.label_group) for stp in stps if network_of(stp.stp_id) in served}
    return ranges, sorted(stp.stp_id for stp in stps if network_of(stp.stp_id) not in served)


def _split(ranges: dict[str, set[int]], pairs: set[StpVlan]) -> tuple[set[StpVlan], set[StpVlan]]:
    """The pairs on a checked STP, split into those within its current DDS range and those outside it."""
    checked = {(stp_id, vlan) for stp_id, vlan in pairs if stp_id in ranges}
    inside = {(stp_id, vlan) for stp_id, vlan in checked if vlan in ranges[stp_id]}
    return inside, checked - inside


def _report(sections: dict[str, set[StpVlan]]) -> str:
    return "\n".join(
        f"  {title}:\n" + "\n".join(f"    {stp_id}: VLAN {collapse_ranges(sorted(vlans))}" for stp_id, vlans in by_stp)
        for title, pairs in sections.items()
        if (by_stp := group_by_stp(pairs).items())
    )


@step("Compare uPA VLANs against the orchestrator")
def compare_upa_vlans() -> State:
    """Raise on any VLAN a uPA holds that the orchestrator does not, or the other way around."""
    upas, aggregator_reservations, upa_reservations = _fetch()
    ranges, unchecked_stps = _scope(upas)

    # A FAILED reservation keeps its VLANs at the aggregator until terminated, but SuPA releases
    # them at once, so the pairs only a FAILED reservation holds are reported on their own.
    held = held_reservations(aggregator_reservations)
    in_use, in_use_outside = _split(ranges, reservations_vlan_pairs(held))
    live, _ = _split(ranges, reservations_vlan_pairs(r for r in held if r.status != ConnectionState.FAILED))
    upa, upa_outside = _split(ranges, upa_vlan_pairs(upa_reservations))

    # A uPA only grants VLANs within the STP's range, so one held outside it predates a range change.
    sections = {
        "held by a uPA but not in use by the orchestrator": upa - in_use,
        "in use by the orchestrator but not held by any uPA": live - upa,
        "held only by a FAILED aggregator reservation, already released by the uPA": in_use - live - upa,
        "held outside the STP's current DDS range": upa_outside | in_use_outside,
    }
    if any(sections.values()):
        raise InconsistentDataError("uPA VLANs and the orchestrator disagree:\n" + _report(sections))

    logger.info("uPA VLANs match the orchestrator", upas=len(upas), vlans=len(upa))
    return {
        "checked_upas": sorted(upa.nsa_id for upa in upas),
        "checked_vlans": len(upa),
        "unchecked_stps": unchecked_stps,
    }


# No run_predicate: see CLAUDE.md.
@task()
def task_validate_upas_against_vlans() -> StepList:
    return begin >> compare_upa_vlans
