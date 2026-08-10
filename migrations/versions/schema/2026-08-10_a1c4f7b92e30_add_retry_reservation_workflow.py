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

"""Add retry reservation workflow.

Revision ID: a1c4f7b92e30
Revises: 16b749b8ea79
Create Date: 2026-08-10 00:00:00.000000

"""

from alembic import op
from orchestrator.core.migrations.helpers import create_workflow, delete_workflow
from orchestrator.core.targets import Target

# revision identifiers, used by Alembic.
revision = "a1c4f7b92e30"
down_revision = "16b749b8ea79"
branch_labels = None
depends_on = None

new_workflows = [
    {
        "name": "retry_reservation",
        "target": Target.MODIFY,
        "is_task": False,
        "description": "Retry reservation",
        "product_type": "MultiDomainPoint2Point",
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    for workflow in new_workflows:
        create_workflow(conn, workflow)


def downgrade() -> None:
    conn = op.get_bind()
    for workflow in new_workflows:
        delete_workflow(conn, workflow["name"])
