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

"""A minimal in-process workflow test harness.

orchestrator-core ships these helpers only in its own ``test/`` tree (not in the package), so we
vendor a trimmed version: ``run_workflow`` mimics ``start_process`` (create the process and run its
steps synchronously, in this thread), ``resume_callback`` drives a workflow waiting in
``AWAITING_CALLBACK`` by injecting the callback payload, and the ``assert_*`` / ``extract_*`` helpers
inspect the resulting ``Process``. Adapted from orchestrator-core ``test/integration_tests/workflows``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from orchestrator.core.services.processes import create_process
from orchestrator.core.utils.json import json_dumps, json_loads
from orchestrator.core.workflow import AwaitingCallback
from orchestrator.core.workflow import Process as WFProcess
from orchestrator.core.workflow import ProcessStat, Step, runwf
from pydantic_forms.types import State

StepLog = list[tuple[Step, WFProcess]]


def _raise_exception(state: Any) -> Any:
    if isinstance(state, Exception):
        raise state
    return state


def assert_complete(result: WFProcess) -> None:
    assert result.on_failed(_raise_exception).iscomplete(), f"Expected Complete, but was: {result}"


def assert_awaiting_callback(result: WFProcess) -> None:
    assert result.on_failed(_raise_exception).isawaitingcallback(), f"Expected AwaitingCallback, but was: {result}"


def assert_failed(result: WFProcess) -> None:
    assert result.isfailed(), f"Expected Failed, but was: {result}"


def extract_state(result: WFProcess) -> State:
    return cast("State", result.unwrap())


def extract_error(result: WFProcess) -> Any:
    return extract_state(result).get("error")


def _store_step(step_log: StepLog) -> Callable[[ProcessStat, Step, WFProcess], WFProcess]:
    def __store_step(pstat: ProcessStat, step: Step, process: WFProcess) -> WFProcess:
        process = process.map(lambda s: json_loads(json_dumps(s)))
        state = process.unwrap()
        state.pop("__step_name_override", None)
        for key in [*state.get("__remove_keys", []), "__remove_keys"]:
            state.pop(key, None)
        if state.pop("__replace_last_state", None):
            step_log[-1] = (step, process)
        else:
            step_log.append((step, process))
        return process

    return __store_step


def _sanitize_input(input_data: State | list[State]) -> list[State]:
    if not isinstance(input_data, list):
        input_data = [input_data]
    return cast("list[State]", json_loads(json_dumps(input_data)))


def product_id(product_type: str) -> str:
    """Return the product id for ``product_type`` (the first input page of a create workflow)."""
    from orchestrator.core.db import ProductTable, db
    from sqlalchemy import select

    return str(db.session.scalar(select(ProductTable.product_id).where(ProductTable.product_type == product_type)))


def run_workflow(workflow_key: str, input_data: State | list[State]) -> tuple[WFProcess, ProcessStat, StepLog]:
    """Create and synchronously run ``workflow_key``; return (result, process, step_log)."""
    pstat = create_process(workflow_key, _sanitize_input(input_data), "john.doe")
    step_log: StepLog = []
    result = runwf(pstat, _store_step(step_log))
    return result, pstat, step_log


def resume_callback(
    process: ProcessStat, step_log: StepLog, callback_result: State, result_key: str = "callback_result"
) -> tuple[WFProcess, StepLog]:
    """Resume a workflow stopped in AWAITING_CALLBACK by injecting ``callback_result`` into the state.

    Mirrors what the callback endpoint does (``state[result_key] = payload``) and runs the remaining
    steps (validate + cleanup + anything after the callback step) synchronously.
    """
    awaiting_step, awaiting_process = step_log[-1]
    assert awaiting_process.isawaitingcallback(), f"Process is not awaiting a callback: {awaiting_process}"
    state = {**awaiting_process.unwrap(), result_key: callback_result}
    remaining_steps = process.workflow.steps[len(step_log) :]
    resumed = process.update(log=remaining_steps, state=AwaitingCallback(state))
    result = runwf(resumed, _store_step(step_log))
    return result, step_log
