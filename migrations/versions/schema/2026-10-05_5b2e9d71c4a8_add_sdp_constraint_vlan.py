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

"""Add an optional VLAN to the SDP constraint.

The resource type is shared with the ServiceAccessPoint ``vlan``, so the downgrade only unlinks it
from SdpConstraint and drops the values stored for that block.

Revision ID: 5b2e9d71c4a8
Revises: c3d81f6a2b74
Create Date: 2026-10-05 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from orchestrator.core.migrations.helpers import (
    create_resource_types_for_product_blocks,
    delete_resource_types_from_product_blocks,
)

revision = "5b2e9d71c4a8"
down_revision = "c3d81f6a2b74"
branch_labels = None
depends_on = None

new_resource_types = {"SdpConstraint": {"vlan": "The VLAN used on the STP"}}


def upgrade() -> None:
    conn = op.get_bind()
    create_resource_types_for_product_blocks(conn, new_resource_types)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """DELETE FROM subscription_instance_values siv
               USING subscription_instances si, product_blocks pb, resource_types rt
               WHERE siv.subscription_instance_id = si.subscription_instance_id
                 AND si.product_block_id = pb.product_block_id
                 AND siv.resource_type_id = rt.resource_type_id
                 AND pb.name = 'SdpConstraint'
                 AND rt.resource_type = 'vlan'"""
        )
    )
    delete_resource_types_from_product_blocks(conn, new_resource_types)
