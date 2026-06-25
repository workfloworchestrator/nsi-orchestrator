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

"""Add reconcile mdp2p workflow.

Revision ID: 16b749b8ea79
Revises: d6b99171601e
Create Date: 2026-06-25 00:00:00.000000

"""

from alembic import op
from orchestrator.core.migrations.helpers import create_workflow, delete_workflow
from orchestrator.core.targets import Target

# revision identifiers, used by Alembic.
revision = "16b749b8ea79"
down_revision = "d6b99171601e"
branch_labels = None
depends_on = None

new_workflows = [
    {
        "name": "reconcile_mdp2p",
        "target": Target.RECONCILE,
        "is_task": False,
        "description": "Reconcile mdp2p",
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
