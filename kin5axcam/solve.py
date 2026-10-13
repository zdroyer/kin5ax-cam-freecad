"""A FreeCAD operation solved for a machine: what the postprocessor and the simulation share.

Three things happen between a path in a document and joint values, and both the
``--machine`` mode of the post and the machine simulation need all three the
same way:

- ``moves_of`` reads the moves out of an operation - the tip of the tool and
  its axis, carried forward word by word the way a control carries them;
- ``tool_of`` makes the tool of the operation as kin5ax sees it, from the tool
  bit of its controller and the holder the options describe;
- ``solve`` hands the moves to the solver and brings the answer back in the
  order of the path, one step per location, the invented ones included.

Lengths in a document are millimetres and lengths in a chain file are whatever
the file's are (metres for the machines shipped with kin5ax), so an ``Options``
says the scale and everything crosses the boundary through it. Only ``moves_of``
and ``tool_of`` need FreeCAD; the rest runs anywhere the binding does.
"""

from kin5axcam import kin5ax

LINEAR_COMMANDS = ("G0", "G00", "G1", "G01")
RAPID_COMMANDS = ("G0", "G00")
#what a move the solver cannot take looks like: an arc, or a canned cycle
ARC_COMMANDS = ("G2", "G02", "G3", "G03")

#the tool stands up until a move says otherwise
VERTICAL = (0.0, 0.0, 1.0)

#the shapes of tool bit whose end is a half sphere of the full diameter
BALL_NOSED_SHAPES = ("ballend", "ballnose", "taperedballnose")

START_CRITERIA = {
    "MIN": kin5ax.START_MIN,
    "MAX": kin5ax.START_MAX,
    "MIN_ABS": kin5ax.START_MIN_ABS,
    "SHORTEST": kin5ax.START_SHORTEST_PATH,
}


class Options(object):
    """How an operation is solved: the unit of the chain file, the holder, the checks, the start.

    unit_in_mm is how many millimetres one length unit of the chain file is -
    1000 for the metres the shipped machines are in. The holder is given here
    because a tool bit of FreeCAD does not describe one. max_step_mm and
    max_turn_degrees bound the steps the solver invents between two moves and
    default to the settings of kin5ax; None leaves a value to the library.
    """

    def __init__(self, unit_in_mm=1000.0, holder_length_mm=50.0, holder_radius_mm=30.0,
                 check_limits=True, check_collisions=True, interpolate=True, max_step_mm=None,
                 max_turn_degrees=None, start=None, rotary_letters=None):
        self.unit_in_mm = float(unit_in_mm)
        self.holder_length_mm = float(holder_length_mm)
        self.holder_radius_mm = float(holder_radius_mm)
        self.check_limits = bool(check_limits)
        self.check_collisions = bool(check_collisions)
        self.interpolate = bool(interpolate)
        self.max_step_mm = None if max_step_mm is None else float(max_step_mm)
        self.max_turn_degrees = None if max_turn_degrees is None else float(max_turn_degrees)
        self.start = None if start is None else str(start).upper()
        self.rotary_letters = None if rotary_letters is None else str(rotary_letters).upper()
        if self.start is not None and self.start not in START_CRITERIA:
            raise ValueError("the start of the trajectory is one of %s, not %r"
                             % (", ".join(START_CRITERIA), start))
        if self.rotary_letters is not None and (len(self.rotary_letters) != 2
                                                or any(c not in "ABC" for c in self.rotary_letters)):
            raise ValueError("the rotary letters are two of A, B and C, such as AC, not %r"
                             % rotary_letters)

    def settings(self):
        """The settings of kin5ax these options ask for, on top of the ones the library recommends."""
        settings = kin5ax.Settings.default()
        settings.check_limits = 1 if self.check_limits else 0
        settings.check_collisions = 1 if self.check_collisions else 0
        settings.interpolate = 1 if self.interpolate else 0
        if self.max_step_mm is not None:
            settings.max_position_difference = self.max_step_mm / self.unit_in_mm
        if self.max_turn_degrees is not None:
            settings.max_orientation_difference_degrees = self.max_turn_degrees
        if self.start is not None:
            settings.start_criterion = START_CRITERIA[self.start]
        return settings


