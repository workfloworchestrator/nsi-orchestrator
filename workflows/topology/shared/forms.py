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

"""Shared form helpers for the topology workflows."""

from typing import cast

from pydantic_forms.validators import Choice

from services.dds_proxy import DdsTopology, fetch_topologies
from workflows.shared import subscribed_values


def subscribed_topology_ids() -> set[str]:
    """Return the ``topology_id`` values that already have a non-terminated Topology subscription."""
    return subscribed_values("Topology", "topology_id")


def available_topologies() -> list[DdsTopology]:
    """Return the dds-proxy topologies that do not yet have a subscription."""
    subscribed = subscribed_topology_ids()
    return [
        topology for topology in fetch_topologies() if topology.id not in subscribed
    ]


def topology_selector(topologies: list[DdsTopology]) -> type[Choice]:
    """Build a dropdown of ``topologies``, keyed by ``topology_id`` and labelled ``name (id)``."""
    options = {
        topology.id: f"{topology.name} ({topology.id})" for topology in topologies
    }
    choices = Choice("TopologyChoice", zip(options.keys(), options.items()))  # type: ignore[arg-type]
    return cast("type[Choice]", choices)
