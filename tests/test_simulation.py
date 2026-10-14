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

    def test_the_links_of_the_picture_are_global_and_a_step_leaves_nothing_touched(self):
        sim = self.simulation
        for name in ("Tool", "Holder", "Unreachable", "Surface", "GougeMarker"):
            self.assertEqual("App::PropertyLinkGlobal", sim.getTypeIdOfProperty(name), name)
        self.assertEqual("App::PropertyLinkListGlobal", sim.getTypeIdOfProperty("Workpiece"))
        sim.Step = sim.StepCount - 1
        for owned in [sim.Tool, sim.Holder, sim.Surface, self.machine] + list(sim.Workpiece):
            self.assertNotIn("Touched", owned.State, owned.Name)

    def test_a_document_with_a_simulation_in_it_opens_again_from_a_script(self):
        """The proxies are pickled modules; a restore may not import them, so Init.py does first."""
        import tempfile

        path = os.path.join(tempfile.mkdtemp(prefix="kin5axcam_"), "simulation.FCStd")
        count = self.simulation.StepCount
        self.document.saveAs(path)
        FreeCAD.closeDocument(self.document.Name)
        self.document = FreeCAD.openDocument(path)
        sim = self.document.getObject("Simulation")
        self.assertIsNotNone(sim.Proxy, "the proxy came back")
        self.assertEqual(count, sim.StepCount)
        self.assertEqual("App::PropertyLinkGlobal", sim.getTypeIdOfProperty("Tool"))
        sim.Step = count // 2
        self.assertEqual(count // 2, sim.Step)
        os.remove(path)

    def test_the_model_and_the_stock_sit_in_the_frame_of_the_material(self):
        linked = {link.LinkedObject.Name for link in self.simulation.Workpiece}
        self.assertIn(self.job.Stock.Name, linked)
        self.assertTrue(any(o.Name in linked for o in self.job.Model.Group), "the model")
        for link in self.simulation.Workpiece:
            self.assertIn(link, self.machine.Material.Group)
            self.assertTrue(link.LinkTransform, "a link carries the placement of what it links to")

    def test_the_stock_is_where_the_cut_is_even_when_the_part_is_not_at_the_origin(self):
        """A model placed away from the origin: the stock follows it, and so must the links and the
        cloud - the linked stock and the surface of the block have to share a bounding box."""
        self.box.Placement.Base = FreeCAD.Vector(37.0, -12.0, 5.0)
        self.document.recompute()
        sim = self.simulation
        stock = [link for link in sim.Workpiece if link.LinkedObject == self.job.Stock][0]
        linked = stock.Shape.BoundBox
        real = self.job.Stock.Shape.BoundBox
        self.assertAlmostEqual(real.XMin, linked.XMin, delta=1e-6, msg="the link is where the stock is")
        self.assertAlmostEqual(real.ZMax, linked.ZMax, delta=1e-6)
        mesh = sim.Surface.Mesh.BoundBox
        voxel = sim.Proxy.voxelSize(sim)
        self.assertAlmostEqual(real.XMin, mesh.XMin, delta=voxel, msg="and so is the mesh")
        self.assertAlmostEqual(real.YMax, mesh.YMax, delta=voxel)

    def test_a_change_of_machine_moves_the_whole_picture(self):
        """Take the machine away and the tool, the cloud and the markers come along, not stay behind."""
        sim = self.simulation
        sim.Step = sim.StepCount // 2
        old_mount = self.machine.ToolMount
        old_tool = sim.Tool
        self.assertIn(old_tool, old_mount.Group)

        sim.Machine = None
        self.document.recompute()
        self.assertIsNone(sim.Machine)
        self.assertEqual([], [o for o in old_mount.Group], "nothing of the simulation left at the mount")
        self.assertEqual([], [o for o in self.machine.Material.Group
                              if o.Name.startswith(sim.Name)], "nor in the material frame")
        self.assertIsNotNone(sim.ToolFrame)
        self.assertIn(sim.Tool, sim.ToolFrame.Group)
        self.assertIn(sim.Surface, sim.PartFrame.Group)
        self.assertEqual([], sim.Workpiece)

        #and back again
        sim.Machine = self.machine
        self.document.recompute()
        self.assertIn(sim.Tool, self.machine.ToolMount.Group)
        self.assertIsNone(sim.ToolFrame)
        self.assertIsNone(sim.PartFrame)
        self.assertGreater(len(sim.Workpiece), 0)

    def test_clearing_the_picture_leaves_nothing_of_the_simulation_in_the_document(self):
        sim = self.simulation
        sim.Step = sim.StepCount - 1
        before = {o.Name for o in self.document.Objects}
        sim.Proxy.clearPicture(sim)
        after = {o.Name for o in self.document.Objects}
        gone = before - after
        self.assertTrue(all(name.startswith(sim.Name) for name in gone), gone)
        self.assertFalse(any(name.startswith(sim.Name) and name != sim.Name for name in after),
                         "nothing of the simulation but the simulation itself")

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

    def test_the_stock_is_cut_as_the_machine_goes(self):
        """The ball of the tool takes material off the top of the box; what is left is a cloud."""
        sim = self.simulation
        self.assertTrue(sim.Cut)
        self.assertIsNotNone(sim.Surface, "the stock as a mesh of voxel faces, from the start")
        self.assertIn(sim.Surface, self.machine.Material.Group)
        whole = sim.Surface.Mesh.CountFacets
        self.assertGreater(whole, 0)
        self.assertEqual(0, whole % 2, "two triangles per face")
        self.assertEqual(0.0, sim.RemovedVolume)
        #the whole stock is a box: its mesh has exactly the faces of its outside
        nx, ny, nz = sim.Proxy._block.dimensions()
        self.assertEqual(2 * 2 * (nx * ny + ny * nz + nx * nz), whole)

        sim.Step = sim.StepCount - 1
        self.assertGreater(sim.RemovedVolume, 0.0, "the path went through the stock")
        stock = self.job.Stock.Shape.Volume
        self.assertLess(sim.RemovedVolume, 0.5 * stock, "but took far from all of it")
        self.assertEqual(0, sim.Gouges, "the holder stayed above the box")
        self.assertIsNone(sim.GougeMarker)
        self.assertNotEqual(whole, sim.Surface.Mesh.CountFacets, "the surface changed")
        #the mesh starts where the stock starts; it may end up to a voxel past it, the block being a
        #whole number of voxels rounded up
        bound = sim.Surface.Mesh.BoundBox
        stock = self.job.Stock.Shape.BoundBox
        voxel = sim.Proxy.voxelSize(sim)
        self.assertAlmostEqual(stock.XMin, bound.XMin, delta=1e-6, msg="the mesh is where the stock is")
        self.assertGreaterEqual(bound.ZMax + 1e-6, stock.ZMax)
        self.assertLess(bound.ZMax, stock.ZMax + voxel + 1e-6)

    def test_the_cut_is_the_same_whether_a_step_is_reached_forwards_or_after_going_back(self):
        sim = self.simulation
        middle = sim.StepCount // 2
        sim.Step = middle
        forwards = sim.RemovedVolume
        self.assertGreater(forwards, 0.0)
        sim.Step = sim.StepCount - 1
        self.assertGreater(sim.RemovedVolume, forwards)
        sim.Step = middle
        self.assertAlmostEqual(forwards, sim.RemovedVolume, delta=1e-9,
                               msg="going back starts the cut again from a whole block")
        sim.Step = 0
        self.assertAlmostEqual(0.0, sim.RemovedVolume, delta=1e-9, msg="nothing cut at the first step")

    def test_the_steps_are_as_dense_as_the_voxels_when_cutting(self):
        """A stamp per location needs a location per voxel, so the cut sets the step when none is set."""
        sim = self.simulation
        options = sim.Proxy.options(sim)
        self.assertAlmostEqual(sim.Proxy.voxelSize(sim), options.max_step_mm, delta=1e-12)
        self.assertGreater(sim.StepCount, 100, "many more locations than the operation's moves")

    def test_switching_the_cut_off_takes_the_cloud_away(self):
        sim = self.simulation
        sim.Cut = False
        self.document.recompute()
        self.assertIsNone(sim.Surface)
        sim.Step = sim.StepCount - 1
        self.assertEqual(0.0, sim.RemovedVolume)

    def test_only_the_operations_asked_for_are_run(self):
        self.simulation.Operations = [self.operation]
        self.document.recompute()
        count = self.simulation.StepCount
        self.assertGreater(count, 0)
        self.simulation.Operations = []
        self.document.recompute()
        self.assertEqual(count, self.simulation.StepCount, "the one active operation either way")


@needs_everything
class AJobWithNoMachine(unittest.TestCase):
    """The leaning path played as it is: the tool at every location in the frame of the part, the
    stock cut, nothing solved and no machine file anywhere."""

    LENGTH, WIDTH, HEIGHT = 100.0, 50.0, 10.0
    DIAMETER = 6.0

    def setUp(self):
        import Path.Main.Job as PathJob

        from tests.test_freecad import top_face_name
        from kin5axcam import simulation, surface5axis

        self.document = FreeCAD.newDocument("kin5axcam_free")
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
        self.operation.Rows = 2
        self.operation.PointsPerRow = 3
        self.operation.Base = [(self.box, (top_face_name(self.box.Shape),))]
        self.operation.ToolAxis = "Normal"
        self.operation.LeanAngle = 30.0
        self.document.recompute()
        self.simulation = simulation.Create("Simulation", None, self.job, self.document)
        self.document.recompute()

    def tearDown(self):
        FreeCAD.closeDocument(self.document.Name)

    def test_the_path_is_the_trajectory_made_dense_by_the_library(self):
        sim = self.simulation
        self.assertIsNone(sim.Machine)
        self.assertGreater(sim.StepCount, 100, "as dense as the voxels")
        self.assertEqual(3 * sim.StepCount, len(sim.Axes))
        self.assertTrue(all(sim.Solved))
        self.assertEqual([], list(sim.Joints), "nothing solved")
        self.assertIn("locations of the path", sim.Report)
        self.assertEqual([], sim.Workpiece, "the model and the stock are where they are already")

    def test_the_tool_stands_at_the_tip_leaning_along_the_axis(self):
        from kin5axcam import solve

        sim = self.simulation
        sim.Step = sim.StepCount - 1
        frame = sim.ToolFrame
        self.assertIsNotNone(frame)
        self.assertIn(sim.Tool, frame.Group)
        last = solve.moves_of(self.operation)[-1]
        z = frame.Placement.Rotation.multVec(FreeCAD.Vector(0, 0, 1))
        for i in range(3):
            self.assertAlmostEqual(last.axis[i], z[i], delta=1e-9, msg="the frame's Z is the tool axis")
        model = solve.tool_model_of(self.operation, sim.Proxy.options(sim))
        tip = frame.Placement.multVec(FreeCAD.Vector(0, 0, -model.assembly_length_mm))
        for i in range(3):
            self.assertAlmostEqual(last.point[i], tip[i], delta=1e-6, msg="and the tip is on the path")

    def test_the_stock_is_cut_in_the_frame_of_the_part(self):
        sim = self.simulation
        self.assertIsNotNone(sim.Surface)
        self.assertIn(sim.Surface, sim.PartFrame.Group)
        self.assertEqual(FreeCAD.Vector(0, 0, 0), sim.PartFrame.Placement.Base)
        sim.Step = sim.StepCount - 1
        self.assertGreater(sim.RemovedVolume, 0.0)
        self.assertLess(sim.RemovedVolume, 0.5 * self.job.Stock.Shape.Volume)
        self.assertEqual(0, sim.Gouges)
        middle = sim.StepCount // 2
        sim.Step = middle
        forwards = sim.RemovedVolume
        sim.Step = sim.StepCount - 1
        sim.Step = middle
        self.assertAlmostEqual(forwards, sim.RemovedVolume, delta=1e-9)


if __name__ == "__main__":
    unittest.main()
