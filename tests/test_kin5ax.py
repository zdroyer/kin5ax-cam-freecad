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

#the real path: inside FreeCAD the addon is reached through a junction from the Mod folder, and the
#test chains of the repository sit next to where the files really are
HERE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CHAINS = os.path.join(os.path.dirname(HERE), "kin5axTests", "TestChains")
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
        self.assertTrue(any(os.path.join("kin5axcam", "lib") in c for c in candidates), candidates)

    def test_a_file_that_is_not_a_library_is_an_error_with_the_path_in_it(self):
        with self.assertRaises(kin5ax.Kin5axError) as caught:
            kin5ax.load(__file__)
        self.assertIn(os.path.basename(__file__), str(caught.exception))


@needs_library
class TheLibrary(unittest.TestCase):

    def test_it_says_which_version_it_is(self):
        self.assertTrue(kin5ax.version().startswith("1"), kin5ax.version())

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


if __name__ == "__main__":
    unittest.main()
