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

import structlog
from orchestrator.core.utils.errors import InconsistentDataError
from orchestrator.core.workflow import StepList, begin, step
from orchestrator.core.workflows.utils import reconcile_workflow
from pydantic_forms.types import State

from products.product_types.stp import ServiceTerminationPoint
from services.dds_proxy import fetch_service_termination_points
from workflows.mdp2p.shared.vlans import stranded_lines, vlans_outside

logger = structlog.get_logger(__name__)


@step("Reconcile capacity and VLAN range from the DDS")
def reconcile_dds_attributes(subscription: ServiceTerminationPoint) -> State:
    """Update capacity and label_group from the dds-proxy; leave them untouched if the STP is gone.

    capacity and label_group (the STP's allowed VLAN range) are both DDS-derived; an operator can
    change either after the STP was subscribed, so reconcile re-reads them. The label_group keeps the
    MDP2P create form validating new VLANs against the STP's current range. A range that leaves out a
    VLAN a subscription stores is refused, and nothing is updated.
    """
    stp_id = subscription.stp.stp_id
    stp_by_id = {stp.id: stp for stp in fetch_service_termination_points()}
    if (dds_stp := stp_by_id.get(stp_id)) is not None:
        if stranded := vlans_outside(stp_id, dds_stp.label_group):
            raise InconsistentDataError(
                f"The DDS range {dds_stp.label_group} of {stp_id} leaves out VLANs that subscriptions use; "
                "move or terminate them and retry:\n" + stranded_lines(stranded),
                {"label_group": dds_stp.label_group, "stranded": stranded},
            )
        subscription.stp.capacity = dds_stp.capacity_mbits
        subscription.stp.label_group = dds_stp.label_group

    return {"subscription": subscription}


@reconcile_workflow()
def reconcile_stp() -> StepList:
    return begin >> reconcile_dds_attributes