class Move(object):
    """One move of an operation: where the tip goes, which way the tool points, how fast."""

    __slots__ = ("index", "source", "command", "point", "axis", "feed")

    def __init__(self, index, source, command, point, axis, feed):
        self.index = index              #its place among the moves of the operation, from 0
        self.source = source            #the index of the command of the path that completed it
        self.command = command          #G0 or G1
        self.point = point              #the tip of the tool, mm, in the frame of the part
        self.axis = axis                #the axis of the tool, a unit vector
        self.feed = feed                #the feed of the move, or None when it said none

    @property
    def rapid(self):
        return self.command in RAPID_COMMANDS

    def __repr__(self):
        return "Move(%d, %s, %r, %r)" % (self.index, self.command, self.point, self.axis)


def moves_of(pathobj):
    """The moves of an operation, in order, as the solver wants them.

    The point is the tip of the tool, carried forward word by word the way a
    control carries it; the axis is the last I J K seen, which is the tool
    standing up until a move says otherwise. The first moves, before all three of
    X, Y and Z have been given, are folded into the first move that has them - a
    machine cannot be sent to a point it has not been told the whole of - and
    the fold is a rapid if any of them was.

    An arc or a canned cycle raises ValueError: the solver takes lines, and those
    have to be turned into lines first.
    """
    from PathScripts import PathUtils

    moves = []
    current = {}
    axis = VERTICAL
    pending_rapid = False
    for source, command in enumerate(PathUtils.getPathWithPlacement(pathobj).Commands):
        name = command.Name
        if name in ARC_COMMANDS or name.startswith("G8") or name.startswith("G7"):
            raise ValueError("%s has a %s, which the solver does not take: an arc has to be written "
                             "as lines and a cycle as moves before it can be solved"
                             % (pathobj.Label, name))
        if name not in LINEAR_COMMANDS:
            continue
        parameters = command.Parameters
        for word in ("X", "Y", "Z"):
            if word in parameters:
                current[word] = float(parameters[word])
        if all(word in parameters for word in ("I", "J", "K")):
            axis = (float(parameters["I"]), float(parameters["J"]), float(parameters["K"]))
        feed = float(parameters["F"]) if "F" in parameters else None
        if not all(word in current for word in ("X", "Y", "Z")):
            pending_rapid = pending_rapid or name in RAPID_COMMANDS
            continue
        if pending_rapid:
            name = "G0"
            pending_rapid = False
        moves.append(Move(len(moves), source, name, (current["X"], current["Y"], current["Z"]), axis,
                          feed))
    return moves


class ToolModel(object):
    """A tool as kin5ax sees it, in millimetres: the dimensions a tool bit gives and the holder it does not.

    A ball nose bit is a ball of half its diameter, programmed at the centre of
    the ball; anything else is a flat end of half its diameter, programmed at
    the tip. The shank is taken as wide as the cutter, which flags a collision
    sooner rather than later.
    """

    def __init__(self, shape, diameter_mm, cutting_height_mm, shank_length_mm, holder_length_mm,
                 holder_radius_mm):
        self.shape = shape                              #kin5ax.TOOL_BALL_NOSE or TOOL_FLAT_END
        self.diameter_mm = float(diameter_mm)
        self.cutting_height_mm = float(cutting_height_mm)
        self.shank_length_mm = float(shank_length_mm)
        self.holder_length_mm = float(holder_length_mm)
        self.holder_radius_mm = float(holder_radius_mm)

    @property
    def radius_mm(self):
        return 0.5 * self.diameter_mm

    @property
    def ball_nosed(self):
        return self.shape == kin5ax.TOOL_BALL_NOSE

    @property
    def assembly_length_mm(self):
        """From the tip of the tool to the tool mount of the machine."""
        return self.cutting_height_mm + self.shank_length_mm + self.holder_length_mm

    def programmed_point(self, tip, axis):
        """Where kin5ax programs this tool for a tip there: the ball centre, or the tip itself."""
        if not self.ball_nosed:
            return tuple(tip)
        return tuple(tip[i] + self.radius_mm * axis[i] for i in range(3))

    def to_kin5ax(self, unit_in_mm):
        """The tool of the library, in the unit of the chain file."""
        radius = self.radius_mm / unit_in_mm
        return kin5ax.Tool(self.shape, radius, radius, self.cutting_height_mm / unit_in_mm,
                           self.shank_length_mm / unit_in_mm, self.holder_length_mm / unit_in_mm,
                           self.holder_radius_mm / unit_in_mm)


def _length(obj, name, default=0.0):
    value = getattr(obj, name, default)
    return float(getattr(value, "Value", value))


