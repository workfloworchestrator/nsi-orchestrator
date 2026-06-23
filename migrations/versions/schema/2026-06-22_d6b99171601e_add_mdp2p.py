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

"""Add mdp2p product.

Revision ID: d6b99171601e
Revises: 454798404715
Create Date: 2026-06-22 21:30:07.495320

"""

from uuid import uuid4

from alembic import op
from orchestrator.core.migrations.helpers import (
    create,
    create_workflow,
    delete,
    delete_workflow,
    ensure_default_workflows,
)
from orchestrator.core.targets import Target

# revision identifiers, used by Alembic.
revision = "d6b99171601e"
down_revision = "454798404715"
branch_labels = None
depends_on = None

new_products = {
    "products": {
        "mdp2p": {
            "product_id": uuid4(),
            "product_type": "MultiDomainPoint2Point",
            "description": "Network Service Interface multi domain point to point",
            "tag": "MDP2P",
            "status": "active",
            "root_product_block": "VirtualCircuit",
            "fixed_inputs": {},
        },
    },
    "product_blocks": {
        "ServiceAccessPoint": {
            "product_block_id": uuid4(),
            "description": "Service access point",
            "tag": "SAP",
            "status": "active",
            "resources": {
                "label": "The label used on the STP",
            },
            "depends_on_block_relations": [
                "ServiceTerminationPoint",
            ],
        },
        "SdpConstraint": {
            "product_block_id": uuid4(),
            "description": "SDP constraint for the PCE",
            "tag": "SDP_CONSTRAINT",
            "status": "active",
            "resources": {
                "constraint_type": "Wether to include or exclude the SDP",
            },
            "depends_on_block_relations": [
                "ServiceDemarcationPoint",
            ],
        },
        "VirtualCircuit": {
            "product_block_id": uuid4(),
            "description": "Virtual circuit product block",
            "tag": "VC",
            "status": "active",
            "resources": {
                "circuit_description": "Virtual circuit description",
                "service_speed": "Speed of the service",
                "state": "Virtual circuit reservation state",
                "global_reservation_id": "Orchestrator-generated global reservation id (urn:uuid:...)",
                "connection_id": "Aggregator-assigned connection id, known after the reserve callback",
            },
            "depends_on_block_relations": [
                "SdpConstraint",
                "ServiceAccessPoint",
            ],
        },
    },
    "workflows": {},
}

new_workflows = [
    {
        "name": "create_mdp2p",
        "target": Target.CREATE,
        "is_task": False,
        "description": "Create mdp2p",
        "product_type": "MultiDomainPoint2Point",
    },
    {
        "name": "modify_mdp2p",
        "target": Target.MODIFY,
        "is_task": False,
        "description": "Modify mdp2p",
        "product_type": "MultiDomainPoint2Point",
    },
    {
        "name": "provision_mdp2p",
        "target": Target.MODIFY,
        "is_task": False,
        "description": "Provision mdp2p",
        "product_type": "MultiDomainPoint2Point",
    },
    {
        "name": "release_mdp2p",
        "target": Target.MODIFY,
        "is_task": False,
        "description": "Release mdp2p",
        "product_type": "MultiDomainPoint2Point",
    },
    {
        "name": "terminate_mdp2p",
        "target": Target.TERMINATE,
        "is_task": False,
        "description": "Terminate mdp2p",
        "product_type": "MultiDomainPoint2Point",
    },
    {
        "name": "validate_mdp2p",
        "target": Target.VALIDATE,
        "is_task": True,
        "description": "Validate mdp2p",
        "product_type": "MultiDomainPoint2Point",
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    create(conn, new_products)
    for workflow in new_workflows:
        create_workflow(conn, workflow)
    ensure_default_workflows(conn)


def downgrade() -> None:
    conn = op.get_bind()
    for workflow in new_workflows:
        delete_workflow(conn, workflow["name"])

    delete(conn, new_products)
