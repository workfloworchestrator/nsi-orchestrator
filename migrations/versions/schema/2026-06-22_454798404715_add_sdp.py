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

"""Add sdp product.

Revision ID: 454798404715
Revises: b66721b43c63
Create Date: 2026-06-22 17:16:51.927374

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
revision = "454798404715"
down_revision = "b66721b43c63"
branch_labels = None
depends_on = None

new_products = {
    "products": {
        "sdp": {
            "product_id": uuid4(),
            "product_type": "ServiceDemarcationPoint",
            "description": "Network Service Interface service demarcation point",
            "tag": "SDP",
            "status": "active",
            "root_product_block": "ServiceDemarcationPoint",
            "fixed_inputs": {},
        },
    },
    "product_blocks": {
        "ServiceDemarcationPoint": {
            "product_block_id": uuid4(),
            "description": "Service demarcation point product block",
            "tag": "SDP",
            "status": "active",
            "resources": {
                "sdp_name": "Service demarcation point name",
            },
            "depends_on_block_relations": [
                "ServiceTerminationPoint",
            ],
        },
    },
    "workflows": {},
}

new_workflows = [
    {
        "name": "create_sdp",
        "target": Target.CREATE,
        "is_task": False,
        "description": "Create sdp",
        "product_type": "ServiceDemarcationPoint",
    },
    {
        "name": "modify_sdp",
        "target": Target.MODIFY,
        "is_task": False,
        "description": "Modify sdp",
        "product_type": "ServiceDemarcationPoint",
    },
    {
        "name": "terminate_sdp",
        "target": Target.TERMINATE,
        "is_task": False,
        "description": "Terminate sdp",
        "product_type": "ServiceDemarcationPoint",
    },
    {
        "name": "validate_sdp",
        "target": Target.VALIDATE,
        "is_task": True,
        "description": "Validate sdp",
        "product_type": "ServiceDemarcationPoint",
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
