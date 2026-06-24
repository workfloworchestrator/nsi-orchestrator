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

"""Connection reservation state machine for the multi domain point-to-point product.

The aggregator-proxy owns the detailed NSI lifecycle and rejects illegal operations itself; this
is the orchestrator's local view, persisted on ``vc.state``. It models only the resting states the
proxy reports back in a callback and the transitions the workflows drive between them:

    CREATED --reserve--> RESERVED --provision--> ACTIVATED
                            ^                         |
                            +--------release----------+
    RESERVED / FAILED --terminate--> TERMINATED   (any reserve/provision/release may end in FAILED)
"""

from statemachine import State, StateMachine


class ConnectionState:
    """The string values stored on ``vc.state``."""

    CREATED = "CREATED"
    RESERVED = "RESERVED"
    ACTIVATED = "ACTIVATED"
    FAILED = "FAILED"
    TERMINATED = "TERMINATED"


class ConnectionStateMachine(StateMachine):
    """Legal transitions of a multi domain point-to-point connection reservation."""

    created = State(ConnectionState.CREATED, initial=True, value=ConnectionState.CREATED)
    reserved = State(ConnectionState.RESERVED, value=ConnectionState.RESERVED)
    activated = State(ConnectionState.ACTIVATED, value=ConnectionState.ACTIVATED)
    failed = State(ConnectionState.FAILED, value=ConnectionState.FAILED)
    terminated = State(ConnectionState.TERMINATED, value=ConnectionState.TERMINATED, final=True)

    reserve_confirmed = created.to(reserved)
    reserve_failed = created.to(failed)
    provision_confirmed = reserved.to(activated)
    provision_failed = reserved.to(failed)
    release_confirmed = activated.to(reserved)
    release_failed = activated.to(failed)
    terminate = reserved.to(terminated) | failed.to(terminated)


def apply(current_state: str, event: str) -> str:
    """Apply ``event`` to a machine starting in ``current_state`` and return the resulting state.

    Raises ``statemachine.exceptions.TransitionNotAllowed`` if the event is illegal from
    ``current_state`` — the caller's guarantee that the connection lifecycle stays consistent.
    """
    machine = ConnectionStateMachine(start_value=current_state)
    machine.send(event)
    return str(machine.current_state_value)
