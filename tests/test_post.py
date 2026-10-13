"""The fanuc_tcp_kin5ax postprocessor: the tool axis vector has to reach the file whole.

What is checked is what was changed in FreeCAD's Fanuc post, since the rest of it
is FreeCAD's and is tested there: that K is written at all, that the vector is a
direction rather than a length, and that an operation with a tool axis is wrapped
in the tool centre point control mode.

Run with freecadcmd. Without FreeCAD the whole of it is skipped.
"""

import importlib.util
import io
import math
import os
import shutil
import tempfile
import unittest

try:
    import FreeCAD
    import Path
except ImportError:                                 # a plain Python: nothing here can run
    FreeCAD = None
    Path = None

needs_freecad = unittest.skipIf(FreeCAD is None, "FreeCAD is not importable: run with freecadcmd")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POST_FILE = os.path.join(HERE, "post", "fanuc_tcp_kin5ax_post.py")


def the_post():
    """The post as a module, loaded from the file the addon ships rather than from an install."""
    spec = importlib.util.spec_from_file_location("fanuc_tcp_kin5ax_post", POST_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def words_of(line):
    """The words of a line of G-code as a dict: "X-1.5 Y2" becomes {"X": -1.5, "Y": 2.0}."""
    words = {}
    for word in line.split():
        try:
            words[word[0]] = float(word[1:])
        except ValueError:
            continue
    return words


def cutting_lines(gcode):
    """The lines that cut: a G1 that moves in X, with the G1 left out when it is modal."""
    lines = []
    moving = False
    for line in gcode.splitlines():
        line = line.strip()
        if line.startswith("("):
            continue
        if line.startswith("G1"):
            moving = True
        elif line.startswith("G"):
            moving = line.startswith("G1")
        if moving and "X" in line:
            lines.append(line)
    return lines


class InstallingIt(unittest.TestCase):
    """install(): a copy into a folder FreeCAD looks in, since an addon cannot add a folder."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="kin5axcam_post_")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_it_copies_the_postprocessor_there(self):
        from kin5axcam import postinstall

        target = postinstall.install(self.folder)
        self.assertTrue(os.path.isfile(target))
        self.assertTrue(target.endswith("_post.py"), "FreeCAD finds a postprocessor by that ending")
        with io.open(target, encoding="utf-8") as copied:
            self.assertIn("G43.5", copied.read())

    def test_it_makes_the_folder_when_there_is_none(self):
        from kin5axcam import postinstall

        folder = os.path.join(self.folder, "not", "there", "yet")
        self.assertTrue(os.path.isfile(postinstall.install(folder)))

    def test_it_can_be_run_again_over_an_older_copy(self):
        from kin5axcam import postinstall

        target = postinstall.install(self.folder)
        with io.open(target, "w", encoding="utf-8") as older:
            older.write("# something else entirely")
        postinstall.install(self.folder)
        with io.open(target, encoding="utf-8") as copied:
            self.assertIn("G43.5", copied.read())


@needs_freecad
class ThePostOfALeaningPath(unittest.TestCase):
    """A box, a ball nose tool and the operation leaning over, posted and read back."""

    LENGTH, WIDTH, HEIGHT = 100.0, 50.0, 10.0
    DIAMETER = 6.0
    ROWS, POINTS = 3, 4
    LEAN = 30.0

    def setUp(self):
        import Path.Main.Job as PathJob

        from tests.test_freecad import top_face_name
        from kin5axcam import surface5axis

        self.document = FreeCAD.newDocument("kin5axcam_post")
        box = self.document.addObject("Part::Box", "Box")
        box.Length, box.Width, box.Height = self.LENGTH, self.WIDTH, self.HEIGHT
        self.document.recompute()

        self.job = PathJob.Create("Job", [box])
        self.document.recompute()
        controller = self.job.Tools.Group[0]
        controller.ToolNumber = 7
        tool = controller.Tool
        tool.ShapeType = "Ballend"
        tool.Diameter = self.DIAMETER
        self.document.recompute()

        self.operation = surface5axis.Create("Surface5Axis", parentJob=self.job)
        self.job.Proxy.addOperation(self.operation)
        self.operation.ToolController = controller
        self.operation.Rows = self.ROWS
        self.operation.PointsPerRow = self.POINTS
        self.operation.Base = [(box, (top_face_name(box.Shape),))]
        self.document.recompute()

        self.post = the_post()

    def tearDown(self):
        FreeCAD.closeDocument(self.document.Name)

    def lean(self, angle=None, rotation=0.0):
        self.operation.ToolAxis = "Normal"
        self.operation.LeanAngle = self.LEAN if angle is None else angle
        self.operation.LeanRotation = rotation
        self.document.recompute()

    def posted(self, arguments="--no-show-editor --no-header"):
        return self.post.export([self.operation], "-", arguments)

    def test_every_cutting_move_carries_the_whole_vector(self):
        """The K word is the point of this post: without it the orientation is half written."""
        self.lean()
        lines = cutting_lines(self.posted())
        self.assertEqual(self.ROWS * (self.POINTS - 1), len(lines))
        for line in lines:
            words = words_of(line)
            for word in ("I", "J", "K"):
                self.assertIn(word, words, "no %s in %r" % (word, line))
            length = math.sqrt(words["I"] ** 2 + words["J"] ** 2 + words["K"] ** 2)
            self.assertAlmostEqual(1.0, length, delta=1e-5,
                                   msg="the axis of the tool is a unit vector: %r" % line)

    def test_the_vector_is_written_every_time_even_when_it_does_not_change(self):
        """A direction that repeats is a tool still pointing that way, not a word to leave out."""
        self.lean()
        lines = cutting_lines(self.posted())
        self.assertGreater(len(lines), 2)
        first = [words_of(line)["K"] for line in lines]
        self.assertEqual(1, len(set(first)), "the level top of the box leans the tool the same way")

    def test_the_operation_is_wrapped_in_tool_centre_point_control(self):
        self.lean()
        gcode = self.posted()
        lines = [line.strip() for line in gcode.splitlines()]
        self.assertIn("G43.5 H7", lines, "the mode, with the tool number of the operation")

        #and round the moves: on before the first of them, cancelled after the last
        cutting = [lines.index(line) for line in cutting_lines(gcode)]
        self.assertLess(lines.index("G43.5 H7"), min(cutting))
        cancelled = [i for i, line in enumerate(lines) if line == "G49" and i > min(cutting)]
        self.assertEqual(1, len(cancelled), "cancelled once, after the moves")
        self.assertGreater(cancelled[0], max(cutting))

    def test_a_tool_standing_up_is_posted_as_it_always_was(self):
        """No vector in the path, so no vector in the file and no mode to switch on."""
        self.assertEqual("Vertical", self.operation.ToolAxis)
        gcode = self.posted()
        self.assertNotIn("G43.5", gcode)
        for line in cutting_lines(gcode):
            for word in ("I", "J", "K"):
                self.assertNotIn(word, words_of(line), "%r in a three-axis file" % word)

    def test_the_mode_can_be_left_out_and_the_vector_still_written(self):
        self.lean()
        gcode = self.posted("--no-show-editor --no-header --no-tcp")
        self.assertNotIn("G43.5", gcode)
        self.assertIn("K", words_of(cutting_lines(gcode)[0]))

    def test_the_mode_and_what_cancels_it_can_be_said(self):
        self.lean()
        gcode = self.posted("--no-show-editor --no-header --tcp-command G43.4 --tcp-cancel G49.1")
        self.assertIn("G43.4 H7", gcode)
        self.assertIn("G49.1", gcode)

    def test_the_vector_is_a_direction_and_not_a_length(self):
        """In inches the coordinates are divided by 25.4 and the tool axis is not.

        This is the other half of the K bug: a unit vector run through the length
        conversion of the post comes out a fortieth of its size, and a reader has
        no way of telling that from a tool leaning a long way over.
        """
        self.lean()
        inches = cutting_lines(self.posted("--no-show-editor --no-header --inches"))
        millimetres = cutting_lines(self.posted())
        self.assertEqual(len(inches), len(millimetres))
        for inch, millimetre in zip(inches, millimetres):
            there, here = words_of(inch), words_of(millimetre)
            self.assertAlmostEqual(here["X"] / 25.4, there["X"], delta=1e-3, msg=inch)
            for word in ("I", "J", "K"):
                self.assertAlmostEqual(here[word], there[word], delta=1e-9,
                                       msg="the vector was converted as a length: %r" % inch)
            length = math.sqrt(there["I"] ** 2 + there["J"] ** 2 + there["K"] ** 2)
            self.assertAlmostEqual(1.0, length, delta=1e-5)

    def test_the_centre_of_an_arc_is_still_a_length(self):
        """I and J on a G2 are where the centre of the arc is, which inches do change."""
        shape = self.document.addObject("Path::Feature", "Arc")
        shape.Path = Path.Path([
            Path.Command("G0", {"X": 0.0, "Y": 0.0, "Z": 0.0}),
            Path.Command("G2", {"X": 25.4, "Y": 0.0, "I": 12.7, "J": 0.0, "F": 100.0}),
        ])
        self.document.recompute()
        gcode = self.post.export([shape], "-", "--no-show-editor --no-header --inches")
        arc = [line for line in gcode.splitlines() if line.startswith("G2 ")]
        self.assertEqual(1, len(arc), gcode)
        words = words_of(arc[0])
        self.assertAlmostEqual(0.5, words["I"], delta=1e-6, msg="12.7 mm is half an inch")
        self.assertNotIn("K", words, "nothing to say about an arc in the XY plane")
        self.assertNotIn("G43.5", gcode, "an arc centre is not a tool axis")


if __name__ == "__main__":
    unittest.main()
