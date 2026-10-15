"""The ctypes binding: kin5ax answers from Python what it answers from C.

These need the shared library and a machine of the test set of the repository,
and skip when either is not there. What they check is the binding - that each
call gets through with its arguments the right way round and its answers whole -
against the forward kinematics, which is the one oracle a solver has: put the
machine somewhere, ask where the tool went, ask the solver to put it back there.
The arithmetic itself is tested in C++, next to the library.
"""

import math
import os
import unittest

from kin5axcam import kin5ax

#the real path: inside FreeCAD the addon may be reached through a junction from the Mod folder,
#and the machine models it ships sit next to where the files really are
HERE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CHAINS = os.path.join(HERE, "Resources", "machines")
#a trunnion table: A tilts, C turns the workpiece - the chain the ABI tests use
CHAIN = os.path.join(CHAINS, "AC_TiltRotaryTable.kc")


def library_is_there():
    try:
        kin5ax.load()
        return True
    except kin5ax.Kin5axError:
        return False


needs_library = unittest.skipUnless(library_is_there(), "the kin5axc shared library is not where the "
                                    "binding looks: %s" % ", ".join(kin5ax.library_candidates()))
needs_chain = unittest.skipUnless(os.path.isfile(CHAIN), "no test chain at %s" % CHAIN)


def a_tool():
    """The default tool of the application: a 16 mm ball nose with a shank and a holder, in metres."""
    return kin5ax.Tool(kin5ax.TOOL_BALL_NOSE, 0.016, 0.016, 0.064, 0.030, 0.050, 0.030)


def q_inside_limits(chain):
    """Joint values inside the limits, the rotary ones away from zero so the tool axis is oblique."""
    q = []
    rotary = 0
    for link in chain.links():
        d = 0.0
        if link.is_revolute:
            d = 0.3 if rotary == 0 else 0.5
            rotary += 1
        if link.constrained and not (link.minimum <= d <= link.maximum):
            d = 0.5 * (link.minimum + link.maximum)
        q.append(d)
    return q


def same_configuration(chain, a, b):
    """The same five joint values as the machine sees them: a rotary axis is itself a full turn on."""
    for link, x, y in zip(chain.links(), a, b):
        d = abs(x - y)
        if link.is_revolute:
            d = math.fmod(d, 2.0 * math.pi)
            d = min(d, 2.0 * math.pi - d)
        if d > 1e-9:
            return False
    return True


class FindingTheLibrary(unittest.TestCase):

    def test_the_places_it_looks_are_listed_and_the_addon_lib_folder_is_one_of_them(self):
        candidates = kin5ax.library_candidates()
        self.assertGreater(len(candidates), 1)
        shipped = os.path.join(kin5ax.addon_directory(), "lib", kin5ax.library_file_name())
        self.assertIn(shipped, candidates, candidates)

    def test_the_addon_ships_the_library_it_needs(self):
        """An installed addon compiles nothing, so the binary has to be in the repository. It is the
        one the binding loads here, unless a developer has pointed KIN5AXC_LIBRARY elsewhere."""
        shipped = os.path.join(kin5ax.addon_directory(), "lib", kin5ax.library_file_name())
        self.assertTrue(os.path.isfile(shipped),
                        "no %s in lib/, so an installed addon would find nothing" % shipped)

    def test_a_file_that_is_not_a_library_is_an_error_with_the_path_in_it(self):
        with self.assertRaises(kin5ax.Kin5axError) as caught:
            kin5ax.load(__file__)
        self.assertIn(os.path.basename(__file__), str(caught.exception))


@needs_library
class TheLibrary(unittest.TestCase):

    def test_it_says_which_version_it_is(self):
        major, minor, patch = kin5ax.version_numbers()
        self.assertEqual("%d.%d.%d" % (major, minor, patch), kin5ax.version())
        self.assertTrue(os.path.isfile(kin5ax.loaded_from()), kin5ax.loaded_from())

    def test_the_library_it_loads_is_the_one_this_binding_was_written_against(self):
        """The two halves ship together and can be installed apart: an old library found through
        KIN5AXC_LIBRARY would otherwise be read at the wrong offsets instead of reported."""
        major, minor, _ = kin5ax.version_numbers()
        self.assertEqual(kin5ax.REQUIRED_VERSION, (major, minor),
                         "the library here is %s" % kin5ax.version())

    def test_a_library_of_another_version_is_refused_with_a_message(self):
        """The check itself, against a library that says it is something else."""

        class Pretender(object):
            def __init__(self, major, minor, patch):
                self.numbers = (major, minor, patch)

            def k5_version(self, major, minor, patch):
                major._obj.value, minor._obj.value, patch._obj.value = self.numbers

        wanted_major, wanted_minor = kin5ax.REQUIRED_VERSION
        kin5ax._check_version(Pretender(wanted_major, wanted_minor, 99), "here")
        for other in ((wanted_major + 1, wanted_minor, 0), (wanted_major, wanted_minor + 1, 0)):
            with self.assertRaises(kin5ax.IncompatibleLibrary) as refused:
                kin5ax._check_version(Pretender(*other), "nowhere/libkin5axc.so")
            self.assertIn("nowhere/libkin5axc.so", str(refused.exception))
            self.assertIn(".".join(str(n) for n in other), str(refused.exception))
            self.assertEqual(other, refused.exception.found)

    def test_the_default_settings_are_the_ones_the_header_promises(self):
        settings = kin5ax.Settings.default()
        self.assertEqual(1, settings.check_limits)
        self.assertEqual(1, settings.check_collisions)
        self.assertEqual(1, settings.interpolate)
        self.assertEqual(kin5ax.START_MIN_ABS, settings.start_criterion)
        self.assertEqual(1, settings.start_count_from_tool)

    def test_a_file_that_is_not_a_chain_is_an_error_with_a_message(self):
        with self.assertRaises(kin5ax.Kin5axError) as caught:
            kin5ax.Chain(os.path.join(CHAINS, "there_is_no_such_machine.kc"))
        self.assertEqual(kin5ax.ERROR_FILE, caught.exception.status)
        self.assertNotEqual("", caught.exception.message)

    def test_a_tool_that_cannot_be_made_is_refused_with_the_reason(self):
        with self.assertRaises(kin5ax.Kin5axError) as caught:
            kin5ax.Tool(kin5ax.TOOL_BALL_NOSE, -0.016, 0.016, 0.064, 0.0, 0.0, 0.0)
        self.assertEqual(kin5ax.ERROR_ARGUMENT, caught.exception.status)
        with self.assertRaises(kin5ax.Kin5axError):
            kin5ax.Tool(42, 0.016, 0.016, 0.064, 0.0, 0.0, 0.0)