def tool_model_of(pathobj, options):
    """The tool of an operation as a ToolModel, or None when the operation has no tool to speak of."""
    controller = getattr(pathobj, "ToolController", None)
    tool = getattr(controller, "Tool", None)
    if tool is None:
        return None
    diameter = _length(tool, "Diameter")
    if diameter <= 0.0:
        return None
    shape = str(getattr(tool, "ShapeType", "") or getattr(tool, "ShapeName", "")).lower()
    cutting = _length(tool, "CuttingEdgeHeight")
    if cutting <= 0.0:
        cutting = 2.0 * diameter
    shank = max(_length(tool, "Length") - cutting, 0.0)
    kind = kin5ax.TOOL_BALL_NOSE if shape in BALL_NOSED_SHAPES else kin5ax.TOOL_FLAT_END
    return ToolModel(kind, diameter, cutting, shank, options.holder_length_mm, options.holder_radius_mm)


def tool_of(pathobj, options):
    """The tool of an operation as kin5ax sees it, or None: the model, made in the unit of the chain."""
    model = tool_model_of(pathobj, options)
    return None if model is None else model.to_kin5ax(options.unit_in_mm)


class Step(object):
    """One location of a solved trajectory, with what it was solved for and what came of it.

    q is the configuration chosen, in the order of the links of the chain and in
    the units of the chain file, or None when the location has no solution.
    move is the Move this location belongs to: its own, or for a location the
    solver invented, the move it is on the way to.
    """

    __slots__ = ("q", "status", "origin", "move")

    def __init__(self, q, status, origin, move):
        self.q = q
        self.status = status
        self.origin = origin
        self.move = move

    @property
    def solved(self):
        return self.q is not None

    @property
    def status_name(self):
        return kin5ax.SOLVE_STATUS_NAMES.get(self.status, "status %d" % self.status)

    @property
    def invented(self):
        return self.origin != kin5ax.FROM_FILE


class Trajectory(object):
    """What solving the moves of an operation gave: a step per location, and the report of the run."""

    def __init__(self, steps, report, position_error_mm, orientation_error):
        self.steps = steps
        self.report = report                    #{status name: count}, the statuses nobody got left out
        self.position_error_mm = position_error_mm
        self.orientation_error = orientation_error

    @property
    def unsolved(self):
        return [step for step in self.steps if not step.solved]

    def describe(self):
        """One line: the counts by status, and the largest errors of the run."""
        return "%s; largest errors %.3g mm and %.3g" % (
            ", ".join("%d %s" % (count, status) for status, count in sorted(self.report.items())),
            self.position_error_mm, self.orientation_error)


def solve(chain, moves, tool_model, options):
    """The moves solved for the chain: a Trajectory in the order of the path.

    tool_model may be None when the options do not check collisions; the tool is
    made for the library here and freed afterwards. A location the solver
    invents on the way to a move is given that move.
    """
    if tool_model is None and options.check_collisions:
        raise ValueError("there is no tool to check collisions with: pick a tool controller, or "
                         "switch the check off")
    scale = options.unit_in_mm
    positions, axes = [], []
    for move in moves:
        programmed = tool_model.programmed_point(move.point, move.axis) if tool_model else move.point
        positions.append(tuple(c / scale for c in programmed))
        axes.append(move.axis)
    tool = tool_model.to_kin5ax(scale) if tool_model is not None else None
    try:
        with chain.postprocess_locations(positions, axes, options.settings(), tool) as path:
            steps = []
            for location in path.locations():
                index = location.file_location - 1
                if location.origin != kin5ax.FROM_FILE:
                    index = min(index + 1, len(moves) - 1)
                steps.append(Step(location.q, location.status, location.origin, moves[index]))
            report = path.report()
            position_error, orientation_error = path.errors()
    finally:
        if tool is not None:
            tool.close()
    return Trajectory(steps, report, position_error * scale, orientation_error)


def rotary_letters(chain, options):
    """What the control calls the two rotary axes, in the order of the chain's default G-code axes.

    The options say, or the names of the links do when they are letters, or
    failing both the guess of kin5ax.
    """
    axes = chain.default_gcode_axes()
    if options.rotary_letters:
        return options.rotary_letters[0], options.rotary_letters[1]
    links = chain.links()
    letters = []
    for index in (axes.angle1, axes.angle2):
        name = links[index].name.strip().upper()
        letters.append(name if name in ("A", "B", "C") else None)
    if None in letters or letters[0] == letters[1]:
        return axes.angle1_letter, axes.angle2_letter
    return letters[0], letters[1]
