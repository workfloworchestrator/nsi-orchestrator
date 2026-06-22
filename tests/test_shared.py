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

"""Tests for shared workflow helpers."""

from __future__ import annotations

import pytest
from pydantic_forms.exceptions import FormValidationError

from services.dds_proxy import DdsProxyError
from workflows.shared import fetch_for_form


def test_fetch_for_form_passes_through_result() -> None:
    assert fetch_for_form(lambda: [1, 2]) == [1, 2]


def test_fetch_for_form_converts_dds_error_to_form_validation_error() -> None:
    def boom() -> list[str]:
        raise DdsProxyError("dds-proxy unavailable")

    with pytest.raises(FormValidationError, match="dds-proxy unavailable"):
        fetch_for_form(boom)
