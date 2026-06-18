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

"""Tests for the topology workflow form helpers."""

from __future__ import annotations

import pytest

from services.dds_proxy import DdsTopology
from workflows.topology.shared import forms


def test_topology_selector_keys_by_id_and_labels_with_name() -> None:
    topologies = [DdsTopology(id="urn:a", name="A"), DdsTopology(id="urn:b", name="B")]

    choice = topology_selector_options(topologies)

    assert choice == {"urn:a": "A (urn:a)", "urn:b": "B (urn:b)"}


def topology_selector_options(topologies: list[DdsTopology]) -> dict[str, str]:
    """Return the {value: label} mapping of the dropdown built by topology_selector."""
    enum = forms.topology_selector(topologies)
    return {member.value: member.label for member in enum}


def test_available_topologies_excludes_already_subscribed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        forms,
        "fetch_topologies",
        lambda: [DdsTopology(id="urn:a", name="A"), DdsTopology(id="urn:b", name="B")],
    )
    monkeypatch.setattr(forms, "subscribed_topology_ids", lambda: {"urn:a"})

    available = forms.available_topologies()

    assert [topology.id for topology in available] == ["urn:b"]
