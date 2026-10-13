"""The zigzag, the lean of the tool and its tip, against surfaces whose answers are known on paper.

Nothing here imports FreeCAD: the generator asks a surface four things and these
surfaces answer them, so the geometry is checked without a CAD kernel in the way.
"""

import math
import unittest

from kin5axcam import pathgen


class Plane(object):
    """The z = 0 plane, u and v the x and y of the point, the normal standing up."""

    ParameterRange = (0.0, 100.0, 0.0, 50.0)

    def valueAt(self, u, v):
        return (u, v, 0.0)

    def normalAt(self, u, v):
        return (0.0, 0.0, 1.0)

    def isPartOfDomain(self, u, v):
        return True


class HoleInThePlane(Plane):
    """The same plane with a band taken out of it, the way a trimmed face has a hole."""

    def __init__(self, hole_from=40.0, hole_to=60.0):
        self.hole_from = hole_from
        self.hole_to = hole_to

    def isPartOfDomain(self, u, v):
        return not (self.hole_from <= u <= self.hole_to)


class Sphere(object):
    """A sphere about the origin, parametrised like the sphere of Part: u around, v up."""

    def __init__(self, radius=10.0):
        self.radius = radius
        self.ParameterRange = (0.0, 2.0 * math.pi, -0.5 * math.pi, 0.5 * math.pi)

    def valueAt(self, u, v):
        return (self.radius * math.cos(v) * math.cos(u),
                self.radius * math.cos(v) * math.sin(u),
                self.radius * math.sin(v))

    def normalAt(self, u, v):
        p = self.valueAt(u, v)
        return (p[0] / self.radius, p[1] / self.radius, p[2] / self.radius)

    def isPartOfDomain(self, u, v):
        return True


class Vector(object):
    """What FreeCAD hands back: an object with x, y and z rather than a sequence."""

    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z


class PlaneOfVectors(Plane):
    def valueAt(self, u, v):
        return Vector(u, v, 0.0)

    def normalAt(self, u, v):
        return Vector(0.0, 0.0, 1.0)


class PlaneWithACrease(Plane):
    """A surface with no normal in the middle of it, the way a degenerate point has none."""

    def normalAt(self, u, v):
        if 40.0 <= u <= 60.0:
            return (0.0, 0.0, 0.0)
        return (0.0, 0.0, 1.0)


class PlaneWithoutADomain(object):
    """A surface that does not answer isPartOfDomain at all: everything counts as inside."""

    ParameterRange = (0.0, 10.0, 0.0, 10.0)

    def valueAt(self, u, v):
        return (u, v, 0.0)

    def normalAt(self, u, v):
        return (0.0, 0.0, 1.0)


def parameters(**kwargs):
    kwargs.setdefault("tip_radius", 3.0)
    kwargs.setdefault("rows", 3)
    kwargs.setdefault("points_per_row", 5)
    return pathgen.ZigZagParameters(**kwargs)


def ball_centre(location, tip_radius):
    """Where the sphere at the end of the tool is: a tip radius up the axis from the tip."""
    return tuple(location.point[i] + tip_radius * location.axis[i] for i in range(3))


def length(v):
    return math.sqrt(sum(c * c for c in v))


