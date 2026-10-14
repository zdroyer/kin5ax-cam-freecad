# kin5axcam — 3D Surface (5axis) for the CAM workbench of FreeCAD

A new operation in FreeCAD's CAM workbench: a zigzag over the parameter space of **one face**, cut
with **any shape of tool**. It is the toolpath source for the five-axis postprocessor of
[kin5ax](../kin5ax/). How the tool is held is the `ToolAxis` property:

| `ToolAxis` | the tool axis | writes |
|---|---|---|
| `Vertical` | stands up, as in any three-axis operation | `G1 X.. Y.. Z..` |
| `Normal` | along the surface normal, leaned over by `LeanAngle` towards `LeanRotation` | `G1 X.. Y.. Z.. I.. J.. K..` |

`I J K` is the vector output convention: the axis of the tool as a unit vector in the coordinates of
the part, which is what kin5ax solves for. A move without them is a move of a tool standing up, so a
`Vertical` path is readable by anything that reads G-code.

What reads the vector is the postprocessor below — either handing it to a control that has TCP, or
solving it with kin5ax for a machine and writing the five axes. FreeCAD's **simulator** never will:
it places the tool with a fixed upright rotation (`Path/Main/Gui/SimulatorGL.py`), so a leaning path
is drawn and simulated as if the tool stood up. Nothing the operation emits can tip it; that view
comes with the kin5ax machine simulation.

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

## How the tool is held

The contact point and the normal come out of the `u, v` sweep, and the two angles turn that normal
into the axis of the tool. The angles are measured in the frame of the contact point: the direction
the pass **travels** in (the chord between the neighbouring points of the pass, flattened into the
tangent plane), the **side** of that travel (the normal crossed with it), and the **normal** itself.

- `LeanAngle` is how far the axis leans away from the normal. Zero leaves it on the normal, which is
  a ball nose tool cutting with the bottom of its ball — the worst-cutting point of it, which is why
  a lean of a few degrees is usual.
- `LeanRotation` is which way it leans, counted round the normal from the travel: **0°** leans the
  tool along the way it travels, which is a lead angle; **90°** leans it to the side, which is a
  tilt. Anything between mixes the two.

Both are measured from the travel, so both **turn with the pass**: on a zigzag the lead angle leads
in each pass rather than leading in one and trailing in the next, and the tilt changes sides with it.
Turning the path round with a start point leans the tool again for the same reason.

The lean has to be less than 90°, which would lay the tool in the surface.

Leaning the tool moves its tip: the ball still has to touch the contact point, so the tip swings
round the ball by the same angle. The operation allows for that in the start depth it suggests —
the top of the face plus as far above it as the tip can get — because the depths hold the **tip**,
and a start depth level with the face would put a leaning path entirely above it and leave nothing
to cut. A start depth set by hand needs the same room.

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
| `ToolAxis` | `Vertical`, or `Normal` to lean the tool off the surface normal |
| `LeanAngle` | how far it leans from the normal |
| `LeanRotation` | which way it leans, round the normal from the direction of travel |

The task dialog has the pages any operation has: **Base Geometry** to pick the face, **Depths**,
**Heights**, a **start point**, and the tool controller and the coolant on the page of the operation
itself.

The depths mean what they say: the tip of the tool is kept between the final and the start depth, and
a pass that leaves the range comes apart there, so the tool lifts over what it may not cut rather
than dragging through it. The depths the operation suggests are the bottom of the face and the top of
it plus room for the tip of a leaning tool, so by default nothing is held back.

**A row of the zigzag is one pass**, from one edge of the face to the other, and the tool is lifted
to the clearance height only at the end of it — or in the middle of it where the face is not there,
or where the depths say the tool may not cut. Nothing else breaks a pass.

