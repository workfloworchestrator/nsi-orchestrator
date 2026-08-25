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

"""Tests for schedules.py."""

from __future__ import annotations

import pytest
from orchestrator.core.schemas.schedules import build_trigger
from orchestrator.core.workflows import ALL_WORKFLOWS

import workflows  # noqa: F401  registers the LazyWorkflowInstance entries
from schedules import NSI_SCHEDULES

SCHEDULE_IDS = [schedule["name"] for schedule in NSI_SCHEDULES]


@pytest.mark.parametrize("schedule", NSI_SCHEDULES, ids=SCHEDULE_IDS)
def test_workflow_name_is_registered(schedule: dict) -> None:
    """A name with no LazyWorkflowInstance can never be scheduled."""
    assert schedule["workflow_name"] in ALL_WORKFLOWS


@pytest.mark.parametrize("schedule", NSI_SCHEDULES, ids=SCHEDULE_IDS)
def test_trigger_builds(schedule: dict) -> None:
    """Bad trigger kwargs are only rejected when the job is created."""
    assert build_trigger(schedule["trigger"], schedule["trigger_kwargs"]) is not None


_CRON_SCHEDULES = [s for s in NSI_SCHEDULES if s["trigger"] == "cron"]


@pytest.mark.parametrize("schedule", _CRON_SCHEDULES, ids=[s["name"] for s in _CRON_SCHEDULES])
def test_avoids_the_hour_and_half_hour_marks(schedule: dict) -> None:
    """Everyone's cron fires on :00 and :30; staggering off them spreads load on shared upstreams."""
    assert schedule["trigger_kwargs"].get("minute") not in (0, 30), "pick an off-minute"
