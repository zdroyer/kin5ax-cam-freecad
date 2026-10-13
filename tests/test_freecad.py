"""The parts that need FreeCAD: the generator against a real Part.Face, and the operation itself.

Run with freecadcmd:

    "<FreeCAD>/bin/freecadcmd.exe" run_tests.py

Without FreeCAD these are skipped, so run_tests.py under a plain Python still
ends in a count.
"""

import math
import unittest

try:
    import FreeCAD
    import Part
except ImportError:                                 # a plain Python: nothing here can run
    FreeCAD = None
    Part = None

from kin5axcam import pathgen

needs_freecad = unittest.skipIf(FreeCAD is None, "FreeCAD is not importable: run with freecadcmd")


def top_face_name(shape):
    """The name of the face of a box whose normal stands up, found rather than assumed."""
    best, best_z = None, None
    for index, face in enumerate(shape.Faces):
        umin, umax, vmin, vmax = face.ParameterRange
        normal = face.normalAt(0.5 * (umin + umax), 0.5 * (vmin + vmax))
        if normal.z < 0.9:
            continue
        z = face.CenterOfMass.z
        if best_z is None or z > best_z:
            best, best_z = index + 1, z
    return None if best is None else "Face%d" % best


@needs_freecad
class TheGeneratorAgainstARealFace(unittest.TestCase):
    """Part.Face answers the four things the generator asks of a surface. This is where that is checked."""

    def setUp(self):
        self.document = FreeCAD.newDocument("kin5axcam_face")

    def tearDown(self):
        FreeCAD.closeDocument(self.document.Name)

    def test_the_face_of_a_sphere(self):
        sphere = self.document.addObject("Part::Sphere", "Sphere")
        sphere.Radius = 20.0
        self.document.recompute()
        face = sphere.Shape.Faces[0]
        parameters = pathgen.ZigZagParameters(tool_radius=3.0, rows=5, points_per_row=9)
        passes = pathgen.generate_passes(face, parameters)
        self.assertGreater(len(passes), 0)
        for one in passes:
            for location in one:
                #the ball centre of a sphere of 20 cut with a ball of 3 is 23 from the middle
                distance = math.sqrt(sum(c * c for c in location.point))
                self.assertAlmostEqual(23.0, distance, delta=1e-9)
                self.assertEqual(pathgen.VERTICAL_AXIS, location.axis)

    def test_a_flat_face_one_radius_below_the_path(self):
        plane = Part.makePlane(100, 50)
        parameters = pathgen.ZigZagParameters(tool_radius=2.5, rows=3, points_per_row=4)
        passes = pathgen.generate_passes(plane, parameters)
        self.assertEqual(3, len(passes))
        for one in passes:
            self.assertEqual(4, len(one))
            for location in one:
                self.assertAlmostEqual(2.5, location.point[2], delta=1e-12)

    def test_a_hole_in_the_face_breaks_the_passes(self):
        """A trimmed face reports its hole through isPartOfDomain, which is what splits a pass."""
        plane = Part.makePlane(100, 50)
        hole = Part.makeCylinder(15, 10, FreeCAD.Vector(50, 25, -5))
        face = plane.cut(hole).Faces[0]
        self.assertTrue(face.isPartOfDomain(5, 5))
        self.assertFalse(face.isPartOfDomain(50, 25))

        parameters = pathgen.ZigZagParameters(tool_radius=2.0, rows=3, points_per_row=5)
        passes = pathgen.generate_passes(face, parameters)
        self.assertGreater(len(passes), 3, "the middle row has to come apart at the hole")
        for one in passes:
            for location in one:
                self.assertTrue(face.isPartOfDomain(location.u, location.v),
                                "a point inside the hole got into a pass")


