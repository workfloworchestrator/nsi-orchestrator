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

"""Add validate aggregator against subscriptions task.

Revision ID: c3d81f6a2b74
Revises: a1c4f7b92e30
Create Date: 2026-08-25 00:00:00.000000

"""

from alembic import op
from orchestrator.core.migrations.helpers import create_task, delete_workflow

# revision identifiers, used by Alembic.
revision = "c3d81f6a2b74"
down_revision = "a1c4f7b92e30"
branch_labels = None
depends_on = None

new_tasks = [
    {
        "name": "task_validate_aggregator_against_subscriptions",
        "description": "Validate aggregator reservations against subscriptions",
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    for task in new_tasks:
        create_task(conn, task)


def downgrade() -> None:
    conn = op.get_bind()
    for task in new_tasks:
        delete_workflow(conn, task["name"])
