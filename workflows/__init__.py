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

from orchestrator.core.workflows import LazyWorkflowInstance

LazyWorkflowInstance(
    "workflows.tasks.validate_aggregator_against_subscriptions",
    "task_validate_aggregator_against_subscriptions",
)

LazyWorkflowInstance("workflows.topology.create_topology", "create_topology")
LazyWorkflowInstance("workflows.topology.modify_topology", "modify_topology")
LazyWorkflowInstance("workflows.topology.terminate_topology", "terminate_topology")
LazyWorkflowInstance("workflows.topology.validate_topology", "validate_topology")

LazyWorkflowInstance("workflows.switchingservice.create_switchingservice", "create_switchingservice")
LazyWorkflowInstance("workflows.switchingservice.modify_switchingservice", "modify_switchingservice")
LazyWorkflowInstance(
    "workflows.switchingservice.terminate_switchingservice",
    "terminate_switchingservice",
)
LazyWorkflowInstance("workflows.switchingservice.validate_switchingservice", "validate_switchingservice")

LazyWorkflowInstance("workflows.stp.create_stp", "create_stp")
LazyWorkflowInstance("workflows.stp.modify_stp", "modify_stp")
LazyWorkflowInstance("workflows.stp.terminate_stp", "terminate_stp")
LazyWorkflowInstance("workflows.stp.validate_stp", "validate_stp")
LazyWorkflowInstance("workflows.stp.reconcile_stp", "reconcile_stp")

LazyWorkflowInstance("workflows.sdp.create_sdp", "create_sdp")
LazyWorkflowInstance("workflows.sdp.modify_sdp", "modify_sdp")
LazyWorkflowInstance("workflows.sdp.terminate_sdp", "terminate_sdp")
LazyWorkflowInstance("workflows.sdp.validate_sdp", "validate_sdp")

LazyWorkflowInstance("workflows.mdp2p.create_mdp2p", "create_mdp2p")
LazyWorkflowInstance("workflows.mdp2p.modify_mdp2p", "modify_mdp2p")
LazyWorkflowInstance("workflows.mdp2p.provision_mdp2p", "provision_mdp2p")
LazyWorkflowInstance("workflows.mdp2p.retry_reservation", "retry_reservation")
LazyWorkflowInstance("workflows.mdp2p.release_mdp2p", "release_mdp2p")
LazyWorkflowInstance("workflows.mdp2p.terminate_mdp2p", "terminate_mdp2p")
LazyWorkflowInstance("workflows.mdp2p.validate_mdp2p", "validate_mdp2p")
LazyWorkflowInstance("workflows.mdp2p.reconcile_mdp2p", "reconcile_mdp2p")
