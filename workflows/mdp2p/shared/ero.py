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

"""Derive an NSI Explicit Route Object from the SDPs a user wants the path to include.

The ERO the PCE understands is a list of *single* STPs: for each SDP to cross it takes the STP on
the side facing the source, and derives the far end itself from the SDP. Getting that orientation
wrong does not raise an error -- the PCE routes around the SDP and returns a path that hairpins
through the far domain -- so the orientation is computed here rather than guessed.

The order is the user's: an ERO is explicit by definition, and in a mesh "via X then Y" and "via Y
then X" are different paths. This module only decides which end of each SDP to name, and refuses an
order it cannot realise.
"""

from collections import defaultdict, deque
from itertools import product

# Number of colon-separated components in an NSI network id, per nsi-pce SimpleStp.NSI_NETWORK_LENGTH.
_NETWORK_COMPONENTS = 6

# Orientation search is 2^n over the chosen SDPs. A real inter-domain path crosses a handful.
MAX_INCLUDED_SDPS = 4


def network_of(stp_id: str) -> str:
    """The network id an STP belongs to.

    Mirrors nsi-pce ``SimpleStp.parseNetworkId``: the first six colon-separated components, e.g.
    ``urn:ogf:network:dev.west.surf.nl:2022:dev-west:london-1`` is on
    ``urn:ogf:network:dev.west.surf.nl:2022:dev-west``. The ``?vlan=`` suffix is stripped first;
    the Java constructor does that but its static parser does not, and a short opaque part would
    otherwise pull the label into the network id.
    """
    return ":".join(stp_id.split("?")[0].split(":")[:_NETWORK_COMPONENTS])


def _adjacency(sdp_pairs: set[frozenset[str]]) -> dict[str, set[str]]:
    """Undirected network graph: an SDP is an edge between the networks of its two STPs."""
    graph: dict[str, set[str]] = defaultdict(set)
    for pair in sdp_pairs:
        left, right = (network_of(stp_id) for stp_id in pair)
        graph[left].add(right)
        graph[right].add(left)
    return graph


def _legs(source_network: str, dest_network: str, oriented: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The network-to-network stretches the PCE must find a path for, given an orientation.

    Between the source and the first SDP, between each SDP's far end and the next SDP's near end,
    and from the last SDP's far end to the destination.
    """
    entries = [source_network, *(network_of(far) for _, far in oriented)]
    exits = [*(network_of(near) for near, _ in oriented), dest_network]
    return list(zip(entries, exits, strict=True))


def _route_length(graph: dict[str, set[str]], legs: list[tuple[str, str]]) -> int | None:
    """Networks crossed by the shortest route visiting each leg in turn, or None if there is none.

    The route may never re-enter a network. That constraint is the whole point: re-entering means
    doubling back, which is the hairpin the PCE silently produces when an ERO names the wrong end
    of an SDP. Hop count alone cannot detect it -- in a ring the hairpin and the intended route are
    the same length -- so the search carries the visited set rather than scoring finished paths.

    BFS over (leg index, current network, networks visited), so the first hit is the shortest.
    """
    start = (0, legs[0][0], frozenset(legs[0][:1]))
    queue = deque([start])
    seen = {start}
    while queue:
        leg, current, visited = queue.popleft()
        if current == legs[leg][1]:
            if leg == len(legs) - 1:
                return len(visited)
            # Cross the SDP into the next leg's entry network.
            entry = legs[leg + 1][0]
            successors = {(leg + 1, entry, visited | {entry})} if entry not in visited else set()
        else:
            successors = {(leg, hop, visited | {hop}) for hop in graph.get(current, set()) - visited}
        fresh = successors - seen
        seen |= fresh
        queue.extend(fresh)
    return None


def ero_stps(
    source_stp_id: str,
    dest_stp_id: str,
    included_sdps: list[tuple[str, str]],
    sdp_pairs: set[frozenset[str]],
) -> list[str]:
    """The source-facing STP of every included SDP, in the order the user chose them.

    ``included_sdps`` are ``(stp_a, stp_z)`` pairs in the user's order; ``sdp_pairs`` is the whole
    known SDP topology (see ``workflows.sdp.shared.forms.subscribed_sdp_pairs``).

    Raises:
        ValueError: when no orientation makes the requested order routable, or when more SDPs are
            requested than the search is bounded to.
    """
    if not included_sdps:
        return []
    if len(included_sdps) > MAX_INCLUDED_SDPS:
        raise ValueError(f"At most {MAX_INCLUDED_SDPS} SDPs can be included in the path")

    graph = _adjacency(sdp_pairs)
    source_network, dest_network = network_of(source_stp_id), network_of(dest_stp_id)

    # Each SDP is used in one of two orientations; keep the shortest whole route that works.
    orientations = (
        [(sdp[1], sdp[0]) if flipped else sdp for sdp, flipped in zip(included_sdps, flips, strict=True)]
        for flips in product((False, True), repeat=len(included_sdps))
    )
    scored = (
        (_route_length(graph, _legs(source_network, dest_network, oriented)), oriented) for oriented in orientations
    )
    routable = [(length, oriented) for length, oriented in scored if length is not None]
    if not routable:
        raise ValueError(
            "The selected SDPs cannot be traversed in this order between the chosen endpoints; "
            "reorder them to follow the path from source to destination"
        )

    _, best = min(routable, key=lambda candidate: candidate[0])
    return [near for near, _ in best]
