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

"""Add validate SDP VLANs task.

Revision ID: 7db252dc184a
Revises: db35332386c4
Create Date: 2026-10-14 00:00:00.000000

"""

from alembic import op
from orchestrator.core.migrations.helpers import create_task, delete_workflow

# revision identifiers, used by Alembic.
revision = "7db252dc184a"
down_revision = "db35332386c4"
branch_labels = None
depends_on = None

new_tasks = [
    {
        "name": "task_validate_sdp_vlans",
        "description": "Validate SDP VLANs",
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
