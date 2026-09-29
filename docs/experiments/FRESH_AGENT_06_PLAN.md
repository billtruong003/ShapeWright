# FRESH_AGENT_06 plan: a mid-poly asset in the agent loop (Phase 10 gate, written before the run)

## Question

Phase 10 measured stage timings on synthetic assets. Does a **real agent loop** on a mid-poly
asset (25k–45k triangles) stay practical: iteration latency, no timeouts, no memory problems, and
no need for the agent to work around performance? It also checks that the new resource limits do
not block legitimate mid-poly work.

## Prompt (task part, verbatim)

> Use this repository to create a detailed mid-poly hero prop for a desktop game: "An ornate stone
> fountain: a round, carved basin with a decorative rim, a central column with stacked bowls,
> sculpted water spouts, weathered stone with moss in the crevices, and a cobbled base ring.
> Between 25,000 and 45,000 triangles, one texture set up to 2048×2048." Inspect it, critique it,
> improve it, and export a validated GLB.

Same isolation and report request as FA-04. Each `sw` command prints its elapsed time, and the agent
is asked to report those times.

## Metrics

Per-command latency (from the agent's report, checked by rerunning the final commands), iterations,
triangles, time and tokens, limit errors hit, any performance workaround, and framework changes.

## Predictions

| # | Prediction |
|---|---|
| M1 | Final asset of 25k–45k triangles, valid and exported |
| M2 | `sw review` takes ≤ 15 s per iteration at the final size; the 2048² bake adds ~10 s |
| M3 | Density comes from segments/subdivide/noise and arrays, with no mesh-file escape |
| M4 | "Moss in the crevices" is expressed with `grime` (colour set to green) |
| M5 | No limit error on legitimate work; at most one `SRC_LIMIT` from an over-ambitious first try, with a clear message |
| M6 | 0 framework changes |
