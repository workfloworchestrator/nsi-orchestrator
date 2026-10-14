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

"""VLAN accounting: which VLANs the orchestrator administers, and which an aggregator or uPA holds.

Shared by the MDP2P forms, which offer the free VLANs, and the nightly uPA check. No form imports.
"""

from collections.abc import Callable, Hashable, Iterable, Iterator
from dataclasses import dataclass, replace
from itertools import groupby
from operator import itemgetter
from typing import Any, Literal
from uuid import UUID

from products.product_blocks.sdp import ServiceDemarcationPointBlock
from products.product_blocks.stp import ServiceTerminationPointBlock
from products.product_types.sdp import ServiceDemarcationPoint
from products.product_types.stp import ServiceTerminationPoint
from services.aggregator_proxy import AggregatorReservation, UpaReservation
from workflows.shared import subscription_ids_for_product_type

StpVlan = tuple[str, int]


@dataclass(frozen=True)
class Holder:
    """Who holds a VLAN: a reservation at the aggregator or at a uPA, named by the ids to search for.

    For an aggregator reservation ``child_connection_id`` is the segment holding the VLAN, which is
    the id the segment's uPA reports; it is None on the reservation's own ends.
    """

    side: Literal["aggregator", "uPA"]
    connection_id: str
    child_connection_id: str | None = None
    global_reservation_id: str | None = None


HeldVlan = tuple[StpVlan, Holder]

# SuPA's rule for a reservation that holds its VLANs (job/reserve.py, _stp_resources_in_use).
_UPA_RELEASED_LIFECYCLE_STATES = {"Failed", "PassedEndTime", "Terminated"}
_UPA_HOLDING_RESERVATION_STATES = {"ReserveHeld", "ReserveCommitting", "ReserveStart"}


def vlan_ranges(spec: str) -> list[tuple[int, int]]:
    """Parse a comma-separated VLAN spec into ``(low, high)`` ranges.

    ``spec`` is the NML form used by both the DDS label group and a reserved STP: a comma-separated
    list of single VLANs and ranges, e.g. ``"1000-1999"`` or ``"100,200-300"``.
    """

    def bounds(part: str) -> tuple[int, int]:
        low, _, high = part.partition("-")
        return int(low), int(high or low)

    return [bounds(part.strip()) for part in spec.split(",") if part.strip()]


def vlan_set(spec: str) -> set[int]:
    """Every VLAN a ``vlan_ranges`` spec covers."""
    return {vlan for low, high in vlan_ranges(spec) for vlan in range(low, high + 1)}


def collapse_ranges(values: list[int]) -> str:
    """Collapse a sorted list of ints into a compact range string, e.g. ``[1, 2, 3, 5] -> "1-3,5"``."""
    runs = [
        [value for _, value in group]
        for _, group in groupby(enumerate(values), key=lambda index_value: index_value[1] - index_value[0])
    ]
    return ",".join(f"{run[0]}" if run[0] == run[-1] else f"{run[0]}-{run[-1]}" for run in runs)


def subscribed_stps() -> list[ServiceTerminationPointBlock]:
    """The STP product blocks of all non-terminated STP subscriptions."""
    return [
        ServiceTerminationPoint.from_subscription(sid).stp
        for sid in subscription_ids_for_product_type("ServiceTerminationPoint")
    ]


def subscribed_sdps() -> dict[UUID, ServiceDemarcationPointBlock]:
    """The SDP product blocks of all non-terminated SDP subscriptions, by subscription id."""
    return {
        sid: ServiceDemarcationPoint.from_subscription(sid).sdp
        for sid in subscription_ids_for_product_type("ServiceDemarcationPoint")
    }


def endpoint_vlan_pairs(endpoint: str | None) -> Iterator[StpVlan]:
    """Yield ``(stp_id, vlan)`` for every VLAN an endpoint string (``<stp>?vlan=<spec>``) holds."""
    stp_id, _, vlan_spec = (endpoint or "").partition("?vlan=")
    return ((stp_id, vlan) for vlan in vlan_set(vlan_spec))


def _held(endpoints: Iterable[str | None], holder: Holder) -> Iterator[HeldVlan]:
    return ((pair, holder) for endpoint in endpoints for pair in endpoint_vlan_pairs(endpoint))


def reservation_held_vlans(reservation: AggregatorReservation) -> list[HeldVlan]:
    """The VLANs one aggregator reservation holds: on every child segment and on its own two ends.

    A path's ends are normally also the outer ends of its first and last segment; such a pair is
    named once, by the segment, whose child connection id is what its uPA knows it by.
    """
    own = Holder("aggregator", reservation.connection_id, global_reservation_id=reservation.global_reservation_id)
    segments = [
        held
        for segment in reservation.segments or []
        for held in _held(
            (segment.source_stp, segment.dest_stp), replace(own, child_connection_id=segment.connection_id)
        )
    ]
    covered = {pair for pair, _ in segments}
    p2ps = reservation.criteria.p2ps if reservation.criteria else None
    ends = [held for held in _held((p2ps.source_stp, p2ps.dest_stp) if p2ps else (), own) if held[0] not in covered]
    return segments + ends


def held_reservations(reservations: Iterable[AggregatorReservation]) -> list[AggregatorReservation]:
    """The aggregator reservations that hold their VLANs: every state except ``TERMINATED``.

    A ``FAILED`` reservation only releases its VLANs once terminated.
    """
    return [reservation for reservation in reservations if reservation.status != "TERMINATED"]


def reservations_vlan_pairs(reservations: Iterable[AggregatorReservation]) -> set[StpVlan]:
    """The ``(stp_id, vlan)`` pairs aggregator reservations hold, along their whole paths."""
    return {pair for reservation in reservations for pair, _ in reservation_held_vlans(reservation)}


def _upa_holds_vlans(reservation: UpaReservation) -> bool:
    """SuPA's rule: unlike at the aggregator, a failed reservation releases its VLANs at once."""
    return (
        reservation.lifecycle_state not in _UPA_RELEASED_LIFECYCLE_STATES
        and reservation.reservation_state in _UPA_HOLDING_RESERVATION_STATES
    )


def upa_held_vlans(reservation: UpaReservation) -> list[HeldVlan]:
    """The VLANs one uPA reservation holds, by SuPA's own rule; none once it has released them."""
    holder = Holder("uPA", reservation.connection_id, global_reservation_id=reservation.global_reservation_id)
    ends = (reservation.source_stp, reservation.dest_stp) if _upa_holds_vlans(reservation) else ()
    return list(_held(ends, holder))


def upa_vlan_pairs(reservations: Iterable[UpaReservation]) -> set[StpVlan]:
    """The ``(stp_id, vlan)`` pairs uPA reservations hold, by SuPA's own rule."""
    return {pair for reservation in reservations for pair, _ in upa_held_vlans(reservation)}


def group_pairs[K: Hashable, V](pairs: Iterable[tuple[K, V]], sort_key: Callable[[K], Any] = repr) -> dict[K, set[V]]:
    """``(key, value)`` pairs as a map from each key to all its values, keys ordered by ``sort_key``."""
    ordered = sorted(pairs, key=lambda pair: sort_key(pair[0]))
    return {key: {value for _, value in group} for key, group in groupby(ordered, key=itemgetter(0))}


def group_by_stp(pairs: Iterable[StpVlan]) -> dict[str, set[int]]:
    """``(stp_id, vlan)`` pairs as a map from STP id to its VLANs, ordered by STP id."""
    return group_pairs(pairs, sort_key=str)
