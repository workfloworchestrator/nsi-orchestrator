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


from orchestrator.core.domain.base import ProductBlockModel
from orchestrator.core.types import SubscriptionLifecycle
from pydantic import computed_field

from products.product_blocks.stp import (
    ServiceTerminationPointBlock,
    ServiceTerminationPointBlockInactive,
    ServiceTerminationPointBlockProvisioning,
)


class ServiceAccessPointBlockInactive(ProductBlockModel, product_block_name="ServiceAccessPoint"):
    vlan: str | None = None
    stp: ServiceTerminationPointBlockInactive | None = None


class ServiceAccessPointBlockProvisioning(
    ServiceAccessPointBlockInactive, lifecycle=[SubscriptionLifecycle.PROVISIONING]
):
    vlan: str
    stp: ServiceTerminationPointBlockProvisioning

    @computed_field  # type: ignore[prop-decorator]
    @property
    def title(self) -> str:
        return f"sap {self.stp.stp_id.removeprefix('urn:ogf:network:')}"


class ServiceAccessPointBlock(ServiceAccessPointBlockProvisioning, lifecycle=[SubscriptionLifecycle.ACTIVE]):
    vlan: str
    stp: ServiceTerminationPointBlock
