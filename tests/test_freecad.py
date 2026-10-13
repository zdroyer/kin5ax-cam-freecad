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
        radius = 3.0
        parameters = pathgen.ZigZagParameters(tip_radius=radius, rows=5, points_per_row=9)
        passes = pathgen.generate_passes(face, parameters)
        self.assertGreater(len(passes), 0)
        for one in passes:
            for location in one:
                #the ball of a 3 mm radius on a sphere of 20 has its centre 23 from the middle, and
                #the tip of a tool standing up is that centre with 3 taken off its height
                centre = (location.point[0], location.point[1], location.point[2] + radius)
                self.assertAlmostEqual(23.0, math.sqrt(sum(c * c for c in centre)), delta=1e-9)
                self.assertEqual(pathgen.VERTICAL_AXIS, location.axis)

    def test_a_flat_face_is_cut_at_its_own_height(self):
        plane = Part.makePlane(100, 50)
        parameters = pathgen.ZigZagParameters(tip_radius=2.5, rows=3, points_per_row=4)
        passes = pathgen.generate_passes(plane, parameters)
        self.assertEqual(3, len(passes))
        for one in passes:
            self.assertEqual(4, len(one))
            for location in one:
                self.assertAlmostEqual(0.0, location.point[2], delta=1e-12)

    def test_a_hole_in_the_face_breaks_the_passes(self):
        """A trimmed face reports its hole through isPartOfDomain, which is what splits a pass."""
        plane = Part.makePlane(100, 50)
        hole = Part.makeCylinder(15, 10, FreeCAD.Vector(50, 25, -5))
        face = plane.cut(hole).Faces[0]
        self.assertTrue(face.isPartOfDomain(5, 5))
        self.assertFalse(face.isPartOfDomain(50, 25))

        parameters = pathgen.ZigZagParameters(tip_radius=2.0, rows=3, points_per_row=5)
        passes = pathgen.generate_passes(face, parameters)
        self.assertGreater(len(passes), 3, "the middle row has to come apart at the hole")
        for one in passes:
            for location in one:
                self.assertTrue(face.isPartOfDomain(location.u, location.v),
                                "a point inside the hole got into a pass")


