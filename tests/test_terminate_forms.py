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

"""Every terminate form builds — it uses Annotated[DisplaySubscription, Field(subscription_id)]."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module_path",
    [
        "workflows.topology.terminate_topology",
        "workflows.switchingservice.terminate_switchingservice",
        "workflows.stp.terminate_stp",
        "workflows.sdp.terminate_sdp",
    ],
)
def test_terminate_form_generator_builds(module_path: str) -> None:
    module = importlib.import_module(module_path)
    form = module.terminate_initial_input_form_generator(
        "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
    )
    assert "subscription_id" in form.model_fields
