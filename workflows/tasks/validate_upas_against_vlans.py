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

"""Compare the VLANs every uPA holds against the VLANs the aggregator's reservations hold."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import chain
from typing import Literal
from uuid import UUID

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
    Holder,
    StpVlan,
    collapse_ranges,
    group_pairs,
    held_reservations,
    reservation_held_vlans,
    reservations_vlan_pairs,
    subscribed_stps,
    upa_held_vlans,
    upa_vlan_pairs,
    vlan_set,
)
from workflows.shared import subscription_ids_for_values

logger = structlog.get_logger(__name__)

_INDENT = " " * 4


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


@dataclass(frozen=True)
class Finding:
    """The VLANs one reservation holds on one STP, with the ids to search for it."""

    stp_id: str
    vlans: str
    side: Literal["aggregator", "uPA"]
    connection_id: str
    child_connection_id: str | None
    global_reservation_id: str | None
    subscription_id: str | None

    def lines(self) -> list[str]:
        """The STP and VLANs, then one indented line per id to search for the reservation holding them."""
        subscription = f"subscription {self.subscription_id}" if self.subscription_id else "no subscription"
        ids = [
            f"{self.side} connection {self.connection_id}",
            f"child {self.child_connection_id}" if self.child_connection_id else None,
            subscription if self.side == "aggregator" else None,
            f"global reservation {self.global_reservation_id}" if self.global_reservation_id else None,
        ]
        return [f"{_INDENT * 2}{self.stp_id}: VLAN {self.vlans}", *(f"{_INDENT * 3}{id_}" for id_ in ids if id_)]


def _holders(
    aggregator_reservations: list[AggregatorReservation], upa_reservations: list[UpaReservation]
) -> dict[StpVlan, set[Holder]]:
    """Every reservation, at the aggregator or a uPA, holding each ``(stp_id, vlan)`` pair."""
    return group_pairs(
        chain(
            chain.from_iterable(map(reservation_held_vlans, aggregator_reservations)),
            chain.from_iterable(map(upa_held_vlans, upa_reservations)),
        )
    )


def _findings(
    pairs: set[StpVlan], holders: dict[StpVlan, set[Holder]], subscriptions: dict[str, UUID]
) -> list[Finding]:
    """One finding per STP and holder, with that holder's VLANs on the STP collapsed into ranges."""
    by_stp_and_holder = group_pairs(
        (((stp_id, holder), vlan) for stp_id, vlan in pairs for holder in holders[(stp_id, vlan)]),
        sort_key=lambda key: (key[0], key[1].connection_id, key[1].child_connection_id or ""),
    )
    return [
        Finding(
            stp_id=stp_id,
            vlans=collapse_ranges(sorted(vlans)),
            subscription_id=str(subscriptions[holder.connection_id]) if holder.connection_id in subscriptions else None,
            **asdict(holder),
        )
        for (stp_id, holder), vlans in by_stp_and_holder.items()
    ]


@step("Compare uPA VLANs against the aggregator")
def compare_upa_vlans() -> State:
    """Raise on any VLAN a uPA holds that no aggregator reservation does, or the other way around."""
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
        "held by a uPA but not in use at the aggregator": upa - in_use,
        "in use at the aggregator but not held by any uPA": live - upa,
        "held only by a FAILED aggregator reservation, already released by the uPA": in_use - live - upa,
        "held outside the STP's current DDS range": upa_outside | in_use_outside,
    }
    if any(sections.values()):
        holders = _holders(held, upa_reservations)
        subscriptions = subscription_ids_for_values("MultiDomainPoint2Point", "connection_id")
        findings = {title: _findings(pairs, holders, subscriptions) for title, pairs in sections.items() if pairs}
        report = "\n".join(
            chain.from_iterable(
                [f"{_INDENT}{title}:", *chain.from_iterable(f.lines() for f in found)]
                for title, found in findings.items()
            )
        )
        details = {title: [asdict(f) for f in found] for title, found in findings.items()}
        raise InconsistentDataError("uPA VLANs and the aggregator disagree:\n" + report, details)

    logger.info("uPA VLANs match the aggregator", upas=len(upas), vlans=len(upa))
    return {
        "checked_upas": sorted(upa.nsa_id for upa in upas),
        "checked_vlans": len(upa),
        "unchecked_stps": unchecked_stps,
    }


# No run_predicate: see CLAUDE.md.
@task()
def task_validate_upas_against_vlans() -> StepList:
    return begin >> compare_upa_vlans
