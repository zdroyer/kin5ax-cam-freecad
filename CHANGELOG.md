# Changelog

The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the versions follow
[semantic versioning](https://semver.org/). While the major number is 0 the interface may change
between minor versions.

Each release says which version of the [kin5ax](https://github.com/zdroyer/kin5ax) library it
carries in `lib/`; the addon refuses a library whose major and minor it was not written against, so
the two are released together.

## [Unreleased]

## [0.3.0] — 2026-10-15

Carries kin5ax 0.3.0, and needs it: the binding refuses 0.2.

The two ends of a machine mean something else than they did. Read the first item before opening a
document made with 0.2.0 on a machine of your own.

### Changed

- **The end of a machine's tool branch is the tool mount, in every chain file.** It used to be the
  tool point in a file that named no tool holder and the mount in a file that named one, so the same
  element of the same format meant two different places and the two halves of this project
  disagreed about which: the chain editor hung the tool from the terminal, this addon hung a holder
  and a tool below it, on the same machine file. Now the tool point hangs the **gauge length** of
  the tool below the mount - the tip-to-mount measurement a presetter gives and a control is set
  with, `GaugeLength` on a simulation and `--gauge-length` on the postprocessor - and 0 stands the
  tool right up against its holder, which is a guess and is said to be one. A machine file of your
  own whose tool terminal was drawn at the tool point now puts the tool one assembly too low: move
  that terminal up to where a holder is really clamped.
- The shipped machines of the three real machines name the holder their taper takes, and every
  shipped file's embedded DTD describes the sections a holder can have.

### Added

- **The tool holder is named and shaped.** A holder is up to three cylinders hanging from the mount
  plus the designation on it, and kin5ax has the sizes of ten common ones: `HolderModel` on a
  simulation, `--holder-model` on the postprocessor, `kin5ax.holder_catalogue()` and
  `kin5ax.holder_by_model()` in the binding. A name the catalogue knows decides the holder's length
  and radius instead of `HolderLength` and `HolderRadius`; any other name is carried as the
  designation of a holder of your own, described by those two. Empty takes the holder the machine
  file says its machine carries.
- The picture draws every cylinder of the holder, hanging from the mount, which is where the
  collision test has it: the slim nose of a collet chuck clears what its flange would not.
- **The part can be held somewhere else than on the table.** `WorkpieceHolder` on a simulation is a
  placement: where the frame the job is programmed in sits on the end of the machine's workpiece
  branch - a vice, a chuck, a plate - and the identity, which it starts at, is the origin of the job
  on the table itself. The workpiece, the cut cloud and the markers hang in a part placed by it, the
  solve and the postprocessor agree with the picture, and the machine stands wherever it has to
  stand to touch the same point of the part. The postprocessor takes
  `--workpiece-holder "x,y,z"` or `"x,y,z,ax,ay,az,deg"`.
- `Chain.default_holder_model()`, `Chain.default_holder()`, `Tool.set_holder()`,
  `Chain.set_workpiece_holder()` and `Chain.workpiece_holder()` in the binding.

## [0.2.0] — 2026-10-15

Carries kin5ax 0.2.0, and needs it: the binding refuses 0.1.

### Changed

- **Every chain file says what its lengths are in.** `unit` is a required field of `.kc` and
  `.kc.json`, one of `mm`, `m` and `in`, and a file without it is refused rather than guessed at.
  The fourteen machines shipped say `m`. A file of your own written before this needs the line
  added.
- The machine in the document reads `UnitInMillimetres` from its file instead of assuming 1000.
- The postprocessor takes the unit from the file; `--machine-unit` now only overrides it, and
  accepts `in` as well.

### Added

- **A FreeCAD machine definition (`.fcm`) can be opened as a machine.** FreeCAD 1.2 ships its
  machines in that form, so it is the file a FreeCAD user actually has. The conversion is lossy:
  what it could not carry across is shown when the machine is made and kept on it as
  `FcmRemarks`, and the addon adds one remark of its own, that an `.fcm` has no collision boxes
  and so a simulation of such a machine will not find a collision whatever the tool does.
  `NegateTableLinearAxes` and `NegateTableRotaryAxes` carry the one convention the file cannot
  state.
- `Chain.from_fcm()`, `Chain.write_fcm()` and `Chain.fcm_remarks()` in the binding, over the
  `kin5axfcm.h` bridge of kin5ax 0.2.0.
- `Chain.unit()`, `Chain.unit_name()` and `Chain.unit_in_mm()` in the binding.

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
  7000, the Reiden RX10 and the Mazak VTC-800/30SR. The file dialog of the machine command opens on
  them, so there is something to put in the document on the day the addon is installed, and on
  wherever a machine was last taken from once that is somewhere else.
- **The kin5ax shared library** for Windows and Linux under `lib/`, so that the addon works as
  installed.

[Unreleased]: https://github.com/zdroyer/kin5ax-cam-freecad/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/zdroyer/kin5ax-cam-freecad/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/zdroyer/kin5ax-cam-freecad/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/zdroyer/kin5ax-cam-freecad/releases/tag/v0.1.0
