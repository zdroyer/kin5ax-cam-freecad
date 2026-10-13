# kin5axcam — 3D Surface (5axis) for the CAM workbench of FreeCAD

A new operation in FreeCAD's CAM workbench: a zigzag over the parameter space of **one face**, cut
with a **ball nose** tool. It is the toolpath source for the five-axis postprocessor of
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

**The centre of the ball, not the tip of the tool.** The surface point moved one tool radius along
the surface normal. That is the programmed point of a ball nose tool in cutter location data and the
point kin5ax solves for, so the path feeds the five-axis postprocessor with nothing in between.

It also means **an ordinary three-axis postprocessor, which expects the tip, cuts one radius too
high**, and the path drawn in the 3D view floats one radius above the surface. Both are the price of
one convention through the whole chain. A property to write tip coordinates instead would be a small
addition if a stock post has to be used.

Moving the centre along the normal puts the ball exactly on the surface at the point it came from.
It says nothing about the rest of the ball, so in a concave corner tighter than the tool radius the
tool still gouges — the usual limit of a point-by-point offset.

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

The task dialog has the pages any operation has: **Base Geometry** to pick the face, **Depths**,
**Heights**, and the tool controller and the coolant on the page of the operation itself. The depths
mean what they say: the tip of the ball is kept between the final and the start depth, and a pass
that leaves the range comes apart there, so the tool lifts over what it may not cut rather than
dragging through it. The depths the operation suggests are the top and the bottom of the face, so by
default nothing is held back.

Not here, and not pretended at: a step down (this is a finishing pass in one go, not a roughing
strategy) and a start point.

The operation refuses, with a message in the report view rather than a silent wrong path: a tool
that is not a ball nose one, no face, more than one face, and parameters that cannot make a path.

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
| every cutting move | `Z 13.000` - the top at 10 plus the ball radius 3 | - |
| every ball centre | - | 23.000 from the middle: 20 plus 3 |
| in the 3D view | the path floats one radius above the face | a dome of passes standing off the surface |

That the path floats above the surface is the ball centre convention, not a fault. Switch
`InvertNormal` on and it drops to one radius *under* the face, which is the same thing from the
other side.

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
5. In the job's **Tools**, add the **6 mm Ball End** bit from the library. Worth trying the other
   way first: leave the default 5 mm end mill selected, run the operation, and the report view says
   what is wrong while the path stays empty.
6. Select the face to cut - one face, the top one.
7. Run the command. The task panel asks for the passes, the points per pass, which parameter they
   sweep, there and back, and which side of the face. Change a field and the path follows.
8. **OK**, then look at the path in the 3D view and at **CAM -> Inspect G-code**.

Things worth doing to it on purpose: pick two faces (the report view says it works on one); cut a
hole through the box with a cylinder and work on the holed top face (the passes come apart at the
hole instead of crossing it); set the points per pass to 1 (refused with a reason).

### One thing about FreeCAD 1.1.1

A script that leaves a job with **two** tool controllers and then creates an operation hits an
`UnboundLocalError` in `PathUtils.findToolController`: with no user interface to ask which
controller to use, it returns a variable it never assigned. Under the interface the question is a
dialog and nothing goes wrong. `examples/make_test_job.py` therefore removes the job's default
controller after adding the ball end one; keep to one controller in a headless script of your own.

## The tests

```sh
py -3 run_tests.py                                    # the geometry, no FreeCAD needed
"C:/Program Files/FreeCAD 1.1.1/bin/freecadcmd.exe" run_tests.py   # and the FreeCAD ones
```

37 tests. The geometry of `pathgen.py` is checked against surfaces whose answers are known on paper
— a plane, a sphere, a plane with a hole in it — because the generator asks a surface only four
things (`ParameterRange`, `valueAt`, `normalAt`, `isPartOfDomain`) and a test can answer them
without a CAD kernel. `Part.Face` answers the same four, which `tests/test_freecad.py` checks
against a real sphere, a real plane and a real trimmed face, and then builds a Job, a tool and an
operation and reads the commands that come out. Without FreeCAD those seven are skipped and the
other fourteen still run.

## Where things are

| | |
|---|---|
| `kin5axcam/pathgen.py` | the geometry: the zigzag and the ball centre. No FreeCAD in it |
| `kin5axcam/surface5axis.py` | the operation: properties, the face, the tool, the commands |
| `kin5axcam/surface5axis_gui.py` | the task panel and the command registration |
| `InitGui.py` | two lines: hands the work to `kin5axcam/startup.py` |
| `kin5axcam/startup.py` | waits for the CAM workbench, then registers the command |
| `Resources/icons/Surface5Axis.svg` | the icon of the command: a toolpath on a turbine blade |
| `tests/` | the two halves of the test suite |
| `examples/make_test_job.py` | builds a job, a ball end tool and an operation to look at |

The operation depends on nothing of kin5ax: a toolpath knows no machine. kin5ax enters at the
postprocessor, which is the next thing to build.
