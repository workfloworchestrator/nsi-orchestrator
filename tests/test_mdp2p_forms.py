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

"""Tests for the multi domain point-to-point form helpers."""

from __future__ import annotations

from types import SimpleNamespace

from workflows.mdp2p.shared.forms import stp_selector


def test_stp_selector_labels_in_sdp_stps() -> None:
    stps = [
        SimpleNamespace(stp_id="urn:ogf:network:x", stp_name="Port X"),
        SimpleNamespace(stp_id="urn:ogf:network:y", stp_name="Port Y"),
    ]
    # stp_selector only reads stp_id/stp_name, so duck-typed stubs stand in for STP blocks.
    choice = stp_selector(stps, used_in_sdp={"urn:ogf:network:x"})  # type: ignore[arg-type]

    members = choice.__members__
    # Keyed by stp id, so the construct step can resolve the block.
    assert set(members) == {"urn:ogf:network:x", "urn:ogf:network:y"}
    # The STP that is part of an SDP is labelled; the free one is not.
    assert members["urn:ogf:network:x"].label == "Port X (in SDP)"
    assert members["urn:ogf:network:y"].label == "Port Y"
