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

from products.product_blocks.topology import (
    TopologyBlock,
    TopologyBlockInactive,
    TopologyBlockProvisioning,
)


class SwitchingServiceBlockInactive(ProductBlockModel, product_block_name="SwitchingService"):
    switching_service_id: str | None = None
    switching_service_name: str | None = None
    topology: TopologyBlockInactive | None = None


class SwitchingServiceBlockProvisioning(SwitchingServiceBlockInactive, lifecycle=[SubscriptionLifecycle.PROVISIONING]):
    switching_service_id: str
    switching_service_name: str
    topology: TopologyBlockProvisioning

    @computed_field  # type: ignore[prop-decorator]
    @property
    def title(self) -> str:
        return f"{self.name} {self.switching_service_id}"


class SwitchingServiceBlock(SwitchingServiceBlockProvisioning, lifecycle=[SubscriptionLifecycle.ACTIVE]):
    switching_service_id: str
    switching_service_name: str
    topology: TopologyBlock
