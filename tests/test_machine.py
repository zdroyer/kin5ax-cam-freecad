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
CHAINS = os.path.join(HERE, "Resources", "machines")
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

    def test_the_unit_comes_from_the_file_unless_it_is_given(self):
        """The file says metres, so the machine says 1000 without being told; a value given
        overrides it, which is what a test that wants another scale uses."""
        from kin5axcam import machine

        own = machine.Create("FromTheFile", CHAIN, document=self.document)
        self.assertEqual(1000.0, own.UnitInMillimetres)
        told = machine.Create("Told", CHAIN, 1.0, self.document)
        self.assertEqual(1.0, told.UnitInMillimetres)

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

    def test_a_joint_that_did_not_move_is_not_shaped_again(self):
        """Rebuilding a shape is work for the view; a step moves two or three joints of five."""
        machine = self.machine
        machine.Configuration = [0.0, 0.0, 0.0, 0.1, 0.5]
        shown = dict(machine.Proxy._shown_joints)
        machine.Configuration = [0.0, 0.0, 0.0, 0.2, 0.5]
        after = machine.Proxy._shown_joints
        changed = [name for name in after if after[name] != shown.get(name)]
        self.assertEqual([machine.ToolJoints[0].Name], changed, "the Z marker and no other")
        machine.JointSize = machine.JointSize * 1.5
        self.assertTrue(all(machine.Proxy._shown_joints[name] != after[name] for name in after),
                        "a new size shapes every marker again")

    def test_the_markers_follow_the_size_they_are_given(self):
        self.machine.Configuration = [0.0, 0.0, 0.0, 0.1, 0.5]
        before = self.machine.ToolJoints[1].Shape.BoundBox.XLength
        self.machine.JointSize = self.machine.JointSize * 2.0
        self.assertAlmostEqual(2.0 * before, self.machine.ToolJoints[1].Shape.BoundBox.XLength, delta=1e-6)

    def test_a_link_into_a_part_is_a_global_link_and_a_pose_leaves_nothing_touched(self):
        """FreeCAD reports an ordinary link into an App::Part as out of scope on every restore, and
        a placement set from outside a part's recompute leaves it touched; neither is wanted."""
        for name in ("ToolJoints", "MaterialJoints"):
            self.assertEqual("App::PropertyLinkListGlobal", self.machine.getTypeIdOfProperty(name))
        self.machine.Configuration = [0.1, 0.05, -0.02, 0.3, 0.5]
        for part in self.machine.ToolBodies + self.machine.ToolArms + [self.machine.ToolMount]:
            self.assertNotIn("Touched", part.State, part.Name)
        for marker in self.machine.ToolJoints:
            self.assertNotIn("Touched", marker.State, marker.Name)

    def test_a_machine_saved_before_the_joint_markers_gains_them_on_restore(self):
        machine = self.machine
        markers = list(machine.ToolJoints) + list(machine.MaterialJoints)
        for marker in markers:
            self.document.removeObject(marker.Name)
        for name in ("ToolJoints", "MaterialJoints", "JointSize", "ShowJoints"):
            machine.removeProperty(name)
        machine.Proxy.onDocumentRestored(machine)
        self.assertIn("ShowJoints", machine.PropertiesList)
        self.assertGreater(machine.JointSize, 0.0)
        self.assertEqual(len(markers), len(machine.ToolJoints) + len(machine.MaterialJoints),
                         "a marker per joint again")
        for index, marker in enumerate(machine.ToolJoints):
            self.assertIn(marker, machine.ToolBodies[index].Group)
            self.assertFalse(marker.Shape.isNull(), "and shaped to the joint it belongs to")

    def test_an_older_document_gets_its_links_made_global_on_restore(self):
        from kin5axcam import machine as module

        self.machine.removeProperty("ToolJoints")
        self.machine.addProperty("App::PropertyLinkList", "ToolJoints", "Kin5axMachine", "as it was")
        markers = [m for m in self.document.Objects if m.Name.startswith("MachineToolJoint")]
        self.machine.ToolJoints = markers
        module.globalise(self.machine, {"ToolJoints": "App::PropertyLinkListGlobal"})
        self.assertEqual("App::PropertyLinkListGlobal", self.machine.getTypeIdOfProperty("ToolJoints"))
        self.assertEqual([m.Name for m in markers], [m.Name for m in self.machine.ToolJoints],
                         "and it still links to what it linked to")

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


