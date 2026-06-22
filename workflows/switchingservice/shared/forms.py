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

"""Shared form helpers for the switching service workflows."""

from typing import cast

from pydantic_forms.validators import Choice

from products.product_blocks.topology import TopologyBlock
from products.product_types.topology import Topology
from services.dds_proxy import DdsSwitchingService, fetch_switching_services
from workflows.shared import subscribed_values, subscription_id_for_value


def available_switching_services() -> list[DdsSwitchingService]:
    """dds-proxy switching services without a subscription whose topology is already subscribed."""
    subscribed = subscribed_values("SwitchingService", "switching_service_id")
    topologies = subscribed_values("Topology", "topology_id")
    return [
        service
        for service in fetch_switching_services()
        if service.id not in subscribed and service.topology_id in topologies
    ]


def switchingservice_selector(services: list[DdsSwitchingService]) -> type[Choice]:
    """Build a dropdown of ``services``, keyed and labelled by ``switching_service_id``."""
    options = {service.id: service.id for service in services}
    choices = Choice("SwitchingService", zip(options.keys(), options.items()))  # type: ignore[arg-type]
    return cast("type[Choice]", choices)


def topology_block_for(topology_id: str) -> TopologyBlock:
    """Return the TopologyBlock of the subscription that owns ``topology_id``."""
    subscription_id = subscription_id_for_value("Topology", "topology_id", topology_id)
    # never None: available_switching_services only offers services whose topology is subscribed
    assert subscription_id is not None
    return Topology.from_subscription(subscription_id).topology
