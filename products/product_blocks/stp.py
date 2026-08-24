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

from products.product_blocks.switchingservice import (
    SwitchingServiceBlock,
    SwitchingServiceBlockInactive,
    SwitchingServiceBlockProvisioning,
)


class ServiceTerminationPointBlockInactive(ProductBlockModel, product_block_name="ServiceTerminationPoint"):
    stp_id: str | None = None
    stp_name: str | None = None
    capacity: int | None = None
    label_group: str | None = None
    switching_service: SwitchingServiceBlockInactive | None = None


class ServiceTerminationPointBlockProvisioning(
    ServiceTerminationPointBlockInactive, lifecycle=[SubscriptionLifecycle.PROVISIONING]
):
    stp_id: str
    stp_name: str
    capacity: int
    label_group: str
    switching_service: SwitchingServiceBlockProvisioning

    @computed_field  # type: ignore[prop-decorator]
    @property
    def title(self) -> str:
        return self.stp_name


class ServiceTerminationPointBlock(ServiceTerminationPointBlockProvisioning, lifecycle=[SubscriptionLifecycle.ACTIVE]):
    stp_id: str
    stp_name: str
    capacity: int
    label_group: str
    switching_service: SwitchingServiceBlock
