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

from enum import StrEnum

from orchestrator.core.domain.base import ProductBlockModel
from orchestrator.core.types import SubscriptionLifecycle
from pydantic import computed_field

from products.product_blocks.sdp import (
    ServiceDemarcationPointBlock,
    ServiceDemarcationPointBlockInactive,
    ServiceDemarcationPointBlockProvisioning,
)


class ConstraintType(StrEnum):
    INCLUDE = "INCLUDE"
    EXCLUDE = "EXCLUDE"


class SdpConstraintBlockInactive(ProductBlockModel, product_block_name="SdpConstraint"):
    constraint_type: ConstraintType | None = None
    sdp: ServiceDemarcationPointBlockInactive | None = None


class SdpConstraintBlockProvisioning(SdpConstraintBlockInactive, lifecycle=[SubscriptionLifecycle.PROVISIONING]):
    constraint_type: ConstraintType
    sdp: ServiceDemarcationPointBlockProvisioning

    @computed_field  # type: ignore[prop-decorator]
    @property
    def title(self) -> str:
        return f"sdp_constraint {self.constraint_type} {self.sdp.sdp_name}"


class SdpConstraintBlock(SdpConstraintBlockProvisioning, lifecycle=[SubscriptionLifecycle.ACTIVE]):
    constraint_type: ConstraintType
    sdp: ServiceDemarcationPointBlock
