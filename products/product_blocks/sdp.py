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

from products.product_blocks.stp import (
    ServiceTerminationPointBlock,
    ServiceTerminationPointBlockInactive,
    ServiceTerminationPointBlockProvisioning,
)

ListOfStps = Annotated[list[SI], Len(min_length=2, max_length=2)]


class ServiceDemarcationPointBlockInactive(ProductBlockModel, product_block_name="ServiceDemarcationPoint"):
    sdp_name: str | None = None
    stps: ListOfStps[ServiceTerminationPointBlockInactive]


class ServiceDemarcationPointBlockProvisioning(
    ServiceDemarcationPointBlockInactive, lifecycle=[SubscriptionLifecycle.PROVISIONING]
):
    sdp_name: str
    stps: ListOfStps[ServiceTerminationPointBlockProvisioning]  # type: ignore[assignment]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def title(self) -> str:
        return self.sdp_name


class ServiceDemarcationPointBlock(ServiceDemarcationPointBlockProvisioning, lifecycle=[SubscriptionLifecycle.ACTIVE]):
    sdp_name: str
    stps: ListOfStps[ServiceTerminationPointBlock]  # type: ignore[assignment]
