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

from collections.abc import Callable, Generator
from typing import Any, NoReturn, TypeAlias, cast
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
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pydantic_forms.core.translations import translations
from pydantic_forms.exceptions import FormValidationError
from pydantic_i18n import PydanticI18n
from sqlalchemy import Select, select

from services.aggregator_proxy import AggregatorProxyError
from services.dds_proxy import DdsProxyError


def summary_form(product_name: str, summary_data: dict) -> Generator:
    summary = migration_summary(summary_data)  # type: ignore[arg-type]
    # The `type` keyword cannot alias a cast() call, so the annotated form stays.
    ProductSummary: TypeAlias = cast("type[MigrationSummary]", summary)  # noqa: UP040

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


def subscription_descriptions_for_values(product_type: str, resource_type: str) -> dict[str, str]:
    """Map each ``resource_type`` value to its subscription description (non-terminated ``product_type``)."""
    query = _value_select(SubscriptionInstanceValueTable.value, product_type, resource_type).add_columns(
        SubscriptionTable.description
    )
    return {value: description for value, description in db.session.execute(query).all()}


def subscription_ids_for_product_type(product_type: str) -> list[UUID]:
    """Return the subscription ids of all non-terminated subscriptions of ``product_type``."""
    query = (
        select(SubscriptionTable.subscription_id)
        .join(ProductTable, SubscriptionTable.product_id == ProductTable.product_id)
        .where(ProductTable.product_type == product_type)
        .where(SubscriptionTable.status != SubscriptionLifecycle.TERMINATED)
    )
    return list(db.session.scalars(query))


def raise_form_validation_error(message: str) -> NoReturn:
    """Raise a FormValidationError carrying ``message`` (rendered cleanly by the orchestrator UI)."""

    class _FormError(BaseModel):
        @model_validator(mode="after")
        def _fail(self) -> "_FormError":
            raise ValueError(message)

    try:
        _FormError()
    except ValidationError as validation_error:
        raise FormValidationError("form", validation_error, PydanticI18n(translations)) from None
    raise RuntimeError(message)  # unreachable: _FormError always raises during validation


def fetch_for_form[T](fetch: Callable[[], T]) -> T:
    """Run a proxy ``fetch`` while building an input form.

    Converts a ``DdsProxyError`` / ``AggregatorProxyError`` (e.g. the proxy is unavailable) into a
    ``FormValidationError`` so the UI shows a clear message instead of a 500.
    """
    try:
        return fetch()
    except (DdsProxyError, AggregatorProxyError) as exc:
        raise_form_validation_error(str(exc))
