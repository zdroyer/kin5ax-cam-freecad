"""The simulation: a job solved on a machine, and the machine stepped through the trajectory.

Needs FreeCAD, the shared library and a model of the test set. The oracle is
the placements: at a solved step, the tool hanging from the mount part has to
put its ball centre - in the frame of the material part - where the move of the
operation asked for it. That closes the loop over the operation, the solver,
the machine object and the simulation at once.
"""

import os
import unittest

try:
    import FreeCAD
except ImportError:                                 # a plain Python: nothing here can run
    FreeCAD = None

from kin5axcam import kin5ax

HERE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CHAINS = os.path.join(os.path.dirname(HERE), "kin5axTests", "TestChains")
CHAIN = os.path.join(CHAINS, "AC_TiltRotaryTable.kc")


def library_is_there():
    try:
        kin5ax.load()
        return True
    except kin5ax.Kin5axError:
        return False


needs_everything = unittest.skipUnless(FreeCAD is not None and os.path.isfile(CHAIN) and library_is_there(),
                                       "needs FreeCAD, the kin5axc library and the AC table test chain")


@needs_everything
class AJobOnAMachine(unittest.TestCase):
    """The leaning box path of the post tests, run on the AC trunnion table."""

    LENGTH, WIDTH, HEIGHT = 100.0, 50.0, 10.0
    DIAMETER = 6.0
    ROWS, POINTS = 2, 3

    def setUp(self):
        import Path.Main.Job as PathJob

        from tests.test_freecad import top_face_name
        from kin5axcam import machine, simulation, surface5axis

        self.document = FreeCAD.newDocument("kin5axcam_simulation")
        self.box = self.document.addObject("Part::Box", "Box")
        self.box.Length, self.box.Width, self.box.Height = self.LENGTH, self.WIDTH, self.HEIGHT
        self.document.recompute()
        self.job = PathJob.Create("Job", [self.box])
        self.document.recompute()
        controller = self.job.Tools.Group[0]
        controller.Tool.ShapeType = "Ballend"
        controller.Tool.Diameter = self.DIAMETER
        self.document.recompute()
        self.operation = surface5axis.Create("Surface5Axis", parentJob=self.job)
        self.job.Proxy.addOperation(self.operation)
        self.operation.ToolController = controller
        self.operation.Rows = self.ROWS
        self.operation.PointsPerRow = self.POINTS
        self.operation.Base = [(self.box, (top_face_name(self.box.Shape),))]
        self.operation.ToolAxis = "Normal"
        self.operation.LeanAngle = 30.0
        self.document.recompute()

        self.machine = machine.Create("Machine", CHAIN, 1000.0, self.document)
        self.simulation = simulation.Create("Simulation", self.machine, self.job, self.document)
        self.document.recompute()

    def tearDown(self):
        FreeCAD.closeDocument(self.document.Name)

    def test_the_whole_job_is_solved_and_every_location_is_reachable(self):
        self.assertGreater(self.simulation.StepCount, self.ROWS * self.POINTS, "the invented steps too")
        self.assertEqual(self.simulation.StepCount, len(self.simulation.Solved))
        self.assertEqual(kin5ax.AXES * self.simulation.StepCount, len(self.simulation.Joints))
        self.assertEqual(3 * self.simulation.StepCount, len(self.simulation.Tips))
        self.assertTrue(all(self.simulation.Solved), self.simulation.Report)
        self.assertIn("solved", self.simulation.Report)
        self.assertIsNone(self.simulation.Unreachable, "nothing to mark")

    def test_the_model_and_the_stock_sit_in_the_frame_of_the_material(self):
        linked = {link.LinkedObject.Name for link in self.simulation.Workpiece}
        self.assertIn(self.job.Stock.Name, linked)
        self.assertTrue(any(o.Name in linked for o in self.job.Model.Group), "the model")
        for link in self.simulation.Workpiece:
            self.assertIn(link, self.machine.Material.Group)

    def test_the_tool_of_the_operation_hangs_from_the_mount(self):
        self.assertIsNotNone(self.simulation.Tool)
        self.assertIsNotNone(self.simulation.Holder)
        self.assertIn(self.simulation.Tool, self.machine.ToolMount.Group)
        self.assertFalse(self.simulation.Tool.Shape.isNull())
        #the tip of the tool is one assembly below the mount
        from kin5axcam import solve
        model = solve.tool_model_of(self.operation, self.simulation.Proxy.options(self.simulation))
        self.assertAlmostEqual(-model.assembly_length_mm, self.simulation.Tool.Placement.Base.z, delta=1e-9)

    def test_stepping_to_the_last_location_puts_the_ball_centre_where_the_last_move_asked(self):
        from kin5axcam import solve

        self.simulation.Step = self.simulation.StepCount - 1
        self.assertTrue(self.simulation.Solved[self.simulation.Step])

        moves = solve.moves_of(self.operation)
        last = moves[-1]
        options = self.simulation.Proxy.options(self.simulation)
        model = solve.tool_model_of(self.operation, options)
        centre = model.programmed_point(last.point, last.axis)
        hang = model.to_kin5ax(options.unit_in_mm).mount_to_point_distance() * options.unit_in_mm

        in_machine = self.machine.ToolMount.Placement.multVec(FreeCAD.Vector(0, 0, -hang))
        in_material = self.machine.Material.Placement.inverse().multVec(in_machine)
        for i in range(3):
            self.assertAlmostEqual(centre[i], in_material[i], delta=1e-3,
                                   msg="%r is not %r" % (in_material, centre))
        axis = self.machine.Material.Placement.inverse().Rotation.multVec(
            self.machine.ToolMount.Placement.Rotation.multVec(FreeCAD.Vector(0, 0, 1)))
        for i in range(3):
            self.assertAlmostEqual(last.axis[i], axis[i], delta=1e-6)

    def test_a_step_moves_the_machine_and_the_machine_only(self):
        self.simulation.Step = 0
        first = FreeCAD.Vector(self.machine.ToolMount.Placement.Base)
        self.simulation.Step = self.simulation.StepCount // 2
        self.assertGreater((FreeCAD.Vector(self.machine.ToolMount.Placement.Base) - first).Length, 0.1)
        self.assertEqual(self.simulation.StepCount // 2, self.simulation.Step)

    def test_a_part_the_machine_cannot_reach_is_marked_where_its_tip_would_be(self):
        self.box.Placement.Base = FreeCAD.Vector(5000.0, 0.0, 0.0)
        self.document.recompute()
        self.assertFalse(any(self.simulation.Solved), "nothing is reachable five metres away")
        self.assertIsNotNone(self.simulation.Unreachable)
        self.assertEqual(self.simulation.StepCount, len(self.simulation.Unreachable.Shape.Vertexes))
        self.assertIn(self.simulation.Unreachable, self.machine.Material.Group)
        self.assertNotIn("solved", self.simulation.Report.replace("unsolved", ""))

    def test_only_the_operations_asked_for_are_run(self):
        self.simulation.Operations = [self.operation]
        self.document.recompute()
        count = self.simulation.StepCount
        self.assertGreater(count, 0)
        self.simulation.Operations = []
        self.document.recompute()
        self.assertEqual(count, self.simulation.StepCount, "the one active operation either way")


if __name__ == "__main__":
    unittest.main()
