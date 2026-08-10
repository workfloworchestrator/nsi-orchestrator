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

"""Tests for deriving an ERO from the SDPs a user wants included in the path."""

import pytest

from workflows.mdp2p.shared.ero import MAX_INCLUDED_SDPS, ero_stps, network_of

# A four-domain chain A <-> B <-> C <-> D, plus a shortcut A <-> D closing it into a ring.
# The ring matters: it makes a hairpin the same length as the intended route, so these cases only
# pass if orientation is decided by "the walk never revisits a network" rather than by hop count.
A, B, C, D = (f"urn:ogf:network:{name}.example.net:2025:topology" for name in ("a", "b", "c", "d"))
AB, BA = f"{A}:to-b", f"{B}:to-a"
BC, CB = f"{B}:to-c", f"{C}:to-b"
CD, DC = f"{C}:to-d", f"{D}:to-c"
AD, DA = f"{A}:to-d", f"{D}:to-a"

TOPOLOGY = {frozenset((AB, BA)), frozenset((BC, CB)), frozenset((CD, DC)), frozenset((AD, DA))}

SOURCE, DEST = f"{A}:customer-1", f"{D}:customer-2"


@pytest.mark.parametrize(
    ("stp_id", "expected"),
    [
        pytest.param(
            "urn:ogf:network:dev.west.surf.nl:2022:dev-west:london-1",
            "urn:ogf:network:dev.west.surf.nl:2022:dev-west",
            id="seven-components",
        ),
        pytest.param(
            "urn:ogf:network:dev.west.surf.nl:2022:dev-west:london-1?vlan=1131",
            "urn:ogf:network:dev.west.surf.nl:2022:dev-west",
            id="vlan-suffix-stripped",
        ),
        pytest.param(
            "urn:ogf:network:es.net:2013::sunn-cr5:10_1_6:+",
            "urn:ogf:network:es.net:2013:",
            id="empty-sixth-component-is-preserved",
        ),
        pytest.param(
            "urn:ogf:network:example.net:2025:port-1?vlan=100",
            "urn:ogf:network:example.net:2025:port-1",
            id="short-opaque-part-keeps-label-out",
        ),
    ],
)
def test_network_of(stp_id: str, expected: str) -> None:
    assert network_of(stp_id) == expected


@pytest.mark.parametrize(
    ("included", "expected"),
    [
        pytest.param([], [], id="no-constraints"),
        pytest.param([(AB, BA)], [AB], id="single-sdp-already-source-facing"),
        pytest.param([(BA, AB)], [AB], id="single-sdp-reversed-is-corrected"),
        pytest.param([(AB, BA), (BC, CB)], [AB, BC], id="two-chained-sdps"),
        pytest.param([(BA, AB), (CB, BC)], [AB, BC], id="two-chained-sdps-both-reversed"),
        pytest.param([(BC, CB)], [BC], id="sparse-waypoint-not-adjacent-to-source"),
        pytest.param([(CD, DC)], [CD], id="sparse-waypoint-adjacent-to-destination"),
        pytest.param([(AD, DA)], [AD], id="the-ring-shortcut"),
        pytest.param([(AB, BA), (BC, CB), (CD, DC)], [AB, BC, CD], id="the-long-way-round-the-ring"),
    ],
)
def test_ero_stps_orients_each_sdp_towards_the_source(included: list[tuple[str, str]], expected: list[str]) -> None:
    assert ero_stps(SOURCE, DEST, included, TOPOLOGY) == expected


_UNKNOWN = "urn:ogf:network:z.example.net:2025:topology:to-nowhere"


@pytest.mark.parametrize(
    ("included", "message"),
    [
        pytest.param(
            [(CD, DC), (AB, BA)],
            "cannot be traversed in this order",
            id="C-D-before-A-B-cannot-get-back-to-A",
        ),
        pytest.param(
            [(_UNKNOWN, f"{B}:to-z")],
            "cannot be traversed in this order",
            id="sdp-outside-the-known-topology",
        ),
        pytest.param(
            [(AB, BA)] * (MAX_INCLUDED_SDPS + 1),
            f"At most {MAX_INCLUDED_SDPS} SDPs",
            id="more-sdps-than-the-search-is-bounded-to",
        ),
    ],
)
def test_ero_stps_rejects(included: list[tuple[str, str]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ero_stps(SOURCE, DEST, included, TOPOLOGY)
