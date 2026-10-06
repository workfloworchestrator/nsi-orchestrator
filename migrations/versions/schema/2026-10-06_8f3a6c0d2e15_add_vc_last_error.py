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

"""Add the last error to the VirtualCircuit.

Revision ID: 8f3a6c0d2e15
Revises: 5b2e9d71c4a8
Create Date: 2026-10-06 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from orchestrator.core.migrations.helpers import (
    create_resource_types_for_product_blocks,
    delete_resource_types_from_product_blocks,
)

revision = "8f3a6c0d2e15"
down_revision = "5b2e9d71c4a8"
branch_labels = None
depends_on = None

new_resource_types = {
    "VirtualCircuit": {"last_error": "The aggregator's reason for the last failed operation, empty after a success"}
}


def upgrade() -> None:
    conn = op.get_bind()
    create_resource_types_for_product_blocks(conn, new_resource_types)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """DELETE FROM subscription_instance_values siv
               USING resource_types rt
               WHERE siv.resource_type_id = rt.resource_type_id
                 AND rt.resource_type = 'last_error'"""
        )
    )
    delete_resource_types_from_product_blocks(conn, new_resource_types)
    # Not core's delete_resource_types: it binds a tuple to ANY(), which psycopg 3 rejects.
    conn.execute(sa.text("DELETE FROM resource_types WHERE resource_type = 'last_error'"))
