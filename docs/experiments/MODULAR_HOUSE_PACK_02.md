# MODULAR_HOUSE_PACK_02: the kit gates re-run (milestone M2)

Re-run of [MODULAR_HOUSE_PACK_01](MODULAR_HOUSE_PACK_01.md)'s ten gates on 2026-10-05, after Phase 21.

**Verdict: PASS, 9 of 10 gates, with gate 9 met in part.** It is not the "strong PASS" M2 hoped for:
- a fresh agent editing this kit would close gate 9 (one fresh-agent task);
- a shared `foundation` asset would remove the one remaining duplication.

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
| 9 | understandable and editable by a fresh agent | **met in part**: FRESH_AGENT_12 built its own mini kit from the wheel alone; no fresh agent has edited THIS kit | not verified |
| 10 | visually intentional | **met in my review**: windows now come in 3 sizes; the stress renders keep the frame language at a 55° pitch | met in my review |