There is **no step down**, and that is deliberate. The operation used to have one, which cut the
depth in bands and kept each point in the band it fell into. On a face that falls away across itself
— a cylinder, a blade — that chopped every row into a piece per band with a lift to the clearance
height between them, and dropped whichever band was left holding a single point, so the surface came
out in short strips with gaps in it. It bought nothing in return: every point was still cut exactly
once, so no material came off any earlier than it would have. Taking the depth in layers properly
means cutting the whole path at every level with each point held no deeper than that level, so that
what is above comes off first — a different thing, and one to build when this operation is asked to
rough as well as to finish.

The **start point**, when switched on, settles which end of the path the tool begins at: the zigzag
is kept as it is and only its direction is decided, by whichever of its two ends is nearer the point.

Not here: a finish depth. That is the depth of the last pass of a roughing sequence, and this
operation follows the surface, so its last band is the finish already.

The operation refuses, with a message in the report view rather than a silent wrong path: no tool,
a ball nose tool of no diameter, no face, more than one face, a lean of 90° or more, and parameters
that cannot make a path.

It also **warns** when the tool is not a ball nose one. The sphere at the end of the tool is all it
knows of the shape — the sides and the flat of an end mill, the shank above the corner of a bull nose
one, the cone of a V bit are nowhere in the arithmetic — so the path is right for a ball nose tool
and an approximation for every other. The warning is in the report view, with the path.

## The postprocessor

`post/fanuc_tcp_kin5ax_post.py` — FreeCAD's own `fanuc_post` with three things changed. Install it
with:

```python
from kin5axcam import postinstall
postinstall.install()
```

which copies it into the macro folder, one of the few folders FreeCAD looks for postprocessors in —
an addon cannot add a folder of its own to that list. Restart, and *fanuc_tcp_kin5ax* is in the
**Post Processor** list of the job. Run it again after updating the addon, since it is a copy.

**`K` is output.** The parameter list of the stock Fanuc post is `X Y Z A B C I J F S T Q R L H D P`
— no `K`, so the third component of every tool axis vector was dropped on the way out and the
orientation left half written. `I-0.534 J0.307` and nothing else is a vector whose `K` can only be
recovered by assuming the tool points upwards. `grbl`, `heidenhain`, `marlin`, `rrf` and
`dynapath_4060` keep `K`; `fanuc`, `linuxcnc`, `mach3_mach4`, `centroid` and `dynapath` drop it.

**`I J K` are directions on a linear move.** On `G2`/`G3` they are the centre of an arc, a length,
converted into the units of the output as before. On `G0`/`G1` they are the tool axis, a direction:
written as they are, with no unit conversion — in an inch program the stock post would have divided
the vector by 25.4 — and written on every move, never suppressed for repeating the value before, a
thing a direction has every right to do. Six digits by default, `--vector-precision` to change it.

**Tool centre point control is switched on round an operation that has a vector**: `G43.5 H<tool>`,
which is the Fanuc mode where the tool axis is commanded by `I J K`, and `G49` afterwards.
`--no-tcp` leaves them out, `--tcp-command` and `--tcp-cancel` say them differently. A three-axis
operation is posted exactly as the stock post posts it.

Mind that **`G49` cancels the tool length offset** along with the mode, so an operation that follows
a five-axis one, on the same tool, needs its offset set up again. The post says so in a comment where
it cancels. A tilted working plane — `G68.2` and the rest — is later work.

### Direct axes: `--machine`

```
--machine "C:/path/to/Reiden_RX10_A_SwivelHead_C_RotaryTable.kc.json"
```

With a kinematic chain file of kin5ax, every move of every operation is **solved for that machine**
and written as its five axes — `G1 X.. Y.. Z.. A.. C..` — instead of as a vector. No `G43.5`, and no
tool length offset either: the length of the tool is in the model the solver is given, so the joint
values already allow for it, and the program is run with the offset cancelled. This is the one mode
that runs on a control with no TCP option, and it is what the kinematics are for.

What goes in: the tip of the tool and its axis from every `G0`/`G1`, carried forward word by word the
way a control carries them — the tool standing up until a move says otherwise, so a three-axis
operation is solved too, with the rotary axes wherever the start criterion puts them. A ball nose
tool is handed over at the centre of its ball, which is where kin5ax programs it. The frame of the
part in FreeCAD is taken to be the frame of the material on the machine.

