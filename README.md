# kin5axcam — 3D Surface (5axis) for the CAM workbench of FreeCAD

A new operation in FreeCAD's CAM workbench: a zigzag over the parameter space of **one face**, cut
with **any shape of tool**. It is the toolpath source for the five-axis postprocessor of
[kin5ax](../kin5ax/), built in three stages:

| stage | the tool axis | state |
|---|---|---|
| 1 | stands up, as in any three-axis operation | **done** |
| 2 | along the surface normal | next |
| 3 | leaning away from the normal by one angle, in a direction given by a second | after that |

Stages 2 and 3 add the axis to each move as `I`, `J` and `K` — the vector output convention — so
`G1 X.. Y.. Z.. I.. J.. K..`. Stage 1 writes no `I J K`: no axis written means the tool stands up,
which is unambiguous.

## The point the path carries

**The tip of the tool**, which is the point a control programs, so the path goes to an ordinary
postprocessor as it is and the picture in the 3D view sits where the tool will be.

Where the tip goes is worked out from the sphere at the end of the tool. The surface point moved one
**tip radius** along the normal is the centre of that sphere, placed where the sphere touches the
surface at that point, and the tip is one tip radius down the tool axis from the centre. The tip
radius comes off the tool:

| the tool | its tip radius |
|---|---|
| ball nose, tapered ball nose | half the diameter |
| bull nose, radius — anything with a `CornerRadius` | that corner radius |
| end mill, V bit, chamfer, drill, a tool that does not say what it is | zero |

A tip radius of zero puts the tip straight on the surface point, so a flat-ended tool cuts the
surface as it is. A ball nose tool follows a curved surface the closest, having the most roundness
to offset — which is a reason to pick one, not a reason for the operation to insist on one.

The sphere touches the surface exactly at the point it came from, and nothing is promised about the
rest of the tool: in a concave corner tighter than the tip radius the tool gouges, and the flat
bottom of an end mill digs into the uphill side of a slope. That is the usual limit of a
point-by-point offset, and a drop-cutter test against the whole tool is what would fix it.

## What the operation does

Passes are laid across the face and points along each pass, both **counted in the parameter space of
the surface**. A face whose parameters run unevenly — the poles of a sphere, an unevenly
parametrised NURBS — therefore gets unevenly spaced passes. A step over in millimetres needs
arc-length sampling and is a later stage.

A row breaks into more than one pass where the face is not there: a hole, a trimmed edge. The tool
is lifted to the clearance height over the gap instead of cutting across it, which is what
`Part.Face.isPartOfDomain` is asked about at every point. What is left of a row after the gaps has
to be at least two points, since one point cuts nothing.

| property | |
|---|---|
| `Rows` | how many passes across the face |
| `PointsPerRow` | how many points along each pass |
| `PathDirection` | `U` for passes at constant v, `V` for passes at constant u |
| `ZigZag` | cut there and back, rather than returning through the air |
| `InvertNormal` | put the tool on the other side of the face |

The task dialog has the pages any operation has: **Base Geometry** to pick the face, **Depths** with
the step down, **Heights**, a **start point**, and the tool controller and the coolant on the page of
the operation itself.

The depths mean what they say: the tip of the tool is kept between the final and the start depth, and
a pass that leaves the range comes apart there, so the tool lifts over what it may not cut rather
than dragging through it. The depths the operation suggests are the top and the bottom of the face,
so by default nothing is held back.

The **step down** cuts the depth in bands from the top down, none deeper than the step. Each point is
cut once, in the band it falls into, rather than the whole path being repeated at every level: a
point already cut needs no second visit, and the tool would only be moving through air if it had one.
A step down of zero, or one that covers the whole range, is a single band, which is the path as it
was.

The **start point**, when switched on, settles which end of the path the tool begins at: the zigzag
is kept as it is and only its direction is decided, by whichever of its two ends is nearer the point.

Not here: a finish depth. That is the depth of the last pass of a roughing sequence, and this
operation follows the surface, so its last band is the finish already.

The operation refuses, with a message in the report view rather than a silent wrong path: no tool,
a ball nose tool of no diameter, no face, more than one face, and parameters that cannot make a
path.

