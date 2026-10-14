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

"""Check that both STPs of every SDP allow the same VLANs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import chain
from uuid import UUID

import structlog
from orchestrator.core.utils.errors import InconsistentDataError
from orchestrator.core.workflow import StepList, begin, step
from orchestrator.core.workflows.utils import task
from pydantic_forms.types import State

from products.product_blocks.sdp import ServiceDemarcationPointBlock
from products.product_blocks.stp import ServiceTerminationPointBlock
from workflows.mdp2p.shared.vlans import collapse_ranges, subscribed_sdps, vlan_set

logger = structlog.get_logger(__name__)

_INDENT = " " * 4


@dataclass(frozen=True)
class StpVlans:
    """One end of an SDP: the VLANs its STP allows, and those the other end does not."""

    stp_id: str
    vlans: str
    only_here: str


@dataclass(frozen=True)
class Mismatch:
    """An SDP whose two STPs allow different VLANs."""

    subscription_id: str
    sdp_name: str
    stps: tuple[StpVlans, StpVlans]

    def lines(self) -> list[str]:
        return [
            f"{_INDENT}SDP {self.sdp_name} (subscription {self.subscription_id}):",
            *(
                f"{_INDENT * 2}{stp.stp_id}: VLAN {stp.vlans}"
                + (f", only here: {stp.only_here}" if stp.only_here else "")
                for stp in self.stps
            ),
        ]


def _end(stp: ServiceTerminationPointBlock, only_here: set[int]) -> StpVlans:
    return StpVlans(stp.stp_id, stp.label_group, collapse_ranges(sorted(only_here)))


def _mismatch(subscription_id: UUID, sdp: ServiceDemarcationPointBlock) -> Mismatch | None:
    """The SDP's mismatch, or None when both its STPs allow exactly the same VLANs."""
    stp_a, stp_z = sdp.stps
    vlans_a, vlans_z = vlan_set(stp_a.label_group), vlan_set(stp_z.label_group)
    if vlans_a == vlans_z:
        return None
    return Mismatch(
        str(subscription_id), sdp.sdp_name, (_end(stp_a, vlans_a - vlans_z), _end(stp_z, vlans_z - vlans_a))
    )


@step("Compare the VLAN ranges of both STPs of every SDP")
def compare_sdp_vlans() -> State:
    """Raise on any SDP whose two STPs do not allow exactly the same VLANs.

    A VLAN only one end allows cannot cross the SDP. The stored ``label_group`` is compared, the
    range the MDP2P form offers from; ``validate_stp`` reports when it drifts from the DDS.
    """
    sdps = subscribed_sdps()
    mismatches = list(filter(None, (_mismatch(sid, sdp) for sid, sdp in sdps.items())))
    if mismatches:
        report = "\n".join(chain.from_iterable(m.lines() for m in mismatches))
        raise InconsistentDataError(
            "SDPs whose STPs allow different VLANs:\n" + report, {"mismatches": [asdict(m) for m in mismatches]}
        )

    logger.info("SDP VLAN ranges match", sdps=len(sdps))
    return {"checked_sdps": len(sdps)}


# No run_predicate: see CLAUDE.md.
@task()
def task_validate_sdp_vlans() -> StepList:
    return begin >> compare_sdp_vlans