@needs_library
@needs_chain
class AMachine(unittest.TestCase):

    def setUp(self):
        self.chain = kin5ax.Chain(CHAIN)
        self.tool = a_tool()

    def tearDown(self):
        self.tool.close()
        self.chain.close()

    def test_it_says_what_unit_its_file_is_in(self):
        """Every chain file declares its unit, and the models shipped are metres: the caller
        multiplies by what the chain says rather than by a number it was told to assume."""
        self.assertEqual(kin5ax.UNIT_M, self.chain.unit())
        self.assertEqual("m", self.chain.unit_name())
        self.assertEqual(1000.0, self.chain.unit_in_mm())

    def test_it_is_a_five_axis_chain_of_three_linear_and_two_rotary_joints(self):
        self.assertTrue(self.chain.is_5c())
        links = self.chain.links()
        self.assertEqual(kin5ax.AXES, len(links))
        self.assertEqual(2, sum(1 for link in links if link.is_revolute))
        for link in links:
            self.assertNotEqual("", link.name)

    def test_the_first_rotary_axis_depends_on_which_end_one_walks_from(self):
        from_tool = self.chain.first_rotary_axis(kin5ax.PART_TOOL)
        from_part = self.chain.first_rotary_axis(kin5ax.PART_MATERIAL_HOLDER)
        self.assertNotEqual(from_tool, from_part)
        self.assertTrue(self.chain.links()[from_tool].is_revolute)
        self.assertTrue(self.chain.links()[from_part].is_revolute)

    def test_the_frames_of_the_tool_branch_end_at_a_tool_mount_that_is_somewhere(self):
        frames = self.chain.frames(kin5ax.PART_TOOL)
        self.assertGreater(len(frames), 0)
        for joint, output in frames:
            self.assertEqual(16, len(joint))
            self.assertEqual(16, len(output))
            self.assertEqual((0.0, 0.0, 0.0, 1.0), (output[3], output[7], output[11], output[15]))
            for start in (0, 4, 8):
                self.assertAlmostEqual(1.0, math.sqrt(sum(c * c for c in output[start:start + 3])),
                                       delta=1e-9, msg="a unit basis vector")
        mount = frames[-1][1]
        self.assertGreater(abs(mount[12]) + abs(mount[13]) + abs(mount[14]), 1e-6)

    def test_the_configuration_can_be_set_and_the_frames_follow(self):
        q = q_inside_limits(self.chain)
        self.chain.set_configuration(q)
        for link, value in zip(self.chain.links(), q):
            self.assertAlmostEqual(value, link.value, delta=1e-12)
        before = self.chain.frames(kin5ax.PART_TOOL)
        self.chain.set_configuration([value + 0.01 for value in q])
        self.assertNotEqual(before, self.chain.frames(kin5ax.PART_TOOL))
        with self.assertRaises(kin5ax.Kin5axError):
            self.chain.set_configuration([0.0, 0.0])

    def test_the_boxes_of_the_segments_come_with_the_minimum_corner_first(self):
        """The Reiden model carries one box on each terminal and none on its joints."""
        with kin5ax.Chain(os.path.join(CHAINS, "Reiden_RX10_A_SwivelHead_C_RotaryTable.kc.json")) as chain:
            total = 0
            for part in (kin5ax.PART_TOOL, kin5ax.PART_MATERIAL_HOLDER):
                frames = chain.frames(part)
                for index in range(len(frames)):
                    boxes = chain.segment_boxes(part, index)
                    for low, high in boxes:
                        for k in range(3):
                            self.assertLessEqual(low[k], high[k])
                    total += len(boxes)
                self.assertGreater(len(chain.segment_boxes(part, len(frames) - 1)), 0, "the terminal")
                with self.assertRaises(kin5ax.Kin5axError):
                    chain.segment_boxes(part, len(frames))
            self.assertEqual(2, total)

    def test_the_tool_is_as_long_as_its_parts(self):
        self.assertAlmostEqual(0.064 + 0.030 + 0.050, self.tool.assembly_length(), delta=1e-12)
        self.assertLess(self.tool.mount_to_point_distance(), self.tool.assembly_length(),
                        "the programmed point of a ball nose tool is above its tip")

    def test_the_solver_puts_the_machine_back_where_the_forward_kinematics_took_it_from(self):
        q = q_inside_limits(self.chain)
        position, axis = self.chain.tool_point(q, self.tool)
        self.assertAlmostEqual(1.0, math.sqrt(sum(c * c for c in axis)), delta=1e-9)

        configurations, status = self.chain.solve_location(position, axis, kin5ax.Settings.default(),
                                                           self.tool)
        self.assertGreater(len(configurations), 0, kin5ax.SOLVE_STATUS_NAMES.get(status))
        self.assertTrue(any(same_configuration(self.chain, q, c) for c in configurations),
                        "one of the configurations is the one the point was taken from: %r not among "
                        "%r" % (q, configurations))
        for c in configurations:
            back, back_axis = self.chain.tool_point(c, self.tool)
            for i in range(3):
                self.assertAlmostEqual(position[i], back[i], delta=1e-9)
                self.assertAlmostEqual(axis[i], back_axis[i], delta=1e-9)

    def test_a_point_nowhere_near_the_machine_has_no_solution_and_a_reason(self):
        configurations, status = self.chain.solve_location((1e3, 1e3, 1e3), (0.0, 0.0, 1.0),
                                                           kin5ax.Settings.default(), self.tool)
        self.assertEqual([], configurations)
        self.assertNotEqual(kin5ax.SOLVED, status)
        self.assertIn(status, kin5ax.SOLVE_STATUS_NAMES)

    def test_a_path_in_memory_is_solved_whole_with_its_steps_invented_between(self):
        q = q_inside_limits(self.chain)
        p, v = self.chain.tool_point(q, self.tool)
        positions = [(p[0] + 0.025 * i, p[1], p[2]) for i in range(3)]
        settings = kin5ax.Settings.default()
        with self.chain.postprocess_locations(positions, [v, v, v], settings, self.tool) as path:
            self.assertEqual(7, path.size(), "the first location, then two steps and a location, twice")
            self.assertEqual(3, path.count_of_origin(kin5ax.FROM_FILE))
            self.assertEqual(4, path.count_of_origin(kin5ax.INTERPOLATED))
            self.assertEqual({"solved": 7}, path.report())
            position_error, orientation_error = path.errors()
            self.assertLess(position_error, 1e-9)
            self.assertLess(orientation_error, 1e-9)
            seen = [location for location in path.locations()]
            self.assertEqual(7, len(seen))
            self.assertEqual([1, 1, 1, 2, 2, 2, 3], [l.file_location for l in seen])
            for location in seen:
                self.assertTrue(location.has_solution)
                self.assertEqual(kin5ax.AXES, len(location.q))
            self.assertEqual(seen[-1].q, path.last_configuration())
            #and every record says what it was solved for: a third of a step on from the one before
            for index, location in enumerate(seen):
                self.assertAlmostEqual(p[0] + 0.025 * index / 3.0, location.position[0], delta=1e-9,
                                       msg="record %d" % index)
                self.assertAlmostEqual(p[1], location.position[1], delta=1e-9)
                self.assertAlmostEqual(p[2], location.position[2], delta=1e-9)
                for k in range(3):
                    self.assertAlmostEqual(v[k], location.axis[k], delta=1e-6)

    def test_a_path_says_which_solids_met_and_at_how_many_locations(self):
        """The model of the spherical wrist meets itself when the tool leans far: the pair and the
        count are what a user can act on, where "it collides" leaves them nowhere."""
        wrist = os.path.join(CHAINS, "3CWithSphericalWrist_withBaseBox.kc")
        if not os.path.isfile(wrist):
            self.skipTest("no spherical wrist model in the test set")
        settings = kin5ax.Settings.default()
        settings.interpolate = 0
        positions = [(0.02 * i - 0.1, 0.0, 0.1) for i in range(12)]
        axes = [(math.sin(math.radians(8.0 * i)), 0.0, math.cos(math.radians(8.0 * i))) for i in range(12)]
        with kin5ax.Chain(wrist) as chain:
            with chain.postprocess_locations(positions, axes, settings, self.tool) as path:
                colliding = path.count_of_status(kin5ax.COLLISION)
                self.assertGreater(colliding, 0, "the far end of that path has to collide")
                pairs = path.collisions()
                self.assertGreater(len(pairs), 0, "and the path says which solids")
                self.assertEqual(sorted((p.locations for p in pairs), reverse=True),
                                 [p.locations for p in pairs], "most locations first")
                for pair in pairs:
                    self.assertNotEqual("", pair.first)
                    self.assertNotEqual(pair.first, pair.second)
                    self.assertLessEqual(pair.locations, colliding)
                    self.assertIn(pair.kind, kin5ax.COLLIDING_KIND_NAMES)
                    self.assertIn(pair.first, pair.describe())
                self.assertEqual(colliding, pairs[0].locations,
                                 "the pair that rejected every colliding location costs all of them")
            settings.check_collisions = 0
            with chain.postprocess_locations(positions, axes, settings, self.tool) as path:
                self.assertEqual([], path.collisions(), "nothing checked, nothing reported")

    def test_the_solution_of_the_last_location_is_where_the_machine_is_left(self):
        """Not necessarily the configuration the point was taken from: a point has two, and the
        trajectory picks the one its start criterion says. It puts the tool at the point either way."""
        q = q_inside_limits(self.chain)
        p, v = self.chain.tool_point(q, self.tool)
        settings = kin5ax.Settings.default()
        settings.interpolate = 0
        with self.chain.postprocess_locations([p], [v], settings, self.tool) as path:
            self.assertEqual(1, path.size())
            left = path.last_configuration()
            self.assertEqual(left, path.location(0).q)
            back, back_axis = self.chain.tool_point(left, self.tool)
            for i in range(3):
                self.assertAlmostEqual(p[i], back[i], delta=1e-9)
                self.assertAlmostEqual(v[i], back_axis[i], delta=1e-9)

    def test_an_empty_path_holds_nothing_and_is_not_an_error(self):
        with self.chain.postprocess_locations([], [], kin5ax.Settings.default(), self.tool) as path:
            self.assertEqual(0, path.size())
            self.assertIsNone(path.last_configuration())

    def test_an_axis_of_no_length_is_refused_with_the_number_of_the_location(self):
        q = q_inside_limits(self.chain)
        p, v = self.chain.tool_point(q, self.tool)
        with self.assertRaises(kin5ax.Kin5axError) as caught:
            self.chain.postprocess_locations([p, p], [v, (0.0, 0.0, 0.0)], kin5ax.Settings.default(),
                                             self.tool)
        self.assertEqual(kin5ax.ERROR_ARGUMENT, caught.exception.status)
        self.assertIn("2", caught.exception.message)

    def test_positions_and_axes_have_to_pair_up(self):
        with self.assertRaises(kin5ax.Kin5axError):
            self.chain.postprocess_locations([(0, 0, 0)], [], kin5ax.Settings.default(), self.tool)
        with self.assertRaises(kin5ax.Kin5axError):
            self.chain.postprocess_locations([(0, 0)], [(0, 0, 1)], kin5ax.Settings.default(), self.tool)

    def test_the_default_gcode_axes_name_the_five_joints_once_each(self):
        axes = self.chain.default_gcode_axes()
        self.assertEqual(5, len({axes.x, axes.y, axes.z, axes.angle1, axes.angle2}))
        links = self.chain.links()
        self.assertTrue(links[axes.angle1].is_revolute)
        self.assertTrue(links[axes.angle2].is_revolute)
        self.assertIn(axes.angle1_letter, "ABC")
        self.assertEqual(1, axes.degrees)
        axes.angle1_letter = "B"
        self.assertEqual("B", axes.angle1_letter)