## Installing it

**Ask FreeCAD where its `Mod` folder is rather than guessing.** In the Python console:

```python
FreeCAD.getUserAppDataDir()
```

Addons go in `Mod` under whatever that prints. On FreeCAD 1.1 it prints a **versioned** folder:

```
C:\Users\you\AppData\Roaming\FreeCAD\v1-1\        ->  ...\FreeCAD\v1-1\Mod\kin5axcam
~/.local/share/FreeCAD/v1-1/                      ->  ~/.local/share/FreeCAD/v1-1/Mod/kin5axcam
```

Older FreeCADs used `%APPDATA%\FreeCAD\Mod` with no version in it, and that is the trap: an addon
dropped there under 1.1 is not loaded, not complained about, and not mentioned anywhere. If this
addon does not appear, look there first and move it.

Then link the directory rather than copying it, so what FreeCAD loads is what the repository holds
and an edit needs no second step. Windows, no administrator needed:

```powershell
$mod = Join-Path $env:APPDATA "FreeCAD\v1-1\Mod"
New-Item -ItemType Junction -Path (Join-Path $mod "kin5axcam") -Target "C:\path\to\inkin5ax\kin5axcam"
```

Linux:

```sh
ln -s ~/path/to/inkin5ax/kin5axcam ~/.local/share/FreeCAD/v1-1/Mod/kin5axcam
```

Restart FreeCAD and switch to the **CAM** workbench, which is when the command registers. To check it
is there, in the Python console:

```python
"CAM_Surface5Axis" in FreeCADGui.listCommands()     # True
```

If that says `False`, register it by hand and read what it says:

```python
from kin5axcam import surface5axis_gui
```

That is the same import the addon does for itself, so whatever stopped it comes out as a traceback
rather than as silence. The registration waits for the CAM workbench because neither CAM nor the
signal to wait on exists while FreeCAD is still starting; a report view that says `not registered
yet ... waiting for the CAM workbench` has not given up, it retries on every workbench change.

The command comes with its own icon. It cannot be added to the **standard** CAM toolbars: those
belong to the CAM workbench and nothing outside it may change them - that is FreeCAD, not this addon.
What you can do is make a toolbar of your own through **Tools -> Customize -> Toolbars** with the CAM
workbench chosen on the right, and put the command on that; it then appears whenever CAM is active.
Or run it from the console with a CAM Job active:

```python
FreeCADGui.runCommand("CAM_Surface5Axis")
```

Tested with **FreeCAD 1.1.1** on Windows. The `Path.Op` layout it uses is the same in 1.0 and 1.2,
but neither has been run.

## Trying it by hand

Two routes. The first builds the whole scene in one go, to see a path within a minute; the second is
what a user actually does, and is the one that reaches the parts a script cannot — the command
appearing, the task panel, the tool library.

### A scene in one paste

With FreeCAD open, in the Python console (**View -> Panels -> Python console**):

```python
import sys; ROOT = r"C:\Users\zdroyer\dev\C++\inkin5ax\kin5axcam"
sys.path.insert(0, ROOT)
exec(open(ROOT + r"\examples\make_test_job.py").read())
build("box")            # a flat top face
build("hemisphere")     # a face curved both ways
```

Each call makes a document with the shape, a CAM job, a tool controller holding the **6 mm Ball
End** bit of FreeCAD's own library, and the operation, and prints what came out. What to look for:

| | the box, 100 x 50 x 10 | the hemisphere, radius 20 |
|---|---|---|
| every cutting move | `Z 10.000` - the face itself, whatever the tool | - |
| the highest move | - | `Z 20.000`, the top of the dome |
| in the 3D view | the path lies on the face | a dome of passes on the surface |

On the hemisphere the moves run down to about `Z 0.273` rather than to zero: the ball of a tool
standing up touches the steep part of the dome with its side, so its tip is below the point it is
cutting, and the final depth — the bottom of the face — cuts that dip off. Lowering the final depth
brings those moves back. Switch `InvertNormal` on and the tool works the other side of the face
instead.

