"""Builds a document to try the 3D Surface (5axis) operation on by hand.

It makes the shape, a CAM job, a tool controller holding the 6 mm ball end bit
that FreeCAD ships, and the operation itself, then prints what came out so the
numbers can be checked against the shape.

From the Python console of FreeCAD, with the path of this addon:

    import sys; ROOT = r"C:\\Users\\you\\dev\\inkin5ax\\kin5axcam"
    sys.path.insert(0, ROOT)
    exec(open(ROOT + r"\\examples\\make_test_job.py").read())
    build("box")                # a flat top face: every cutting move at one height
    build("hemisphere")         # a curved face: the ball centre on a bigger sphere

Or headless, which proves the same numbers without a window:

    "<FreeCAD>/bin/freecadcmd.exe" examples/make_test_job.py
"""

import os
import sys

import FreeCAD

#the ball end bit of the library FreeCAD ships: "shape-type": "Ballend", 6 mm across
BALL_END_BIT = os.path.join("Mod", "CAM", "Tools", "Bit", "6mm_Ball_End.fctb")

#the shapes to try it on, and which way their interesting face points
BOX = (100.0, 50.0, 10.0)
HEMISPHERE_RADIUS = 20.0


def addon_on_the_path():
    """Makes sure the addon can be imported, whether or not it is installed in Mod."""
    try:
        import kin5axcam                        # noqa: F401
        return
    except ImportError:
        pass
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    except NameError:                           #pasted rather than run: nothing to go on
        raise ImportError(
            "kin5axcam cannot be imported: install it in FreeCAD's Mod folder, or put the "
            "directory that holds it on sys.path before running this")
    if root not in sys.path:
        sys.path.insert(0, root)
    import kin5axcam                            # noqa: F401


def ball_end_tool(document):
    """The 6 mm ball end bit of FreeCAD's own library, in that document.

    A bit read from a .fctb file is an asset, and a tool controller wants a
    document object, so it is attached to the document on the way through.
    """
    path = os.path.join(FreeCAD.getHomePath(), BALL_END_BIT)
    if not os.path.isfile(path):
        raise ValueError("the ball end bit of the tool library is not where it was expected: " + path)
    from Path.Tool import ToolBit
    return ToolBit.from_file(path).attach_to_doc(document)


def make_shape(document, shape):
    """The shape to cut, and the name of the face to cut on it."""
    if shape == "box":
        box = document.addObject("Part::Box", "Box")
        box.Length, box.Width, box.Height = BOX
        document.recompute()
        return box, top_face_name(box.Shape)
    if shape == "hemisphere":
        #the upper half of a sphere standing on the origin: one face, curved both ways
        sphere = document.addObject("Part::Sphere", "Hemisphere")
        sphere.Radius = HEMISPHERE_RADIUS
        sphere.Angle1 = 0.0
        document.recompute()
        return sphere, "Face1"
    raise ValueError('the shapes to try are "box" and "hemisphere", not %r' % shape)


def top_face_name(shape):
    """The face whose normal stands up, found rather than assumed."""
    best, best_z = None, None
    for index, face in enumerate(shape.Faces):
        umin, umax, vmin, vmax = face.ParameterRange
        if face.normalAt(0.5 * (umin + umax), 0.5 * (vmin + vmax)).z < 0.9:
            continue
        z = face.CenterOfMass.z
        if best_z is None or z > best_z:
            best, best_z = index + 1, z
    return None if best is None else "Face%d" % best


def build(shape="box", rows=12, points_per_row=40, zigzag=True):
    """Makes the document, the job, the tool, the operation, and says what came out."""
    addon_on_the_path()
    from kin5axcam import surface5axis
    import Path.Main.Job as PathJob
    import Path.Tool.Controller as PathController

    document = FreeCAD.newDocument("Surface5Axis_" + shape)
    model, face = make_shape(document, shape)
    if face is None:
        raise ValueError("no face of that shape has its normal pointing up")

    job = PathJob.Create("Job", [model])
    document.recompute()

    #A new job comes with a 5 mm end mill, and this operation cuts with a ball nose tool. The
    #default controller is not merely left unused but removed: FreeCAD 1.1.1 cannot choose between
    #two tool controllers when there is no user interface to ask - PathUtils.findToolController
    #returns a local variable it never assigned - and an operation asks for one as it is created.
    #Under the interface the choice is a dialog and either controller may stay.
    was_there = list(job.Tools.Group)
    controller = PathController.Create("TC: 6mm Ball End", tool=ball_end_tool(document), toolNumber=1)
    job.Proxy.addToolController(controller)
    for old in was_there:
        document.removeObject(old.Name)
    document.recompute()

    operation = surface5axis.Create("Surface5Axis", parentJob=job)
    job.Proxy.addOperation(operation)
    operation.ToolController = controller
    operation.Rows = rows
    operation.PointsPerRow = points_per_row
    operation.ZigZag = zigzag
    operation.Base = [(model, (face,))]
    document.recompute()

    report(operation, model, face)
    return document, operation


def report(operation, model, face):
    """The numbers to check by eye: how much was cut, and where."""
    print("")
    print("--- %s on %s of %s" % (operation.Label, face, model.Label))
    tool = operation.ToolController.Tool
    print("tool: %s, shape %r, diameter %s"
          % (tool.Label, getattr(tool, "ShapeType", None), tool.Diameter))
    if "Invalid" in operation.State:
        print("the operation did not recompute: %s" % (operation.State,))
        print("look in the report view for the reason")
        return
    commands = operation.Path.Commands
    cutting = [c for c in commands if c.Name == "G1" and "X" in c.Parameters]
    print("commands: %d, of which cutting moves: %d" % (len(commands), len(cutting)))
    if not cutting:
        print("nothing was cut: look in the report view for the reason")
        return
    zs = [c.Parameters["Z"] for c in cutting]
    print("the cutting moves run from Z %.3f to Z %.3f" % (min(zs), max(zs)))
    print("clearance %s, safe %s" % (operation.ClearanceHeight, operation.SafeHeight))
    print("the first three cutting moves:")
    for command in cutting[:3]:
        p = command.Parameters
        print("    X %9.3f  Y %9.3f  Z %9.3f" % (p["X"], p["Y"], p["Z"]))
    print("")
    print("What to check: the path carries the centre of the ball, so it stands one tool radius")
    print("(%.3f) off the surface everywhere." % (0.5 * tool.Diameter.Value,))
    print("")


#Run under freecadcmd, which execs a file without __name__ == "__main__", this builds both shapes
#and says what came out. Under the interface it builds nothing until build() is called, because
#there the point is to look at the result rather than read it.
if not FreeCAD.GuiUp:
    #freecadcmd swallows a traceback and prints only the message, which is not enough to act on
    import traceback
    try:
        build("box")
        build("hemisphere")
    except Exception:
        traceback.print_exc(file=sys.stdout)
        raise
