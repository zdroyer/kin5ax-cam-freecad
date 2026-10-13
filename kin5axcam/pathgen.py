"""The geometry of the 3D Surface (5axis) operation, with no FreeCAD in it.

A surface here is anything that answers the four things a ``Part.Face`` answers:

    ``ParameterRange``       (umin, umax, vmin, vmax)
    ``valueAt(u, v)``        the point there
    ``normalAt(u, v)``       the normal there
    ``isPartOfDomain(u, v)`` whether that (u, v) is inside the trimmed face

A point or a normal may be an ``App.Vector``, anything else with ``x``, ``y``
and ``z``, or any sequence of three numbers. ``Part.Face`` answers all four, so
the operation hands one straight over; the tests hand over an analytic sphere
and a plane, whose answers are known on paper.

The three things worked out here, in this order:

**The contact point.** The zigzag over the parameter space of the face gives a
(u, v), and the surface answers with the point and the normal there. That point
is where the tool touches the part, and it is the one thing that depends neither
on the tool nor on how the tool is held.

**The tool axis.** Either straight up, which is the three-axis reading of the
operation, or the surface normal leaned over by two angles: ``lean_angle`` away
from the normal, and ``lean_rotation`` saying which way it leans - round the
normal, counted from the direction the pass runs in. Nothing leans at a
``lean_angle`` of zero, where the axis is the normal itself. A lean at zero
rotation is a lead angle, leaning along the travel; at ninety degrees it is a
tilt, leaning to the side of it.

**Where the tip goes**, which is what the G-code carries, because the tip is the
point a control programs. The sphere at the end of the tool has to touch the
surface at the contact point, which puts its centre one tip radius along the
normal, and the tip is one tip radius back down the tool axis from that centre:

    tip = contact + tip_radius * (normal - axis)

The tip radius is half the diameter of a ball nose tool, the corner radius of a
bull nose one, and zero for an end mill, a V bit or a drill. A tip radius of
zero leaves the tip on the contact point whatever the axis does.

The sphere touches the surface exactly at the point it was computed from, and
nothing is promised about the rest of the tool. In a concave corner tighter than
the tip radius the tool gouges, the flat bottom of an end mill digs into the
uphill side of a slope, and a leaning tool can put its shank through the part
somewhere else entirely - because a single contact point knows nothing of any of
it. That is the usual limit of a point-by-point offset.
"""

import math

#the tool axis of the three-axis interpretation: the tool stands up, always
VERTICAL_AXIS = (0.0, 0.0, 1.0)

#the two ways the axis of the tool may be decided
AXIS_VERTICAL = "VERTICAL"      #straight up: three axes, and no orientation to write
AXIS_NORMAL = "NORMAL"          #the surface normal, leaned over by the two angles
AXIS_MODES = (AXIS_VERTICAL, AXIS_NORMAL)

#a normal shorter than this is no direction, and the point it belongs to is skipped
MINIMUM_NORMAL_LENGTH = 1.0e-12

#a lean this small is no lean, and then the direction it would lean towards is not needed
MINIMUM_LEAN_DEGREES = 1.0e-9


def as_xyz(v):
    """An App.Vector, anything with x/y/z, or a sequence of three, as a tuple of floats."""
    if hasattr(v, "x"):
        return (float(v.x), float(v.y), float(v.z))
    return (float(v[0]), float(v[1]), float(v[2]))


