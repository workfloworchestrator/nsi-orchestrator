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


from orchestrator.core.domain.base import SubscriptionModel
from orchestrator.core.types import SubscriptionLifecycle

from products.product_blocks.topology import (
    TopologyBlock,
    TopologyBlockInactive,
    TopologyBlockProvisioning,
)


class TopologyInactive(SubscriptionModel, is_base=True):
    topology: TopologyBlockInactive


class TopologyProvisioning(
    TopologyInactive, lifecycle=[SubscriptionLifecycle.PROVISIONING]
):
    topology: TopologyBlockProvisioning


class Topology(TopologyProvisioning, lifecycle=[SubscriptionLifecycle.ACTIVE]):
    topology: TopologyBlock
