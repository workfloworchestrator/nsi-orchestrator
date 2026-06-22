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

from collections.abc import Generator
from typing import Any, TypeAlias, cast
from uuid import UUID

from orchestrator.core.db import (
    ProductTable,
    ResourceTypeTable,
    SubscriptionInstanceTable,
    SubscriptionInstanceValueTable,
    SubscriptionTable,
    db,
)
from orchestrator.core.domain.base import ProductBlockModel
from orchestrator.core.forms import FormPage
from orchestrator.core.forms.validators import MigrationSummary, migration_summary
from orchestrator.core.types import SubscriptionLifecycle
from pydantic import ConfigDict
from sqlalchemy import Select, select


def summary_form(product_name: str, summary_data: dict) -> Generator:
    summary = migration_summary(summary_data)  # type: ignore[arg-type]
    ProductSummary: TypeAlias = cast("type[MigrationSummary]", summary)

    class SummaryForm(FormPage):
        model_config = ConfigDict(title=f"{product_name} summary")

        product_summary: ProductSummary

    yield SummaryForm


def create_summary_form(user_input: dict, product_name: str, fields: list[str]) -> Generator:
    columns = [[str(user_input[nm]) for nm in fields]]
    yield from summary_form(product_name, {"labels": fields, "columns": columns})


def modify_summary_form(user_input: dict, block: ProductBlockModel, fields: list[str]) -> Generator:
    before = [str(getattr(block, nm)) for nm in fields]
    after = [str(user_input[nm]) for nm in fields]
    yield from summary_form(
        block.subscription.product.name,  # type: ignore[union-attr]
        {
            "labels": fields,
            "headers": ["Before", "After"],
            "columns": [before, after],
        },
    )


def _value_select(column: Any, product_type: str, resource_type: str) -> Select:
    """Select ``column`` for a resource type across non-terminated subscriptions of a product type."""
    return (
        select(column)
        .select_from(SubscriptionInstanceValueTable)
        .join(
            ResourceTypeTable,
            SubscriptionInstanceValueTable.resource_type_id == ResourceTypeTable.resource_type_id,
        )
        .join(
            SubscriptionInstanceTable,
            SubscriptionInstanceValueTable.subscription_instance_id
            == SubscriptionInstanceTable.subscription_instance_id,
        )
        .join(
            SubscriptionTable,
            SubscriptionInstanceTable.subscription_id == SubscriptionTable.subscription_id,
        )
        .join(ProductTable, SubscriptionTable.product_id == ProductTable.product_id)
        .where(ProductTable.product_type == product_type)
        .where(ResourceTypeTable.resource_type == resource_type)
        .where(SubscriptionTable.status != SubscriptionLifecycle.TERMINATED)
    )


def subscribed_values(product_type: str, resource_type: str) -> set[str]:
    """Return the ``resource_type`` values across non-terminated ``product_type`` subscriptions."""
    return set(db.session.scalars(_value_select(SubscriptionInstanceValueTable.value, product_type, resource_type)))


def subscription_id_for_value(product_type: str, resource_type: str, value: str) -> UUID | None:
    """Return the subscription id whose ``resource_type`` equals ``value`` (first match), or None."""
    query = _value_select(SubscriptionTable.subscription_id, product_type, resource_type).where(
        SubscriptionInstanceValueTable.value == value
    )
    result: UUID | None = db.session.scalars(query).first()
    return result