@needs_freecad
class TheOperation(unittest.TestCase):
    """A job, a tool, a face, and the commands that come out."""

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
        #the commands carry the tip, and on a level face the tip of any tool is on the face
        for move in moves:
            self.assertAlmostEqual(self.HEIGHT, move.Parameters["Z"], delta=1e-9)
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
            self.assertAlmostEqual(self.HEIGHT, plunge.Parameters["Z"], delta=1e-9)

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
        """The start point, which is a feature and therefore a page and a property."""
        self.makeBitABallNose()
        operation = self.createOperation()
        for name in ("UseStartPoint", "StartPoint"):
            self.assertTrue(hasattr(operation, name), "the operation has no %s" % name)

    def test_a_row_that_falls_away_is_one_pass_and_not_a_pass_for_each_depth(self):
        """A face that drops 20 mm across itself: the tool cuts it in one go, lifting once per row.

        This is what the step down used to break. Banding the depth cut each row
        into a piece per band, lifted the tool to the clearance height between
        the pieces, and dropped whatever band held a single point - so a surface
        that falls away came out as a handful of short passes with a gap in them.
        """
        document = self.document
        cylinder = document.addObject("Part::Cylinder", "Cylinder")
        cylinder.Radius = 20.0
        cylinder.Height = 50.0
        cylinder.Angle = 90.0
        cylinder.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90)
        document.recompute()
        #a quarter cylinder lying down, rolled so that its round face rises from the side of it to
        #the top: one face, falling away across itself, which is where banding used to show
        round_face = [i + 1 for i, f in enumerate(cylinder.Shape.Faces)
                      if f.Surface.TypeId == "Part::GeomCylinder"]
        self.assertEqual(1, len(round_face), "the quarter cylinder has one round face")
        round_face = round_face[0]

        self.makeBitABallNose()
        from kin5axcam import surface5axis
        operation = surface5axis.Create("Surface5Axis", parentJob=self.job)
        self.job.Proxy.addOperation(operation)
        operation.ToolController = self.toolController
        operation.Rows = 4
        operation.PointsPerRow = 9
        operation.Base = [(cylinder, ("Face%d" % round_face,))]
        #the depths out of the way, so that what is being looked at is the passes and nothing else:
        #where the face turns vertical the tip of a tool standing up is a radius below the surface,
        #which the bottom of the face would otherwise clip
        operation.setExpression("FinalDepth", None)
        operation.FinalDepth = -10.0
        document.recompute()

        self.assertFalse("Invalid" in operation.State, operation.State)
        plunges = [c for c in operation.Path.Commands if c.Name == "G1" and "X" not in c.Parameters]
        self.assertEqual(4, len(plunges), "one plunge per row: every row is a single pass")
        self.assertEqual(4 * 8, len(self.cuttingMoves(operation)),
                         "and every point of every row is cut, none dropped with a band")

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

    def test_any_shape_of_tool_cuts(self):
        """The shape decides the radius of the sphere at the end of the tool, and nothing else.

        On the level top of the box that radius makes no difference to the path -
        a ball touching a level face is straight under its own centre, whatever
        its size - so what this says is that none of these is turned away.
        """
        from kin5axcam import surface5axis

        for shape, radius in (("Endmill", 0.0),
                              ("Ballend", 0.5 * self.DIAMETER),
                              ("VBit", 0.0),
                              ("Drill", 0.0)):
            tool = self.toolController.Tool
            tool.ShapeType = shape
            tool.Diameter = self.DIAMETER
            self.document.recompute()
            operation = self.createOperation()
            self.assertEqual(radius, operation.Proxy.tipRadius(operation),
                             "the tip radius of a %s" % shape)
            moves = self.cuttingMoves(operation)
            self.assertEqual(self.ROWS * (self.POINTS - 1), len(moves),
                             "a %s cut nothing" % shape)
            for move in moves:
                self.assertAlmostEqual(self.HEIGHT, move.Parameters["Z"], delta=1e-9)
            self.document.removeObject(operation.Name)
            self.document.recompute()

    def test_a_rounded_corner_is_the_radius_of_the_tip(self):
        """A bull nose tool says what its corner radius is, and that is the sphere at its end."""
        tool = self.toolController.Tool
        tool.ShapeType = "Bullnose"
        tool.Diameter = self.DIAMETER
        if not hasattr(tool, "CornerRadius"):
            tool.addProperty("App::PropertyLength", "CornerRadius", "Bit", "the rounded corner")
        tool.CornerRadius = 1.5
        self.document.recompute()
        operation = self.createOperation()
        self.assertAlmostEqual(1.5, operation.Proxy.tipRadius(operation), delta=1e-12)

    def test_the_tool_stands_up_until_asked_otherwise(self):
        """A three-axis path, and no orientation in it: nothing says I, J or K."""
        self.makeBitABallNose()
        operation = self.createOperation()
        self.assertEqual("Vertical", operation.ToolAxis)
        for command in operation.Path.Commands:
            for name in ("I", "J", "K"):
                self.assertNotIn(name, command.Parameters,
                                 "a vertical tool needs nothing said about its axis")

    def test_the_axis_along_the_normal_is_written_into_every_cutting_move(self):
        """On the level top of the box the normal stands up, so the axis is 0, 0, 1."""
        self.makeBitABallNose()
        operation = self.createOperation()
        operation.ToolAxis = "Normal"
        self.document.recompute()
        moves = self.cuttingMoves(operation)
        self.assertEqual(self.ROWS * (self.POINTS - 1), len(moves))
        for move in moves:
            self.assertAlmostEqual(0.0, move.Parameters["I"], delta=1e-9)
            self.assertAlmostEqual(0.0, move.Parameters["J"], delta=1e-9)
            self.assertAlmostEqual(1.0, move.Parameters["K"], delta=1e-9)
            #the tool points along the normal, so its tip is on the face itself
            self.assertAlmostEqual(self.HEIGHT, move.Parameters["Z"], delta=1e-9)

    def test_the_two_angles_lean_the_tool_and_move_its_tip(self):
        """A lead angle of 30 on the level top of the box, where the arithmetic is on paper.

        The normal stands up and a pass runs along x, so a lean of 30 towards the
        travel puts the axis at (sin 30, 0, cos 30). The ball still touches the
        face, so the tip rises by r - r cos 30 and moves back by r sin 30.
        """
        import math

        radius = 0.5 * self.DIAMETER
        self.makeBitABallNose()
        operation = self.createOperation()
        operation.ToolAxis = "Normal"
        operation.LeanAngle = 30.0
        self.document.recompute()

        moves = self.cuttingMoves(operation)
        self.assertEqual(self.ROWS * (self.POINTS - 1), len(moves))
        for move in moves:
            self.assertAlmostEqual(0.0, move.Parameters["J"], delta=1e-9)
            self.assertAlmostEqual(math.cos(math.radians(30.0)), move.Parameters["K"], delta=1e-9)
            self.assertAlmostEqual(0.5, abs(move.Parameters["I"]), delta=1e-9)
            self.assertAlmostEqual(self.HEIGHT + radius * (1.0 - math.cos(math.radians(30.0))),
                                   move.Parameters["Z"], delta=1e-9)

        #there and back: the lead angle leans with the travel, so it turns over with the pass
        first = [m.Parameters["I"] for m in moves[: self.POINTS - 1]]
        second = [m.Parameters["I"] for m in moves[self.POINTS - 1: 2 * (self.POINTS - 1)]]
        self.assertTrue(all(i > 0.0 for i in first), "the first pass runs one way")
        self.assertTrue(all(i < 0.0 for i in second), "and the second runs the other")

        #and the tilt: round the normal from the travel, which is the y direction here. It is
        #measured from the travel like the lead angle, so it changes sides with the pass as well.
        operation.LeanRotation = 90.0
        self.document.recompute()
        tilted = self.cuttingMoves(operation)
        for move in tilted:
            self.assertAlmostEqual(0.0, move.Parameters["I"], delta=1e-9)
            self.assertAlmostEqual(0.5, abs(move.Parameters["J"]), delta=1e-9)
        self.assertTrue(all(m.Parameters["J"] > 0.0 for m in tilted[: self.POINTS - 1]))
        self.assertTrue(all(m.Parameters["J"] < 0.0
                            for m in tilted[self.POINTS - 1: 2 * (self.POINTS - 1)]))

    def test_a_lean_that_lays_the_tool_in_the_surface_is_refused(self):
        self.makeBitABallNose()
        operation = self.createOperation()
        operation.ToolAxis = "Normal"
        operation.LeanAngle = 90.0
        self.document.recompute()
        self.assertEqual([], self.cuttingMoves(operation))

    def test_a_ball_nose_tool_of_no_width_has_no_ball(self):
        tool = self.toolController.Tool
        tool.ShapeType = "Ballend"
        tool.Diameter = 0.0
        self.document.recompute()
        operation = self.createOperation()
        self.assertIsNone(operation.Proxy.tipRadius(operation))
        self.assertEqual([], self.cuttingMoves(operation))

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