class ThePointOfThePathIsTheTip(unittest.TestCase):
    """What the commands carry, and the sphere at the end of the tool it is worked out from."""

    def test_on_a_flat_face_the_tip_sits_on_the_surface(self):
        """Whatever the radius: the face is level, so the ball touches it straight underneath."""
        for radius in (0.0, 3.0, 25.0):
            passes = pathgen.generate_passes(Plane(), parameters(tip_radius=radius))
            self.assertEqual(3, len(passes))
            for one in passes:
                self.assertEqual(5, len(one))
                for location in one:
                    self.assertAlmostEqual(0.0, location.point[2], delta=1e-12,
                                           msg="a tip radius of %r" % radius)
                    self.assertEqual(location.point[0], location.surface_point[0])
                    self.assertEqual(location.point[1], location.surface_point[1])
                    self.assertEqual(pathgen.VERTICAL_AXIS, location.axis)

    def test_a_tool_with_nothing_round_about_it_puts_its_tip_on_the_surface_point(self):
        """An end mill, a V bit, a drill: a tip radius of zero, and no offset to make."""
        surface = Sphere(radius=10.0)
        passes = pathgen.generate_passes(surface, parameters(tip_radius=0.0, rows=5, points_per_row=9))
        self.assertEqual(5, len(passes))
        for one in passes:
            for location in one:
                self.assertEqual(location.surface_point, location.point)

    def test_the_ball_of_the_tool_touches_the_surface_where_the_point_came_from(self):
        """The invariant the offset is for, on a face that curves away in both parameters.

        The ball is one radius from the surface point, and on the outside of the
        sphere rather than inside it, which is to say along the normal.
        """
        radius = 2.5
        surface = Sphere(radius=10.0)
        passes = pathgen.generate_passes(surface,
                                         parameters(tip_radius=radius, rows=7, points_per_row=13))
        self.assertEqual(7, len(passes))
        for one in passes:
            for location in one:
                centre = ball_centre(location, radius)
                self.assertAlmostEqual(12.5, length(centre), delta=1e-12,
                                       msg="a ball of 2.5 rides on a sphere of 10 + 2.5")
                touch = [centre[i] - location.surface_point[i] for i in range(3)]
                self.assertAlmostEqual(radius, length(touch), delta=1e-12,
                                       msg="the ball touches the surface")
                for i in range(3):
                    self.assertAlmostEqual(radius * location.normal[i], touch[i], delta=1e-12,
                                           msg="and touches it along the normal")

    def test_the_normal_can_be_turned_round(self):
        surface = Sphere(radius=10.0)
        passes = pathgen.generate_passes(surface, parameters(tip_radius=2.5, flip_normal=True))
        for one in passes:
            for location in one:
                #the tool goes inside the sphere now, so its ball rides on one of 10 - 2.5
                self.assertAlmostEqual(7.5, length(ball_centre(location, 2.5)), delta=1e-12)

    def test_a_point_of_the_surface_can_be_a_vector_object(self):
        passes = pathgen.generate_passes(PlaneOfVectors(), parameters())
        self.assertEqual(3, len(passes))
        self.assertAlmostEqual(0.0, passes[0][0].point[2], delta=1e-12)


class Slope(Plane):
    """A plane leaning 45 degrees about the y axis: z rises with u, and so does the normal."""

    def valueAt(self, u, v):
        return (u / math.sqrt(2.0), v, u / math.sqrt(2.0))

    def normalAt(self, u, v):
        return (-1.0 / math.sqrt(2.0), 0.0, 1.0 / math.sqrt(2.0))


