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

The point of a location is **the centre of the ball of the tool**: the surface
point moved one tool radius along the normal. That is what a cutter location
file carries for a ball nose tool and what kin5ax calls the programmed point -
not the tip. A path of ball centres handed to an ordinary three-axis
postprocessor cuts one radius too high.

Moving the ball centre along the normal puts the ball exactly on the surface at
the point it was computed from. It says nothing about the rest of the ball, so
in a concave corner tighter than the tool radius the tool still gouges; that is
the usual limit of a point-by-point offset and no surface operation this simple
avoids it.
"""

import math

#the tool axis of the three-axis interpretation: the tool stands up, always
VERTICAL_AXIS = (0.0, 0.0, 1.0)

#a normal shorter than this is no direction, and the point it belongs to is skipped
MINIMUM_NORMAL_LENGTH = 1.0e-12


def as_xyz(v):
    """An App.Vector, anything with x/y/z, or a sequence of three, as a tuple of floats."""
    if hasattr(v, "x"):
        return (float(v.x), float(v.y), float(v.z))
    return (float(v[0]), float(v[1]), float(v[2]))


class Location(object):
    """One place the tool is asked to be: where its ball centre goes, and which way its axis points.

    ``point`` and ``axis`` are tuples of three floats, ``axis`` a unit vector.
    ``u`` and ``v`` are the parameters of the surface point this came from, kept
    because the later stages of the operation need to know where they are.
    """

    __slots__ = ("point", "axis", "u", "v", "surface_point", "normal")

    def __init__(self, point, axis, u, v, surface_point, normal):
        self.point = point
        self.axis = axis
        self.u = u
        self.v = v
        self.surface_point = surface_point      #where the ball touches the surface
        self.normal = normal                    #the surface normal there, a unit vector

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
    """

    def __init__(self, tool_radius, rows=20, points_per_row=60, direction="U",
                 zigzag=True, flip_normal=False):
        self.tool_radius = float(tool_radius)
        self.rows = int(rows)
        self.points_per_row = int(points_per_row)
        self.direction = str(direction).upper()
        self.zigzag = bool(zigzag)
        self.flip_normal = bool(flip_normal)

    def check(self):
        """Raises ValueError when these parameters cannot make a path."""
        if self.tool_radius <= 0.0:
            raise ValueError("the tool radius has to be greater than zero: this operation cuts with "
                             "the ball of a ball nose tool")
        if self.rows < 1:
            raise ValueError("a path needs at least one pass")
        if self.points_per_row < 2:
            raise ValueError("a pass of fewer than two points cuts nothing")
        if self.direction not in ("U", "V"):
            raise ValueError('the direction of the passes is "U" or "V", not %r' % self.direction)


def parameters_at(values, index, count):
    """The index-th of count values spread over [values[0], values[1]], the middle when count is 1."""
    low, high = values
    if count <= 1:
        return 0.5 * (low + high)
    return low + (high - low) * float(index) / float(count - 1)


def location_at(surface, u, v, params):
    """The location for one point of the surface, or None when there is nothing there.

    None means the point is outside the trimmed face, or the surface has no
    normal there - the pole of a degenerate parametrisation, a crease.
    """
    is_part_of_domain = getattr(surface, "isPartOfDomain", None)
    if is_part_of_domain is not None and not is_part_of_domain(u, v):
        return None
    point = as_xyz(surface.valueAt(u, v))
    normal = as_xyz(surface.normalAt(u, v))
    if params.flip_normal:
        normal = (-normal[0], -normal[1], -normal[2])
    length = math.sqrt(normal[0] ** 2 + normal[1] ** 2 + normal[2] ** 2)
    if length < MINIMUM_NORMAL_LENGTH:
        return None
    normal = (normal[0] / length, normal[1] / length, normal[2] / length)
    radius = params.tool_radius
    centre = (point[0] + radius * normal[0],
              point[1] + radius * normal[1],
              point[2] + radius * normal[2])
    return Location(centre, VERTICAL_AXIS, u, v, point, normal)


def tip_of(location, tool_radius):
    """Where the tip of the ball is: one tool radius down the axis from the centre of the ball."""
    return (location.point[0] - tool_radius * location.axis[0],
            location.point[1] - tool_radius * location.axis[1],
            location.point[2] - tool_radius * location.axis[2])


def keep_if_worth_cutting(passes, current):
    """Adds a stretch to the passes when it is long enough to cut anything, and starts a new one."""
    if len(current) > 1:
        passes.append(current)
    return []


def clip_to_depths(passes, bottom, top, tool_radius, tolerance=1.0e-7):
    """The passes with everything outside the depth range taken out.

    bottom and top are the heights the tip of the tool may work between, which is what the final and
    the start depth of an operation mean. The tip rather than the point of the path: the path carries
    the centre of the ball, and a depth is about how deep the tool goes.

    A pass that leaves the range comes apart the way one that leaves the face does, so the tool is
    lifted over what it may not cut rather than dragged through it.
    """
    kept = []
    for one in passes:
        current = []
        for location in one:
            z = tip_of(location, tool_radius)[2]
            if z < bottom - tolerance or z > top + tolerance:
                current = keep_if_worth_cutting(kept, current)
                continue
            current.append(location)
        keep_if_worth_cutting(kept, current)
    return kept


def generate_passes(surface, params):
    """The passes of a zigzag over the parameter space of one face.

    A pass is a list of Locations the tool cuts through in one go. A row of the
    zigzag breaks into more than one pass where the face is not there - a hole,
    a trimmed edge - so that the tool is lifted over the gap instead of cutting
    across it. A pass of a single point cuts nothing and is dropped.
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
    return passes
