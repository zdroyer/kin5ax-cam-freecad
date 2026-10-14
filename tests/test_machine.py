"""The machine in a document: parts for its segments, placed where kin5ax says they are.

Needs FreeCAD, the shared library and a model of the test set; skipped without
any of them. The oracle is the binding itself: the parts have to stand where the
frames of the chain put them, and a configuration set on the object has to move
them the way the same configuration moves the chain.
"""

import os
import tempfile
import unittest

try:
    import FreeCAD
except ImportError:                                 # a plain Python: nothing here can run
    FreeCAD = None

from kin5axcam import kin5ax

HERE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CHAINS = os.path.join(os.path.dirname(HERE), "kin5axTests", "TestChains")
#a swivel head and a rotary table, with a box on each terminal and none on the joints
CHAIN = os.path.join(CHAINS, "Reiden_RX10_A_SwivelHead_C_RotaryTable.kc.json")


def library_is_there():
    try:
        kin5ax.load()
        return True
    except kin5ax.Kin5axError:
        return False


needs_everything = unittest.skipUnless(FreeCAD is not None and os.path.isfile(CHAIN) and library_is_there(),
                                       "needs FreeCAD, the kin5axc library and the Reiden test chain")


def close_to(a, b, tolerance=1e-6):
    return all(abs(a[i] - b[i]) < tolerance for i in range(3))


