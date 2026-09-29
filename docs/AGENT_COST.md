# Agent UX and cost (Phase 14)

## Question

Where does a fresh agent spend its tool calls and tokens? Which of those costs does the repository
cause, as opposed to the modelling itself? Can a **repeat benchmark class** be done meaningfully
cheaper **with quality preserved**?

Baseline (FRESH_AGENT_01, a single stylized prop): 542 s, 65 tool calls, ~150k tokens.

## Research: 13 fresh-agent transcripts, 946 tool calls

`tools/experiments/cost_breakdown.py` classifies every tool call in the subagent transcripts of
FA-01 to FA-09. One shell call can carry several labels, for example an edit followed by
`sw review`. The transcripts themselves stay outside the repository.

| Run | Calls | Tokens | Calls before the first build |
|---|---|---|---|
| FA-01 anvil | 65 | ~150k | 9 |
| FA-02 staircase | 49 | ~149k | 8 |
| FA-03 six-asset pack | 120 | ~272k | 20 |
| FA-04 textured chest | 66 | ~188k | 18 |
| FA-05 four probes + held-out gate | 49–131 | ~198k (gate) | 8–14 |
| FA-06 fountain | 70 | ~210k | 17 |
| FA-07 import | 88 | ~208k | 7 |
| FA-08 engine props | 68 | ~181k | 15 |
| FA-09 Haiku signpost | 32 | ~78k | 15 |

**Share of calls by label** (FA-01 to FA-09, larger model runs and FA-09 run A):

| Label | Calls | Share | Note |
|---|---|---|---|
| edit asset | 211 | 22% | about a third are Python heredocs doing `s.replace(...)` on the YAML |
| `sw review` | 204 | 22% | **47 of these came back FAIL** |
| view image | 182 | 19% | the inner loop: edit → review → look |
| read framework code | 115 | 12% | `backend.py` 31, `assemble.py` 29, `validate/checks.py` 16, `cli.py` 8 |
| `sw render` | 103 | 11% | extra views beyond the review sheet: top-down material/parts, textured close-ups |
| `sw snapshot` | 87 | 9% | |
| `sw validate` | 85 | 9% | |
| `sw doc` | 70 | 7% | |
| read example asset/component | 52 | 6% | |
| read docs | 50 | 5% | |
| custom geometry/file probe | 32 | 3% | numpy/trimesh scripts to answer questions the CLI does not |
| read report JSON | 29 | 3% | |

**Errors met in `sw review`/`sw validate` output**, by frequency: `SRC_SCHEMA` 52, `UV_TEXEL_DENSITY`
41, `GEO_OPEN_EDGES` 47, `GEO_PART_FRAGMENTED` 31, `STYLE_THIN_FEATURE` 25, non-manifold/winding 40,
`BUDGET_TRIANGLES` 19, `CHECK_FAILED` 15, `SRC_EXPR` 11, `OP_FAILED` (booleans) 32.

The single most frequent schema error (15 failed builds across 4 runs) is the **YAML flow-list comma
trap**. `size: [atan2(a, b), 1, 2]` is split by YAML into `"atan2(a"` and `"b)"`. The hint names the
fix, but every occurrence still costs a failed build and an edit.

Framework-code reads answer semantics questions: how rotation and centring work, radial arrays,
`origin`, pivots, collision naming. They also come from bug-hunting in runs that found real bugs
(FA-03, FA-04, FA-05 gate).

## Findings (classified)

| # | Finding | Class | Cost it causes |
|---|---|---|---|
| C1 | The inner loop is at least 3 calls per iteration (edit, review, view image), and usually 4–5 with stats or render | inherent to the harness; can be made more informative per call | ~60% of calls |
| C2 | Expressions containing commas inside flow lists break the YAML parse | **ERGONOMICS (parser)** | 15 failed builds |
| C3 | 8–20 calls before the first build (doctor, caps, docs, examples) | DISCOVERY | 15–25% of a single-prop run |
| C4 | Agents write Python scripts to probe geometry or reports | DISCOVERY / capability gaps | ~6% |
| C5 | Semantics questions answered by reading `assemble.py` and `backend.py` | DOCUMENTATION | ~12%, concentrated in early runs |
