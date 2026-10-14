# Changelog

The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the versions follow
[semantic versioning](https://semver.org/). While the major number is 0 the interface may change
between minor versions.

Each release says which version of the [kin5ax](https://github.com/zdroyer/kin5ax) library it
carries in `lib/`; the addon refuses a library whose major and minor it was not written against, so
the two are released together.

## [Unreleased]

## [0.1.0] — 2026-10-14

The first release: everything below arrived while the addon lived inside the library repository, and
this is the point at which it became one of its own.

### Added

- **3D Surface (5axis)**, an operation for the CAM workbench: a zigzag over the parameter space of
  one face, cut with any shape of tool. The path carries the tip of the tool, worked out from the
  roundness at the end of it, and every cutting move carries the tool axis as `I J K`.
- The tool stands up, or points along the surface normal **leaned over by two angles**, both
  measured from the direction the pass travels in, so a lead angle leads in every pass of a zigzag.
- **A postprocessor**, `fanuc_tcp_kin5ax_post.py`: the whole vector written, the operation wrapped in
  `G43.5`/`G49` for a control that has TCP, and with `--machine <chain file>` the five axes solved by
  kin5ax instead, which is the one mode that runs without a TCP option.
- **The machine in the document**: a part per segment of the chain, read from a `.kc`/`.kc.json`
  file, with the collision boxes of the file, the tool mount and the material as parts, and the job's
  tool, model and stock placed in them.
- **A player** over the solved job: a slider over the locations, play and pause at a rate you set, a
  step either way, the report of the solve, and the configuration of every joint.
- **Collisions reported and shown**: which two solids met and at how many locations, a colliding
  location posed where the machine would have had to be with the two solids painted red, a solid that
  has met anything left orange to the end of the run, and an optional pause where the machine first
  meets itself.
- **The cutting simulated**, as voxels: the stock of the job cut step by step with the tool of each
  operation, the removed volume and the gouges as properties, the surface as a mesh of the exposed
  voxel faces, a reset, and an option to cut at a location the machine cannot reach as well.
- The cut also runs **with no machine at all**, straight along the path in the frame of the part.
- **Machine models** for fourteen chains under `Resources/machines/`, including the SHW UniForce
  7000, the Reiden RX10 and the Mazak VTC-800/30SR.
- **The kin5ax shared library** for Windows and Linux under `lib/`, so that the addon works as
  installed.

[Unreleased]: https://github.com/zdroyer/kin5ax-cam-freecad/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/zdroyer/kin5ax-cam-freecad/releases/tag/v0.1.0
