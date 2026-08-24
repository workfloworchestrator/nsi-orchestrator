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

"""Tests for the product block titles.

Every title is built from the block's human-readable name, never from an id or urn; these guard
against a regression to the id form. The properties are called with stubs, so no database is needed.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from products.product_blocks.sap import ServiceAccessPointBlockProvisioning
from products.product_blocks.sdp import ServiceDemarcationPointBlockProvisioning
from products.product_blocks.sdp_constraint import ConstraintType, SdpConstraintBlockProvisioning
from products.product_blocks.stp import ServiceTerminationPointBlockProvisioning
from products.product_blocks.switchingservice import SwitchingServiceBlockProvisioning
from products.product_blocks.topology import TopologyBlockProvisioning
from products.product_blocks.vc import VirtualCircuitBlockProvisioning


@pytest.mark.parametrize(
    ("block", "stub", "expected"),
    [
        pytest.param(
            TopologyBlockProvisioning,
            SimpleNamespace(topology_name="Development topology west"),
            "Development topology west",
            id="topology",
        ),
        pytest.param(
            SwitchingServiceBlockProvisioning,
            SimpleNamespace(switching_service_name="Core SS"),
            "Core SS",
            id="switchingservice",
        ),
        pytest.param(
            ServiceTerminationPointBlockProvisioning,
            SimpleNamespace(stp_name="Port X"),
            "Port X",
            id="stp",
        ),
        pytest.param(
            ServiceAccessPointBlockProvisioning,
            SimpleNamespace(stp=SimpleNamespace(stp_name="Port X"), vlan="1779"),
            "Port X VLAN 1779",
            id="sap",
        ),
        pytest.param(
            ServiceDemarcationPointBlockProvisioning,
            SimpleNamespace(sdp_name="Amsterdam to Geneva"),
            "Amsterdam to Geneva",
            id="sdp",
        ),
        pytest.param(
            SdpConstraintBlockProvisioning,
            SimpleNamespace(
                constraint_type=ConstraintType.INCLUDE,
                sdp=SimpleNamespace(sdp_name="Amsterdam to Geneva"),
            ),
            "INCLUDE Amsterdam to Geneva",
            id="sdp_constraint",
        ),
        pytest.param(
            VirtualCircuitBlockProvisioning,
            SimpleNamespace(circuit_description="Amsterdam to Geneva"),
            "Amsterdam to Geneva",
            id="vc",
        ),
    ],
)
def test_title_uses_the_human_readable_name(block: Any, stub: SimpleNamespace, expected: str) -> None:
    assert block.title.fget(stub) == expected