class TheLeanOfTheTool(unittest.TestCase):
    """The two angles: how far the tool leans from the normal, and which way it leans.

    A plane is enough for the arithmetic, its normal being the same everywhere
    and the passes running along x: the frame the lean is measured in is then the
    travel (1, 0, 0), the side of it (0, 1, 0) and the normal (0, 0, 1).
    """

    def leaning(self, **kwargs):
        kwargs.setdefault("axis_mode", pathgen.AXIS_NORMAL)
        kwargs.setdefault("rows", 2)
        kwargs.setdefault("points_per_row", 3)
        return pathgen.generate_passes(Plane(), parameters(**kwargs))

    def assertDirection(self, expected, got, msg=None):
        for i in range(3):
            self.assertAlmostEqual(expected[i], got[i], delta=1e-12, msg=msg)

    def test_without_a_lean_the_tool_points_along_the_normal(self):
        """Which puts the tip on the contact point: the ball touches the surface under its middle."""
        surface = Sphere(radius=10.0)
        passes = pathgen.generate_passes(surface, parameters(axis_mode=pathgen.AXIS_NORMAL,
                                                             rows=5, points_per_row=9))
        self.assertEqual(5, len(passes))
        for one in passes:
            for location in one:
                self.assertDirection(location.normal, location.axis)
                self.assertDirection(location.surface_point, location.point)

    def test_a_lean_of_no_rotation_leans_the_tool_the_way_it_travels(self):
        """A lead angle. The first pass runs along +u, so the tool leans into +x."""
        passes = self.leaning(lean_angle=30.0)
        for location in passes[0]:
            self.assertDirection((0.5, 0.0, math.sqrt(3.0) / 2.0), location.axis)

    def test_the_lean_follows_the_way_the_pass_runs_rather_than_the_parameter(self):
        """There and back: the second pass travels the other way, so the lead angle turns with it."""
        passes = self.leaning(lean_angle=30.0, zigzag=True)
        self.assertEqual([0.0, 50.0, 100.0], [l.u for l in passes[0]])
        self.assertEqual([100.0, 50.0, 0.0], [l.u for l in passes[1]])
        for location in passes[1]:
            self.assertDirection((-0.5, 0.0, math.sqrt(3.0) / 2.0), location.axis)

    def test_a_rotation_of_ninety_degrees_leans_the_tool_to_the_side(self):
        """A tilt angle: round the normal from the travel, which puts it along +y here."""
        passes = self.leaning(lean_angle=30.0, lean_rotation=90.0)
        for location in passes[0]:
            self.assertDirection((0.0, 0.5, math.sqrt(3.0) / 2.0), location.axis)

    def test_the_rotation_goes_all_the_way_round(self):
        for rotation, expected in ((0.0, (0.5, 0.0)),
                                   (90.0, (0.0, 0.5)),
                                   (180.0, (-0.5, 0.0)),
                                   (270.0, (0.0, -0.5)),
                                   (-90.0, (0.0, -0.5))):
            location = self.leaning(lean_angle=30.0, lean_rotation=rotation)[0][0]
            self.assertDirection((expected[0], expected[1], math.sqrt(3.0) / 2.0), location.axis,
                                 msg="a rotation of %r" % rotation)

    def test_the_lean_is_from_the_normal_and_not_from_the_vertical(self):
        """On a face leaning 45 degrees, a lean of 45 along the travel stands the tool up."""
        passes = pathgen.generate_passes(
            Slope(), parameters(axis_mode=pathgen.AXIS_NORMAL, rows=1, points_per_row=3,
                                lean_angle=45.0, tip_radius=3.0))
        for location in passes[0]:
            self.assertDirection(pathgen.VERTICAL_AXIS, location.axis,
                                 msg="the normal leans 45 one way and the lean takes it back")

    def test_the_ball_touches_the_contact_point_however_the_tool_leans(self):
        """What the tip is worked out for, on a face that curves away in both parameters.

        The ball of the tool is one radius from the contact point, in the
        direction of the normal, whatever the axis of the tool does - that is the
        whole of the arithmetic, and it is what a leaning tool must not break.
        """
        radius = 2.5
        surface = Sphere(radius=10.0)
        for lean, rotation in ((0.0, 0.0), (20.0, 35.0), (-15.0, 190.0), (60.0, 270.0)):
            passes = pathgen.generate_passes(
                surface, parameters(tip_radius=radius, rows=5, points_per_row=9,
                                    axis_mode=pathgen.AXIS_NORMAL,
                                    lean_angle=lean, lean_rotation=rotation))
            for one in passes:
                for location in one:
                    self.assertAlmostEqual(1.0, length(location.axis), delta=1e-12,
                                           msg="the axis of the tool is a unit vector")
                    centre = ball_centre(location, radius)
                    touch = [centre[i] - location.surface_point[i] for i in range(3)]
                    self.assertAlmostEqual(radius, length(touch), delta=1e-12,
                                           msg="a lean of %r towards %r" % (lean, rotation))
                    for i in range(3):
                        self.assertAlmostEqual(radius * location.normal[i], touch[i], delta=1e-12,
                                               msg="a lean of %r towards %r" % (lean, rotation))

    def test_a_tool_with_no_ball_stays_on_the_contact_point_whatever_it_does(self):
        """A tip radius of zero has nothing to offset, so the lean moves the tool and not the tip."""
        passes = self.leaning(tip_radius=0.0, lean_angle=30.0, lean_rotation=45.0)
        for one in passes:
            for location in one:
                self.assertEqual(location.surface_point, location.point)

    def test_turning_the_path_round_leans_the_tool_again(self):
        """start_near reverses the travel, and a lead angle that stayed put would drag backwards."""
        params = parameters(axis_mode=pathgen.AXIS_NORMAL, rows=2, points_per_row=3,
                            lean_angle=30.0)
        passes = pathgen.generate_passes(Plane(), params)
        self.assertDirection((0.5, 0.0, math.sqrt(3.0) / 2.0), passes[0][0].axis)

        #the path ends at the far end of the last pass; starting there turns the whole of it round
        turned = pathgen.start_near(passes, passes[-1][-1].point, params)
        self.assertEqual((0.0, 50.0), (turned[0][0].u, turned[0][0].v))
        for one in turned:
            for index, location in enumerate(one[:-1]):
                travelling = one[index + 1].surface_point[0] - location.surface_point[0]
                self.assertGreater(location.axis[0] * travelling, 0.0,
                                   "the tool leans the way it travels")