@needs_freecad
class TheOperation(unittest.TestCase):
    """A job, a ball nose tool, a face, and the commands that come out."""

    #the box the operation works on, and the tool it cuts with
    LENGTH, WIDTH, HEIGHT = 100.0, 50.0, 10.0
    DIAMETER = 6.0
    ROWS, POINTS = 3, 4

    def setUp(self):
        self.document = FreeCAD.newDocument("kin5axcam_op")
        self.box = self.document.addObject("Part::Box", "Box")
        self.box.Length = self.LENGTH
        self.box.Width = self.WIDTH
        self.box.Height = self.HEIGHT
        self.document.recompute()

        import Path.Main.Job as PathJob
        self.job = PathJob.Create("Job", [self.box])
        self.document.recompute()
        self.toolController = self.job.Tools.Group[0]

    def tearDown(self):
        FreeCAD.closeDocument(self.document.Name)

    def makeBitABallNose(self):
        """The default bit of a new job is an end mill; this makes it say it is a ball nose one.

        The tool library of 1.1 builds its bits through an asset manager that is
        test scaffolding of the CAM workbench itself, and an addon has no
        business depending on it. The operation reads two things off a tool -
        what shape it is and how wide - so the two are what this sets.
        """
        tool = self.toolController.Tool
        tool.ShapeType = "Ballend"
        tool.Diameter = self.DIAMETER
        self.document.recompute()
        return tool

    def createOperation(self):
        from kin5axcam import surface5axis
        operation = surface5axis.Create("Surface5Axis", parentJob=self.job)
        self.job.Proxy.addOperation(operation)
        operation.ToolController = self.toolController
        operation.Rows = self.ROWS
        operation.PointsPerRow = self.POINTS
        operation.ZigZag = True
        name = top_face_name(self.box.Shape)
        self.assertIsNotNone(name, "the box has a face whose normal stands up")
        operation.Base = [(self.box, (name,))]
        self.document.recompute()
        return operation

    def cuttingMoves(self, operation):
        """The G1 moves that cut, which are the ones that have an X."""
        return [c for c in operation.Path.Commands if c.Name == "G1" and "X" in c.Parameters]

    def test_the_path_of_a_flat_top_face(self):
        self.makeBitABallNose()
        operation = self.createOperation()
        self.assertFalse("Invalid" in operation.State, "the operation recomputed: %s" % operation.State)

        moves = self.cuttingMoves(operation)
        #three passes of four points: three moves in each pass after the plunge into the first point
        self.assertEqual(self.ROWS * (self.POINTS - 1), len(moves))
        #the top of the box is at 10 and the ball of a 6 mm tool has a radius of 3
        for move in moves:
            self.assertAlmostEqual(self.HEIGHT + 0.5 * self.DIAMETER, move.Parameters["Z"], delta=1e-9)
            self.assertGreaterEqual(move.Parameters["X"], -1e-9)
            self.assertLessEqual(move.Parameters["X"], self.LENGTH + 1e-9)

        #there and back: the first pass runs one way and the second the other
        first = [m.Parameters["X"] for m in moves[: self.POINTS - 1]]
        second = [m.Parameters["X"] for m in moves[self.POINTS - 1: 2 * (self.POINTS - 1)]]
        self.assertEqual(sorted(first), first)
        self.assertEqual(sorted(second, reverse=True), second)

        #The tool is lifted to the clearance height before the first pass and after every pass, and
        #the base class of the operation appends one more retract of its own after all of it - hence
        #one more than the passes plus the opening one.
        rapids = [c for c in operation.Path.Commands if c.Name == "G0" and "Z" in c.Parameters]
        clearance = operation.ClearanceHeight.Value
        atClearance = [r for r in rapids if abs(r.Parameters["Z"] - clearance) < 1e-9]
        self.assertEqual(self.ROWS + 2, len(atClearance))
        #whatever else happens, the tool does not end the operation down in the material
        last = operation.Path.Commands[-1]
        self.assertEqual("G0", last.Name)
        self.assertAlmostEqual(clearance, last.Parameters["Z"], delta=1e-9)

        #the plunges: one per pass, down to the cutting height
        plunges = [c for c in operation.Path.Commands if c.Name == "G1" and "X" not in c.Parameters]
        self.assertEqual(self.ROWS, len(plunges))
        for plunge in plunges:
            self.assertAlmostEqual(self.HEIGHT + 0.5 * self.DIAMETER, plunge.Parameters["Z"], delta=1e-9)

    def test_the_operation_offers_what_the_task_dialog_needs(self):
        """The pages of the task dialog come from the features, so these are what puts them there."""
        self.makeBitABallNose()
        operation = self.createOperation()
        for name in ("ToolController", "CoolantMode", "StartDepth", "FinalDepth",
                     "ClearanceHeight", "SafeHeight", "Base"):
            self.assertTrue(hasattr(operation, name), "the operation has no %s" % name)

    def test_the_depths_say_where_the_face_is(self):
        self.makeBitABallNose()
        operation = self.createOperation()
        #the top of the box, which is the only height this operation cuts at
        self.assertAlmostEqual(self.HEIGHT, operation.OpStartDepth.Value, delta=1e-9)
        self.assertAlmostEqual(self.HEIGHT, operation.OpFinalDepth.Value, delta=1e-9)

    def test_the_depths_limit_what_is_cut(self):
        self.makeBitABallNose()
        operation = self.createOperation()
        self.assertGreater(len(self.cuttingMoves(operation)), 0)

        #a start depth below the face puts the whole of it out of reach
        operation.setExpression("StartDepth", None)
        operation.StartDepth = self.HEIGHT - 1.0
        self.document.recompute()
        self.assertEqual([], self.cuttingMoves(operation),
                         "the face is above the start depth, so none of it may be cut")

        #and putting it back brings the path back
        operation.StartDepth = self.HEIGHT + 1.0
        self.document.recompute()
        self.assertEqual(self.ROWS * (self.POINTS - 1), len(self.cuttingMoves(operation)))

    def test_the_operation_has_what_the_face_operation_has(self):
        """Step down and start point, which are features and therefore pages and properties."""
        self.makeBitABallNose()
        operation = self.createOperation()
        for name in ("StepDown", "UseStartPoint", "StartPoint"):
            self.assertTrue(hasattr(operation, name), "the operation has no %s" % name)

    def test_a_restored_document_gets_any_property_it_is_missing(self):
        """An operation saved before a property existed has to open, not break."""
        self.makeBitABallNose()
        operation = self.createOperation()
        operation.PathDirection = "V"
        operation.removeProperty("ZigZag")
        self.assertFalse(hasattr(operation, "ZigZag"))
        operation.Proxy.opOnDocumentRestored(operation)
        self.assertTrue(hasattr(operation, "ZigZag"), "the missing property was put back")
        self.assertEqual("V", operation.PathDirection,
                         "and the chosen value of the enumeration survived its list being set")

    def test_the_start_point_decides_which_end_the_path_begins_at(self):
        self.makeBitABallNose()
        operation = self.createOperation()
        first = self.cuttingMoves(operation)[0].Parameters
        self.assertLess(first["X"], 0.5 * self.LENGTH, "it begins at the near end by default")

        operation.UseStartPoint = True
        operation.StartPoint = FreeCAD.Vector(self.LENGTH, self.WIDTH, self.HEIGHT)
        self.document.recompute()
        turned = self.cuttingMoves(operation)[0].Parameters
        self.assertGreater(turned["X"], 0.5 * self.LENGTH,
                           "asked to start at the far corner, it begins there")

    def test_a_tool_that_is_not_a_ball_nose_one_cuts_nothing(self):
        tool = self.toolController.Tool
        tool.ShapeType = "Endmill"
        self.document.recompute()
        operation = self.createOperation()
        self.assertEqual([], self.cuttingMoves(operation),
                         "an end mill has no ball to cut a surface with")

    def test_without_a_face_there_is_no_path(self):
        self.makeBitABallNose()
        from kin5axcam import surface5axis
        operation = surface5axis.Create("Surface5Axis", parentJob=self.job)
        self.job.Proxy.addOperation(operation)
        operation.ToolController = self.toolController
        operation.Base = []
        self.document.recompute()
        self.assertEqual([], self.cuttingMoves(operation))

    def test_more_than_one_face_is_refused(self):
        self.makeBitABallNose()
        operation = self.createOperation()
        self.assertGreater(len(self.cuttingMoves(operation)), 0)
        #a second face makes it ambiguous, and the operation says so instead of choosing
        name = top_face_name(self.box.Shape)
        others = [f for f in ("Face1", "Face2", "Face3") if f != name]
        operation.Base = [(self.box, (name, others[0]))]
        self.document.recompute()
        self.assertEqual([], self.cuttingMoves(operation))


if __name__ == "__main__":
    unittest.main()
