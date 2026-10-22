# Rocky architecture index

This analysis describes the current implementation and the documented real-time
redesign in [`docs/REALTIME_PLAN.md`](../../../../docs/REALTIME_PLAN.md). The
redesign is a proposal; these artifacts do not approve a provider, freeze a
migration boundary, or authorize implementation changes.
The reuse-first app survey and proof-of-fit gate are in
[`docs/OPEN_SOURCE_OPTIONS.md`](../../../../docs/OPEN_SOURCE_OPTIONS.md).

## Implementation Guide

**This index is not the full contract. Do not implement from this file alone; follow the artifact paths below.**

### Global artifacts

- `unit_graph.yaml`
  - Who reads: all workers.
  - Use for: external triggers, source anchors, dependencies, public signatures,
    and shared-module references.
  - How to consume: find the assigned unit and follow its source anchors,
    dependencies, and shared references.
- `wire_contracts.yaml`
  - Who reads: workers changing browser, voice-server, or model-provider
    integrations.
  - Use for: existing HTTP and model-provider request/response contracts.
  - How to consume: filter by the assigned unit; preserve current contracts
    unless a design decision explicitly changes them.
- `shared_modules.yaml`
  - Who reads: workers changing code used by more than one unit.
  - Use for: the voice service module and eye renderer shared by current
    entrypoints.
  - How to consume: filter rows where `used_by_units` includes the assigned
    unit; limit `shared_refs.used_fields` to the listed fields.
- `cross_unit_state.yaml`
  - Who reads: workers changing state shared between units.
  - Use for: implicit state flows crossing unit boundaries.
  - How to consume: filter flows by `writer.unit` or `reader.unit`; currently
    there are no statically identified cross-unit implicit state flows.
- `project-structure.md`
  - Who reads: design and planning workers.
  - Use for: current project type, modules, entrypoints, and functional areas.
- `tech-stack.md`
  - Who reads: design and planning workers.
  - Use for: verified existing runtime, dependencies, and platform constraints.

There is no `migration_boundary.yaml`: the request was to research and plan,
not to select files for a rewrite. There is no `seams.yaml`: no partial-migration
cut was declared or selected. Existing HTTP boundaries are documented in
`wire_contracts.yaml`. There is no `data-model.md`: the repository contains no
database or ORM model.

### Unit: `desktop-companion`

- External trigger: launch `python rocky_desktop_app.py`; keyboard, microphone,
  and camera actions in the pygame window.
- Must read:
  - `units/desktop-companion/behavior.yaml` — visible states, input paths,
    fallback behavior, side effects, and thread model.
  - `units/desktop-companion/bindings.yaml` — CLI flags and runtime config.
  - `units/desktop-companion/unit_decomposition.yaml` — advisory split
    candidates only; `commit: false`.
- Relevant global rows:
  - `wire_contracts.yaml` entries for `desktop-companion`.
  - `shared_modules.yaml` entries where `used_by_units` includes
    `desktop-companion`.
  - `cross_unit_state.yaml` flows touching `desktop-companion`.
- Before DONE report: artifact paths read, implemented
  `must_preserve` items, unresolved/deferred contracts, and tests/build/runtime
  evidence.

### Unit: `browser-companion`

- External trigger: launch `python app.py`, then use its HTTP routes from the
  browser.
- Must read `units/browser-companion/behavior.yaml`,
  `units/browser-companion/bindings.yaml`, and
  `units/browser-companion/unit_decomposition.yaml` for behavior, CLI/route
  wiring, and advisory splits.
- Relevant global rows: `wire_contracts.yaml` entries for
  `browser-companion`; shared modules used by this unit; cross-unit flows
  touching this unit.
- Before DONE report: artifact paths read, implemented
  `must_preserve` items, unresolved/deferred contracts, and tests/build/runtime
  evidence.

### Unit: `voice-service`

- External trigger: `python rocky_say.py` CLI options, or its local HTTP server
  started with `--server start`.
- Must read `units/voice-service/behavior.yaml`,
  `units/voice-service/bindings.yaml`, and
  `units/voice-service/unit_decomposition.yaml` for generation/server behavior,
  CLI/runtime wiring, and advisory splits.
- Relevant global rows: `wire_contracts.yaml` entries for `voice-service`;
  shared modules used by this unit; cross-unit flows touching this unit.
- Before DONE report: artifact paths read, implemented
  `must_preserve` items, unresolved/deferred contracts, and tests/build/runtime
  evidence.

### Unit: `eyes-preview`

- External trigger: `python rocky_eyes.py --selftest <directory>`.
- Must read `units/eyes-preview/behavior.yaml`,
  `units/eyes-preview/bindings.yaml`, and
  `units/eyes-preview/unit_decomposition.yaml` for render/output behavior,
  CLI wiring, and advisory splits.
- Relevant global rows: shared modules used by this unit; cross-unit flows
  touching this unit.
- Before DONE report: artifact paths read, implemented
  `must_preserve` items, unresolved/deferred contracts, and tests/build/runtime
  evidence.