class TheZigZag(unittest.TestCase):

    def test_the_passes_lie_across_the_face_and_the_points_along_it(self):
        passes = pathgen.generate_passes(Plane(), parameters(rows=3, points_per_row=5))
        #three rows over v in 0..50, five points over u in 0..100
        self.assertEqual([0.0, 25.0, 50.0], [one[0].v for one in passes])
        self.assertEqual([0.0, 25.0, 50.0, 75.0, 100.0], [l.u for l in passes[0]])

    def test_every_other_pass_runs_the_other_way(self):
        passes = pathgen.generate_passes(Plane(), parameters(rows=3, points_per_row=5, zigzag=True))
        self.assertEqual([0.0, 25.0, 50.0, 75.0, 100.0], [l.u for l in passes[0]])
        self.assertEqual([100.0, 75.0, 50.0, 25.0, 0.0], [l.u for l in passes[1]])
        self.assertEqual([0.0, 25.0, 50.0, 75.0, 100.0], [l.u for l in passes[2]])

    def test_without_the_zigzag_every_pass_runs_the_same_way(self):
        passes = pathgen.generate_passes(Plane(), parameters(rows=3, points_per_row=5, zigzag=False))
        for one in passes:
            self.assertEqual([0.0, 25.0, 50.0, 75.0, 100.0], [l.u for l in one])

    def test_the_passes_can_sweep_the_other_parameter(self):
        passes = pathgen.generate_passes(Plane(), parameters(rows=3, points_per_row=5, direction="V"))
        #now a pass is at constant u and sweeps v
        self.assertEqual([0.0, 50.0, 100.0], [one[0].u for one in passes])
        self.assertEqual([0.0, 12.5, 25.0, 37.5, 50.0], [l.v for l in passes[0]])

    def test_a_single_pass_lies_down_the_middle(self):
        passes = pathgen.generate_passes(Plane(), parameters(rows=1, points_per_row=5))
        self.assertEqual(1, len(passes))
        self.assertAlmostEqual(25.0, passes[0][0].v, delta=1e-12)


class WhatIsNotThere(unittest.TestCase):

    def test_a_hole_breaks_a_pass_in_two_instead_of_cutting_across_it(self):
        passes = pathgen.generate_passes(HoleInThePlane(40.0, 60.0),
                                         parameters(rows=2, points_per_row=5))
        #u = 50 is in the hole, so each row gives the two points before it and the two after
        self.assertEqual(4, len(passes))
        self.assertEqual([0.0, 25.0], [l.u for l in passes[0]])
        self.assertEqual([75.0, 100.0], [l.u for l in passes[1]])
        for one in passes:
            for location in one:
                self.assertFalse(40.0 <= location.u <= 60.0)

    def test_what_is_left_of_a_pass_has_to_be_worth_cutting(self):
        #a wide hole leaves one point at each end of every row, and one point cuts nothing
        passes = pathgen.generate_passes(HoleInThePlane(20.0, 80.0),
                                         parameters(rows=2, points_per_row=5))
        self.assertEqual([], passes)

    def test_a_point_with_no_normal_is_left_out(self):
        passes = pathgen.generate_passes(PlaneWithACrease(), parameters(rows=1, points_per_row=5))
        self.assertEqual(2, len(passes))
        self.assertEqual([0.0, 25.0], [l.u for l in passes[0]])
        self.assertEqual([75.0, 100.0], [l.u for l in passes[1]])

    def test_a_surface_that_does_not_know_its_domain_is_all_there(self):
        passes = pathgen.generate_passes(PlaneWithoutADomain(), parameters(rows=2, points_per_row=3))
        self.assertEqual(2, len(passes))
        self.assertEqual(3, len(passes[0]))