What comes out: one line per location, the ones kin5ax invents between two moves included (the
default is a step of no more than 1/100 of the chain's unit and a turn of no more than one degree;
`--max-step`, `--max-turn`, `--no-interpolation`). A free rotary axis is written the nearest turn to
its last value, so a table never sweeps 360° between two lines that mean the same position. A
location the solver cannot place is **left out** and said so — `(UNSOLVED: ... AT X.. Y.. Z..)` where
the line would have been, a count at the end of the operation, and a warning in the report view.

| argument | |
|---|---|
| `--machine-unit m\|mm` | the length unit of the chain file; `m` for the machines kin5ax ships, and the default |
| `--rotary-letters AC` | what the control calls the two rotary axes; the default is the names of the links when they are letters |
| `--holder-length 50`, `--holder-radius 30` | the holder, in mm, which a tool bit of FreeCAD does not describe |
| `--no-limits`, `--no-collisions` | leave a check out |
| `--start MIN\|MAX\|MIN_ABS\|SHORTEST` | where the trajectory starts, by the first rotary axis |

Arcs and canned cycles are refused with a message: the solver takes lines, and a `G2` has to be
written as lines before it can be solved. The shank is taken as wide as the cutter, which flags a
collision sooner rather than later.

### The library it calls

`kin5axcam/kin5ax.py` is a `ctypes` binding to `kin5axc`, the C interface of the library — a chain,
a tool, the settings, a path solved in memory and read back location by location, the frames of the
machine for drawing it. No FreeCAD in it; it is usable from any Python. The shared library is looked
for at the path in `KIN5AXC_LIBRARY`, in `kin5axcam/lib/`, and in the build trees of a checkout,
in that order; the error of a failed load lists every place it tried.

Lengths cross that boundary **in the unit of the chain file**, which the file does not state and
which is metres for every machine shipped with kin5ax. The post scales by `--machine-unit`; anything
else calling the binding scales for itself.

The file keeps the licence it came from, **LGPL-2.1-or-later**, not the MIT of the rest of kin5ax,
and keeps its FreeCAD copyright lines. Being a copy rather than a rewrite means a fix to FreeCAD's
Fanuc post can be brought over by reading the difference between the two files.

## The machine on the screen

Two more commands, registered with the operation: **Machine from kin5ax** (`CAM_Kin5axMachine`) and
**Simulate on the machine** (`CAM_Kin5axSimulate`). Like the operation they go on a toolbar of your
own through Tools → Customize, or run from the console:

```python
FreeCADGui.runCommand("CAM_Kin5axMachine")      # asks for a .kc.json, puts the machine in the document
FreeCADGui.runCommand("CAM_Kin5axSimulate")     # the job on the machine, solved, and the player
```

**The machine** is a group with an `App::Part` per segment of each branch of the chain. Each holds
the collision boxes of that segment exactly as the file gives them and the solver checks them — what
is seen is what collides — and a thin arm to the next segment, so a file that carries boxes on its
terminals only (the three shipped machines do) is still a stick figure that moves the right way. Two
more parts mark the ends: the **tool mount** and the **material**. Set its `Configuration` — five
joint values, in the order of the links of the chain, in the units of the file — and every part is
placed by the frames kin5ax computes; no recompute, the placements change under the view. A segment
part can hold anything, so a real body of the machine can be dropped in next to its boxes.

**The simulation** holds a machine, a job and the trajectory the operations of the job solve to on
that machine — five joint values per location, the ones kin5ax invents between two moves included,
kept in its properties so that a saved document still scrubs. Recomputing it is the batch: every
operation solved again, the same `kin5axcam.solve` the post uses, so what is seen here is what is
written there. Its `Step` is the picture: the machine takes that configuration, the tool of the
step's operation hangs from the mount by the length of its assembly (the bit's own solid, or a
cylinder when it has none), the model and the stock of the job sit in the frame of the material
through links, and a location the machine cannot reach is a **red vertex** where its tip would have
been. The report of the solve is a property too, and when the machine met itself on the way, so is
**what met what**: `Collisions` holds a line per pair of solids with the number of locations it cost
— *C and Tool holder: 331 locations*, *the tool cuts into Material holder: 25 locations* — and the
same lines are in the report under *what met*. A pair is counted once per location however many of
its configurations it rejected. That is the difference between knowing a path collides and knowing
the machine cannot tilt that far.

