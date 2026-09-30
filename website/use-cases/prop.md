# A game prop in one session

This is the mailbox a fresh agent made with nothing but `pip install` and `llms.txt` (experiment FA-11, Phase 16), shown step by step. Blocks marked `# run` are executed by the documentation tests, so they work as written.

## 1. Brief

```bash
# run
sw brief "a stylized wooden mailbox on a post for a cozy mobile game, under 900 triangles"
```

`brief` prints the closest example asset with its full source, the profile and budget (here `mobile_mid`: 1,500 tris and **2 materials**), the rules for this kind of prop, and the vocabulary.

## 2. Write the source

```yaml
# file: assets/mailbox/asset.yaml
shapewright: 0.1
asset: {name: mailbox, kind: prop/street/mailbox, description: Cozy wooden mailbox on a post.}
profile: mobile_mid
style: stylized_lowpoly
budget: {triangles: 850}

params:
  bw: 0.36        # box width
  bh: 0.24        # box height
  bd: 0.5         # box depth
  post_h: 0.7
  post_w: 0.12

materials:
  wood: {archetype: wood, color: "#8a5a36", grain_strength: 0.35, edge_wear: 0.3}
  red:  {archetype: painted, color: "#c9382e"}

parts:
  post:
    shape: {type: chamfer_box, size: [post_w, post_h, post_w], chamfer: 0.012}
    anchor: bottom
    position: [0, 0, 0]
    material: wood
  bracket:
    shape: {type: chamfer_box, size: [0.2, 0.05, bd], chamfer: 0.01}
    anchor: bottom
    attach: {to: post, at: top}
    material: wood
  body:
    shape: {type: chamfer_box, size: [bw, bh, bd], chamfer: 0.015}
    anchor: bottom
    attach: {to: bracket, at: top}
    material: wood
  roof:
    doc: arched top, a half-circle profile extruded along the box
    shape:
      type: extrude
      depth: bd + 0.06
      polygon: [[-0.2, 0], [0.2, 0], {arc: {center: [0, 0], radius: 0.2, from: 0, to: 180, segments: 6}}]
    anchor: bottom
    attach: {to: body, at: top, offset: [0, -0.02, 0]}
    material: red
  door:
    shape: {type: chamfer_box, size: [0.26, 0.17, 0.03], chamfer: 0.005}
    anchor: back
    attach: {to: body, at: front}
    material: wood
  flag:
    shape: {type: chamfer_box, size: [0.03, 0.11, 0.15], chamfer: 0.004}
    anchor: left
    attach: {to: body, at: right, offset: [0, 0.05, 0.1]}
    material: red

checks:
  - {expr: asset.height, min: 0.9, max: 1.3}
```

Every part is placed by **anchors**: "the bottom of the body sits on the top of the bracket". There is no arithmetic on coordinates, so changing `post_h` moves everything above it.

## 3. Review, look, critique

```bash
# run
sw review mailbox
```

Open `assets/mailbox/.build/sheet.png`. It holds orthographic views with scale bars, 3/4 views, part colours, a texel checker and the UV layout. Critique specifically, in the form *part.param → change, reason*. The agent's first sheet showed:

- `BUDGET_MATERIALS`: 4 materials against a budget of 2. The fix was to merge the materials into wood and red.
- `STYLE_THIN_FEATURE` on the door, knob and flag at 2 cm. The fix was to raise them to 3 cm, the style's minimum.
- The flag was hidden from the front. The fix was to make it larger and raise it.

## 4. Try values without editing, then keep one

```bash
# run
sw validate mailbox --set post_h=0.85     # expect-fail: the height check (0.9-1.3 m) catches it
sw validate mailbox --set post_h=0.8
sw set mailbox post_h=0.8
sw snapshot mailbox -m "taller post" --critique "0.7 read stubby next to a person"
```

The `checks:` line in the source is design intent written as a test, so a param change that breaks the intent fails validation. This is the same mechanism a stress test uses on a whole kit.

## 5. Export

```bash
# run
sw export mailbox --target godot
```

This writes `assets/mailbox/export/mailbox_godot.glb` and a `.report.json` with triangles against the budget, draw calls, collision, the Khronos validator result (when installed) and a re-import round-trip.
