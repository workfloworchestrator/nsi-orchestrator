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

from typing import Annotated

from annotated_types import Len
from orchestrator.core.domain.base import ProductBlockModel
from orchestrator.core.types import SI, SubscriptionLifecycle
from pydantic import computed_field

from products.product_blocks.sap import (
    ServiceAccessPointBlock,
    ServiceAccessPointBlockInactive,
    ServiceAccessPointBlockProvisioning,
)
from products.product_blocks.sdp_constraint import (
    SdpConstraintBlock,
    SdpConstraintBlockInactive,
    SdpConstraintBlockProvisioning,
)

ListOfSaps = Annotated[list[SI], Len(min_length=2, max_length=2)]

ListOfSdp_constraints = Annotated[list[SI], Len(min_length=0)]


class VirtualCircuitBlockInactive(ProductBlockModel, product_block_name="VirtualCircuit"):
    circuit_description: str | None = None
    service_speed: int | None = None
    saps: ListOfSaps[ServiceAccessPointBlockInactive]
    sdp_constraints: ListOfSdp_constraints[SdpConstraintBlockInactive]
    state: str | None = None
    global_reservation_id: str | None = None
    connection_id: str | None = None


class VirtualCircuitBlockProvisioning(VirtualCircuitBlockInactive, lifecycle=[SubscriptionLifecycle.PROVISIONING]):
    circuit_description: str
    service_speed: int
    saps: ListOfSaps[ServiceAccessPointBlockProvisioning]  # type: ignore[assignment]
    sdp_constraints: ListOfSdp_constraints[SdpConstraintBlockProvisioning]  # type: ignore[assignment]
    state: str
    global_reservation_id: str
    connection_id: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def title(self) -> str:
        return self.circuit_description


class VirtualCircuitBlock(VirtualCircuitBlockProvisioning, lifecycle=[SubscriptionLifecycle.ACTIVE]):
    circuit_description: str
    service_speed: int
    saps: ListOfSaps[ServiceAccessPointBlock]  # type: ignore[assignment]
    sdp_constraints: ListOfSdp_constraints[SdpConstraintBlock]  # type: ignore[assignment]
    state: str
    global_reservation_id: str
    connection_id: str
