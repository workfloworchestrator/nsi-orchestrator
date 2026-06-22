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

from typing import Annotated, cast

from annotated_types import Ge, Le
from pydantic_forms.validators import Choice

from products.product_blocks.sdp import ServiceDemarcationPointBlock
from products.product_blocks.stp import ServiceTerminationPointBlock
from products.product_types.sdp import ServiceDemarcationPoint
from products.product_types.stp import ServiceTerminationPoint
from workflows.shared import subscription_ids_for_product_type
from workflows.sdp.shared.forms import stp_block_for, subscribed_sdp_pairs

# A VLAN id; the aggregator encodes it on the STP as "...?vlan=<n>".
Vlan = Annotated[int, Ge(1), Le(4094)]


def subscribed_stps() -> list[ServiceTerminationPointBlock]:
    """The STP product blocks of all non-terminated STP subscriptions."""
    return [
        ServiceTerminationPoint.from_subscription(sid).stp
        for sid in subscription_ids_for_product_type("ServiceTerminationPoint")
    ]


def stps_used_in_sdp() -> set[str]:
    """The STP ids that are already part of a service demarcation point subscription."""
    return {stp_id for pair in subscribed_sdp_pairs() for stp_id in pair}


def stp_selector(stps: list[ServiceTerminationPointBlock], used_in_sdp: set[str]) -> type[Choice]:
    """Dropdown of all ``stps`` keyed by stp id; those already in an SDP are labelled ``(in SDP)``."""
    options = {stp.stp_id: (f"{stp.stp_name} (in SDP)" if stp.stp_id in used_in_sdp else stp.stp_name) for stp in stps}
    choices = Choice("ServiceTerminationPoint", zip(options.keys(), options.items()))  # type: ignore[arg-type]
    return cast("type[Choice]", choices)


def subscribed_sdp_options() -> dict[str, str]:
    """Map each SDP subscription id to a label naming its two STP ids."""
    options = {}
    for sid in subscription_ids_for_product_type("ServiceDemarcationPoint"):
        stp_a, stp_z = (stp.stp_id for stp in ServiceDemarcationPoint.from_subscription(sid).sdp.stps)
        options[str(sid)] = f"{stp_a.removeprefix('urn:ogf:network:')} <-> {stp_z.removeprefix('urn:ogf:network:')}"
    return options


def sdp_selector(options: dict[str, str]) -> type[Choice]:
    """Dropdown of SDP subscriptions keyed by subscription id, labelled with their STP pair."""
    choices = Choice("ServiceDemarcationPoint", zip(options.keys(), options.items()))  # type: ignore[arg-type]
    return cast("type[Choice]", choices)


def sdp_block_for(subscription_id: str) -> ServiceDemarcationPointBlock:
    """Return the SDP product block of the given SDP subscription."""
    return ServiceDemarcationPoint.from_subscription(subscription_id).sdp


__all__ = [
    "Vlan",
    "sdp_block_for",
    "sdp_selector",
    "stp_block_for",
    "stp_selector",
    "stps_used_in_sdp",
    "subscribed_sdp_options",
    "subscribed_stps",
]