The same script runs without a window, which is the quickest check that nothing is broken:

```sh
"C:/Program Files/FreeCAD 1.1.1/bin/freecadcmd.exe" examples/make_test_job.py
```

### The route a user takes

1. **Part** workbench: a box, or a sphere with `Angle1 = 0` for a hemisphere.
2. **CAM** workbench. The command registers the first time CAM is activated; check with
   `"CAM_Surface5Axis" in FreeCADGui.listCommands()` in the console.
3. **Tools -> Customize -> Toolbars**: make a toolbar in the CAM workbench and put *3D Surface
   (5axis)* on it. An addon cannot add a button to a toolbar it does not own, which is why this is
   by hand.
4. Create a **Job** on the shape.
5. In the job's **Tools**, add the **6 mm Ball End** bit from the library — or leave the default
   end mill, which cuts too, with its tip on the face rather than the ball of a round end rolling
   over it.
6. Select the face to cut - one face, the top one.
7. Run the command. The task panel asks for the passes, the points per pass, which parameter they
   sweep, there and back, and which side of the face. Change a field and the path follows.
8. **OK**, then look at the path in the 3D view and at **CAM -> Inspect G-code**.

Things worth doing to it on purpose: pick two faces (the report view says it works on one); cut a
hole through the box with a cylinder and work on the holed top face (the passes come apart at the
hole instead of crossing it); set the points per pass to 1 (refused with a reason).

### Two things about FreeCAD

A script that leaves a job with **two** tool controllers and then creates an operation hits an
`UnboundLocalError` in `PathUtils.findToolController`: with no user interface to ask which
controller to use, it returns a variable it never assigned. Under the interface the question is a
dialog and nothing goes wrong. `examples/make_test_job.py` therefore removes the job's default
controller after adding the ball end one; keep to one controller in a headless script of your own.

Before showing the task dialog, FreeCAD asks the view provider of the operation which selection gate
to put up, and the generic answer looks the operation's name up in a table written into
`Path/Op/Gui/Selection.py`. The table has no room for an operation from outside and the lookup has no
default, so the name of this one raised `KeyError` one line before the dialog would have been shown -
no page, no OK, no Cancel, and no message, because the call comes from C++ which swallows it. The
view provider in `surface5axis_gui.py` answers the question itself, with the gate the Face operation
uses, so the table is never consulted. Still an unguarded lookup on FreeCAD's main branch, looked at
on 2026-10-13, so this is not a workaround to take out again.

## The tests

```sh
py -3 run_tests.py                                    # the geometry, no FreeCAD needed
"C:/Program Files/FreeCAD 1.1.1/bin/freecadcmd.exe" run_tests.py   # and the FreeCAD ones
```

51 tests. The geometry of `pathgen.py` is checked against surfaces whose answers are known on paper
— a plane, a sphere, a plane with a hole in it — because the generator asks a surface only four
things (`ParameterRange`, `valueAt`, `normalAt`, `isPartOfDomain`) and a test can answer them
without a CAD kernel. `Part.Face` answers the same four, which `tests/test_freecad.py` checks
against a real sphere, a real plane and a real trimmed face, and then builds a Job, a tool and an
operation and reads the commands that come out. Without FreeCAD those fifteen are skipped and the
other thirty-six still run.

## Where things are

| | |
|---|---|
| `kin5axcam/pathgen.py` | the geometry: the zigzag and the tip of the tool. No FreeCAD in it |
| `kin5axcam/surface5axis.py` | the operation: properties, the face, the tool, the commands |
| `kin5axcam/surface5axis_gui.py` | the task panel, the view provider and the command |
| `InitGui.py` | two lines: hands the work to `kin5axcam/startup.py` |
| `kin5axcam/startup.py` | waits for the CAM workbench, then registers the command |
| `Resources/icons/Surface5Axis.svg` | the icon of the command: a toolpath on a turbine blade |
| `tests/` | the two halves of the test suite |
| `examples/make_test_job.py` | builds a job, a ball end tool and an operation to look at |

The operation depends on nothing of kin5ax: a toolpath knows no machine. kin5ax enters at the
postprocessor, which is the next thing to build.
