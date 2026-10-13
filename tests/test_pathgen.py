"""The zigzag and the ball centre offset, against surfaces whose answers are known on paper.

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
    kwargs.setdefault("tool_radius", 3.0)
    kwargs.setdefault("rows", 3)
    kwargs.setdefault("points_per_row", 5)
    return pathgen.ZigZagParameters(**kwargs)


class TheBallCentreIsTheProgrammedPoint(unittest.TestCase):

    def test_on_a_plane_it_is_one_radius_above_the_surface(self):
        passes = pathgen.generate_passes(Plane(), parameters(tool_radius=3.0))
        self.assertEqual(3, len(passes))
        for one in passes:
            self.assertEqual(5, len(one))
            for location in one:
                self.assertAlmostEqual(3.0, location.point[2], delta=1e-12)
                self.assertAlmostEqual(0.0, location.surface_point[2], delta=1e-12)
                self.assertEqual(location.point[0], location.surface_point[0])
                self.assertEqual(location.point[1], location.surface_point[1])
                self.assertEqual(pathgen.VERTICAL_AXIS, location.axis)

    def test_on_a_sphere_every_centre_is_a_radius_further_out(self):
        surface = Sphere(radius=10.0)
        passes = pathgen.generate_passes(surface, parameters(tool_radius=2.5, rows=7, points_per_row=13))
        self.assertEqual(7, len(passes))
        for one in passes:
            for location in one:
                distance = math.sqrt(sum(c * c for c in location.point))
                self.assertAlmostEqual(12.5, distance, delta=1e-12)
                #and the ball touches the sphere where the location was taken from
                touch = math.sqrt(sum(c * c for c in location.surface_point))
                self.assertAlmostEqual(10.0, touch, delta=1e-12)

    def test_the_normal_can_be_turned_round(self):
        surface = Sphere(radius=10.0)
        passes = pathgen.generate_passes(surface, parameters(tool_radius=2.5, flip_normal=True))
        for one in passes:
            for location in one:
                distance = math.sqrt(sum(c * c for c in location.point))
                self.assertAlmostEqual(7.5, distance, delta=1e-12)

    def test_a_point_of_the_surface_can_be_a_vector_object(self):
        passes = pathgen.generate_passes(PlaneOfVectors(), parameters())
        self.assertEqual(3, len(passes))
        self.assertAlmostEqual(3.0, passes[0][0].point[2], delta=1e-12)


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
        for kwargs, word in (({"tool_radius": 0.0}, "radius"),
                             ({"tool_radius": -1.0}, "radius"),
                             ({"rows": 0}, "pass"),
                             ({"points_per_row": 1}, "two points"),
                             ({"direction": "W"}, "direction")):
            with self.assertRaises(ValueError) as caught:
                pathgen.generate_passes(surface, parameters(**kwargs))
            self.assertIn(word, str(caught.exception), msg="for %r" % kwargs)


if __name__ == "__main__":
    unittest.main()


class TheDepths(unittest.TestCase):
    """clip_to_depths: what the tool may not reach is taken out, and the pass comes apart there."""

    def passes_over_a_slope(self):
        """A plane tilted so that the tip of the tool runs from z = 0 up to z = 100."""

        class Slope(Plane):
            def valueAt(self, u, v):
                return (u, v, u)            # z rises with u

            def normalAt(self, u, v):
                return (0.0, 0.0, 1.0)      # straight up, so the tip is one radius below the centre

        return pathgen.generate_passes(Slope(), parameters(rows=1, points_per_row=5, tool_radius=3.0))

    def test_the_tip_is_a_radius_down_the_axis_from_the_centre(self):
        passes = pathgen.generate_passes(Plane(), parameters(rows=1, points_per_row=2))
        location = passes[0][0]
        self.assertAlmostEqual(3.0, location.point[2], delta=1e-12)
        self.assertAlmostEqual(0.0, pathgen.tip_of(location, 3.0)[2], delta=1e-12,
                               msg="the tip of the ball sits on the surface")

    def test_nothing_is_taken_out_when_the_range_holds_it_all(self):
        passes = self.passes_over_a_slope()
        kept = pathgen.clip_to_depths(passes, -1.0, 101.0, 3.0)
        self.assertEqual([[l.u for l in one] for one in passes],
                         [[l.u for l in one] for one in kept])

    def test_what_is_too_deep_or_too_high_goes(self):
        passes = self.passes_over_a_slope()          # tips at z = 0, 25, 50, 75, 100
        kept = pathgen.clip_to_depths(passes, 20.0, 80.0, 3.0)
        self.assertEqual([[25.0, 50.0, 75.0]], [[l.u for l in one] for one in kept])

    def test_a_range_in_the_middle_breaks_the_pass_in_two(self):
        #a surface that dips in the middle: the tips run 0, 40, 0, 40, 0 as u goes along
        class Valley(Plane):
            def valueAt(self, u, v):
                return (u, v, 40.0 if (u / 25.0) % 2 == 1 else 0.0)

            def normalAt(self, u, v):
                return (0.0, 0.0, 1.0)

        passes = pathgen.generate_passes(Valley(), parameters(rows=1, points_per_row=5, tool_radius=3.0))
        self.assertEqual([0.0, 40.0, 0.0, 40.0, 0.0], [l.surface_point[2] for l in passes[0]])
        kept = pathgen.clip_to_depths(passes, -1.0, 10.0, 3.0)
        self.assertEqual([], kept, "two points apiece are not worth cutting on their own")
        kept = pathgen.clip_to_depths(passes, 30.0, 50.0, 3.0)
        self.assertEqual([], kept, "and neither is one point apiece")

    def test_the_edge_of_the_range_counts_as_inside(self):
        #the flat face: every tip sits at exactly zero, which a range of zero to zero has to keep
        passes = pathgen.generate_passes(Plane(), parameters(rows=1, points_per_row=4, tool_radius=3.0))
        kept = pathgen.clip_to_depths(passes, 0.0, 0.0, 3.0)
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

        return pathgen.generate_passes(Slope(), parameters(rows=1, points_per_row=5, tool_radius=3.0))

    def test_a_step_down_that_covers_the_range_is_one_band(self):
        passes = self.slope()
        self.assertEqual([[0.0, 25.0, 50.0, 75.0, 100.0]],
                         [[l.u for l in one] for one in pathgen.in_layers(passes, 200.0, 0.0, 100.0, 3.0)])

    def test_no_step_down_at_all_is_one_band(self):
        passes = self.slope()
        self.assertEqual(1, len(pathgen.in_layers(passes, 0.0, 0.0, 100.0, 3.0)))

    def test_the_bands_come_down_from_the_top_and_each_point_is_cut_once(self):
        passes = self.slope()                       # tips at z = 0, 25, 50, 75, 100
        layers = pathgen.in_layers(passes, 50.0, 0.0, 100.0, 3.0)
        #the top band holds what is above 50, the bottom band the rest; 50 itself is on the boundary
        #of both and is kept by the band that reaches it first, coming down
        points = [[l.u for l in one] for one in layers]
        self.assertEqual([[50.0, 75.0, 100.0], [0.0, 25.0, 50.0]], points)
        self.assertEqual([0.0, 25.0, 50.0, 50.0, 75.0, 100.0],
                         sorted(u for one in points for u in one))

    def test_a_band_with_too_little_in_it_is_dropped_like_any_other_pass(self):
        passes = self.slope()
        layers = pathgen.in_layers(passes, 10.0, 0.0, 100.0, 3.0)
        for one in layers:
            self.assertGreaterEqual(len(one), 2)


class TheStartPoint(unittest.TestCase):
    """start_near: which end of the path the tool begins at."""

    def passes(self):
        return pathgen.generate_passes(Plane(), parameters(rows=3, points_per_row=5))

    def test_a_point_by_the_beginning_leaves_the_path_as_it_is(self):
        passes = self.passes()
        self.assertEqual([l.u for l in passes[0]],
                         [l.u for l in pathgen.start_near(passes, (0.0, 0.0, 0.0))[0]])

    def test_a_point_by_the_other_end_turns_the_path_round(self):
        passes = self.passes()
        #the path ends at the far corner of the last pass; a start point there begins it from there
        last = passes[-1][-1].point
        turned = pathgen.start_near(passes, last)
        self.assertEqual(last, turned[0][0].point)
        #and the whole of it is still there, pass for pass and point for point
        self.assertEqual(sorted((l.u, l.v) for one in passes for l in one),
                         sorted((l.u, l.v) for one in turned for l in one))
        self.assertEqual([len(one) for one in passes], [len(one) for one in turned])

    def test_nothing_to_arrange_is_not_an_error(self):
        self.assertEqual([], pathgen.start_near([], (0.0, 0.0, 0.0)))
