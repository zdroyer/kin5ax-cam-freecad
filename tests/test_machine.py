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
