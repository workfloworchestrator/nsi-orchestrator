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

"""Add topology product.

Revision ID: 13e35d8ae1ed
Revises: 6de093f3da73
Create Date: 2026-06-18 13:32:04.869381

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
revision = "13e35d8ae1ed"
down_revision = "6de093f3da73"
branch_labels = None
depends_on = None

new_products = {
    "products": {
        "topology": {
            "product_id": uuid4(),
            "product_type": "Topology",
            "description": "Network Service Interface topology",
            "tag": "TOPOLOGY",
            "status": "active",
            "root_product_block": "Topology",
            "fixed_inputs": {},
        },
    },
    "product_blocks": {
        "Topology": {
            "product_block_id": uuid4(),
            "description": "Topology product block",
            "tag": "TOPOLOGY",
            "status": "active",
            "resources": {
                "topology_id": "Unique NSI topology identifier",
                "topology_name": "Topology description (as set by topology operator)",
            },
            "depends_on_block_relations": [],
        },
    },
    "workflows": {},
}

new_workflows = [
    {
        "name": "create_topology",
        "target": Target.CREATE,
        "is_task": False,
        "description": "Create topology",
        "product_type": "Topology",
    },
    {
        "name": "modify_topology",
        "target": Target.MODIFY,
        "is_task": False,
        "description": "Modify topology",
        "product_type": "Topology",
    },
    {
        "name": "terminate_topology",
        "target": Target.TERMINATE,
        "is_task": False,
        "description": "Terminate topology",
        "product_type": "Topology",
    },
    {
        "name": "validate_topology",
        "target": Target.VALIDATE,
        "is_task": True,
        "description": "Validate topology",
        "product_type": "Topology",
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