def length_of(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def normalised(v):
    """The vector as a unit one, or None when it is too short to have a direction."""
    length = length_of(v)
    if length < MINIMUM_NORMAL_LENGTH:
        return None
    return (v[0] / length, v[1] / length, v[2] / length)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def across(normal, v):
    """What is left of v once the part of it along the normal is taken out, as a unit vector.

    None when nothing is left: a v along the normal has no direction in the
    tangent plane of the surface.
    """
    along = dot(v, normal)
    return normalised((v[0] - along * normal[0],
                       v[1] - along * normal[1],
                       v[2] - along * normal[2]))


def any_direction_across(normal):
    """Some unit vector across the normal, for when the direction of travel gives none.

    Which one it is does not matter, only that it is perpendicular to the
    normal: this is the fallback for a pass with no travel to speak of, where
    whichever way the lean points is as good as any other.
    """
    for candidate in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
        direction = across(normal, candidate)
        if direction is not None:
            return direction
    return VERTICAL_AXIS            # pragma: no cover - a unit normal is never all three


class Location(object):
    """One place the tool is asked to be, and where on the part it touches while it is there.

    ``surface_point`` is the contact point and ``normal`` the unit normal there,
    both of them answers of the surface. ``u`` and ``v`` are the parameters they
    were taken at, kept because a pass is laid out in that space.

    ``point`` is where the tip of the tool goes and ``axis`` which way the tool
    points, both tuples of three floats and the axis a unit vector. Those two
    are empty until ``orient_passes`` works them out, which happens once the
    passes are in the order they will be cut in.
    """

    __slots__ = ("point", "axis", "u", "v", "surface_point", "normal")

    def __init__(self, surface_point, normal, u, v):
        self.surface_point = surface_point      #where the tool touches the surface
        self.normal = normal                    #the surface normal there, a unit vector
        self.u = u
        self.v = v
        self.point = None                       #where the tip goes, from orient_passes
        self.axis = None                        #which way the tool points, the same

    def __repr__(self):
        return "Location(point=%r, axis=%r, u=%r, v=%r)" % (self.point, self.axis, self.u, self.v)


class ZigZagParameters(object):
    """What the zigzag over the parameter space of one face is made of.

    ``rows`` passes are laid out across the face and ``points_per_row`` points
    along each of them, both counted in the parameter space of the surface - not
    in millimetres, so a face whose parameters run unevenly (the poles of a
    sphere) gets uneven passes. A step over in millimetres is a later stage.

    ``direction`` says which parameter a pass sweeps: "U" for passes at constant
    v, "V" for passes at constant u. With ``zigzag`` the direction alternates
    from pass to pass, so the tool cuts there and back; without it every pass
    runs the same way and the tool returns through the air.

    ``axis_mode``, ``lean_angle`` and ``lean_rotation`` say how the tool is held
    - see the top of this module. The angles are in degrees, and are not asked
    about while the axis stands up.
    """

    def __init__(self, tip_radius, rows=20, points_per_row=60, direction="U",
                 zigzag=True, flip_normal=False, axis_mode=AXIS_VERTICAL,
                 lean_angle=0.0, lean_rotation=0.0):
        #the radius of the sphere at the end of the tool: half the diameter of a ball nose tool, the
        #corner radius of a bull nose one, zero for a tool whose end has no roundness to it
        self.tip_radius = float(tip_radius)
        self.rows = int(rows)
        self.points_per_row = int(points_per_row)
        self.direction = str(direction).upper()
        self.zigzag = bool(zigzag)
        self.flip_normal = bool(flip_normal)
        self.axis_mode = str(axis_mode).upper()
        self.lean_angle = float(lean_angle)
        self.lean_rotation = float(lean_rotation)

    def check(self):
        """Raises ValueError when these parameters cannot make a path."""
        if self.tip_radius < 0.0:
            raise ValueError("a tip radius cannot be negative: %r" % self.tip_radius)
        if self.rows < 1:
            raise ValueError("a path needs at least one pass")
        if self.points_per_row < 2:
            raise ValueError("a pass of fewer than two points cuts nothing")
        if self.direction not in ("U", "V"):
            raise ValueError('the direction of the passes is "U" or "V", not %r' % self.direction)
        if self.axis_mode not in AXIS_MODES:
            raise ValueError("the axis of the tool is one of %s, not %r"
                             % (", ".join(AXIS_MODES), self.axis_mode))
        if abs(self.lean_angle) >= 90.0:
            raise ValueError("a lean of %r degrees from the normal lays the tool in the surface or "
                             "under it: the lean has to be less than 90" % self.lean_angle)


def parameters_at(values, index, count):
    """The index-th of count values spread over [values[0], values[1]], the middle when count is 1."""
    low, high = values
    if count <= 1:
        return 0.5 * (low + high)
    return low + (high - low) * float(index) / float(count - 1)


def location_at(surface, u, v, params):
    """The contact point and the normal at one point of the surface, or None when there is none.

    None means the point is outside the trimmed face, or the surface has no
    normal there - the pole of a degenerate parametrisation, a crease. Where the
    tool goes is not settled here: that is orient_passes, once the order of the
    passes is known.
    """
    is_part_of_domain = getattr(surface, "isPartOfDomain", None)
    if is_part_of_domain is not None and not is_part_of_domain(u, v):
        return None
    point = as_xyz(surface.valueAt(u, v))
    normal = as_xyz(surface.normalAt(u, v))
    if params.flip_normal:
        normal = (-normal[0], -normal[1], -normal[2])
    normal = normalised(normal)
    if normal is None:
        return None
    return Location(point, normal, u, v)


def feed_direction(one, index):
    """Which way the tool travels at that point of a pass, in the tangent plane of the surface.

    The chord between the neighbouring contact points, which is the direction of
    the two moves the point sits between, so that the direction turns with the
    pass rather than jumping from move to move. The part of it standing out of
    the surface comes off, the lean being measured in the tangent plane.
    """
    normal = one[index].normal
    before = one[index - 1] if index > 0 else one[index]
    after = one[index + 1] if index + 1 < len(one) else one[index]
    chord = (after.surface_point[0] - before.surface_point[0],
             after.surface_point[1] - before.surface_point[1],
             after.surface_point[2] - before.surface_point[2])
    direction = across(normal, chord)
    if direction is None:
        return any_direction_across(normal)
    return direction


def tool_axis(normal, feed, lean_angle, lean_rotation):
    """The normal leaned by lean_angle, towards lean_rotation round it from the feed direction.

    A rotation of zero leans the tool the way it travels, which is a lead angle;
    ninety degrees leans it to the left of that, which is a tilt. Both angles
    are in degrees.
    """
    if abs(lean_angle) < MINIMUM_LEAN_DEGREES:
        return normal
    lean = math.radians(lean_angle)
    turn = math.radians(lean_rotation)
    #the frame at the contact point: the way the tool travels, the side of that, and the normal
    side = cross(normal, feed)
    towards = (math.cos(turn) * feed[0] + math.sin(turn) * side[0],
               math.cos(turn) * feed[1] + math.sin(turn) * side[1],
               math.cos(turn) * feed[2] + math.sin(turn) * side[2])
    axis = (math.cos(lean) * normal[0] + math.sin(lean) * towards[0],
            math.cos(lean) * normal[1] + math.sin(lean) * towards[1],
            math.cos(lean) * normal[2] + math.sin(lean) * towards[2])
    #the frame is orthonormal, so this is a unit vector already; normalising is for the rounding
    return normalised(axis) or normal


def orient_passes(passes, params):
    """Where the tip of the tool goes and which way the tool points, for every location.

    Worked out last of all, when the passes are in the order they will be cut
    in: the lean of the tool is measured from the direction the pass runs in, so
    turning a pass round turns the lean with it and it has to be worked out
    again. Both values are written into the locations, and the passes come back
    for the caller to carry on with.
    """
    radius = params.tip_radius
    vertical = params.axis_mode == AXIS_VERTICAL
    for one in passes:
        for index, location in enumerate(one):
            if vertical:
                axis = VERTICAL_AXIS
            else:
                axis = tool_axis(location.normal, feed_direction(one, index),
                                 params.lean_angle, params.lean_rotation)
            location.axis = axis
            #the ball touches the surface at the contact point, which puts its centre one radius
            #along the normal, and the tip is one radius back down the axis of the tool
            location.point = (location.surface_point[0] + radius * (location.normal[0] - axis[0]),
                              location.surface_point[1] + radius * (location.normal[1] - axis[1]),
                              location.surface_point[2] + radius * (location.normal[2] - axis[2]))
    return passes


def keep_if_worth_cutting(passes, current):
    """Adds a stretch to the passes when it is long enough to cut anything, and starts a new one."""
    if len(current) > 1:
        passes.append(current)
    return []


def clip_to_depths(passes, bottom, top, tolerance=1.0e-7):
    """The passes with everything outside the depth range taken out.

    bottom and top are the heights the tip of the tool may work between, which is what the final and
    the start depth of an operation mean - and the tip is what a location carries, so the height of
    the point is the height to compare.

    A pass that leaves the range comes apart the way one that leaves the face does, so the tool is
    lifted over what it may not cut rather than dragged through it.
    """
    kept = []
    for one in passes:
        current = []
        for location in one:
            z = location.point[2]
            if z < bottom - tolerance or z > top + tolerance:
                current = keep_if_worth_cutting(kept, current)
                continue
            current.append(location)
        keep_if_worth_cutting(kept, current)
    return kept


def in_layers(passes, step_down, bottom, top):
    """The passes cut in bands from the top down, none of them deeper than step_down.

    A surface operation that takes the whole depth in one go asks the tool to plunge the full height
    of the part at the first steep place. Cutting in bands takes the top off first and works down, so
    each band removes at most step_down of material.

    Each point is cut once, in the band it falls into, rather than the whole path being repeated at
    every level: a point already cut does not need visiting again, and the tool would only be moving
    through air if it did. A step down of zero, or one that covers the whole range, is one band -
    which is the path as it was.
    """
    if step_down <= 0.0 or top - bottom <= step_down:
        return clip_to_depths(passes, bottom, top)
    layers = []
    level = top
    while level > bottom:
        lower = max(bottom, level - step_down)
        layers.extend(clip_to_depths(passes, lower, level))
        level = lower
    return layers


def start_near(passes, point, params):
    """The passes arranged so the path starts at whichever of its two ends is nearest the point.

    The zigzag is kept as it is - only its direction is settled. There are four ways round for a path
    that runs there and back: begin at either end of the first pass or either end of the last, which
    is to say the list of passes may be reversed and each pass with it.

    Turning the path round turns the travel round with it, so the tool is leaned again afterwards: a
    lean along the way the tool travels has to follow the way it now travels.
    """
    if not passes:
        return passes
    candidates = (
        passes,
        [list(reversed(one)) for one in reversed(passes)],
    )
    best, best_distance = passes, None
    for arrangement in candidates:
        first = arrangement[0][0].point
        distance = ((first[0] - point[0]) ** 2 + (first[1] - point[1]) ** 2
                    + (first[2] - point[2]) ** 2)
        if best_distance is None or distance < best_distance:
            best, best_distance = arrangement, distance
    return orient_passes(best, params)


def generate_passes(surface, params):
    """The passes of a zigzag over the parameter space of one face.

    A pass is a list of Locations the tool cuts through in one go. A row of the
    zigzag breaks into more than one pass where the face is not there - a hole,
    a trimmed edge - so that the tool is lifted over the gap instead of cutting
    across it. A pass of a single point cuts nothing and is dropped.

    The tool is leaned and the tip worked out at the end of it, when every pass
    knows which way it runs.
    """
    params.check()
    umin, umax, vmin, vmax = surface.ParameterRange
    if params.direction == "U":
        sweep, row = (umin, umax), (vmin, vmax)
    else:
        sweep, row = (vmin, vmax), (umin, umax)

    passes = []
    for i in range(params.rows):
        row_value = parameters_at(row, i, params.rows)
        indexes = list(range(params.points_per_row))
        if params.zigzag and i % 2:
            indexes.reverse()
        current = []
        for j in indexes:
            sweep_value = parameters_at(sweep, j, params.points_per_row)
            if params.direction == "U":
                u, v = sweep_value, row_value
            else:
                u, v = row_value, sweep_value
            location = location_at(surface, u, v, params)
            if location is None:
                current = keep_if_worth_cutting(passes, current)
                continue
            current.append(location)
        keep_if_worth_cutting(passes, current)
    return orient_passes(passes, params)