**And it is shown.** A location the machine cannot reach *because it would collide* is not skipped
over: the machine is posed at a configuration that puts the tool where that location asks — the
collision check off, the configuration nearest the pose before it, which is the one it would have
swung into — and the two solids that meet there are painted **red**, the tool and its holder with
them. `Collided` names the pairs for that location and the player says *what meets here*. Stepping to
a location that solves takes the red off, but a solid that has met anything stays **orange** to the
end of the run (`CollidedEver`), so what a path has cost is still visible once the tool has moved on.

The stock is cut at such a location as well, since the tool was asked to be there and what it would
have taken off is worth seeing beside the collision — the cutting simulation of the library will not
go there, having no configuration for it, so the stamp is made straight into the material. `Cut in a
collision` in the player, `CutInCollision` on the object, turns it off; on the job this came from it
is 2 472 mm³ of 27 805.

**The player** is the task panel the simulate command opens: a slider over the locations, play and
pause at a rate you set, a step either way, first and last, and the report. It moves `Step` and
nothing else. **Pause on a collision or a gouge**, on by default, stops the playback where the
machine first meets itself or the tool first drags its shank through material — at the start of such
a stretch, not at every location of it, so that pressing play again carries on. **Reset** makes the
stock whole again, forgets what has met what, and goes back to the first location. A tick passes a **turn in place** — a run of locations whose tip does not move, which
is the tool reorienting at one point: the swing of a lead angle at the end of a pass, or the solver's
way through a singular direction of a wrist — in one go and says how many it passed; the cut is made
at every one of them either way. *Every location* draws them all.

Properties worth knowing: `Operations` (none means every active operation of the job), the holder
the tool bit does not describe, the two checks, `Interpolate` with `MaxStep` and `MaxTurn`, and
`Start`. The unit of the chain file is on the machine, `UnitInMillimetres`.

**With no machine at all.** Leave `Machine` empty — the simulate command does, when the document has
no machine — and there is nothing to solve: the path itself is the trajectory, made as dense as the
voxels **by the library** (`k5_simulation_create_from_locations`, the same interpolation the solver
uses between two locations of a file), and the tool is drawn at the tip and the axis of every
location in the frame of the part, leaning the way the operation said. The stock is cut the same
way, in the frame of the part, and the player shows tip and axis instead of joint values. This is the
five-axis cutting simulation FreeCAD's own cannot do, and it needs no machine file: the question it
answers — *does this path, with the tool leaning like this, cut what I meant?* — comes before the
question of which machine.

**The cut.** With `Cut` on — it is, by default — the stock of the job becomes a block of voxels in
the library, in the frame of the material, and every step cuts it with the tool of the step's
operation: the ball or the flat end takes material off, and anything the shank or the holder meets
that is still there is a **gouge**. What is left is a **mesh of the voxels** under the material part
— the exposed faces only, which the library works out (`k5_material_surface_triangles`): every side
of a material voxel with a removed voxel or the outside behind it, and not one face a renderer could
not see — redrawn every `RefreshEvery` steps; `RemovedVolume` and `Gouges` are properties, the first
gouge is an orange marker, and the player shows both under the slider.
`VoxelSize` is a hundred and fiftieth of the stock's longest side unless set — a 100 mm stock cuts in
0.67 mm voxels.

Three things to know about it. The library stamps the tool into the voxels **once per location
with nothing swept between two**, so when cutting the simulation makes the invented steps as dense
as the voxels (`MaxStep` left at 0) — many more locations than the operation has moves, and the
reason a cut looks like a cut. **Stepping backwards starts the cut again** from a whole block, since
voxels cannot be uncut; scrubbing the slider back is a recut up to there, which is fast at these
sizes. And the cut needs the solved paths of the library, which live only while the document is
open: a reopened document still scrubs the machine, but **recompute the simulation to cut again**.

