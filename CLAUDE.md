# CLAUDE.md

Guidance for working in `nsi-orchestrator`. See [README.md](README.md) for the product/architecture
overview; this file is the working reference for commands, conventions, and the patterns specific to
this codebase.

## What this is

An [orchestrator-core](https://github.com/workfloworchestrator/orchestrator-core) 5.1.x application
(imports under `orchestrator.core.*`) that manages the lifecycle of five products — Topology,
SwitchingService, STP, SDP, and MultiDomainPoint2Point (MDP2P) — over the
[nsi-dds-proxy](https://github.com/workfloworchestrator/nsi-dds-proxy) (topology source) and the
[nsi-aggregator-proxy](https://github.com/workfloworchestrator/nsi-aggregator-proxy) (its NRM).
Python 3.13, managed with `uv`.

## Commands

```shell
uv sync                                            # install runtime + dev deps
export DATABASE_URI=postgresql+psycopg://nsi:nsi@localhost/nsi
uv run python main.py db upgrade heads             # apply migrations
OAUTH2_ACTIVE=false uv run uvicorn wsgi:app --port 8080  # run the API (auth off for local dev)
uv run ruff check . && uv run ruff format --check . # lint + format
uv run mypy .                                      # types (strict, whole tree except migrations)
uv run pytest                                      # tests (needs an nsi-test DB with pgvector)
```

**Always `export DATABASE_URI` before `db`/`generate`/`pytest`.** Without it, orchestrator-core falls
back to its built-in `nwa:nwa@localhost/orchestrator-core` default — a different, drifted scratch DB.
The local dev DB is `nsi`; pytest's integration harness creates and migrates a throwaway `nsi-test`.
Both need the pgvector extension.

## Layout

- `products/product_blocks/`, `products/product_types/` — the domain model (one module per block /
  product). `products/services/description.py` builds the human-readable subscription description via
  a `singledispatch` registered per product/block type.
- `workflows/<product>/` — `create`/`modify`/`validate`/`terminate` (+ `reconcile` for STP; +
  `provision`/`release`/`reconcile`/`retry_reservation` for MDP2P), plus
  `workflows/<product>/shared/forms.py` for the form selectors and block lookups. All instances are
  registered in `workflows/__init__.py`.
- `workflows/mdp2p/shared/ero.py` — derives the NSI Explicit Route Object from the included SDPs.
  Pure, no I/O; `network_of` mirrors nsi-pce's `SimpleStp.parseNetworkId` (first **six** colon
  components, `?vlan=` stripped first).
- `workflows/tasks/` — system tasks (`Target.SYSTEM`, `@task()`).
  `validate_aggregator_against_subscriptions.py` compares the aggregator's live reservations against
  the MDP2P `connection_id`s in both directions — the one direction `validate_mdp2p` cannot see,
  since it walks outward from a subscription. Worth doing for the aggregator and *not* the DDS: the
  aggregator-proxy speaks for a single requester NSA, so a connection without a subscription is
  anomalous, whereas an unsubscribed DDS entry is the normal state of every ANA peer's topology.
  Terminated reservations are excluded (their subscriptions are terminated too, so they are already
  outside `subscribed_values`), and a failed fetch aborts rather than diffing against nothing.
- `schedules.py` — this project's cron entries, registered through core's schedule API by the
  `scheduler load-project-schedule` command that `main.py` attaches to core's `scheduler` sub-app.
  The chart's init container runs it after `load-initial-schedule`, chained with `&&` inside the same
  `until` loop so a failure in either retries the pair while waiting for the DB and Redis. It must run
  from that singleton and not the multi-replica API app: `add_unique_scheduled_task_to_queue` is not
  safe for concurrent use. Times are staggered off core's 00:10 / 02:30 and off the `:00`/`:30` marks.
  This is **not** the deprecated `@scheduler` decorator; it drives the same API the UI does.
- `workflows/shared.py` — cross-product form helpers: `create_summary_form`/`modify_summary_form`,
  `subscription_id_for_value`, `raise_form_validation_error`, and `fetch_for_form` (wraps a proxy
  fetch so a proxy error surfaces as a `FormValidationError` instead of a crashed step).
- `services/` — `dds_proxy.py` and `aggregator_proxy.py` (httpx clients returning pydantic models);
  `edge_auth.py` factors the shared mTLS / dev-header `client_kwargs` both use.
- `workflows/mdp2p/shared/fsm.py` — the python-statemachine connection FSM
  (`CREATED→RESERVED→ACTIVATED`, `terminate`→`TERMINATED`, any step→`FAILED`, `retry`→`CREATED` from
  `FAILED`), persisted on `vc.state`. Note this is the orchestrator's local view; the
  aggregator-proxy has its own, larger state machine (`RESERVING`/`ACTIVATING`/`DEACTIVATING` too)
  and knows nothing about `retry` — to it that is a terminate plus a new reserve.
- `templates/` — generator input YAMLs (data model only), one per product.
- `tests/` — unit tests (mocked proxies); `tests/workflows/` — DB-backed end-to-end tests.

## Patterns specific to this repo

- **Auth gate (`auth.py` + `wsgi.py`).** A coarse in-process check plugged into orchestrator-core's
  `AuthManager`, matching the token's `groups_claim` (default `eduperson_entitlement`) against two
  tiers: `settings.write_groups` for all of REST and the GraphQL mutations, `settings.read_groups`
  (unioned with the writers) for the GraphQL queries. `GroupGateGraphql` tells the two apart via
  oauth2-lib's `method` discriminator (see `auth.py`); anything that is not `"QUERY"` falls through
  to the write set, so a new discriminator fails closed. The gate fails closed and bypasses only
  when `OAUTH2_ACTIVE` is off. `wsgi.py` also disables the docs/GraphiQL/introspection schema surface
  and **refuses to boot** when `OAUTH2_ACTIVE` is on but `OAUTH2_AUTHORIZATION_ACTIVE` is off or
  `write_groups` is empty (orchestrator-core's GraphQL layer silently skips authz when that flag is
  off). `OAUTH2_ACTIVE` defaults on, so local dev runs with `OAUTH2_ACTIVE=false`; the real groups live
  in deployment config, never in the source default. Note oauth2-lib's `MUTATIONS_ENABLED` defaults to
  `False`, so today the mutation branch is never reached — it is the safety net for when that flips.
- **Async aggregator operations use `callback_step`.** reserve/provision/release/terminate fire a
  request with a `callback_route` (`retry_reservation` chains a terminate and a reserve, the first
  behind a `conditional`), the aggregator-proxy POSTs the result back, and the validate step
  reads it from `callback_result`. `callback_step(...)` is a single `step_group` in `workflow.steps`
  (it is *not* expanded into sub-steps); the awaiting state carries
  `__sub_step == "<group> - Await callback"`. Each passes `timeout=settings.aggregator_callback_timeout`
  (540s) as a backstop: a step still awaiting after the timeout is failed by orchestrator-core's
  sweep task so it can be retried/aborted. **Retrying a callback step replays the whole group, so the
  action step re-fires the request** — the aggregator-proxy handles that idempotently (reserve dedups
  on `globalReservationId`; provision/release/terminate re-deliver when already in the target state).
- **Workflow input pages** (list of form pages): create `[{product}, {fields}, {summary}]`; modify
  `[{subscription_id}, {fields}, {summary}]`; validate/reconcile `[{subscription_id}]`; terminate
  `[{subscription_id}, {}]`.
- **Read-only "show the subscription" field**: `SubscriptionId = Annotated[DisplaySubscription,
  Field(UUID(subscription_id))]`. Wrap the default in `UUID(...)` — `DisplaySubscription` is UUID-typed,
  and a raw `UUIDstr` default makes pydantic warn "Expected uuid" on serialization.
- **State-gating** (e.g. provision only when RESERVED) happens in the form generator via
  `raise_form_validation_error(...)`, not in a workflow step, so the user sees it before the run starts.

- **The version is the git tag; never edit it.** `pyproject.toml` is `dynamic = ["version"]` with
  setuptools-scm, so a tag builds `0.3.0` and any other commit builds `0.3.1.dev<n>+g<sha>`. The
  container build has no `.git`, so `container.yml` resolves the version on the runner and passes
  `--build-arg VERSION`, which the `Dockerfile` exports as
  `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NSI_ORCHESTRATOR`. Omitting it fails the build by design. `uv.lock`
  records the project as `(dynamic)` and so does not churn per commit. See README **Versioning**.

- **Register a system task with `create_task`, not `create_workflow`.** It belongs to no product, so
  it must not be linked into `products_workflows`. `create_task` inserts `target='SYSTEM'` and
  `is_task=TRUE` itself, and requires a `description` (`workflows.description` is `NOT NULL`).
- **`load-project-schedule` is only idempotent once a scheduler has run**, exactly as for core's
  `load-initial-schedule`: `add_unique_scheduled_task_to_queue` dedups against the
  `workflows_apscheduler_jobs` linker table, which is written when the scheduler drains the queue.
  Against a database whose scheduler has never run, each invocation queues the job again.
- **A scheduled task that fails by design must not carry `run_predicate=no_uncompleted_instance`.**
  The predicate counts `failed` / `inconsistent_data` / `api_unavailable` as uncompleted, and
  `task_clean_up_tasks` only reaps `completed`, so the first failure would block every later run —
  silently, logged at INFO by the scheduler. A nightly cron cannot overlap a task that takes seconds.
- **Raise `AssertionError` for drift, not `InconsistentDataError`.** Only the former reaches
  `ProcessStatus.INCONSISTENT_DATA` (and the NOC assignee): core's mapping at
  `services/processes.py` compares the error class name against the literal `"InconsistentData"`,
  while `errors.py` writes `type(err).__name__`, i.e. `"InconsistentDataError"` — so that branch is
  dead. A proxy `RuntimeError` (`DdsProxyError` / `AggregatorProxyError`) lands in plain `failed`.

## Gotchas

- **Capacity is Mbit/s throughout; NML/DDS is bit/s.** `DdsServiceTerminationPoint.capacity_bits` is
  the raw wire value — always store and compare via `capacity_mbits`.

- **Don't name a product-block field `description` or `label`** — both collide with
  `ProductBlockModel`'s own fields (`description` is the editable block description; `label` is an
  instance field that makes `Block.new(label=...)` raise). The VC uses `circuit_description`; the SAP
  stores its VLAN as `vlan`.
- **Mocking proxies in tests**: patch the single `services.dds_proxy._fetch` for the DDS. For the
  aggregator, the workflow modules call `aggregator_proxy.<fn>` (module attribute → patch
  `aggregator_proxy.<fn>`), **but `workflows/mdp2p/shared/forms.py` does
  `from services.aggregator_proxy import list_reservations`** — an import-by-name binding that must be
  patched on the `forms` module, not on `aggregator_proxy`, or the create form hits the real aggregator.
- **The ERO names one STP per SDP, the end facing the source**, in the user's selection order. The
  PCE derives the far end itself. Naming the wrong end is *not* an error — it routes around the SDP
  and hairpins through the far domain — which is why `ero.py` searches for a route that never
  re-enters a network instead of picking by hop count. Selection order is path order and is never
  reordered.
- **The ERO only has any effect under the `sequential` or `tree` PCE algorithm.** `chainPCE` is
  `reachabilityPCE` alone, which copies the ERO to every child segment without computing against it.
  nsi-safnari defaults to `chain`; the ANA deployment runs `SEQUENTIAL`.
- **Excluding SDPs is rejected, not ignored.** nsi-safnari's `pointToPointServiceFormat` drops the
  p2ps `<exclusion>` element and nsi-pce never applies it, so accepting it would silently route
  through the SDP the user asked to avoid. The field and `ConstraintType.EXCLUDE` remain in the model;
  the gate is one line in `create_mdp2p._check_endpoints`.
- **A retry mints a new `global_reservation_id`.** The aggregator-proxy dedups on it *before* reading
  the criteria, so reusing it would hand back the old failed connection and ignore every correction.

## Conventions

- Apache-2.0 header `# Copyright 2026 SURF.` on every `.py` file.
- ruff line-length 120; mypy strict over the whole tree (tests included), `migrations/` excluded from both.
- Python style: prefer comprehensions / itertools over loops, `match`/`case` over `isinstance` chains,
  and `@pytest.mark.parametrize` (with `pytest.param(..., id=...)`) over near-duplicate test functions.
- Comments explain the code, not the process. Commit subjects ≤72 chars, body wrapped at 100, with a
  bulleted list of changes; no `Co-Authored-By` trailer.