@needs_library
@needs_chain
class TheCutting(unittest.TestCase):
    """A path across the top of a block, cut by the ball of the tool: the groove is where it went."""

    def setUp(self):
        self.chain = kin5ax.Chain(CHAIN)
        self.tool = a_tool()

    def tearDown(self):
        self.tool.close()
        self.chain.close()

    def test_a_block_is_whole_to_begin_with_and_its_surface_is_its_outside(self):
        with kin5ax.Material((0.1, 0.1, 0.05), 0.005, (-0.05, -0.05, 0.0)) as block:
            nx, ny, nz = block.dimensions()
            self.assertGreaterEqual(nx, 20)
            total, removed = block.volumes()
            self.assertGreater(total, 0.0)
            self.assertEqual(0.0, removed)
            surface = block.surface()
            self.assertGreater(len(surface), 0)
            self.assertLess(len(surface) // 3, nx * ny * nz, "the inside is not surface")
            self.assertEqual(0, len(surface) % 3)

    def test_the_exposed_faces_of_a_whole_block_are_its_outside(self):
        with kin5ax.Material((0.10, 0.05, 0.02), 0.01, (0.0, 0.0, 0.0)) as block:
            nx, ny, nz = block.dimensions()
            triangles = block.surface_triangles()
            self.assertEqual(18 * 2 * (nx * ny + ny * nz + nx * nz), len(triangles))
            for i in range(0, len(triangles), 3):
                self.assertGreaterEqual(triangles[i], -1e-12)
                self.assertLessEqual(triangles[i], nx * 0.01 + 1e-12)

    def test_one_stamp_of_the_tool_wherever_it_is_put(self):
        """What a host does for a location its simulation will not cut: put the tool there and stamp."""
        with kin5ax.Material((0.12, 0.06, 0.03), 0.002, (-0.06, -0.03, -0.03)) as block:
            self.assertEqual(0.0, block.volumes()[1])
            gouged, _ = block.cut(self.tool, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
            self.assertFalse(gouged, "the shank is above the block")
            after_one = block.volumes()[1]
            self.assertGreater(after_one, 0.0, "a bite out of it")
            block.cut(self.tool, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
            self.assertEqual(after_one, block.volumes()[1], "a voxel removed is removed")
            #a tool whose cutting part is 20 mm: the 64 mm one reaches out of a block 30 mm deep
            stubby = kin5ax.Tool(kin5ax.TOOL_BALL_NOSE, 0.016, 0.016, 0.020, 0.030, 0.050, 0.030)
            gouged, where = block.cut(stubby, (0.04, 0.0, -0.02), (0.0, 0.0, 1.0))
            stubby.close()
            self.assertTrue(gouged, "pushed in, its shank is in material still there")
            self.assertEqual(3, len(where))
            self.assertGreater(where[2], -0.03, "and the place of it is in the block")
            with self.assertRaises(kin5ax.Kin5axError):
                block.cut(self.tool, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    def test_a_block_that_cannot_be_made_is_refused(self):
        with self.assertRaises(kin5ax.Kin5axError):
            kin5ax.Material((0.0, 0.1, 0.05), 0.005, (0.0, 0.0, 0.0))
        with self.assertRaises(kin5ax.Kin5axError):
            kin5ax.Material((1.0, 1.0, 1.0), 1e-6, (0.0, 0.0, 0.0))

    def test_a_leaning_ball_cuts_with_no_machine_at_all(self):
        """The path as it is - points and axes - made dense by the library and cut: a groove one
        radius deep under it, since the lowest point of a ball does not care where the shank points."""
        radius = 0.016
        lean = math.radians(30.0)
        axis = (math.sin(lean), 0.0, math.cos(lean))
        settings = kin5ax.Settings.default()
        settings.max_position_difference = 0.002        #as dense as the voxels
        block = kin5ax.Material((0.12, 0.06, 0.03), 0.002, (-0.06, -0.03, -0.03))
        cutting = kin5ax.Simulation.from_locations(self.tool, settings, [(-0.04, 0.0, 0.0), (0.04, 0.0, 0.0)],
                                                   [axis, axis], block)
        index, count, finished = cutting.progress()
        self.assertEqual(41, count, "80 mm in 2 mm steps, and the first location")
        position, direction, source, invented = cutting.location(1)
        self.assertAlmostEqual(-0.038, position[0], delta=1e-9)
        self.assertAlmostEqual(axis[0], direction[0], delta=1e-9)
        self.assertEqual((0, True), (source, invented))
        self.assertEqual((1, False), cutting.location(40)[2:])
        self.assertEqual(41, len(list(cutting.locations())))
        with self.assertRaises(kin5ax.Kin5axError):
            cutting.location(41)

        cutting.run()
        self.assertTrue(cutting.progress()[2])
        surface = block.surface()
        under, beside = -1.0, -1.0
        for i in range(len(surface) // 3):
            x, y, z = surface[3 * i], surface[3 * i + 1], surface[3 * i + 2]
            if abs(x) > 0.03:
                continue
            if abs(y) < 0.001:
                under = max(under, z)
            if abs(y - 0.025) < 0.0015:
                beside = max(beside, z)
        self.assertLess(under, -0.5 * radius, "a groove under the path")
        self.assertGreater(under, -radius - 0.004, "one radius deep, lean or no lean")
        self.assertGreater(beside, -0.004, "and nothing taken off beside it")
        self.assertEqual(0, cutting.gouges()[0], "the shank leans away above the block")
        cutting.close()

        with self.assertRaises(kin5ax.Kin5axError) as caught:
            kin5ax.Simulation.from_locations(self.tool, settings, [(0, 0, 0), (1, 0, 0)],
                                             [(0, 0, 1), (0, 0, 0)], block)
        self.assertIn("2", caught.exception.message)
        empty = kin5ax.Simulation.from_locations(self.tool, settings, [], [], block)
        self.assertEqual((0, 0, True), empty.progress())
        empty.close()
        block.close()

    def test_the_locations_of_a_simulation_on_a_chain_are_its_tool_points(self):
        q = q_inside_limits(self.chain)
        p, v = self.chain.tool_point(q, self.tool)
        settings = kin5ax.Settings.default()
        settings.check_collisions = 0
        path = self.chain.postprocess_locations([p], [v], settings, self.tool)
        block = kin5ax.Material((0.1, 0.1, 0.05), 0.005, (-0.05, -0.05, -0.2))
        with kin5ax.Simulation(self.chain, self.tool, path, block) as cutting:
            position, axis, source, invented = cutting.location(0)
            for i in range(3):
                self.assertAlmostEqual(p[i], position[i], delta=1e-9)
                self.assertAlmostEqual(v[i], axis[i], delta=1e-9)
            self.assertEqual((0, False), (source, invented))
        block.close()
        path.close()

    def test_the_ball_cuts_a_groove_under_the_path_and_nowhere_else(self):
        radius = 0.016
        settings = kin5ax.Settings.default()
        settings.check_collisions = 0           #the block is not in the chain's model of itself
        #the ball centre on the top face of the block, so that the ball dips a radius into it
        positions = [(-0.04 + 0.02 * i, 0.0, 0.0) for i in range(5)]
        axes = [(0.0, 0.0, 1.0)] * 5
        path = self.chain.postprocess_locations(positions, axes, settings, self.tool)
        self.assertEqual(path.count_of_status(kin5ax.SOLVED), path.size(), path.report())
        block = kin5ax.Material((0.12, 0.06, 0.03), 0.002, (-0.06, -0.03, -0.03))
        with kin5ax.Simulation(self.chain, self.tool, path, block) as cutting:
            index, count, finished = cutting.progress()
            self.assertEqual((0, path.size(), False), (index, count, finished))
            self.assertTrue(cutting.step())
            total, after_one = block.volumes()
            self.assertGreater(after_one, 0.0, "the ball took a bite")
            cutting.run()
            self.assertEqual((count, count, True), cutting.progress())
            total, removed = block.volumes()
            self.assertGreater(removed, after_one)
            self.assertLess(removed, total)
            #the top of what is left: under the path the floor of the groove, beside it the block
            surface = block.surface()
            under, beside = -1.0, -1.0
            for i in range(len(surface) // 3):
                x, y, z = surface[3 * i], surface[3 * i + 1], surface[3 * i + 2]
                if abs(x) > 0.03:
                    continue
                if abs(y) < 0.001:
                    under = max(under, z)
                if abs(y - 0.025) < 0.0015:
                    beside = max(beside, z)
            self.assertLess(under, -0.5 * radius, "a groove under the path")
            self.assertGreater(under, -radius - 0.004, "no deeper than the ball reaches, to a voxel")
            self.assertGreater(beside, -0.004, "and nothing taken off beside it")
            self.assertEqual(0, cutting.gouges()[0], "the shank stayed above the block")
            self.assertFalse(cutting.step(), "nothing past the end")
            cutting.reset()
            self.assertEqual(0, cutting.progress()[0])
        block.reset()
        self.assertEqual(0.0, block.volumes()[1], "whole again")
        block.close()
        path.close()


if __name__ == "__main__":
    unittest.main()


@needs_library
@needs_chain
class TheFreeCadMachineFileBridge(unittest.TestCase):
    """kin5axfcm.h through the binding: a FreeCAD machine file in, a chain out, and the remarks.

    The conversion itself is tested in C++. What is tested here is that a host can
    reach it and, above all, can read what it could not carry: a bridge whose
    remarks never arrive is a bridge that converts silently, and what it drops is
    the difference between the machine in the file and the machine being solved for.
    """

    def setUp(self):
        import tempfile

        self.folder = tempfile.mkdtemp(prefix="kin5axcam_fcm_")
        self.written = os.path.join(self.folder, "written.fcm")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.folder, ignore_errors=True)

    def a_machine_file(self):
        """One written by the bridge itself, from the trunnion table of the test set."""
        with kin5ax.Chain(CHAIN) as chain:
            chain.write_fcm(self.written)
            return chain.fcm_remarks()

    def test_writing_one_says_what_it_could_not_carry(self):
        remarks = self.a_machine_file()
        self.assertTrue(os.path.isfile(self.written))
        self.assertTrue(remarks, "an .fcm holds no collision boxes and this said nothing")
        joined = " ".join(remarks)
        self.assertIn("collision boxes", joined)
        self.assertIn("tool reference point", joined,
                      "the tool terminal does not survive and has to be said")

    def test_reading_one_gives_a_chain_in_millimetres(self):
        self.a_machine_file()
        chain = kin5ax.Chain.from_fcm(self.written)
        try:
            self.assertEqual(kin5ax.UNIT_MM, chain.unit(), "an .fcm is millimetres by definition")
            self.assertEqual(1.0, chain.unit_in_mm())
            self.assertTrue(chain.is_5c())
            self.assertEqual(kin5ax.AXES, len(chain.links()))
        finally:
            chain.close()

    def test_the_remarks_of_reading_are_the_remarks_of_the_last_conversion(self):
        self.a_machine_file()
        chain = kin5ax.Chain.from_fcm(self.written)
        try:
            reading = chain.fcm_remarks()
            self.assertNotIn("collision boxes", " ".join(reading),
                             "those belonged to writing the file, not to reading it")
            #the fields FreeCAD keeps that a kinematic chain has no place for
            self.assertTrue(reading, "the file carries max_velocity and the rest, and they are dropped")
        finally:
            chain.close()

    def test_a_chain_of_kin5ax_carries_no_remarks(self):
        with kin5ax.Chain(CHAIN) as chain:
            self.assertEqual([], chain.fcm_remarks(), "it has been through no conversion")

    def test_the_conventions_a_machine_file_cannot_state_reach_the_conversion(self):
        """Which way a table axis is counted is not in the file and cannot be guessed; set wrong,
        a part comes out mirrored, so the option has to be reachable from here."""
        self.a_machine_file()
        options = kin5ax.FcmOptions.default()
        self.assertEqual(0, options.negate_table_rotary_axes)
        options.negate_table_rotary_axes = 1
        plain = kin5ax.Chain.from_fcm(self.written)
        negated = kin5ax.Chain.from_fcm(self.written, options)
        try:
            q = [0.5 if link.is_revolute else 0.0 for link in plain.links()]
            a, _ = plain.tool_point(q)
            b, _ = negated.tool_point(q)
            apart = sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5
            self.assertGreater(apart, 1e-9, "the same joint values put the tool in the same place")
        finally:
            plain.close()
            negated.close()

    def test_a_file_that_is_not_a_machine_is_refused_with_a_message(self):
        with self.assertRaises(kin5ax.Kin5axError) as caught:
            kin5ax.Chain.from_fcm(os.path.join(self.folder, "there_is_no_such_machine.fcm"))
        self.assertNotEqual("", caught.exception.message)


@needs_library
class TheHolderOfAToolModel(unittest.TestCase):
    """What the addon builds a tool out of: the bit's dimensions and the holder nobody measured.

    A designation the catalogue knows brings three cylinders with it, and then
    the holder length of the model is what they add up to rather than whatever a
    property was left at. Everything here is in millimetres, and the catalogue
    is in metres.
    """

    def test_a_named_holder_brings_its_cylinders_in_millimetres(self):
        from kin5axcam import solve

        model, metres = kin5ax.holder_catalogue()[0]
        millimetres = solve.catalogue_holder_mm(model)
        self.assertEqual([(1000.0 * length, 1000.0 * radius) for length, radius in metres],
                         millimetres)
        self.assertIsNone(solve.catalogue_holder_mm("no such holder"))
        self.assertIsNone(solve.catalogue_holder_mm(""))

    def test_a_named_holder_decides_the_length_of_the_assembly(self):
        from kin5axcam import solve

        model_name, sections = kin5ax.holder_catalogue()[0]
        holder_mm = 1000.0 * sum(length for length, _ in sections)
        tool = solve.ToolModel(kin5ax.TOOL_FLAT_END, 6.0, 30.0, 20.0, 50.0, 30.0,
                               holder_model=model_name)
        self.assertAlmostEqual(holder_mm, tool.holder_length_mm, delta=1e-9,
                               msg="the holder that was named, not the property it replaces")
        self.assertEqual(len(sections), len(tool.holder_sections_mm))
        self.assertAlmostEqual(30.0 + 20.0 + holder_mm, tool.assembly_length_mm, delta=1e-9)

    def test_a_name_the_catalogue_has_not_leaves_the_single_cylinder(self):
        from kin5axcam import solve

        tool = solve.ToolModel(kin5ax.TOOL_FLAT_END, 6.0, 30.0, 20.0, 50.0, 30.0,
                               holder_model="the one in the second drawer")
        self.assertEqual([(50.0, 30.0)], tool.holder_sections_mm)
        self.assertAlmostEqual(30.0 + 20.0 + 50.0, tool.assembly_length_mm, delta=1e-9)

    def test_the_cylinders_reach_the_library(self):
        """The whole point of naming one: a collision check on the shape of that holder."""
        from kin5axcam import solve

        model_name, sections = kin5ax.holder_catalogue()[0]
        model = solve.ToolModel(kin5ax.TOOL_FLAT_END, 6.0, 30.0, 20.0, 0.0, 0.0,
                                holder_model=model_name)
        tool = model.to_kin5ax(1000.0)
        try:
            self.assertAlmostEqual((30.0 + 20.0 + model.holder_length_mm) / 1000.0,
                                   tool.gauge_length(), delta=1e-12)
        finally:
            tool.close()


def vice_frame(lift=80.0, quarter_turn=True):
    """A vice that holds the part `lift` above the table, its jaws a quarter turn about OZ.

    16 doubles in the layout of Chain.frames(): the rows are the images of the
    axes and the last row is the origin.
    """
    m = [0.0] * 16
    if quarter_turn:
        m[1], m[4] = 1.0, -1.0              #OX of the part along the OY of the table
    else:
        m[0], m[5] = 1.0, 1.0
    m[10] = 1.0
    m[14] = lift
    m[15] = 1.0
    return tuple(m)


@needs_library
@needs_chain
class TheWorkpieceHolder(unittest.TestCase):
    """The vice: where the frame the moves are given in sits on the table of the machine.

    It is the mirror image of the gauge length of a tool. A cutter location says
    nothing about where the part is held, so the holder is what the machine has
    to know, and everything the library answers about a location is in the frame
    of the part either way.
    """

    def setUp(self):
        self.chain = kin5ax.Chain(CHAIN)
        self.tool = kin5ax.Tool(kin5ax.TOOL_BALL_NOSE, 0.016, 0.016, 0.064, 0.030, 0.050, 0.030)

    def tearDown(self):
        self.tool.close()
        self.chain.close()

    def test_a_chain_starts_with_the_part_on_the_table(self):
        identity = tuple(1.0 if i % 5 == 0 else 0.0 for i in range(16))
        self.assertEqual(identity, self.chain.workpiece_holder())
        self.chain.set_workpiece_holder(None)
        self.assertEqual(identity, self.chain.workpiece_holder(), "None is the identity")

    def test_the_holder_comes_back_as_it_was_given(self):
        frame = vice_frame(lift=0.08)
        self.chain.set_workpiece_holder(frame)
        for given, back in zip(frame, self.chain.workpiece_holder()):
            self.assertAlmostEqual(given, back, delta=1e-12)

    def test_a_frame_that_scales_is_no_way_of_holding_anything(self):
        frame = list(vice_frame(lift=0.08, quarter_turn=False))
        frame[0] = 2.0
        with self.assertRaises(kin5ax.Kin5axError) as caught:
            self.chain.set_workpiece_holder(frame)
        self.assertIn("rigid", caught.exception.message)

    def test_lifting_the_part_lowers_what_the_machine_reports(self):
        q = q_inside_limits(self.chain)
        on_the_table, axis = self.chain.tool_point(q, self.tool)
        self.chain.set_workpiece_holder(vice_frame(lift=0.08, quarter_turn=False))
        in_the_vice, turned = self.chain.tool_point(q, self.tool)
        self.assertAlmostEqual(on_the_table[0], in_the_vice[0], delta=1e-12)
        self.assertAlmostEqual(on_the_table[1], in_the_vice[1], delta=1e-12)
        self.assertAlmostEqual(on_the_table[2] - 0.08, in_the_vice[2], delta=1e-12,
                               msg="the part came up to meet the tool")
        for i in range(3):
            self.assertAlmostEqual(axis[i], turned[i], delta=1e-12, msg="a lift turns nothing")

    def test_a_location_is_solved_in_the_frame_of_the_part(self):
        """The whole point: the moves are the part's, and where it is held is the machine's."""
        q = q_inside_limits(self.chain)
        target, axis = self.chain.tool_point(q, self.tool)
        self.chain.set_workpiece_holder(vice_frame(lift=0.08))
        settings = kin5ax.Settings.default()
        settings.check_collisions = 0        #the holder meets the head boxes of the models
        solutions, status = self.chain.solve_location(target, axis, settings, self.tool)
        self.assertTrue(solutions, "the location is reachable with the part on a vice too")
        for solution in solutions:
            back, back_axis = self.chain.tool_point(solution, self.tool)
            for i in range(3):
                self.assertAlmostEqual(target[i], back[i], delta=1e-9)
                self.assertAlmostEqual(axis[i], back_axis[i], delta=1e-9)
            self.assertGreater(sum(abs(solution[i] - q[i]) for i in range(len(q))), 1e-6,
                               "the machine stands somewhere else than it did without the vice")


@needs_library
class TheWorkpieceHolderOfTheOptions(unittest.TestCase):
    """The addon works in millimetres and the chain in its own unit: the holder is scaled once."""

    def test_only_the_translation_is_a_length(self):
        from kin5axcam import solve

        frame = vice_frame(lift=80.0)
        options = solve.Options(unit_in_mm=1000.0, workpiece_holder_mm=frame)
        scaled = options.workpiece_holder()
        self.assertAlmostEqual(0.08, scaled[14], delta=1e-12)
        for i in range(12):
            self.assertAlmostEqual(frame[i], scaled[i], delta=1e-12, msg="a turn has no unit")

    def test_no_holder_stays_no_holder(self):
        from kin5axcam import solve

        self.assertIsNone(solve.Options().workpiece_holder())

    def test_a_holder_of_the_wrong_size_is_refused_where_it_is_given(self):
        from kin5axcam import solve

        with self.assertRaises(ValueError):
            solve.Options(workpiece_holder_mm=(1.0, 2.0, 3.0))


@needs_library
class TheCatalogueOfToolHolders(unittest.TestCase):
    """The holders a five-axis machine usually carries, so that one can be picked from a list.

    A host matches what a machine file names against the holders it has of its
    own; this list is what it offers when it has none. The sizes are in metres,
    whatever unit the chain is in.
    """

    def test_it_holds_named_holders_of_plausible_size(self):
        holders = kin5ax.holder_catalogue()
        self.assertGreaterEqual(len(holders), 5)
        for model, sections in holders:
            self.assertNotEqual("", model)
            self.assertGreaterEqual(len(sections), 1)
            self.assertLessEqual(len(sections), kin5ax.HOLDER_SECTIONS)
            length = sum(section[0] for section in sections)
            self.assertGreater(length, 0.02, "%s is shorter than any holder" % model)
            self.assertLess(length, 0.30, "%s is longer than any holder" % model)
            for one_length, radius in sections:
                self.assertGreater(one_length, 0.0)
                self.assertGreater(radius, 0.0)

    def test_a_holder_is_found_by_its_designation_exactly(self):
        model, sections = kin5ax.holder_catalogue()[0]
        self.assertEqual(sections, kin5ax.holder_by_model(model))
        self.assertIsNone(kin5ax.holder_by_model(model.lower()),
                          "guessing at a spelling would put the wrong holder on the machine")
        self.assertIsNone(kin5ax.holder_by_model("no such holder"))


@needs_library
@needs_chain
class TheHolderAMachineFileNames(unittest.TestCase):
    """What the chain says its machine usually carries: a default to offer, and nothing more.

    The end of the tool branch is the tool mount whether a holder is named or
    not, and the tip of the tool reaches the gauge length below it either way.
    """

    def test_a_machine_of_the_catalogue_names_its_holder_and_its_cylinders(self):
        chain = kin5ax.Chain(os.path.join(
            CHAINS, "Mazak_VTC800-30SR_B_SwivelHead_C_RotaryTable.kc"))
        try:
            model = chain.default_holder_model()
            self.assertNotEqual("", model)
            sections = chain.default_holder()
            self.assertEqual(sections, kin5ax.holder_by_model(model),
                             "the file and the catalogue agree on the holder of that name")
        finally:
            chain.close()

    def test_a_holder_of_the_catalogue_goes_onto_a_tool(self):
        """What a host does with the list: the holder it picked becomes the tool's."""
        sections = kin5ax.holder_by_model(kin5ax.holder_catalogue()[0][0])
        tool = kin5ax.Tool(kin5ax.TOOL_FLAT_END, 0.006, 0.0, 0.030, 0.020, 0.0, 0.0)
        try:
            tool.set_holder(sections)
            holder = sum(length for length, _ in sections)
            self.assertAlmostEqual(0.030 + 0.020 + holder, tool.gauge_length(), delta=1e-12)
        finally:
            tool.close()

    def test_a_measured_tool_does_not_move_when_its_holder_changes(self):
        tool = kin5ax.Tool(kin5ax.TOOL_FLAT_END, 0.006, 0.0, 0.030, 0.020, 0.050, 0.030, 0.200)
        try:
            tool.set_holder(kin5ax.holder_by_model(kin5ax.holder_catalogue()[0][0]))
            self.assertAlmostEqual(0.200, tool.gauge_length(), delta=1e-12,
                                   msg="that is what measuring a tool is for")
        finally:
            tool.close()

    def test_more_cylinders_than_a_holder_has_are_refused(self):
        tool = kin5ax.Tool(kin5ax.TOOL_FLAT_END, 0.006, 0.0, 0.030, 0.020, 0.0, 0.0)
        try:
            with self.assertRaises(ValueError):
                tool.set_holder([(0.01, 0.02)] * (kin5ax.HOLDER_SECTIONS + 1))
        finally:
            tool.close()


@needs_library
@needs_chain
class TheGaugeLengthOfATool(unittest.TestCase):
    """The tool length a control is set with: from the tip to where the holder is clamped.

    A machine's tool branch ends at the place a holder is clamped, the same place
    for every tool it ever holds, so how far the tip reaches below it belongs to
    what is in the spindle and not to the chain. That is the measurement a
    presetter gives and a control is set with, and it is why the same dimensions
    can sit at two different heights.
    """

    def setUp(self):
        self.chain = kin5ax.Chain(CHAIN)

    def tearDown(self):
        self.chain.close()

    def test_a_tool_says_the_length_it_was_made_with(self):
        tool = kin5ax.Tool(kin5ax.TOOL_BALL_NOSE, 0.016, 0.016, 0.064, 0.030, 0.050, 0.030, 0.250)
        try:
            self.assertAlmostEqual(0.250, tool.gauge_length(), delta=1e-12)
            self.assertAlmostEqual(0.250, tool.assembly_length(), delta=1e-12)
            self.assertAlmostEqual(0.250 - 0.016, tool.mount_to_point_distance(), delta=1e-12,
                                   msg="the ball centre hangs one radius above the tip")
        finally:
            tool.close()

    def test_not_given_is_the_tool_standing_against_its_holder(self):
        """What every caller meant before the length existed, and what a tool bit that does not
        carry one implies."""
        tool = kin5ax.Tool(kin5ax.TOOL_BALL_NOSE, 0.016, 0.016, 0.064, 0.030, 0.050, 0.030)
        try:
            self.assertAlmostEqual(0.064 + 0.030 + 0.050, tool.gauge_length(), delta=1e-12)
        finally:
            tool.close()

    def test_two_tools_of_the_same_solids_reach_their_difference_apart(self):
        short = kin5ax.Tool(kin5ax.TOOL_BALL_NOSE, 0.016, 0.016, 0.064, 0.030, 0.050, 0.030, 0.150)
        long_one = kin5ax.Tool(kin5ax.TOOL_BALL_NOSE, 0.016, 0.016, 0.064, 0.030, 0.050, 0.030, 0.250)
        try:
            q = q_inside_limits(self.chain)
            a, _ = self.chain.tool_point(q, short)
            b, _ = self.chain.tool_point(q, long_one)
            apart = sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5
            self.assertAlmostEqual(0.100, apart, delta=1e-12,
                                   msg="the longer tool reaches exactly its extra length further")
        finally:
            short.close()
            long_one.close()