@needs_everything
class AMachineInADocument(unittest.TestCase):

    def setUp(self):
        from kin5axcam import machine

        self.document = FreeCAD.newDocument("kin5axcam_machine")
        self.machine = machine.Create("Machine", CHAIN, 1000.0, self.document)
        self.document.recompute()

    def tearDown(self):
        FreeCAD.closeDocument(self.document.Name)

    def test_it_has_a_part_per_segment_of_each_branch_and_the_two_end_frames(self):
        with kin5ax.Chain(CHAIN) as chain:
            tool_segments = len(chain.frames(kin5ax.PART_TOOL))
            material_segments = len(chain.frames(kin5ax.PART_MATERIAL_HOLDER))
        self.assertEqual(tool_segments, len(self.machine.ToolBodies))
        self.assertEqual(material_segments, len(self.machine.MaterialBodies))
        self.assertEqual(tool_segments - 1, len(self.machine.ToolArms), "an arm to each next segment")
        self.assertEqual(material_segments - 1, len(self.machine.MaterialArms))
        self.assertIsNotNone(self.machine.ToolMount)
        self.assertIsNotNone(self.machine.Material)
        for part in self.machine.ToolBodies + self.machine.MaterialBodies + [self.machine.ToolMount]:
            self.assertEqual("App::Part", part.TypeId)

    def test_the_boxes_of_the_file_are_in_the_parts_of_their_segments_in_millimetres(self):
        boxes = [o for o in self.document.Objects if o.TypeId == "Part::Feature" and "Box" in o.Name]
        self.assertEqual(2, len(boxes), "one box on each terminal of this model")
        with kin5ax.Chain(CHAIN) as chain:
            low, high = chain.segment_boxes(kin5ax.PART_TOOL, len(chain.frames(kin5ax.PART_TOOL)) - 1)[0]
        holder = [b for b in boxes if b in self.machine.ToolBodies[-1].Group][0]
        bound = holder.Shape.BoundBox
        self.assertAlmostEqual((high[0] - low[0]) * 1000.0, bound.XLength, delta=1e-6)
        self.assertAlmostEqual((high[2] - low[2]) * 1000.0, bound.ZLength, delta=1e-6)
        self.assertAlmostEqual(low[0] * 1000.0, bound.XMin, delta=1e-6, msg="the minimum corner where "
                               "the file puts it, in the frame of the segment")

    def test_the_parts_stand_where_the_frames_of_the_chain_put_them(self):
        q = [0.1, 0.05, -0.02, 0.3, 0.5]
        self.machine.Configuration = q
        with kin5ax.Chain(CHAIN) as chain:
            chain.set_configuration(q)
            frames = chain.frames(kin5ax.PART_TOOL)
            for index, (joint, output) in enumerate(frames):
                body = self.machine.ToolBodies[index]
                self.assertTrue(close_to([c * 1000.0 for c in joint[12:15]], body.Placement.Base),
                                "segment %d: %r is not at %r" % (index, body.Placement.Base, joint[12:15]))
                self.assertTrue(close_to(joint[8:11], body.Placement.Rotation.multVec(FreeCAD.Vector(0, 0, 1))),
                                "the Z of the joint frame is the axis of the joint")
            mount = [c * 1000.0 for c in frames[-1][1][12:15]]
            self.assertTrue(close_to(mount, self.machine.ToolMount.Placement.Base))
            material = [c * 1000.0 for c in chain.frames(kin5ax.PART_MATERIAL_HOLDER)[-1][1][12:15]]
            self.assertTrue(close_to(material, self.machine.Material.Placement.Base))

    def test_the_tool_point_of_the_chain_is_below_the_mount_part_by_the_tool_it_is_given(self):
        """The oracle of the whole picture: the mount part, a tool hanging from it, and the solver's
        own tool point in the frame of the material agree to a micrometre."""
        q = [0.1, 0.05, -0.02, 0.3, 0.5]
        self.machine.Configuration = q
        with kin5ax.Chain(CHAIN) as chain:
            tool = kin5ax.Tool(kin5ax.TOOL_BALL_NOSE, 0.008, 0.008, 0.040, 0.030, 0.050, 0.030)
            hang = tool.mount_to_point_distance() * 1000.0
            point, axis = chain.tool_point(q, tool)
        in_machine = self.machine.ToolMount.Placement.multVec(FreeCAD.Vector(0, 0, -hang))
        in_material = self.machine.Material.Placement.inverse().multVec(in_machine)
        self.assertTrue(close_to([c * 1000.0 for c in point], in_material, 1e-3),
                        "%r is not %r" % (in_material, point))
        tool_axis = self.machine.Material.Placement.inverse().Rotation.multVec(
            self.machine.ToolMount.Placement.Rotation.multVec(FreeCAD.Vector(0, 0, 1)))
        self.assertTrue(close_to(axis, tool_axis))

    def test_a_configuration_moves_the_parts_without_a_recompute(self):
        #the links of this model run C, Y, X, Z, A: the first joint turns the table, which moves the
        #material and not the tool mount, so it is the Z of the tool branch that is moved here
        before = FreeCAD.Vector(self.machine.ToolMount.Placement.Base)
        self.machine.Configuration = [0.0, 0.0, 0.0, 0.2, 0.0]
        after = self.machine.ToolMount.Placement.Base
        self.assertGreater((after - before).Length, 1.0, "the mount moved with its Z joint")
        table = FreeCAD.Vector(self.machine.Material.Placement.Base)
        self.machine.Configuration = [0.5, 0.0, 0.0, 0.2, 0.0]
        self.assertTrue(close_to(table, self.machine.Material.Placement.Base),
                        "the table turns about its own axis, so its origin stays put")
        self.assertGreater(abs(self.machine.Material.Placement.Rotation.Angle), 0.4, "but it turned")

    def test_every_joint_has_a_marker_and_no_terminal_has_one(self):
        with kin5ax.Chain(CHAIN) as chain:
            tool_joints = len(chain.frames(kin5ax.PART_TOOL)) - 1
            material_joints = len(chain.frames(kin5ax.PART_MATERIAL_HOLDER)) - 1
        self.assertEqual(tool_joints, len(self.machine.ToolJoints))
        self.assertEqual(material_joints, len(self.machine.MaterialJoints))
        self.assertEqual(kin5ax.AXES, tool_joints + material_joints)
        for index, marker in enumerate(self.machine.ToolJoints):
            self.assertIn(marker, self.machine.ToolBodies[index].Group, "in the frame of its joint")
        self.assertGreater(self.machine.JointSize, 0.0, "a size picked from the machine")
        self.assertTrue(self.machine.ShowJoints)

    def test_a_turning_joint_shows_a_sector_as_wide_as_its_angle_on_the_side_of_its_sign(self):
        """The links of this model run C, Y, X, Z, A: A is the last link and the second segment of
        the tool branch. A sector about Z from zero to the angle lies on +Y for a positive angle and
        on -Y for a negative one; its volume says how wide it is."""
        import math

        size = self.machine.JointSize
        thickness = 0.08 * size
        a_marker = self.machine.ToolJoints[1]
        self.machine.Configuration = [0.0, 0.0, 0.0, 0.0, math.radians(60.0)]
        sector = [s for s in a_marker.Shape.Solids if s.Volume > 0.5 * (math.pi * size * size * thickness / 6.0)]
        self.assertEqual(1, len(sector), "a wedge beside the dial")
        self.assertAlmostEqual(math.pi * size * size * thickness / 6.0, sector[0].Volume,
                               delta=0.02 * math.pi * size * size * thickness)
        self.assertGreater(sector[0].BoundBox.YMax, 0.5 * size, "a positive angle sweeps towards +Y")
        self.assertGreater(sector[0].BoundBox.YMin, -1e-6)

        self.machine.Configuration = [0.0, 0.0, 0.0, 0.0, math.radians(-60.0)]
        sector = [s for s in a_marker.Shape.Solids if s.Volume > 0.5 * (math.pi * size * size * thickness / 6.0)]
        self.assertLess(sector[0].BoundBox.YMin, -0.5 * size, "a negative one towards -Y")
        self.assertLess(sector[0].BoundBox.YMax, 1e-6)

        self.machine.Configuration = [0.0] * 5
        self.assertEqual(1, len(a_marker.Shape.Solids), "the dial alone at zero")

    def test_a_sliding_joint_shows_a_box_as_long_as_its_travel(self):
        """Z is the first segment of the tool branch, link index 3, in metres in the file."""
        size = self.machine.JointSize
        z_marker = self.machine.ToolJoints[0]
        self.machine.Configuration = [0.0, 0.0, 0.0, 0.12, 0.0]
        box = max(z_marker.Shape.Solids, key=lambda s: s.Volume)
        self.assertAlmostEqual(120.0, box.BoundBox.ZLength, delta=1e-6, msg="120 mm of travel")
        self.assertAlmostEqual(size, box.BoundBox.XLength, delta=1e-6)
        self.assertAlmostEqual(0.0, box.BoundBox.ZMin, delta=1e-6, msg="from zero up")
        self.machine.Configuration = [0.0, 0.0, 0.0, -0.05, 0.0]
        box = max(z_marker.Shape.Solids, key=lambda s: s.Volume)
        self.assertAlmostEqual(50.0, box.BoundBox.ZLength, delta=1e-6)
        self.assertAlmostEqual(-50.0, box.BoundBox.ZMin, delta=1e-6, msg="from the travel up to zero")

    def test_the_markers_follow_the_size_they_are_given(self):
        self.machine.Configuration = [0.0, 0.0, 0.0, 0.1, 0.5]
        before = self.machine.ToolJoints[1].Shape.BoundBox.XLength
        self.machine.JointSize = self.machine.JointSize * 2.0
        self.assertAlmostEqual(2.0 * before, self.machine.ToolJoints[1].Shape.BoundBox.XLength, delta=1e-6)

    def test_the_machine_survives_being_saved_and_opened_again(self):
        self.machine.Configuration = [0.1, 0.05, -0.02, 0.3, 0.5]
        mount = FreeCAD.Vector(self.machine.ToolMount.Placement.Base)
        path = os.path.join(tempfile.mkdtemp(prefix="kin5axcam_"), "machine.FCStd")
        self.document.saveAs(path)
        FreeCAD.closeDocument(self.document.Name)
        self.document = FreeCAD.openDocument(path)
        machine = self.document.getObject("Machine")
        self.assertIsNotNone(machine.Proxy)
        self.assertTrue(close_to(mount, machine.ToolMount.Placement.Base), "placed as it was saved")
        machine.Configuration = [0.0, 0.0, 0.0, 0.0, 0.0]
        self.assertGreater((FreeCAD.Vector(machine.ToolMount.Placement.Base) - mount).Length, 1.0,
                           "and it still moves after the restore, the chain opened again")
        os.remove(path)


if __name__ == "__main__":
    unittest.main()
