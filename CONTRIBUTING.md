# Working on kin5axcam

## The two halves

The kinematics, the collision checks and the voxel cutting are C++, in
[kin5ax](https://github.com/zdroyer/kin5ax). This repository is the FreeCAD half: the operation, the
postprocessor, the machine in the document, the player, and a `ctypes` binding to the C interface of
that library. A change to how a machine is solved belongs there; a change to what FreeCAD shows
belongs here.

The two are released together, because the binding mirrors the C structures field by field.
`kin5axcam/kin5ax.py` holds `REQUIRED_VERSION`, which is the major and minor of the library it was
written against, and refuses anything else as it loads. While the major number is 0 the minor has to
match exactly.

## The branches

| branch | what it is |
|---|---|
| `main` | where the work happens, and the default branch. Every feature arrives on a branch of its own and is merged with `--no-ff`, so the history says what each change was for |
| `releases` | what users install. `package.xml` names it, so the Addon Manager follows it rather than the tip of `main` |

A release is `main` merged into `releases`, with the version in `package.xml`, a heading in
`CHANGELOG.md` and a `vX.Y.Z` tag. `lib/` is rebuilt from the matching tag of the library and
committed in the same change, so that the pair in a release is always the pair that was tested.

## Running the tests

```sh
py -3 run_tests.py                                                  # the ones that need no FreeCAD
"C:/Program Files/FreeCAD 1.1.1/bin/freecadcmd.exe" run_tests.py    # and the FreeCAD ones
```

The first form is what the GitHub workflow runs on every push, and it loads the library out of
`lib/` on a machine that did not build it. The second needs FreeCAD 1.1 or newer and is run by hand.

A test that needs FreeCAD, or the shared library, says so and is skipped rather than failing when it
is not there, so both forms end in a count and neither ends in an import error. Watch the number
skipped: a run that skips seventy-odd tests under `freecadcmd` is a run that did not find the
library, not a run that passed.

## Developing against a library you are building

Point the addon at your build and it will ignore the shipped one:

```sh
export KIN5AXC_LIBRARY=~/dev/kin5ax/build/kin5axc/libkin5axc.so.0.1.0
```

A checkout of the library kept beside this repository is found without that, which is the ordinary
case for someone working on both.

## Installing a checkout

Link it into FreeCAD's `Mod` folder rather than copying, so that what FreeCAD loads is what the
repository holds. The README has the commands for Windows and Linux. Ask FreeCAD where that folder
is with `FreeCAD.getUserAppDataDir()`; on 1.1 it is a versioned path, and an addon dropped in the
unversioned one is not loaded and not complained about.

## What the code is like

Comments say why, not what. A test is named for the thing it promises, so that a failure reads as a
sentence about the program rather than a number. Lengths crossing into the library are in the unit
of the chain file, which the file declares and `Chain.unit_in_mm()` reports, and the caller scales.
