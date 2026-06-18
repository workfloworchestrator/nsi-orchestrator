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

"""Tests for the subscription description service."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from products.product_types.topology import TopologyProvisioning
from products.services.description import description


def test_topology_is_registered() -> None:
    assert TopologyProvisioning in description.registry


def test_topology_description_uses_product_name_and_topology_name() -> None:
    # Call the registered implementation directly with a stub, so no database is needed.
    topology_description = description.dispatch(TopologyProvisioning)
    stub = SimpleNamespace(
        product=SimpleNamespace(name="topology"),
        topology=SimpleNamespace(topology_name="Development topology west"),
    )

    assert topology_description(stub) == "topology Development topology west"


def test_description_for_unregistered_type_raises() -> None:
    default_implementation = description.dispatch(object)

    with pytest.raises(TypeError):
        default_implementation(object())