class ParametersThatCannotMakeAPath(unittest.TestCase):

    def test_they_are_refused_with_a_reason(self):
        surface = Plane()
        for kwargs, word in (({"tip_radius": -1.0}, "radius"),
                             ({"axis_mode": "SIDEWAYS"}, "axis of the tool"),
                             ({"axis_mode": pathgen.AXIS_NORMAL, "lean_angle": 90.0}, "lean"),
                             ({"axis_mode": pathgen.AXIS_NORMAL, "lean_angle": -120.0}, "lean"),
                             ({"rows": 0}, "pass"),
                             ({"points_per_row": 1}, "two points"),
                             ({"direction": "W"}, "direction")):
            with self.assertRaises(ValueError) as caught:
                pathgen.generate_passes(surface, parameters(**kwargs))
            self.assertIn(word, str(caught.exception), msg="for %r" % kwargs)

    def test_a_tool_with_no_radius_at_all_is_not_one_of_them(self):
        """A flat tool is a tip radius of zero, which was refused while this cut with a ball only."""
        self.assertEqual(3, len(pathgen.generate_passes(Plane(), parameters(tip_radius=0.0))))


class TheDepths(unittest.TestCase):
    """clip_to_depths: what the tool may not reach is taken out, and the pass comes apart there."""

    def passes_over_a_slope(self):
        """A plane tilted so that the tip of the tool runs from z = 0 up to z = 100."""

        class Slope(Plane):
            def valueAt(self, u, v):
                return (u, v, u)            # z rises with u

            def normalAt(self, u, v):
                return (0.0, 0.0, 1.0)      # straight up, so the tip lands on the surface point

        return pathgen.generate_passes(Slope(), parameters(rows=1, points_per_row=5, tip_radius=3.0))

    def test_the_height_that_is_clipped_is_the_height_of_the_tip(self):
        passes = self.passes_over_a_slope()
        self.assertEqual([0.0, 25.0, 50.0, 75.0, 100.0], [l.point[2] for l in passes[0]])

    def test_nothing_is_taken_out_when_the_range_holds_it_all(self):
        passes = self.passes_over_a_slope()
        kept = pathgen.clip_to_depths(passes, -1.0, 101.0)
        self.assertEqual([[l.u for l in one] for one in passes],
                         [[l.u for l in one] for one in kept])

    def test_what_is_too_deep_or_too_high_goes(self):
        passes = self.passes_over_a_slope()          # tips at z = 0, 25, 50, 75, 100
        kept = pathgen.clip_to_depths(passes, 20.0, 80.0)
        self.assertEqual([[25.0, 50.0, 75.0]], [[l.u for l in one] for one in kept])

    def test_a_range_in_the_middle_breaks_the_pass_in_two(self):
        #a surface that dips in the middle: the tips run 0, 40, 0, 40, 0 as u goes along
        class Valley(Plane):
            def valueAt(self, u, v):
                return (u, v, 40.0 if (u / 25.0) % 2 == 1 else 0.0)

            def normalAt(self, u, v):
                return (0.0, 0.0, 1.0)

        passes = pathgen.generate_passes(Valley(), parameters(rows=1, points_per_row=5, tip_radius=3.0))
        self.assertEqual([0.0, 40.0, 0.0, 40.0, 0.0], [l.surface_point[2] for l in passes[0]])
        kept = pathgen.clip_to_depths(passes, -1.0, 10.0)
        self.assertEqual([], kept, "two points apiece are not worth cutting on their own")
        kept = pathgen.clip_to_depths(passes, 30.0, 50.0)
        self.assertEqual([], kept, "and neither is one point apiece")

    def test_the_edge_of_the_range_counts_as_inside(self):
        #the flat face: every tip sits at exactly zero, which a range of zero to zero has to keep
        passes = pathgen.generate_passes(Plane(), parameters(rows=1, points_per_row=4, tip_radius=3.0))
        kept = pathgen.clip_to_depths(passes, 0.0, 0.0)
        self.assertEqual(1, len(kept))
        self.assertEqual(4, len(kept[0]))


