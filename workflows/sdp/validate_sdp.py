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

import structlog
from orchestrator.core.utils.errors import InconsistentDataError
from orchestrator.core.workflow import StepList, begin, step
from orchestrator.core.workflows.utils import validate_workflow
from pydantic_forms.types import State

from products.product_blocks.stp import ServiceTerminationPointBlock
from products.product_types.sdp import ServiceDemarcationPoint
from services.dds_proxy import fetch_service_demarcation_points
from workflows.mdp2p.shared.vlans import collapse_ranges, vlan_set

logger = structlog.get_logger(__name__)


@step("Validate service demarcation point is still present in the DDS")
def validate_sdp_present_in_dds(subscription: ServiceDemarcationPoint) -> State:
    """Assert the subscription's STP pair is still advertised by the dds-proxy."""
    pair = frozenset(stp.stp_id for stp in subscription.sdp.stps)
    known_pairs = {frozenset((sdp.stp_a_id, sdp.stp_z_id)) for sdp in fetch_service_demarcation_points()}
    if pair not in known_pairs:
        raise InconsistentDataError(
            f"Service demarcation point {sorted(pair)} is no longer present in the dds-proxy "
            "/service-demarcation-points endpoint"
        )

    return {"subscription": subscription}


def _end(stp: ServiceTerminationPointBlock, only_here: set[int]) -> dict[str, str]:
    return {"stp_id": stp.stp_id, "vlans": stp.label_group, "only_here": collapse_ranges(sorted(only_here))}


@step("Validate both STPs of the service demarcation point allow the same VLANs")
def validate_sdp_vlans_match(subscription: ServiceDemarcationPoint) -> None:
    """Assert both STPs allow exactly the same VLANs; a VLAN only one end allows cannot cross the SDP.

    Compares the stored ``label_group``, the range the MDP2P form offers from; ``validate_stp``
    reports when it drifts from the DDS.
    """
    stp_a, stp_z = subscription.sdp.stps
    vlans_a, vlans_z = vlan_set(stp_a.label_group), vlan_set(stp_z.label_group)
    if vlans_a != vlans_z:
        ends = [_end(stp_a, vlans_a - vlans_z), _end(stp_z, vlans_z - vlans_a)]
        lines = (
            f"    {end['stp_id']}: VLAN {end['vlans']}"
            + (f", only here: {end['only_here']}" if end["only_here"] else "")
            for end in ends
        )
        raise InconsistentDataError("The STPs of this SDP allow different VLANs:\n" + "\n".join(lines), {"stps": ends})


@validate_workflow()
def validate_sdp() -> StepList:
    return begin >> validate_sdp_present_in_dds >> validate_sdp_vlans_match
