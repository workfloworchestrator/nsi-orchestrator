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

"""Shared form helpers for the service termination point workflows."""

from typing import cast

from pydantic_forms.validators import Choice

from products.product_blocks.switchingservice import SwitchingServiceBlock
from products.product_types.switchingservice import SwitchingService
from services.dds_proxy import DdsServiceTerminationPoint, fetch_service_termination_points
from workflows.shared import subscribed_values, subscription_id_for_value


def available_service_termination_points() -> list[DdsServiceTerminationPoint]:
    """dds-proxy STPs without a subscription whose switching service is already subscribed."""
    subscribed = subscribed_values("ServiceTerminationPoint", "stp_id")
    switching_services = subscribed_values("SwitchingService", "switching_service_id")
    return [
        stp
        for stp in fetch_service_termination_points()
        if stp.id not in subscribed and stp.switching_service_id in switching_services
    ]


def stp_selector(stps: list[DdsServiceTerminationPoint]) -> type[Choice]:
    """Build a dropdown of ``stps``, keyed by ``stp_id`` and labelled ``name (id)``."""
    options = {stp.id: f"{stp.name} ({stp.id})" for stp in stps}
    choices = Choice("ServiceTerminationPoint", zip(options.keys(), options.items()))  # type: ignore[arg-type]
    return cast("type[Choice]", choices)


def switchingservice_block_for(switching_service_id: str) -> SwitchingServiceBlock:
    """Return the SwitchingServiceBlock of the subscription that owns ``switching_service_id``."""
    subscription_id = subscription_id_for_value("SwitchingService", "switching_service_id", switching_service_id)
    # never None: available_service_termination_points only offers stps whose switching service is subscribed
    assert subscription_id is not None
    return SwitchingService.from_subscription(subscription_id).switchingservice
