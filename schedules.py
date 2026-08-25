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

"""This project's scheduled tasks, registered through orchestrator-core's schedule API.

See README **Scheduled tasks** for how these are loaded and CLAUDE.md for the deduplication caveat.
"""

import typer
from orchestrator.core.schedules.service import add_unique_scheduled_task_to_queue
from orchestrator.core.schemas.schedules import APSchedulerJobCreate
from orchestrator.core.services.workflows import get_workflow_by_name

NSI_SCHEDULES: list[dict] = [
    {
        "name": "Validate aggregator against subscriptions",
        "workflow_name": "task_validate_aggregator_against_subscriptions",
        "trigger": "cron",
        "trigger_kwargs": {"hour": 1, "minute": 50},
    },
]


def load_project_schedules(
    recreate: bool = typer.Option(False, help="Whether to delete any existing schedules before creating"),
) -> None:
    """Register this project's schedules, on top of core's ``load-initial-schedule``."""
    for schedule in NSI_SCHEDULES:
        workflow_name = schedule["workflow_name"]
        workflow = get_workflow_by_name(workflow_name)
        if not workflow:
            raise RuntimeError(
                f"Cannot schedule unknown workflow {workflow_name!r}; is it registered in workflows/__init__.py "
                "and created by a migration?"
            )
        payload = APSchedulerJobCreate(**schedule, workflow_id=workflow.workflow_id)
        created = add_unique_scheduled_task_to_queue(payload, recreate=recreate)
        typer.echo(f"{'Queued' if created else 'Already scheduled'}: {schedule['name']}")