What is not here yet: a smooth surface (marching cubes in the library, in place of the voxel faces),
the sweep of the tool between two locations, and the difference between what is left and the model,
which is what a finish pass is judged by.

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
   sweep, there and back, which side of the face, and how the tool is held. Change a field and the
   path follows.
8. **OK**, then look at the path in the 3D view and at **CAM -> Inspect G-code**.

Things worth doing to it on purpose: pick two faces (the report view says it works on one); cut a
hole through the box with a cylinder and work on the holed top face (the passes come apart at the
hole instead of crossing it); set the points per pass to 1 (refused with a reason).

And the angles, on the hemisphere, where they are easiest to see: set `ToolAxis` to `Normal` and the
path becomes a dome of tool axes pointing out of the sphere. Give `LeanAngle` 15° and the whole lot
leans into the travel; give `LeanRotation` 90° and it leans to the side instead. **CAM → Inspect
G-code** shows the `I J K` on every cutting move.

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

148 tests. The geometry of `pathgen.py` is checked against surfaces whose answers are known on paper
— a plane, a sphere, a plane with a hole in it — because the generator asks a surface only four
things (`ParameterRange`, `valueAt`, `normalAt`, `isPartOfDomain`) and a test can answer them
without a CAD kernel. `Part.Face` answers the same four, which `tests/test_freecad.py` checks
against a real sphere, a real plane and a real trimmed face, and then builds a Job, a tool and an
operation and reads the commands that come out. `tests/test_post.py` posts a leaning path through
the postprocessor and reads the G-code back, word by word — with a vector, and solved for the
trunnion table of the library's test set, where the forward kinematics of the library is the
oracle: the joint values of the last line, put back into the chain, have to give the ball centre of
the last move. `tests/test_kin5ax.py` checks the binding against the same oracle, and
`tests/test_machine.py` and `tests/test_simulation.py` close the loop over the document: at the
last step the tool hanging from the mount part puts its ball centre, in the frame of the material
part, where the last move asked — and the stock has less volume after the path than before it, the
same amount whether a step is reached forwards or after going back — on a machine and without one.
Without FreeCAD fifty-seven are skipped and the other sixty-nine still run; the ones that need the
shared library skip when it is not built.

## Where things are

| | |
|---|---|
| `kin5axcam/pathgen.py` | the geometry: the zigzag and the tip of the tool. No FreeCAD in it |
| `kin5axcam/surface5axis.py` | the operation: properties, the face, the tool, the commands |
| `kin5axcam/surface5axis_gui.py` | the task panel, the view provider and the command |
| `InitGui.py` | two lines: hands the work to `kin5axcam/startup.py` |
| `kin5axcam/startup.py` | waits for the CAM workbench, then registers the command |
| `Resources/icons/Surface5Axis.svg` | the icon of the command: a toolpath on a turbine blade |
| `kin5axcam/kin5ax.py` | kin5ax from Python: a ctypes binding to the C interface of the library |
| `kin5axcam/solve.py` | an operation solved for a machine: the moves, the tool, the trajectory — shared by the post and the simulation |
| `kin5axcam/machine.py` | the machine in the document: a part per segment, placed by the chain |
| `kin5axcam/simulation.py` | a job on a machine: the trajectory in properties, `Step` posing the machine |
| `kin5axcam/machine_gui.py` | the two commands and the player |
| `post/fanuc_tcp_kin5ax_post.py` | the postprocessor: the whole vector with TCP, or the five axes solved by kin5ax |
| `kin5axcam/postinstall.py` | copies that file where FreeCAD looks for postprocessors |
| `tests/` | the three parts of the test suite |
| `examples/make_test_job.py` | builds a job, a ball end tool and an operation to look at |

The operation depends on nothing of kin5ax: a toolpath knows no machine. kin5ax enters at the
postprocessor, which is the next thing to build.