class TheMachinesThatShipWithTheAddon(unittest.TestCase):
    """Fourteen chain files come with the addon, and a user has to be able to find them.

    They are the only thing that makes the machine command usable on the day it
    is installed: without one there is nothing to open, and a file dialog that
    starts on whatever folder FreeCAD used last says nothing about their
    existing at all.
    """

    def test_they_are_there_and_the_real_machines_among_them(self):
        self.assertTrue(os.path.isdir(CHAINS), CHAINS)
        files = sorted(f for f in os.listdir(CHAINS) if f.endswith((".kc", ".kc.json")))
        self.assertGreaterEqual(len(files), 14, files)
        for catalogue in ("SHW_UniForce7000_AC_ForkHead",
                          "Reiden_RX10_A_SwivelHead_C_RotaryTable",
                          "Mazak_VTC800-30SR_B_SwivelHead_C_RotaryTable"):
            self.assertIn(catalogue + ".kc", files)
            self.assertIn(catalogue + ".kc.json", files, "the JSON form as well")

    @unittest.skipUnless(library_is_there(), "needs the kin5axc library")
    def test_every_one_of_them_opens_as_a_chain(self):
        """A model that ships and does not load is worse than one that is missing."""
        for name in sorted(os.listdir(CHAINS)):
            if not name.endswith((".kc", ".kc.json")):
                continue
            with kin5ax.Chain(os.path.join(CHAINS, name)) as chain:
                links = chain.links()
                self.assertEqual(kin5ax.AXES, len(links), name)
                turning = [l for l in links if l.is_revolute]
                self.assertEqual(2, len(turning), "%s: a five-axis machine has two rotary joints" % name)

    @unittest.skipUnless(FreeCAD is not None, "needs FreeCAD for the parameter store")
    def test_the_dialog_opens_on_them_until_a_machine_is_taken_from_somewhere_else(self):
        from kin5axcam import machine as machine_module

        parameters = FreeCAD.ParamGet(machine_module.PARAMETERS)
        before = parameters.GetString("LastMachineFolder", "")
        try:
            parameters.SetString("LastMachineFolder", "")
            self.assertEqual(os.path.realpath(CHAINS),
                             os.path.realpath(machine_module.machine_folder()),
                             "a fresh install opens on the machines it ships")

            elsewhere = tempfile.mkdtemp(prefix="kin5axcam_machines_")
            machine_module.remember_machine_folder(os.path.join(elsewhere, "mine.kc"))
            self.assertEqual(os.path.realpath(elsewhere),
                             os.path.realpath(machine_module.machine_folder()),
                             "and afterwards on wherever the last one came from")

            #a folder that has gone away falls back rather than opening nowhere
            os.rmdir(elsewhere)
            self.assertEqual(os.path.realpath(CHAINS),
                             os.path.realpath(machine_module.machine_folder()))
        finally:
            parameters.SetString("LastMachineFolder", before)


if __name__ == "__main__":
    unittest.main()


@needs_everything
class AMachineFromAFreeCadMachineFile(unittest.TestCase):
    """A machine in the document read from an .fcm: the unit, and the remarks a user has to see.

    FreeCAD 1.2 ships its machines as .fcm, so this is the file a FreeCAD user
    actually has. The conversion is lossy, and the one loss that matters here is
    the collision boxes: an .fcm has none, so the collision check of a simulation
    runs against nothing. A run that finds nothing looks exactly like a run that
    is safe, which is why the machine says so rather than leaving it to be noticed.
    """

    def setUp(self):
        import tempfile

        from kin5axcam import machine

        self.document = FreeCAD.newDocument("kin5axcam_fcm_machine")
        self.folder = tempfile.mkdtemp(prefix="kin5axcam_fcm_")
        self.fcm = os.path.join(self.folder, "machine.fcm")
        with kin5ax.Chain(CHAIN) as chain:
            chain.write_fcm(self.fcm)
        self.machine = machine.Create("FromFreeCad", self.fcm, document=self.document)
        self.document.recompute()

    def tearDown(self):
        import shutil

        FreeCAD.closeDocument(self.document.Name)
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_the_unit_is_millimetres_because_that_is_what_the_file_is(self):
        self.assertEqual(1.0, self.machine.UnitInMillimetres)

    def test_the_remarks_of_the_import_are_kept_on_the_machine(self):
        remarks = list(self.machine.FcmRemarks)
        self.assertTrue(remarks, "the file carries fields a kinematic chain has no place for")
        for line in remarks:
            self.assertNotEqual("", line.strip())

    def test_what_repeats_for_every_axis_is_said_once_to_the_user(self):
        """FreeCAD keeps a few scheduling fields on every axis and a chain has no place for any of
        them, so the bridge reports one drop per axis per field: eleven identical lines for an
        ordinary machine, which would push the remark that matters off the bottom of the box."""
        from kin5axcam import machine

        stored = list(self.machine.FcmRemarks)
        per_axis = [line for line in stored if "is not part of a kinematic chain" in line]
        self.assertGreater(len(per_axis), 3, "this file drops several fields on several axes")

        shown = machine.importRemarks(self.machine)
        summarised = [line for line in shown if "has no place for" in line]
        self.assertEqual(1, len(summarised), shown)
        self.assertIn("max_velocity", summarised[0])
        self.assertLess(len(shown), len(stored), "the full list stays on the machine")
        #and what is not a repeat is left exactly as the bridge said it
        self.assertTrue(any("collision boxes" in line for line in shown))

    def test_it_says_that_a_collision_check_against_it_would_find_nothing(self):
        from kin5axcam import machine

        with kin5ax.Chain.from_fcm(self.fcm) as chain:
            self.assertEqual(0, machine.collisionBoxCount(chain),
                             "an .fcm file has no room for collision boxes")
        lines = machine.importRemarks(self.machine)
        self.assertTrue(any("collision" in line for line in lines),
                        "nothing warned that the check would find nothing: %r" % lines)

    def test_a_machine_from_a_chain_of_kin5ax_says_none_of_this(self):
        from kin5axcam import machine

        plain = machine.Create("FromKin5ax", CHAIN, document=self.document)
        self.document.recompute()
        self.assertEqual([], list(plain.FcmRemarks))
        self.assertEqual([], machine.importRemarks(plain))
        with kin5ax.Chain(CHAIN) as chain:
            self.assertGreater(machine.collisionBoxCount(chain), 0, "the shipped models have boxes")

    def test_the_parts_of_the_machine_are_built_from_it_like_any_other(self):
        #a machine that has not been posed yet carries no configuration of its own; the proxy
        #answers with five zeros until one is set, as it does for a chain of kin5ax
        self.assertEqual(kin5ax.AXES, len(self.machine.Proxy.configuration(self.machine)))
        self.assertIsNotNone(self.machine.ToolMount)
        self.assertIsNotNone(self.machine.Material)
        self.machine.Configuration = [0.0] * kin5ax.AXES
        self.assertEqual(kin5ax.AXES, len(self.machine.Configuration))
