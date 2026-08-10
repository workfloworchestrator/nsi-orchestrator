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
from dataclasses import dataclass
from functools import cached_property
from itertools import chain, groupby
from typing import Annotated, cast

from annotated_types import Ge, Le
from orchestrator.core.forms import FormPage
from pydantic import ConfigDict, ValidationInfo, field_validator, model_validator
from pydantic_forms.validators import Choice, Divider, choice_list

from products.product_blocks.sdp import ServiceDemarcationPointBlock
from products.product_blocks.stp import ServiceTerminationPointBlock
from products.product_types.sdp import ServiceDemarcationPoint
from products.product_types.stp import ServiceTerminationPoint
from services.aggregator_proxy import list_reservations
from workflows.mdp2p.shared.ero import ero_stps
from workflows.sdp.shared.forms import stp_block_for, subscribed_sdp_pairs
from workflows.shared import fetch_for_form, subscription_ids_for_product_type

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


@dataclass(frozen=True)
class SdpTopology:
    """Every SDP subscription, loaded once.

    The connection form needs the same set four ways -- as labels, as STP pairs to orient an ERO,
    as a graph to route over, and as the STPs that must be gated behind ``allow_stps_in_sdp`` --
    and each load is a full domain-model hydration per subscription.
    """

    names: dict[str, str]
    """Subscription id -> service demarcation point name."""

    stps: dict[str, tuple[str, str]]
    """Subscription id -> its ``(stp_a_id, stp_z_id)`` pair."""

    @cached_property
    def pairs(self) -> set[frozenset[str]]:
        """The SDP topology as an undirected edge set."""
        return {frozenset(pair) for pair in self.stps.values()}

    @cached_property
    def stp_ids(self) -> set[str]:
        """Every STP that is part of an SDP."""
        return set(chain.from_iterable(self.stps.values()))

    def ero(self, source_stp: str, dest_stp: str, include_sdps: list[str]) -> list[str]:
        """The ERO for ``include_sdps`` (subscription ids, in the user's order). Raises if unroutable."""
        return ero_stps(source_stp, dest_stp, [self.stps[str(sdp_id)] for sdp_id in include_sdps], self.pairs)


def sdp_topology() -> SdpTopology:
    """Load every SDP subscription once."""
    sdps = {
        str(sid): ServiceDemarcationPoint.from_subscription(sid).sdp
        for sid in subscription_ids_for_product_type("ServiceDemarcationPoint")
    }
    return SdpTopology(
        names={sid: sdp.sdp_name for sid, sdp in sdps.items()},
        stps={sid: (sdp.stps[0].stp_id, sdp.stps[1].stp_id) for sid, sdp in sdps.items()},
    )


def sdp_selector(options: dict[str, str]) -> type[Choice]:
    """Dropdown of SDP subscriptions keyed by subscription id, labelled with their STP pair."""
    choices = Choice("ServiceDemarcationPoint", zip(options.keys(), options.items()))  # type: ignore[arg-type]
    return cast("type[Choice]", choices)


def sdp_block_for(subscription_id: str) -> ServiceDemarcationPointBlock:
    """Return the SDP product block of the given SDP subscription."""
    return ServiceDemarcationPoint.from_subscription(subscription_id).sdp


CONNECTION_SUMMARY_FIELDS = [
    "circuit_description",
    "service_speed",
    "source_stp",
    "source_vlan",
    "destination_stp",
    "destination_vlan",
    "path",
]


def path_summary(topology: SdpTopology, include_sdps: list[str]) -> str:
    """The included SDPs as a readable string.

    The summary page renders every field with ``str()``, which on a list of ``Choice`` members
    would show enum reprs of subscription ids, so name the SDPs instead.
    """
    return ", ".join(topology.names[str(sdp_id)] for sdp_id in include_sdps) or "unconstrained"


