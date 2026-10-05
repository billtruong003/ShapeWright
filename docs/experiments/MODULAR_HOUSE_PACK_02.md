# MODULAR_HOUSE_PACK_02: the kit gates re-run (milestone M2)

Re-run of [MODULAR_HOUSE_PACK_01](MODULAR_HOUSE_PACK_01.md)'s ten gates on 2026-10-05, after Phase 21.

**Verdict: PASS, all 10 gates (strong PASS).** The first pass left gate 9 met in part. A fresh agent then edited this
kit (FRESH_AGENT_13, below), which closes gate 9. Its shared `house_foundation` module also removes the one
duplication noted under gate 3.

Milestone M2 (kit-grade) asks for the ten gates again, on the kit as it is now: 26 modules and 3 houses built from module instances, one shared trim sheet, LODs, and the workshop's multi-hull collision. Evidence is in `docs/experiments/mhp_02/`:
- `metrics.json` (`tools/experiments/mhp_metrics.py`, now with an export-folder argument);
- `exports_khronos.txt` (29 exports, each with the Khronos validator);
- `stress_validate.txt`;
- `stress_houses_trim.png`.

| # | gate | result now | was (§17) |
|---|---|---|---|
| 1 | three visibly different houses from one kit | **met** | met |
| 2 | predictable alignment without widespread hand offsets | **met**: no hand offsets remain (shutters and awnings by `measure:`); literals per house 8 / 18 / 20 (were 31 / 51 / 57), Parameterization Ratio 0.86–0.90 | met with exceptions |
| 3 | meaningful structural reuse | **met, with a note**: 12 components (36 instance lines in modules); houses are only module instances. The cottage and the townhouse repeat the same 6 foundation, deck and steps instance lines (a shared `foundation` asset would remove them). | met |
| 4 | coherent shared materials | **met, stronger**: 7 pack materials, 0 asset-level definitions, and ONE shared trim sheet for all 29 assets (texture memory −83.8 %, Phase 21) | met |
| 5 | parameter changes do not destroy the kit | **met**: the same 5-parameter stress gives 29 / 29 PASS with no warnings, 0 coordinate edits and 0 repairs | met (1 repair, texel warnings) |
| 6 | no normal task requires framework modification | **met for this re-run**: rebuilding, stressing, exporting and measuring the kit needed no framework change. One false warning was fixed: `STYLE_THIN_FEATURE` fired on the door brace made exactly at the 30 mm minimum (float rounding, now a 0.1 mm tolerance). Over its history the kit drove 5 framework changes, all in. | not met |
| 7 | no z-fighting, duplicate surfaces or severe interpenetration | **met**: the seam validator is clean on all 29 assets, default and stressed | met |
| 8 | game-ready GLBs export | **met**: 29 PASS, Khronos 0 errors and 0 warnings on all 29, LOD1/2 silhouettes 0.945–0.996, the workshop's collision imports in Godot (218 bodies, walkable doors) | met |
| 9 | understandable and editable by a fresh agent | **met** (FRESH_AGENT_13): a fresh agent with no hints added `house_bakery` (PASS, about 7 min) and factored the shared foundation into `house_foundation` (both houses unchanged in geometry and status, about 10 min), with no framework change; rated the kit 8/10 | not verified |
| 10 | visually intentional | **met in my review**: windows now come in 3 sizes; the stress renders keep the frame language at a 55° pitch | met in my review |

## FRESH_AGENT_13: a fresh agent edits the kit

The report is [FRESH_AGENT_13.md](FRESH_AGENT_13.md). The agent had a clean checkout of `main` and no hints, and was not allowed to change `shapewright/`. Both of its assets were adopted into the kit.

**Its findings, and what was done with them:**
- **Stale README:** `modular_house_pack/README.md` said houses cannot place modules and have no LODs. Fixed.
- **Texture shift (not fixed):** the trim-sheet U offset is seeded from the full part name, so moving parts into a sub-module (`foundation_*`) shifts their texture slightly (at most 14/255). Seeding by base name would avoid it; left as a backlog item.
- **Undocumented behaviours (not fixed):**
  - nested assets' sockets are copied into the parent with a prefix;
  - the golden hash depends on part order;
  - a stale `uv.lock.yaml` is silently ignored under a trim sheet.

  These are recorded for the backlog.
