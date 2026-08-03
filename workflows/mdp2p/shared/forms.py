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

"""Shared form helpers for the multi domain point-to-point workflows.

The create form picks two endpoints (source and destination) from the subscribed STPs and,
optionally, service demarcation points to include or exclude from the path. STPs that are already
part of an SDP are shown but labelled, and gated behind a checkbox (see ``create_mdp2p``).
"""

from collections.abc import Iterator
from itertools import chain, groupby
from typing import Annotated, cast

from annotated_types import Ge, Le
from pydantic_forms.validators import Choice

from products.product_blocks.sdp import ServiceDemarcationPointBlock
from products.product_blocks.stp import ServiceTerminationPointBlock
from products.product_types.sdp import ServiceDemarcationPoint
from products.product_types.stp import ServiceTerminationPoint
from services.aggregator_proxy import list_reservations
from workflows.sdp.shared.forms import stp_block_for, subscribed_sdp_pairs
from workflows.shared import subscription_ids_for_product_type

# A VLAN id; the aggregator encodes it on the STP as "...?vlan=<n>".
Vlan = Annotated[int, Ge(1), Le(4094)]


def vlan_ranges(spec: str) -> list[tuple[int, int]]:
    """Parse a comma-separated VLAN spec into ``(low, high)`` ranges.

    ``spec`` is the NML form used by both the DDS label group and a reserved STP: a comma-separated
    list of single VLANs and ranges, e.g. ``"1000-1999"`` or ``"100,200-300"``.
    """

    def bounds(part: str) -> tuple[int, int]:
        low, _, high = part.partition("-")
        return int(low), int(high or low)

    return [bounds(part.strip()) for part in spec.split(",") if part.strip()]


def vlan_in_label_group(vlan: int, label_group: str) -> bool:
    """True if ``vlan`` falls within an STP's advertised VLAN ranges."""
    return any(low <= vlan <= high for low, high in vlan_ranges(label_group))


def _collapse_ranges(values: list[int]) -> str:
    """Collapse a sorted list of ints into a compact range string, e.g. ``[1, 2, 3, 5] -> "1-3,5"``."""
    runs = [
        [value for _, value in group]
        for _, group in groupby(enumerate(values), key=lambda index_value: index_value[1] - index_value[0])
    ]
    return ",".join(f"{run[0]}" if run[0] == run[-1] else f"{run[0]}-{run[-1]}" for run in runs)


def available_vlan_ranges(label_group: str, in_use: set[int]) -> str:
    """The STP's free VLANs (``label_group`` minus ``in_use``) as a compact range string."""
    free = sorted(vlan for low, high in vlan_ranges(label_group) for vlan in range(low, high + 1) if vlan not in in_use)
    return _collapse_ranges(free) or "none available"


def subscribed_stps() -> list[ServiceTerminationPointBlock]:
    """The STP product blocks of all non-terminated STP subscriptions."""
    return [
        ServiceTerminationPoint.from_subscription(sid).stp
        for sid in subscription_ids_for_product_type("ServiceTerminationPoint")
    ]


def stps_used_in_sdp() -> set[str]:
    """The STP ids that are already part of a service demarcation point subscription."""
    return {stp_id for pair in subscribed_sdp_pairs() for stp_id in pair}


def _endpoint_vlan_pairs(endpoint: str) -> Iterator[tuple[str, int]]:
    """Yield ``(stp_id, vlan)`` for every VLAN an endpoint string (``<stp>?vlan=<spec>``) holds."""
    stp_id, _, vlan_spec = endpoint.partition("?vlan=")
    return ((stp_id, vlan) for low, high in vlan_ranges(vlan_spec) for vlan in range(low, high + 1))


def vlans_in_use_by_stp() -> dict[str, set[int]]:
    """VLANs currently held per STP id, parsed from the aggregator's reservations.

    A reservation holds its VLANs in every state except ``TERMINATED`` (a ``FAILED`` reservation
    only releases them once terminated), so only terminated reservations are excluded.
    """
    criteria = (
        reservation.criteria
        for reservation in list_reservations()
        if reservation.criteria is not None and reservation.status != "TERMINATED"
    )
    endpoints = chain.from_iterable((item.p2ps.source_stp, item.p2ps.dest_stp) for item in criteria)
    pairs = sorted(chain.from_iterable(_endpoint_vlan_pairs(endpoint) for endpoint in endpoints))
    return {stp_id: {vlan for _, vlan in group} for stp_id, group in groupby(pairs, key=lambda pair: pair[0])}


def stp_selector(
    stps: list[ServiceTerminationPointBlock], used_in_sdp: set[str], in_use_by_stp: dict[str, set[int]]
) -> type[Choice]:
    """Dropdown of all ``stps`` keyed by stp id.

    The label shows the STP name and the VLANs still free on it (its DDS range minus the VLANs the
    aggregator reports as in use), so the user sees the available range while choosing; STPs already
    part of an SDP are additionally marked ``in SDP``.
    """

    def option_label(stp: ServiceTerminationPointBlock) -> str:
        sdp_marker = ", in SDP" if stp.stp_id in used_in_sdp else ""
        available = available_vlan_ranges(stp.label_group, in_use_by_stp.get(stp.stp_id, set()))
        return f"{stp.stp_name} (VLAN {available}{sdp_marker})"

    options = {stp.stp_id: option_label(stp) for stp in stps}
    choices = Choice("ServiceTerminationPoint", zip(options.keys(), options.items()))  # type: ignore[arg-type]
    return cast("type[Choice]", choices)


def subscribed_sdp_options() -> dict[str, str]:
    """Map each SDP subscription id to its service demarcation point name."""
    return {
        str(sid): ServiceDemarcationPoint.from_subscription(sid).sdp.sdp_name
        for sid in subscription_ids_for_product_type("ServiceDemarcationPoint")
    }


def sdp_selector(options: dict[str, str]) -> type[Choice]:
    """Dropdown of SDP subscriptions keyed by subscription id, labelled with their STP pair."""
    choices = Choice("ServiceDemarcationPoint", zip(options.keys(), options.items()))  # type: ignore[arg-type]
    return cast("type[Choice]", choices)


def sdp_block_for(subscription_id: str) -> ServiceDemarcationPointBlock:
    """Return the SDP product block of the given SDP subscription."""
    return ServiceDemarcationPoint.from_subscription(subscription_id).sdp


__all__ = [
    "Vlan",
    "available_vlan_ranges",
    "sdp_block_for",
    "sdp_selector",
    "stp_block_for",
    "stp_selector",
    "stps_used_in_sdp",
    "subscribed_sdp_options",
    "subscribed_stps",
    "vlan_in_label_group",
    "vlan_ranges",
    "vlans_in_use_by_stp",
]
