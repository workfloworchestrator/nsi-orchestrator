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

"""Shared form helpers for the service demarcation point workflows.

An SDP has no id of its own; it is identified by the (order-independent) pair of its two STP ids.
"""

from typing import cast

from pydantic_forms.validators import Choice

from products.product_blocks.stp import ServiceTerminationPointBlock
from products.product_types.sdp import ServiceDemarcationPoint
from products.product_types.stp import ServiceTerminationPoint
from services.dds_proxy import DdsServiceDemarcationPoint, fetch_service_demarcation_points
from workflows.shared import (
    subscribed_values,
    subscription_descriptions_for_values,
    subscription_id_for_value,
    subscription_ids_for_product_type,
)


def subscribed_sdp_pairs() -> set[frozenset[str]]:
    """The STP-id pairs already covered by a non-terminated SDP subscription."""
    return {
        frozenset(stp.stp_id for stp in ServiceDemarcationPoint.from_subscription(sid).sdp.stps)
        for sid in subscription_ids_for_product_type("ServiceDemarcationPoint")
    }


def available_service_demarcation_points() -> list[DdsServiceDemarcationPoint]:
    """dds-proxy SDPs without a subscription whose two STPs are both already subscribed."""
    subscribed_pairs = subscribed_sdp_pairs()
    subscribed_stps = subscribed_values("ServiceTerminationPoint", "stp_id")
    return [
        sdp
        for sdp in fetch_service_demarcation_points()
        if frozenset((sdp.stp_a_id, sdp.stp_z_id)) not in subscribed_pairs
        and {sdp.stp_a_id, sdp.stp_z_id} <= subscribed_stps
    ]


def sdp_selector(sdps: list[DdsServiceDemarcationPoint]) -> type[Choice]:
    """Build a dropdown of ``sdps``, keyed by the ``stp_a_id|stp_z_id`` pair and labelled with both ids."""
    descriptions = subscription_descriptions_for_values("ServiceTerminationPoint", "stp_id")

    def side(stp_id: str) -> str:
        return descriptions.get(stp_id) or stp_id.removeprefix("urn:ogf:network:")

    options = {f"{sdp.stp_a_id}|{sdp.stp_z_id}": f"{side(sdp.stp_a_id)} <-> {side(sdp.stp_z_id)}" for sdp in sdps}
    choices = Choice("ServiceDemarcationPoint", zip(options.keys(), options.items()))  # type: ignore[arg-type]
    return cast("type[Choice]", choices)


def stp_block_for(stp_id: str) -> ServiceTerminationPointBlock:
    """Return the ServiceTerminationPointBlock of the subscription that owns ``stp_id``."""
    subscription_id = subscription_id_for_value("ServiceTerminationPoint", "stp_id", stp_id)
    # never None: available_service_demarcation_points only offers SDPs whose STPs are subscribed
    assert subscription_id is not None
    return ServiceTerminationPoint.from_subscription(subscription_id).stp
