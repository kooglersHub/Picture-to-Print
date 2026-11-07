# Trellis to solid print geometry

The print repository starts empty. The game repository uses AssetFurnace on
Modal (Pixal3D, Blender, SkinTokens). Its generation/rigging/animation code is
not a print repair stage. Moonveil's Trellis example is a textured GLB from
`microsoft/TRELLIS.2-4B`, with game-oriented decimation to 50,000 vertices.

Build a standalone CPU postprocessor accepting existing Trellis GLB, STL, OBJ,
or PLY. Preserve scene transforms, center before float32 conversion, strip
materials and scale explicitly to mm. Prefer MeshLib HoleWindingRule with
sampled visibility stripping and collision-aware inner-shell removal.
Retain Blender/OpenVDB as an explicit comparison backend. Validate the actual
exported STL after reloading. Export STL and 3MF (explicit millimeters) plus
a versioned JSON manifest with sampled bidirectional surface deviation.

## Approaches

- Trimesh repair alone: lightweight but primarily repairs triangle/quad holes;
  insufficient for arbitrary broken generated surfaces.
- MeshLib: selected by the implementer after the user supplied research that
  normal remeshing had already failed. Optional explicitly installed dependency;
  commercial development requires a separate license before shop use.
- Blender/OpenVDB: initially selected, retained as a comparison backend because
  complex synthetic cases also fail this backend's export validation.

## Contract and limits

CLI and Python function return geometry validation and review reasons. Never
label an arbitrary image-derived object as certified printable: wall thickness,
supports, strength and likeness still need review. A closed triangle surface
represents a solid; slicer infill is a separate setting. Enclosed inner shells
must be removed so slicers do not interpret them as cavities.

Defaults: longest dimension 100 mm; voxel size 0.4 mm; subprocess timeout
300 seconds; maximum estimated voxel bounding grid 150 million cells. Reject
nonfinite dimensions, empty geometry and resolution exceeding this budget.
Geometry changes always require visual review. Multiple external parts require
assembly review. No silent largest-component selection, texture baking, rigging,
GPU provisioning, public upload endpoint, checkout or billing implementation.

Use a unique output directory per job, fail if it already exists, and publish
exports only after validation. Manifest status: `geometry_ready` or
`rejected`, with `review_required: true`, input hash, parameters, artifacts and
metrics. A future shop worker calls the same function and stores outputs under
its own order/job identifier; it must not expose local paths to customers.

Sources checked 2026-11-07:
- https://docs.blender.org/manual/id/dev/modeling/modifiers/generate/remesh.html
- https://trimesh.org/trimesh.repair.html
- https://meshlib.io/documentation/License.html
- https://www.blender.org/support/faq/

The original Trellis worker is not available locally. A raw-mesh hook integrates
with pipeline.run(image)[0] before simplify/to_glb. Synthetic tests run locally;
the existing 03_lantern_wraith.glb was additionally obtained from the game repo
via sparse checkout for a CPU-only real-asset comparison. Neither model weights
nor reference assets are committed to this public repository.