class TheLayers(unittest.TestCase):
    """in_layers: the depth is taken in bands from the top down, none deeper than the step down."""

    def slope(self):
        """A plane tilted so the tip of the tool runs from z = 0 at u = 0 up to z = 100 at u = 100."""

        class Slope(Plane):
            def valueAt(self, u, v):
                return (u, v, u)

            def normalAt(self, u, v):
                return (0.0, 0.0, 1.0)

        return pathgen.generate_passes(Slope(), parameters(rows=1, points_per_row=5, tip_radius=3.0))

    def test_a_step_down_that_covers_the_range_is_one_band(self):
        passes = self.slope()
        self.assertEqual([[0.0, 25.0, 50.0, 75.0, 100.0]],
                         [[l.u for l in one] for one in pathgen.in_layers(passes, 200.0, 0.0, 100.0)])

    def test_no_step_down_at_all_is_one_band(self):
        passes = self.slope()
        self.assertEqual(1, len(pathgen.in_layers(passes, 0.0, 0.0, 100.0)))

    def test_the_bands_come_down_from_the_top_and_each_point_is_cut_once(self):
        passes = self.slope()                       # tips at z = 0, 25, 50, 75, 100
        layers = pathgen.in_layers(passes, 50.0, 0.0, 100.0)
        #the top band holds what is above 50, the bottom band the rest; 50 itself is on the boundary
        #of both and is kept by the band that reaches it first, coming down
        points = [[l.u for l in one] for one in layers]
        self.assertEqual([[50.0, 75.0, 100.0], [0.0, 25.0, 50.0]], points)
        self.assertEqual([0.0, 25.0, 50.0, 50.0, 75.0, 100.0],
                         sorted(u for one in points for u in one))

    def test_a_band_with_too_little_in_it_is_dropped_like_any_other_pass(self):
        passes = self.slope()
        layers = pathgen.in_layers(passes, 10.0, 0.0, 100.0)
        for one in layers:
            self.assertGreaterEqual(len(one), 2)


class TheStartPoint(unittest.TestCase):
    """start_near: which end of the path the tool begins at."""

    def passes(self):
        return pathgen.generate_passes(Plane(), parameters(rows=3, points_per_row=5))

    def test_a_point_by_the_beginning_leaves_the_path_as_it_is(self):
        passes = self.passes()
        self.assertEqual([l.u for l in passes[0]],
                         [l.u for l in pathgen.start_near(passes, (0.0, 0.0, 0.0), parameters())[0]])

    def test_a_point_by_the_other_end_turns_the_path_round(self):
        passes = self.passes()
        #the path ends at the far corner of the last pass; a start point there begins it from there
        last = passes[-1][-1].point
        turned = pathgen.start_near(passes, last, parameters())
        self.assertEqual(last, turned[0][0].point)
        #and the whole of it is still there, pass for pass and point for point
        self.assertEqual(sorted((l.u, l.v) for one in passes for l in one),
                         sorted((l.u, l.v) for one in turned for l in one))
        self.assertEqual([len(one) for one in passes], [len(one) for one in turned])

    def test_nothing_to_arrange_is_not_an_error(self):
        self.assertEqual([], pathgen.start_near([], (0.0, 0.0, 0.0), parameters()))


if __name__ == "__main__":
    unittest.main()
