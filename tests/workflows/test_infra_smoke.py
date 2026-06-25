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

"""Smoke test that the integration test database is created, migrated and session-bound."""

from __future__ import annotations

from orchestrator.core.db import ProductTable, db
from sqlalchemy import select


def test_database_is_migrated() -> None:
    product_types = set(db.session.scalars(select(ProductTable.product_type)))
    assert {
        "Topology",
        "SwitchingService",
        "ServiceTerminationPoint",
        "ServiceDemarcationPoint",
        "MultiDomainPoint2Point",
    } <= product_types
