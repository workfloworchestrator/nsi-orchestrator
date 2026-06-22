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

"""Add stp product.

Revision ID: b66721b43c63
Revises: e9c7f020ab00
Create Date: 2026-06-22 16:07:18.928406

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
revision = "b66721b43c63"
down_revision = "e9c7f020ab00"
branch_labels = None
depends_on = None

new_products = {
    "products": {
        "stp": {
            "product_id": uuid4(),
            "product_type": "ServiceTerminationPoint",
            "description": "Network Service Interface service termination point",
            "tag": "STP",
            "status": "active",
            "root_product_block": "ServiceTerminationPoint",
            "fixed_inputs": {},
        },
    },
    "product_blocks": {
        "ServiceTerminationPoint": {
            "product_block_id": uuid4(),
            "description": "Service termination point product block",
            "tag": "STP",
            "status": "active",
            "resources": {
                "stp_id": "Unique NSI service termination point identifier",
                "stp_name": "Service termination point name",
                "capacity": "The capacity of this service termination point",
                "label_group": "The set of allowed labels for this service termination point",
            },
            "depends_on_block_relations": [
                "SwitchingService",
            ],
        },
    },
    "workflows": {},
}

new_workflows = [
    {
        "name": "create_stp",
        "target": Target.CREATE,
        "is_task": False,
        "description": "Create stp",
        "product_type": "ServiceTerminationPoint",
    },
    {
        "name": "modify_stp",
        "target": Target.MODIFY,
        "is_task": False,
        "description": "Modify stp",
        "product_type": "ServiceTerminationPoint",
    },
    {
        "name": "terminate_stp",
        "target": Target.TERMINATE,
        "is_task": False,
        "description": "Terminate stp",
        "product_type": "ServiceTerminationPoint",
    },
    {
        "name": "validate_stp",
        "target": Target.VALIDATE,
        "is_task": True,
        "description": "Validate stp",
        "product_type": "ServiceTerminationPoint",
    },
    {
        "name": "reconcile_stp",
        "target": Target.RECONCILE,
        "is_task": False,
        "description": "Reconcile stp",
        "product_type": "ServiceTerminationPoint",
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
