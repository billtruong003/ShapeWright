# Validation layers

Every command that builds an asset runs all layers, so the agent sees every problem at once.

| layer | checks |
|---|---|
| source | schema, references, expressions, limits (typos come with suggestions) |
| geometry | closed manifold, winding, degenerate or duplicate faces, **displacement that inverts faces** |
| assembly | nothing floats (1 mm), grounding, origin, hidden parts, **seams: coplanar overlaps that z-fight**, contact-only parts |
| budget | triangles, materials and draw calls against the profile |
| intent | the asset's own `checks:` |
| surface | UV bounds and overlap, texel density, baked textures |
| style | style-profile heuristics (warnings only) |
| export | Khronos glTF validator and a re-import round-trip |

Every issue has a stable code, a location and a hint, and `sw doc CODE` explains it. Perceptual quality (proportions, style fit) is deliberately *not* scored. The review sheet exists for that. The full list is in [issue codes](../reference/codes.md).
