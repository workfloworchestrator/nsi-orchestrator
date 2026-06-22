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

"""Add switchingservice product.

Revision ID: e9c7f020ab00
Revises: 13e35d8ae1ed
Create Date: 2026-06-22 13:15:20.500588

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
revision = "e9c7f020ab00"
down_revision = "13e35d8ae1ed"
branch_labels = None
depends_on = None

new_products = {
    "products": {
        "switchingservice": {
            "product_id": uuid4(),
            "product_type": "SwitchingService",
            "description": "Network Service Interface switching service",
            "tag": "SWITCHINGSERVICE",
            "status": "active",
            "root_product_block": "SwitchingService",
            "fixed_inputs": {},
        },
    },
    "product_blocks": {
        "SwitchingService": {
            "product_block_id": uuid4(),
            "description": "Switching service product block",
            "tag": "SWITCHINGSERVICE",
            "status": "active",
            "resources": {
                "switching_service_id": "Unique NSI switching service identifier",
                "switching_service_name": "Switching service name",
            },
            "depends_on_block_relations": [
                "Topology",
            ],
        },
    },
    "workflows": {},
}

new_workflows = [
    {
        "name": "create_switchingservice",
        "target": Target.CREATE,
        "is_task": False,
        "description": "Create switchingservice",
        "product_type": "SwitchingService",
    },
    {
        "name": "modify_switchingservice",
        "target": Target.MODIFY,
        "is_task": False,
        "description": "Modify switchingservice",
        "product_type": "SwitchingService",
    },
    {
        "name": "terminate_switchingservice",
        "target": Target.TERMINATE,
        "is_task": False,
        "description": "Terminate switchingservice",
        "product_type": "SwitchingService",
    },
    {
        "name": "validate_switchingservice",
        "target": Target.VALIDATE,
        "is_task": True,
        "description": "Validate switchingservice",
        "product_type": "SwitchingService",
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
