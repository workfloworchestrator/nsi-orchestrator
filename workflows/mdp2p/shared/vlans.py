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

from collections.abc import Iterable, Iterator
from itertools import chain, groupby

from products.product_blocks.stp import ServiceTerminationPointBlock
from products.product_types.stp import ServiceTerminationPoint
from services.aggregator_proxy import AggregatorReservation, UpaReservation
from workflows.shared import subscription_ids_for_product_type

StpVlan = tuple[str, int]

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


def endpoint_vlan_pairs(endpoint: str | None) -> Iterator[StpVlan]:
    """Yield ``(stp_id, vlan)`` for every VLAN an endpoint string (``<stp>?vlan=<spec>``) holds."""
    stp_id, _, vlan_spec = (endpoint or "").partition("?vlan=")
    return ((stp_id, vlan) for vlan in vlan_set(vlan_spec))


def _reservation_endpoints(reservation: AggregatorReservation) -> Iterator[str]:
    """The STPs a reservation holds a VLAN on: its own two ends and both ends of every child segment."""
    own = [reservation.criteria.p2ps.source_stp, reservation.criteria.p2ps.dest_stp] if reservation.criteria else []
    segments = chain.from_iterable((segment.source_stp, segment.dest_stp) for segment in reservation.segments or [])
    return (stp for stp in chain(own, segments) if stp is not None)


def held_reservations(reservations: Iterable[AggregatorReservation]) -> list[AggregatorReservation]:
    """The aggregator reservations that hold their VLANs: every state except ``TERMINATED``.

    A ``FAILED`` reservation only releases its VLANs once terminated.
    """
    return [reservation for reservation in reservations if reservation.status != "TERMINATED"]


def reservations_vlan_pairs(reservations: Iterable[AggregatorReservation]) -> set[StpVlan]:
    """The ``(stp_id, vlan)`` pairs aggregator reservations hold, along their whole paths."""
    endpoints = chain.from_iterable(_reservation_endpoints(reservation) for reservation in reservations)
    return set(chain.from_iterable(endpoint_vlan_pairs(endpoint) for endpoint in endpoints))


def upa_vlan_pairs(reservations: Iterable[UpaReservation]) -> set[StpVlan]:
    """The ``(stp_id, vlan)`` pairs uPA reservations hold, by SuPA's own rule.

    Unlike at the aggregator, a failed reservation releases its VLANs at once.
    """
    holding = (
        reservation
        for reservation in reservations
        if reservation.lifecycle_state not in _UPA_RELEASED_LIFECYCLE_STATES
        and reservation.reservation_state in _UPA_HOLDING_RESERVATION_STATES
    )
    endpoints = chain.from_iterable((reservation.source_stp, reservation.dest_stp) for reservation in holding)
    return set(chain.from_iterable(endpoint_vlan_pairs(endpoint) for endpoint in endpoints))


def group_by_stp(pairs: Iterable[StpVlan]) -> dict[str, set[int]]:
    """``(stp_id, vlan)`` pairs as a map from STP id to its VLANs."""
    ordered = sorted(pairs)
    return {stp_id: {vlan for _, vlan in group} for stp_id, group in groupby(ordered, key=lambda pair: pair[0])}
