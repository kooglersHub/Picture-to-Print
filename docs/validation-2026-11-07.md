# Validation on 2026-11-07

Python 3.14, Windows x64, MeshLib 3.1.4.297, Blender 4.5.9 LTS.
Full automated suite: 19 passed, including a real Blender invocation and
Windows descendant-process timeout handling. Ruff check and format check pass.
Independent review found two issues (concave containment and float32 distant
origins); both were reproduced by failing tests and fixed. Targeted independent
re-review passed seven geometry tests and the timeout test.

## Existing Trellis asset

CPU-only postprocessing of the game's existing `03_lantern_wraith.glb`.
No model weights downloaded and no paid GPU generation run.
Source SHA-256: `b2e956aff76263d28dd081cd0e80a29b93bdb1424e27d7c465568c148c415c2b`.
Both variants use longest dimension 100 mm and voxel size 0.4 mm.

| Metric | Input | MeshLib + visibility | Blender comparison |
| --- | ---: | ---: | ---: |
| Open boundary edges | 89 | 0 | 0 |
| Nonmanifold edges (includes boundaries) | 218 | 0 | 0 |
| Consistent winding | no | yes | yes |
| All components positive closed volume | no | yes | yes |
| Triangles | 49,434 | 457,656 | 561,976 |
| Components | 80 | 254 | 538 |
| Enclosed shells removed | — | 130 | 3 |
| Hidden faces removed | — | 32,468 | — |
| Native self-intersections after reconstruction | — | 0 | 0 |
| Sampled bidirectional p95 deviation, mm | — | 1.184 | 0.238 |
| Sampled maximum deviation, mm | — | 4.236 | 1.487 |

These results establish closed export geometry, not production readiness.
The raw defective input contains internal surfaces, so distance from *all* its
surfaces also measures intentional interior removal; it is not a pure visible
silhouette error metric. Visual comparison remains necessary. In the MeshLib
result, 223 of 254 components are smaller in volume than one 0.4 mm voxel;
the largest component holds 96.6% of total volume. Islands are deliberately
reported and preserved, including separate meaningful parts such as the lantern.
No automatic largest-component-only filter was used.

The local exports contain STL, millimeter 3MF and the complete manifest. A
local shaded before/after comparison was rendered and inspected; source assets
and derived meshes/images are excluded from Git. The lantern's fine detail
and separate pieces still need inspection and cleanup before sale.

## What is still unverified

- No slicer layer-preview check or physical resin/FDM print was performed.
- No fresh GPU generation through the user's original Trellis/Modal worker;
  its raw-mesh hook is implemented and tested independently.
- The real input was already GLB-postprocessed. A raw mesh from the same seed
  is needed to distinguish generation defects from GLB export defects.
- MeshLib commercial licensing must be resolved before commercial deployment.

MeshLib remains the preferred programmable backend because it can target
welded internal walls and volume reconstruction explicitly. The real example
does not prove it universally preserves form better than Blender. Both
procedures retain a mandatory review gate; neither is sold as a guaranteed
one-click printability certificate.
