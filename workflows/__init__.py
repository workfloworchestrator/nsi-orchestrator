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

LazyWorkflowInstance("workflows.topology.create_topology", "create_topology")
LazyWorkflowInstance("workflows.topology.modify_topology", "modify_topology")
LazyWorkflowInstance("workflows.topology.terminate_topology", "terminate_topology")
LazyWorkflowInstance("workflows.topology.validate_topology", "validate_topology")

LazyWorkflowInstance(
    "workflows.switchingservice.create_switchingservice", "create_switchingservice"
)
LazyWorkflowInstance(
    "workflows.switchingservice.modify_switchingservice", "modify_switchingservice"
)
LazyWorkflowInstance(
    "workflows.switchingservice.terminate_switchingservice",
    "terminate_switchingservice",
)
LazyWorkflowInstance(
    "workflows.switchingservice.validate_switchingservice", "validate_switchingservice"
)
