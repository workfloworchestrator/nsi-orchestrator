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

from services.aggregator_proxy import AggregatorReservation


def held_reservation(
    status: str,
    source_stp: str,
    dest_stp: str,
    *,
    connection_id: str = "c",
    sdps: list[tuple[str, str, int]] | None = None,
) -> AggregatorReservation:
    """A ``detail=full`` reservation between two ``<stp>?vlan=<n>`` ends, crossing ``sdps``.

    Each SDP is ``(near end, far end, VLAN)`` and becomes a child segment holding that VLAN on both ends.
    """
    segments = [
        {"order": order, "sourceSTP": f"{near}?vlan={vlan}", "destSTP": f"{far}?vlan={vlan}"}
        for order, (near, far, vlan) in enumerate(sdps or [])
    ]
    return AggregatorReservation.model_validate(
        {
            "connectionId": connection_id,
            "description": "d",
            "status": status,
            "criteria": {"p2ps": {"capacity": 1000, "sourceSTP": source_stp, "destSTP": dest_stp}},
            "segments": segments,
        }
    )