def connection_form(
    title: str,
    topology: SdpTopology,
    *,
    defaults: dict[str, object] | None = None,
    released_vlans: set[int] = frozenset(),  # type: ignore[assignment]
) -> type[FormPage]:
    """The form describing an MDP2P connection, shared by the create and retry workflows.

    ``defaults`` prefills fields for the retry workflow; a field absent from it stays required.
    ``released_vlans`` are VLANs the aggregator still reports as in use but which this subscription
    is about to give up, so a retry can keep the VLAN it already had.
    """
    values = defaults or {}
    stps = subscribed_stps()
    label_group_by_id = {stp.stp_id: stp.label_group for stp in stps}
    in_use_by_stp = {stp_id: vlans - released_vlans for stp_id, vlans in fetch_for_form(vlans_in_use_by_stp).items()}
    ServiceTerminationPointChoice = stp_selector(stps, topology.stp_ids, in_use_by_stp)
    ServiceDemarcationPointChoice = sdp_selector(topology.names)

    class ConnectionForm(FormPage):
        model_config = ConfigDict(title=title)

        circuit_description: str = values.get("circuit_description", ...)  # type: ignore[assignment]
        service_speed: int = values.get("service_speed", ...)  # type: ignore[assignment]

        endpoints: Divider

        source_stp: ServiceTerminationPointChoice = values.get("source_stp", ...)  # type: ignore[valid-type]
        source_vlan: Vlan = values.get("source_vlan", ...)  # type: ignore[assignment]
        destination_stp: ServiceTerminationPointChoice = values.get("destination_stp", ...)  # type: ignore[valid-type]
        destination_vlan: Vlan = values.get("destination_vlan", ...)  # type: ignore[assignment]
        # STPs that are part of an SDP are shown but only selectable when this is ticked.
        allow_stps_in_sdp: bool = False

        path_constraints: Divider

        # Literal defaults, not default_factory: only those end up as "default": [] in the JSON schema,
        # which the UI needs to initialise the field as an empty array instead of undefined.
        include_sdps: choice_list(ServiceDemarcationPointChoice, unique_items=True) = values.get("include_sdps", [])  # type: ignore[valid-type]
        exclude_sdps: choice_list(ServiceDemarcationPointChoice, unique_items=True) = []  # type: ignore[valid-type]

        @field_validator("source_vlan", "destination_vlan")
        @classmethod
        def _vlan_within_stp_range(cls, vlan: int, info: ValidationInfo) -> int:
            # source_vlan -> source_stp, destination_vlan -> destination_stp (defined before it).
            assert info.field_name is not None
            stp_id = info.data.get(info.field_name.replace("_vlan", "_stp"))
            if stp_id is not None:
                stp_id = str(stp_id)
                label_group = label_group_by_id[stp_id]
                if not vlan_in_label_group(vlan, label_group):
                    raise ValueError(f"must be within the STP's VLAN range ({label_group})")
                if vlan in in_use_by_stp.get(stp_id, set()):
                    raise ValueError("is already in use on the selected STP")
            return vlan

        @model_validator(mode="after")
        def _check_endpoints(self) -> "ConnectionForm":
            if str(self.source_stp) == str(self.destination_stp):
                raise ValueError("Source and destination STP must be different")
            if not self.allow_stps_in_sdp and {str(self.source_stp), str(self.destination_stp)} & topology.stp_ids:
                raise ValueError("A selected STP is part of an SDP; tick 'allow stps in sdp' to use it anyway")
            if set(self.include_sdps) & set(self.exclude_sdps):
                raise ValueError("An SDP cannot be both included and excluded")
            if self.exclude_sdps:
                # The aggregator drops p2ps <exclusion> and the PCE never applies it, so honouring
                # this would silently produce a path through the SDP the user asked to avoid.
                raise ValueError("Excluding SDPs from the path is not yet supported by the aggregator")
            if self.include_sdps:
                # Reject an unrealizable order here, before the workflow starts.
                topology.ero(str(self.source_stp), str(self.destination_stp), list(self.include_sdps))
            return self

    return ConnectionForm


__all__ = [
    "CONNECTION_SUMMARY_FIELDS",
    "SdpTopology",
    "Vlan",
    "available_vlan_ranges",
    "connection_form",
    "path_summary",
    "sdp_block_for",
    "sdp_selector",
    "sdp_topology",
    "stp_block_for",
    "stp_selector",
    "stps_used_in_sdp",
    "subscribed_stps",
    "vlan_in_label_group",
    "vlan_ranges",
    "vlans_in_use_by_stp",
]
