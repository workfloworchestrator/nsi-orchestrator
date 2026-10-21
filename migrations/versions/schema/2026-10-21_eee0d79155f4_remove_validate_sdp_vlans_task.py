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

"""Remove validate SDP VLANs task; validate_sdp checks the VLANs now.

Soft-deletes the task, as core's ``WorkflowTable.delete`` does, so its past runs stay readable:
``processes.workflow_id`` has no cascade. Its schedule is deleted; the linker row cascades with it.

Revision ID: eee0d79155f4
Revises: 7db252dc184a
Create Date: 2026-10-21 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "eee0d79155f4"
down_revision = "7db252dc184a"
branch_labels = None
depends_on = None

TASK = "task_validate_sdp_vlans"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM apscheduler_jobs
            WHERE id IN (SELECT schedule_id
                         FROM workflows_apscheduler_jobs
                                  JOIN workflows USING (workflow_id)
                         WHERE name = :name)
            """
        ),
        {"name": TASK},
    )
    conn.execute(sa.text("UPDATE workflows SET deleted_at = now() WHERE name = :name"), {"name": TASK})


def downgrade() -> None:
    # The schedule comes back with `scheduler load-project-schedule` from the older schedules.py.
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE workflows SET deleted_at = NULL WHERE name = :name"), {"name": TASK})
