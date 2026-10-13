# SPDX-License-Identifier: LGPL-2.1-or-later

"""

CAM post processor for a Fanuc controller doing five-axis work with the tool axis vector.

This is FreeCAD's own fanuc_post with three things changed, and it stays under the
licence of the file it came from - LGPL-2.1-or-later, not the MIT of the rest of
kin5ax. Keeping it a copy rather than a rewrite means a fix to the Fanuc post of
FreeCAD can be brought over by reading the difference between the two.

**K is output.** The parameter list of the Fanuc post is X Y Z A B C I J F S T Q
R L H D P - no K, so the third component of every tool axis vector was dropped
on the way out and the orientation left the program half written. A reader could
only get it back by assuming the tool points upwards.

**I, J and K are directions on a linear move.** They are arc centres on G2 and G3
and that is still how they are written, as lengths, converted into the units of
the output. On G0 and G1 they are the tool axis vector, which is a direction: it
is written as it is, with no unit conversion - without that an inch program would
have had the vector scaled by 1/25.4 - and never suppressed for repeating the
value of the move before, which a direction has every right to do.

**Tool centre point control is switched on and off round an operation that has
vectors.** G43.5 is the Fanuc mode in which the tool axis is commanded by I, J
and K, which is what this writes, and G49 cancels it afterwards. Mind that G49
cancels the tool length offset with it: an operation that comes after a five-axis
one, with the same tool, has to have its offset set up again.

**With --machine, the moves are solved and written as machine axes.** Given a
kinematic chain file of kin5ax (.kc or .kc.json), every move of every operation
is handed to the solver - the tip of the tool and its axis, in the frame of the
part - and comes back as the five joint values of that machine, written as
X Y Z and the two rotary letters. No G43.5 then, and no tool length offset
either: the length of the tool is in the model the solver was given, so the
program is run with the offset cancelled. This is the one mode that runs on a
control with no TCP option at all, and it is the mode that needs kin5ax.

The frame of the part in FreeCAD is taken to be the frame of the material of
the chain file - the origin of the job is where the workpiece sits on the
machine. A move the solver cannot place is left out of the file and said so, in
a comment where it would have been and in a count at the end of the operation.

Nothing here knows about a tilted working plane. G68.2 and the rest are the later
work.

"""

# ***************************************************************************
# *   Copyright (c) 2014 sliptonic <shopinthewoods@gmail.com>               *
# *   Copyright (c) 2021 shadowbane1000 <tyler@colberts.us>                 *
# *   Copyright (c) 2026 Przemyslaw Zdroik - the kin5ax changes above       *
# *                                                                         *
# *   This file is part of the FreeCAD CAx development system.              *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful,            *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Lesser General Public License for more details.                   *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with FreeCAD; if not, write to the Free Software        *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************/

import FreeCAD
from FreeCAD import Units
import Path
import argparse
import datetime
import math
import shlex
import os.path
import Path.Base.Util as PathUtil
import Path.Post.Utils as PostUtils
from PathScripts import PathUtils
from builtins import open as pyopen

TOOLTIP = """
FreeCAD's Fanuc postprocessor, with the tool axis vector carried through: the K
word is written as well as I and J, the three of them are written as directions
rather than lengths on a linear move, and an operation that has a tool axis is
wrapped in G43.5 (tool centre point control, type 2 - the tool axis commanded by
I J K) and G49.

Mind that G49 cancels the tool length offset as well, so an operation following
a five-axis one has to have its offset set up again.

With --machine <chain file> every move is solved by kin5ax instead and written
as the machine axes X Y Z A C - direct axes, no TCP, the tool length in the
model. --machine-unit says the unit of the chain file (m for the machines that
ship with kin5ax), --rotary-letters what the control calls the two rotary
axes, --holder-length and --holder-radius the holder FreeCAD's tool bits do
not describe.

It can be used from inside FreeCAD once it is in the macro folder, or from a
script with:

import fanuc_tcp_kin5ax_post
fanuc_tcp_kin5ax_post.export(object, "/path/to/file.ncc", "")
"""

# Preamble text will appear at the beginning of the GCODE output file.
DEFAULT_PREAMBLE = """G17 G54 G40 G49 G80 G90 G94
"""

# Postamble text will appear following the last operation.
DEFAULT_POSTAMBLE = """M05
G17 G54 G90 G80 G40
M30
"""

now = datetime.datetime.now()

parser = argparse.ArgumentParser(prog="fanuc_tcp_kin5ax", add_help=False)
parser.add_argument("--no-header", action="store_true", help="suppress header output")
parser.add_argument("--no-comments", action="store_true", help="suppress comment output")
parser.add_argument("--line-numbers", action="store_true", help="prefix with line numbers")
parser.add_argument(
    "--no-show-editor",
    action="store_true",
    help="don't pop up editor before writing output",
)
parser.add_argument("--precision", help="number of digits of precision, default=3 (mm) or 4 (in)")
parser.add_argument(
    "--preamble",
    help='set commands to be issued before the first command, default="'
    + DEFAULT_PREAMBLE.replace("\n", "\\n")
    + '"',
)
parser.add_argument(
    "--postamble",
    help="set commands to be issued after the last command, "
    + 'default="'
    + DEFAULT_POSTAMBLE.replace("\n", "\\n")
    + '"',
)
parser.add_argument(
    "--inches", action="store_true", help="Convert output for US imperial mode (G20)"
)
parser.add_argument(
    "--no-modal",
    action="store_true",
    help="Don't output the Same G-command Name USE NonModal Mode",
)
parser.add_argument(
    "--no-axis-modal", action="store_true", help="Don't output the Same Axis Value Mode"
)
parser.add_argument(
    "--no-tlo",
    action="store_true",
    help="suppress tool length offset (G43) following tool changes",
)
parser.add_argument(
    "--end-spindle-empty",
    action="store_true",
    help="place last tool in tool change carousel before postamble",
)
parser.add_argument(
    "--no-tcp",
    action="store_true",
    help="write the tool axis vector but no G43.5/G49 around the operation that has one",
)
parser.add_argument(
    "--tcp-command",
    help='the mode to switch on for an operation with a tool axis, default="G43.5"',
)
parser.add_argument(
    "--tcp-cancel",
    help='what cancels it afterwards, default="G49"',
)
parser.add_argument(
    "--vector-precision",
    help="number of digits of the tool axis vector, default=6",
)
parser.add_argument(
    "--machine",
    help="a kin5ax chain file (.kc or .kc.json): solve every move for that machine and write the "
    "joint values as X Y Z and the two rotary axes, instead of the tool axis vector",
)
parser.add_argument(
    "--machine-unit",
    help='the length unit of the chain file, "m" or "mm", default="m"',
)
parser.add_argument(
    "--rotary-letters",
    help="what the control calls the two rotary axes, in the order of the chain, e.g. AC; the default "
    "is the names of the links when they are letters, else the guess of kin5ax",
)
parser.add_argument(
    "--holder-length",
    help="the holder between the tool and the spindle, in mm, which a tool bit does not say; default=50",
)
parser.add_argument(
    "--holder-radius",
    help="and its radius in mm, default=30",
)
parser.add_argument(
    "--no-limits", action="store_true", help="do not refuse a configuration outside the joint limits"
)
parser.add_argument(
    "--no-collisions", action="store_true", help="do not refuse a configuration whose parts meet"
)
parser.add_argument(
    "--no-interpolation",
    action="store_true",
    help="write the moves as they are, with nothing invented between two of them",
)
parser.add_argument(
    "--max-step",
    help="no invented step longer than this, in mm (default: the setting of kin5ax, 1/100 of its unit)",
)
parser.add_argument(
    "--max-turn",
    help="nor turning the tool axis further than this, in degrees (default: the setting of kin5ax)",
)
parser.add_argument(
    "--start",
    help='where the trajectory starts: the first rotary axis at MIN, MAX, MIN_ABS (default) or '
    'SHORTEST for whatever makes the whole path shortest',
)

TOOLTIP_ARGS = parser.format_help()

# These globals set common customization preferences
OUTPUT_COMMENTS = True
OUTPUT_HEADER = True
OUTPUT_LINE_NUMBERS = False
SHOW_EDITOR = True
MODAL = True  # if true commands are suppressed if the same as previous line.
USE_TLO = True  # if true G43 will be output following tool changes
OUTPUT_DOUBLES = (
    False  # if false duplicate axis values are suppressed if the same as previous line.
)
COMMAND_SPACE = " "
LINENR = 100  # line number starting value

END_SPINDLE_EMPTY = False

# Tool centre point control: the mode in which the tool axis is commanded by I, J and K, and what
# cancels it. The vector is a direction, so it is written with digits of its own rather than with
# the precision of a length.
USE_TCP = True
TCP_COMMAND = "G43.5"
TCP_CANCEL = "G49"
VECTOR_PRECISION = 6

# The moves on which I, J and K are the tool axis vector. On G2 and G3 they are the centre of the
# arc, which is a length and is left alone.
LINEAR_COMMANDS = ("G0", "G00", "G1", "G01")
RAPID_COMMANDS = ("G0", "G00")
# What a move the solver cannot take looks like: an arc, or a canned cycle.
ARC_COMMANDS = ("G2", "G02", "G3", "G03")

# The machine, when the moves are to be solved rather than handed to the control with a vector.
MACHINE = None
MACHINE_UNIT_IN_MM = 1000.0               # metres, the unit of the chain files that ship with kin5ax
ROTARY_LETTERS = None                     # None: the names of the links, or the guess of kin5ax
HOLDER_LENGTH_MM = 50.0
HOLDER_RADIUS_MM = 30.0
CHECK_LIMITS = True
CHECK_COLLISIONS = True
INTERPOLATE = True
MAX_STEP_MM = None
MAX_TURN_DEGREES = None
START_CRITERION = None
# the tool stands up until a move says otherwise
VERTICAL = (0.0, 0.0, 1.0)

# These globals will be reflected in the Machine configuration of the project
UNITS = "G21"  # G21 for metric, G20 for us standard
UNIT_SPEED_FORMAT = "mm/min"
UNIT_FORMAT = "mm"

MACHINE_NAME = "fanuc"
CORNER_MIN = {"x": 0, "y": 0, "z": 0}
CORNER_MAX = {"x": 500, "y": 300, "z": 300}
PRECISION = 3

# this global is used to pass spindle speed from the tool command into the machining command for
# rigid tapping.
tapSpeed = 0

PREAMBLE = DEFAULT_PREAMBLE
POSTAMBLE = DEFAULT_POSTAMBLE

# Pre operation text will be inserted before every operation
PRE_OPERATION = """"""

# Post operation text will be inserted after every operation
POST_OPERATION = """"""

# Tool Change commands will be inserted before a tool change
# Move to tool change Z position
TOOL_CHANGE = """G28 G91 Z0
"""

# List of drill G codes where some parameters are required and their
# required parameters.
DRILL_OPERATION = ("G73", "G81", "G82", "G83", "G85")
DRILL_PARAM_REQ = ("L", "P", "Q", "R", "Z")

# The settings shared between methods
PREAMBLE = None
POSTAMBLE = None


def processArguments(argstring):
    """
    Apply default values and command line arguments before
    processing commands.

    """
    global OUTPUT_HEADER
    global OUTPUT_COMMENTS
    global OUTPUT_LINE_NUMBERS
    global SHOW_EDITOR
    global PRECISION
    global DEFAULT_PREAMBLE
    global DEFAULT_POSTAMBLE
    global PREAMBLE
    global POSTAMBLE
    global UNITS
    global UNIT_SPEED_FORMAT
    global UNIT_FORMAT
    global MODAL
    global USE_TLO
    global END_SPINDLE_EMPTY
    global OUTPUT_DOUBLES
    global LINENR
    global USE_TCP
    global TCP_COMMAND
    global TCP_CANCEL
    global VECTOR_PRECISION
    global MACHINE
    global MACHINE_UNIT_IN_MM
    global ROTARY_LETTERS
    global HOLDER_LENGTH_MM
    global HOLDER_RADIUS_MM
    global CHECK_LIMITS
    global CHECK_COLLISIONS
    global INTERPOLATE
    global MAX_STEP_MM
    global MAX_TURN_DEGREES
    global START_CRITERION

    try:
        args = parser.parse_args(shlex.split(argstring))
        USE_TCP = not args.no_tcp
        if args.tcp_command:
            TCP_COMMAND = args.tcp_command
        if args.tcp_cancel:
            TCP_CANCEL = args.tcp_cancel
        if args.vector_precision is not None:
            VECTOR_PRECISION = int(args.vector_precision)
        MACHINE = args.machine
        if args.machine_unit:
            MACHINE_UNIT_IN_MM = {"m": 1000.0, "mm": 1.0}[args.machine_unit.lower()]
        ROTARY_LETTERS = args.rotary_letters.upper() if args.rotary_letters else None
        if ROTARY_LETTERS is not None and (len(ROTARY_LETTERS) != 2
                                           or any(c not in "ABC" for c in ROTARY_LETTERS)):
            raise ValueError("--rotary-letters takes two of A, B and C, such as AC")
        if args.holder_length is not None:
            HOLDER_LENGTH_MM = float(args.holder_length)
        if args.holder_radius is not None:
            HOLDER_RADIUS_MM = float(args.holder_radius)
        CHECK_LIMITS = not args.no_limits
        CHECK_COLLISIONS = not args.no_collisions
        INTERPOLATE = not args.no_interpolation
        MAX_STEP_MM = float(args.max_step) if args.max_step is not None else None
        MAX_TURN_DEGREES = float(args.max_turn) if args.max_turn is not None else None
        START_CRITERION = args.start.upper() if args.start else None
        if START_CRITERION is not None and START_CRITERION not in ("MIN", "MAX", "MIN_ABS", "SHORTEST"):
            raise ValueError("--start is MIN, MAX, MIN_ABS or SHORTEST")
        if args.no_header:
            OUTPUT_HEADER = False
        else:
            OUTPUT_HEADER = True
        if args.no_comments:
            OUTPUT_COMMENTS = False
        else:
            OUTPUT_COMMENTS = True
        if args.line_numbers:
            OUTPUT_LINE_NUMBERS = True
            LINENR = 100
        else:
            OUTPUT_LINE_NUMBERS = False
        if args.no_show_editor:
            SHOW_EDITOR = False
        else:
            SHOW_EDITOR = True
        # print("Show editor = %s" % SHOW_EDITOR)  # Commented to reduce test noise
        if args.preamble is not None:
            PREAMBLE = args.preamble.replace("\\n", "\n")
        else:
            PREAMBLE = DEFAULT_PREAMBLE
        if args.postamble is not None:
            POSTAMBLE = args.postamble.replace("\\n", "\n")
        else:
            POSTAMBLE = DEFAULT_POSTAMBLE
        if args.inches:
            UNITS = "G20"
            UNIT_SPEED_FORMAT = "in/min"
            UNIT_FORMAT = "in"
            PRECISION = 4
        else:
            UNITS = "G21"
            UNIT_SPEED_FORMAT = "mm/min"
            UNIT_FORMAT = "mm"
            PRECISION = 3
        if args.precision:
            PRECISION = int(args.precision)
        if args.no_modal:
            MODAL = False
        else:
            MODAL = True
        if args.no_tlo:
            USE_TLO = False
        else:
            USE_TLO = True
        if args.no_axis_modal:
            OUTPUT_DOUBLES = True
        else:
            OUTPUT_DOUBLES = False
        if args.end_spindle_empty:
            END_SPINDLE_EMPTY = True
        else:
            END_SPINDLE_EMPTY = False

    except Exception:
        return False

    return True


def export(objectslist, filename, argstring):
    if not processArguments(argstring):
        return None
    global UNITS
    global UNIT_FORMAT
    global UNIT_SPEED_FORMAT
    global HORIZRAPID
    global VERTRAPID
    global USE_TLO

    for obj in objectslist:
        if not hasattr(obj, "Path"):
            print(
                "the object " + obj.Name + " is not a path. Please select only path and Compounds."
            )
            return None

    machine = None
    if MACHINE:
        try:
            machine = Machine(MACHINE)
        except Exception as problem:
            FreeCAD.Console.PrintError("fanuc_tcp_kin5ax: the machine cannot be used: %s\n" % problem)
            return None
        # the length of the tool is in the model the solver is given, so the joint values it answers
        # with already allow for it: a tool length offset on top would apply it twice
        USE_TLO = False

    # print("postprocessing...")  # Commented to reduce test noise
    gcode = ""

    gcode += "%\n"

    # write header
    if OUTPUT_HEADER:
        # Get current version info
        major = int(FreeCAD.ConfigGet("BuildVersionMajor"))
        minor = int(FreeCAD.ConfigGet("BuildVersionMinor"))

        # the filename variable always contain "-", use more relevant
        # information
        job = PathUtils.findParentJob(objectslist[0])
        if job:
            body, job = job.FullName.split("#")
        else:
            # Workaround for the TestFanucPost code, where there is no
            # job returned by findParentJob
            body, job = ("FREECAD-FILENAME-GOES-HERE", "JOB-NAME-GOES-HERE")
        gcode += "(" + body.upper() + ", " + job.upper() + ")\n"
        gcode += (
            linenumber() + "(POST PROCESSOR: FANUC USING FREECAD %d.%d" % (major, minor) + ")\n"
        )
        gcode += linenumber() + "(OUTPUT TIME:" + str(now).upper() + ")\n"

    # Write the preamble
    if OUTPUT_COMMENTS:
        gcode += linenumber() + "(BEGIN PREAMBLE)\n"
    for line in PREAMBLE.splitlines():
        gcode += linenumber() + line + "\n"
    gcode += linenumber() + UNITS + "\n"

    for obj in objectslist:

        # to stay compatible with FreeCAD 1.0
        def activeForOp(obj):
            # The activeForOp method is available since 2025-05-04 /
            # commit 1e87d8e6681b755b9757f94b1201e50eb84b28a2
            if hasattr(PathUtil, "activeForOp"):
                return PathUtil.activeForOp(obj)
            if hasattr(obj, "Active"):
                return obj.Active
            if hasattr(obj, "Base") and hasattr(obj.Base, "Active"):
                return obj.Base.Active
            return True

        # Skip inactive operations
        if not activeForOp(obj):
            continue

        # do the pre_op
        if OUTPUT_COMMENTS:
            gcode += linenumber() + "(BEGIN OPERATION: %s)\n" % obj.Label.upper()
            gcode += linenumber() + "(MACHINE UNITS: %s)\n" % (UNIT_SPEED_FORMAT.upper())
        for line in PRE_OPERATION.splitlines(True):
            gcode += linenumber() + line

        # to stay compatible with FreeCAD 1.0
        def coolantModeForOp(obj):
            # The coolantModeForOp method is available since
            # 2025-05-04 / commit
            # 1e87d8e6681b755b9757f94b1201e50eb84b28a2
            if hasattr(PathUtil, "coolantModeForOp"):
                return PathUtil.coolantModeForOp(obj)
            if (
                hasattr(obj, "CoolantMode")
                or hasattr(obj, "Base")
                and hasattr(obj.Base, "CoolantMode")
            ):
                if hasattr(obj, "CoolantMode"):
                    return obj.CoolantMode
                else:
                    return obj.Base.CoolantMode
            return "None"

        # get coolant mode
        coolantMode = coolantModeForOp(obj)

        # turn coolant on if required
        if OUTPUT_COMMENTS:
            if not coolantMode == "None":
                gcode += linenumber() + "(COOLANT ON:" + coolantMode.upper() + ")\n"
        if coolantMode == "Flood":
            gcode += linenumber() + "M8" + "\n"
        if coolantMode == "Mist":
            gcode += linenumber() + "M7" + "\n"

        # with a machine, every move of an operation is solved and written as the five axes
        if machine is not None and hasMoves(obj):
            try:
                gcode += machine.parse(obj)
            except Exception as problem:
                FreeCAD.Console.PrintError("fanuc_tcp_kin5ax: %s: %s\n" % (obj.Label, problem))
                return None
            if OUTPUT_COMMENTS:
                gcode += linenumber() + "(FINISH OPERATION: %s)\n" % obj.Label.upper()
            for line in POST_OPERATION.splitlines(True):
                gcode += linenumber() + line
            if not coolantMode == "None":
                if OUTPUT_COMMENTS:
                    gcode += linenumber() + "(COOLANT OFF:" + coolantMode.upper() + ")\n"
                gcode += linenumber() + "M9" + "\n"
            continue

        # switch tool centre point control on for an operation that commands the tool axis: in
        # G43.5 the control is told where the tip of the tool goes and which way the tool points,
        # and works out the rotary axes itself
        leaning = USE_TCP and toolAxisVector(obj)
        if leaning:
            offset = toolLengthOffsetNumber(obj)
            if offset is None:
                FreeCAD.Console.PrintWarning(
                    "fanuc_tcp_kin5ax: %s commands the tool axis but has no tool number, so %s is "
                    "written without an H word\n" % (obj.Label, TCP_COMMAND))
                tcp = TCP_COMMAND
            else:
                tcp = "%s H%d" % (TCP_COMMAND, offset)
            if OUTPUT_COMMENTS:
                gcode += linenumber() + "(TOOL CENTRE POINT CONTROL ON: %s)\n" % tcp
            gcode += linenumber() + tcp + "\n"

        # process the operation gcode
        gcode += parse(obj)

        if leaning:
            if OUTPUT_COMMENTS:
                gcode += linenumber() + (
                    "(TOOL CENTRE POINT CONTROL OFF - %s CANCELS THE TOOL LENGTH OFFSET TOO)\n"
                    % TCP_CANCEL)
            gcode += linenumber() + TCP_CANCEL + "\n"

        # do the post_op
        if OUTPUT_COMMENTS:
            gcode += linenumber() + "(FINISH OPERATION: %s)\n" % obj.Label.upper()
        for line in POST_OPERATION.splitlines(True):
            gcode += linenumber() + line

        # turn coolant off if required
        if not coolantMode == "None":
            if OUTPUT_COMMENTS:
                gcode += linenumber() + "(COOLANT OFF:" + coolantMode.upper() + ")\n"
            gcode += linenumber() + "M9" + "\n"

    if END_SPINDLE_EMPTY:
        if OUTPUT_COMMENTS:
            gcode += "(BEGIN MAKING SPINDLE EMPTY)\n"
        gcode += linenumber() + "M05\n"
        for line in TOOL_CHANGE.splitlines(True):
            gcode += linenumber() + line
        gcode += linenumber() + "M6 T0\n"
    # do the post_amble
    if OUTPUT_COMMENTS:
        gcode += "(BEGIN POSTAMBLE)\n"
    for line in POSTAMBLE.splitlines():
        gcode += linenumber() + line + "\n"

    if FreeCAD.GuiUp and SHOW_EDITOR:
        dia = PostUtils.GCodeEditorDialog()
        dia.editor.setText(gcode)
        result = dia.exec_()
        if result:
            final = dia.editor.toPlainText()
        else:
            final = gcode
    else:
        final = gcode

    # print("done postprocessing.")  # Commented to reduce test noise

    if not filename == "-":
        gfile = pyopen(filename, "w")
        gfile.write(final)
        gfile.close()

    return final


def toolAxisVector(pathobj):
    """Whether the path of this object commands the tool axis, which is what G43.5 is wanted for.

    I, J and K on a linear move are the axis of the tool; on an arc they are the
    centre of it, which says nothing about how the tool is held.
    """
    if not hasattr(pathobj, "Path") or pathobj.Path is None:
        return False
    for command in pathobj.Path.Commands:
        if command.Name in LINEAR_COMMANDS:
            for word in ("I", "J", "K"):
                if word in command.Parameters:
                    return True
    return False


def toolLengthOffsetNumber(pathobj):
    """The H number G43.5 is given, which is the tool number of the operation, or None."""
    controller = getattr(pathobj, "ToolController", None)
    number = getattr(controller, "ToolNumber", None)
    if number:
        return int(number)
    return None


def hasMoves(pathobj):
    """Whether this object moves the tool at all: a tool controller or a fixture does not."""
    if not hasattr(pathobj, "Path") or pathobj.Path is None:
        return False
    for command in pathobj.Path.Commands:
        if command.Name in LINEAR_COMMANDS or command.Name in ARC_COMMANDS:
            return True
        if command.Name.startswith("G8") or command.Name.startswith("G7"):
            return True
    return False


def formatLength(value_mm):
    """A length in mm as the post writes lengths: in the units of the output, to its precision."""
    pos = Units.Quantity(value_mm, FreeCAD.Units.Length)
    return format(float(pos.getValueAs(UNIT_FORMAT)), "." + str(PRECISION) + "f")


def noNegativeZero(text):
    """A -0.000 is a 0.000: the sign of a rounding error is nothing to write down."""
    if text.startswith("-") and float(text) == 0.0:
        return text[1:]
    return text


def formatFeed(value):
    speed = Units.Quantity(value, FreeCAD.Units.Velocity)
    return format(float(speed.getValueAs(UNIT_SPEED_FORMAT)), "." + str(PRECISION) + "f")


class Machine(object):
    """A machine of kin5ax, and the solving of an operation's moves for it.

    Opened once per export, with the chain file and the settings the arguments
    asked for. parse() takes an operation and gives back its G-code, the moves
    as joint values; the tool is made from the tool controller of the operation
    each time, since operations have tools of their own.
    """

    def __init__(self, chain_file):
        from kin5axcam import kin5ax

        self.kin5ax = kin5ax
        self.chain = kin5ax.Chain(chain_file)
        if not self.chain.is_5c():
            raise ValueError("%s is not a five-axis chain of three linear and two rotary joints"
                             % chain_file)
        self.scale = MACHINE_UNIT_IN_MM          # mm per unit of the chain file
        self.axes = self.chain.default_gcode_axes()
        self.letters = self.rotaryLetters()
        self.settings = self.makeSettings()
        self.links = self.chain.links()

    def rotaryLetters(self):
        """What the control calls the two rotary axes: the argument, the names of the links, the guess."""
        if ROTARY_LETTERS:
            return ROTARY_LETTERS[0], ROTARY_LETTERS[1]
        links = self.chain.links()
        letters = []
        for index in (self.axes.angle1, self.axes.angle2):
            name = links[index].name.strip().upper()
            letters.append(name if name in ("A", "B", "C") else None)
        if None in letters or letters[0] == letters[1]:
            return self.axes.angle1_letter, self.axes.angle2_letter
        return letters[0], letters[1]

    def makeSettings(self):
        kin5ax = self.kin5ax
        settings = kin5ax.Settings.default()
        settings.check_limits = 1 if CHECK_LIMITS else 0
        settings.check_collisions = 1 if CHECK_COLLISIONS else 0
        settings.interpolate = 1 if INTERPOLATE else 0
        if MAX_STEP_MM is not None:
            settings.max_position_difference = MAX_STEP_MM / self.scale
        if MAX_TURN_DEGREES is not None:
            settings.max_orientation_difference_degrees = MAX_TURN_DEGREES
        if START_CRITERION is not None:
            settings.start_criterion = {
                "MIN": kin5ax.START_MIN, "MAX": kin5ax.START_MAX,
                "MIN_ABS": kin5ax.START_MIN_ABS, "SHORTEST": kin5ax.START_SHORTEST_PATH,
            }[START_CRITERION]
        return settings

    def makeTool(self, pathobj):
        """The tool of the operation as kin5ax sees it, or None when the operation has none.

        A ball nose bit is a ball of half its diameter, programmed at the centre
        of the ball; anything else is a flat end of half its diameter, programmed
        at the tip. The shank is taken as wide as the cutter, which flags a
        collision sooner rather than later. The holder is what the arguments say,
        a tool bit not describing one.
        """
        kin5ax = self.kin5ax
        controller = getattr(pathobj, "ToolController", None)
        tool = getattr(controller, "Tool", None)
        if tool is None:
            return None
        diameter = float(getattr(getattr(tool, "Diameter", 0.0), "Value", getattr(tool, "Diameter", 0.0)))
        if diameter <= 0.0:
            return None
        shape = str(getattr(tool, "ShapeType", "") or getattr(tool, "ShapeName", "")).lower()
        cutting = float(getattr(getattr(tool, "CuttingEdgeHeight", 0.0), "Value",
                                getattr(tool, "CuttingEdgeHeight", 0.0)))
        length = float(getattr(getattr(tool, "Length", 0.0), "Value", getattr(tool, "Length", 0.0)))
        if cutting <= 0.0:
            cutting = 2.0 * diameter
        shank = max(length - cutting, 0.0)
        radius = 0.5 * diameter / self.scale
        kind = kin5ax.TOOL_BALL_NOSE if shape in ("ballend", "ballnose", "taperedballnose") \
            else kin5ax.TOOL_FLAT_END
        return kin5ax.Tool(kind, radius, radius, cutting / self.scale, shank / self.scale,
                           HOLDER_LENGTH_MM / self.scale, HOLDER_RADIUS_MM / self.scale)

    def collect(self, pathobj):
        """The moves of the operation as locations for the solver, and everything else as it is.

        A list of entries in the order of the path: ("move", command, point_mm,
        axis, feed) for G0 and G1, ("other", command) for the rest. The point is
        the tip of the tool, carried forward word by word the way a control
        carries it; the axis is the last I J K seen, which is the tool standing up
        until a move says otherwise. The first moves, before all three of X, Y
        and Z have been given, are folded into the first move that has them: a
        machine cannot be sent to a point it has not been told the whole of.
        """
        entries = []
        current = {}
        axis = VERTICAL
        pending = None
        for command in PathUtils.getPathWithPlacement(pathobj).Commands:
            name = command.Name
            if name in ARC_COMMANDS or name.startswith("G8") or name.startswith("G7"):
                raise ValueError("%s is a %s, which the solver does not take: an arc has to be "
                                 "written as lines and a cycle as moves before it can be solved"
                                 % (pathobj.Label, name))
            if name not in LINEAR_COMMANDS:
                entries.append(("other", command))
                continue
            parameters = command.Parameters
            for word in ("X", "Y", "Z"):
                if word in parameters:
                    current[word] = float(parameters[word])
            if all(word in parameters for word in ("I", "J", "K")):
                axis = (float(parameters["I"]), float(parameters["J"]), float(parameters["K"]))
            feed = float(parameters["F"]) if "F" in parameters else None
            if not all(word in current for word in ("X", "Y", "Z")):
                pending = (name, feed)
                continue
            if pending is not None:
                name = pending[0] if pending[0] in RAPID_COMMANDS else name
                pending = None
            entries.append(("move", name, (current["X"], current["Y"], current["Z"]), axis, feed))
        return entries

    def parse(self, pathobj):
        """The G-code of one operation: its moves solved for this machine."""
        kin5ax = self.kin5ax
        entries = self.collect(pathobj)
        moves = [entry for entry in entries if entry[0] == "move"]
        tool = self.makeTool(pathobj)
        if tool is None and CHECK_COLLISIONS:
            raise ValueError("%s has no tool to check collisions with: pick a tool controller, or "
                             "post with --no-collisions" % pathobj.Label)

        # the programmed point: the ball nose tool of kin5ax is programmed at the centre of its ball,
        # one radius up the axis from the tip the path carries
        positions, vectors = [], []
        for _, _, point, axis, _ in moves:
            lift = tool.r if (tool is not None and tool.shape == kin5ax.TOOL_BALL_NOSE) else 0.0
            positions.append(tuple(point[i] / self.scale + lift * axis[i] for i in range(3)))
            vectors.append(axis)
        path = self.chain.postprocess_locations(positions, vectors, self.settings, tool)

        # the solved locations, back in the order of the path: a location of the file is its move,
        # one invented on the way to the next belongs to that next move
        solved = {}
        unsolved = []
        for location in path.locations():
            index = location.file_location - 1
            if location.origin != kin5ax.FROM_FILE:
                index = min(index + 1, len(moves) - 1)
            solved.setdefault(index, []).append(location)
            if not location.has_solution:
                unsolved.append((index, location))
        report = path.report()
        position_error, orientation_error = path.errors()
        path.close()
        if tool is not None:
            tool.close()

        out = ""
        if OUTPUT_COMMENTS:
            out += linenumber() + "(SOLVED FOR %s BY KIN5AX %s: AXES %s %s, TOOL LENGTH IN THE MODEL)\n" % (
                self.chain.name().upper(), kin5ax.version(), self.letters[0], self.letters[1])
        last = {}
        lastcommand = None
        lastfeed = None
        move_index = -1
        for entry in entries:
            if entry[0] == "other":
                command = entry[1]
                if command.Name.startswith("(") and not OUTPUT_COMMENTS:
                    continue
                words = [command.Name] + ["%s%s" % (k, v) for k, v in command.Parameters.items()]
                out += linenumber() + COMMAND_SPACE.join(words).upper() + "\n"
                continue
            move_index += 1
            _, name, point, axis, feed = entry
            for location in solved.get(move_index, []):
                if not location.has_solution:
                    if OUTPUT_COMMENTS:
                        out += linenumber() + "(UNSOLVED: %s AT X%s Y%s Z%s)\n" % (
                            location.status_name.upper(), formatLength(point[0]),
                            formatLength(point[1]), formatLength(point[2]))
                    continue
                words = []
                if not (MODAL and name == lastcommand):
                    words.append(name)
                for letter, index, scale, unlimited in self.axisWords():
                    value = location.q[index] * scale
                    if unlimited:
                        value = self.nearestTurn(value, last.get(letter))
                    text = noNegativeZero(formatLength(value) if letter in "XYZ"
                                          else format(value, "." + str(PRECISION) + "f"))
                    #the same word as the line before is left out, the comparison being made on
                    #what would be written: a solution differs from the last by 1E-16 and means it
                    if OUTPUT_DOUBLES or last.get(letter) != text:
                        words.append(letter + text)
                        last[letter] = text
                if feed and name not in RAPID_COMMANDS and (feed != lastfeed or OUTPUT_DOUBLES):
                    words.append("F" + formatFeed(feed))
                    lastfeed = feed
                if words:
                    out += linenumber() + COMMAND_SPACE.join(words).upper() + "\n"
                lastcommand = name
        if OUTPUT_COMMENTS:
            out += linenumber() + "(KIN5AX: %s; LARGEST ERRORS %.3g MM AND %.3g)\n" % (
                ", ".join("%d %s" % (count, status.upper()) for status, count in sorted(report.items())),
                position_error * self.scale, orientation_error)
        if unsolved:
            FreeCAD.Console.PrintWarning(
                "fanuc_tcp_kin5ax: %s: %d of %d locations have no solution on %s - %s\n" % (
                    pathobj.Label, len(unsolved), sum(len(v) for v in solved.values()),
                    self.chain.name(), ", ".join("%d %s" % (count, status)
                                                 for status, count in sorted(report.items()))))
        return out

    def axisWords(self):
        """The words of a solved line in the order the post writes them: X Y Z, then the rotary letters.

        Each is (letter, index into q, factor from the joint value to the word,
        whether the axis turns without limits): mm per unit of the file for a
        length, degrees per radian for an angle.
        """
        degrees = 180.0 / math.pi
        rotary = []
        for letter, index in ((self.letters[0], self.axes.angle1), (self.letters[1], self.axes.angle2)):
            rotary.append((letter, index, degrees, not self.links[index].constrained))
        rotary.sort(key=lambda w: w[0])
        return [("X", self.axes.x, self.scale, False), ("Y", self.axes.y, self.scale, False),
                ("Z", self.axes.z, self.scale, False)] + rotary

    @staticmethod
    def nearestTurn(degrees, previous):
        """The equivalent of an angle nearest the one written before, for an axis that turns freely.

        The solver hands back one representative of a class of equivalents - 90
        and -270 are the same position of a rotary table - and may hand back a
        different one for the next location. Written as they come, the two are a
        full turn apart and the control turns the table through it. An axis
        without limits is the same axis a turn on, so the nearest is written.
        """
        if previous is None:
            return degrees
        try:
            previous = float(previous)
        except (TypeError, ValueError):
            return degrees
        while degrees - previous > 180.0:
            degrees -= 360.0
        while previous - degrees > 180.0:
            degrees += 360.0
        return degrees

    def close(self):
        self.chain.close()


def linenumber():
    global LINENR
    if OUTPUT_LINE_NUMBERS is True:
        LINENR += 10
        return "N" + str(LINENR) + " "
    return ""


def parse(pathobj):
    global PRECISION
    global DRILL_OPERATION
    global DRILL_PARAM_REQ
    global MODAL
    global OUTPUT_DOUBLES
    global UNIT_FORMAT
    global UNIT_SPEED_FORMAT
    global tapSpeed

    out = ""
    lastcommand = None
    precision_string = "." + str(PRECISION) + "f"
    vector_string = "." + str(VECTOR_PRECISION) + "f"
    currLocation = {}  # keep track for no doubles

    # the order of parameters
    # arcs need work.  original code from mach3_4 doesn't want K properties on XY plane.  Not sure
    # what fanuc does here.
    params = [
        "X",
        "Y",
        "Z",
        "A",
        "B",
        "C",
        "I",
        "J",
        "K",
        "F",
        "S",
        "T",
        "Q",
        "R",
        "L",
        "H",
        "D",
        "P",
    ]
    firstmove = Path.Command("G0", {"X": -1, "Y": -1, "Z": -1, "F": 0.0})
    currLocation.update(firstmove.Parameters)  # set First location Parameters

    if hasattr(pathobj, "Group"):  # We have a compound or project.
        # if OUTPUT_COMMENTS:
        #     out += linenumber() + "(compound: " + pathobj.Label + ")\n"
        for p in pathobj.Group:
            out += parse(p)
        return out
    else:  # parsing simple path

        # groups might contain non-path things like stock.
        if not hasattr(pathobj, "Path"):
            return out

        # if OUTPUT_COMMENTS:
        #     out += linenumber() + "(" + pathobj.Label + ")\n"

        adaptiveOp = False
        opHorizRapid = 0
        opVertRapid = 0

        if "Adaptive" in pathobj.Name:
            adaptiveOp = True
            if hasattr(pathobj, "ToolController"):
                if (
                    hasattr(pathobj.ToolController, "HorizRapid")
                    and pathobj.ToolController.HorizRapid > 0
                ):
                    opHorizRapid = Units.Quantity(
                        pathobj.ToolController.HorizRapid, FreeCAD.Units.Velocity
                    )
                else:
                    FreeCAD.Console.PrintWarning(
                        "Tool Controller Horizontal Rapid Values are unset" + "\n"
                    )

                if (
                    hasattr(pathobj.ToolController, "VertRapid")
                    and pathobj.ToolController.VertRapid > 0
                ):
                    opVertRapid = Units.Quantity(
                        pathobj.ToolController.VertRapid, FreeCAD.Units.Velocity
                    )
                else:
                    FreeCAD.Console.PrintWarning(
                        "Tool Controller Vertical Rapid Values are unset" + "\n"
                    )

        commands = PathUtils.getPathWithPlacement(pathobj).Commands
        for index, c in enumerate(commands):

            outstring = []
            outsuffix = []
            command = c.Name
            if index + 1 == len(commands):
                nextcommand = ""
            else:
                nextcommand = commands[index + 1].Name

            if adaptiveOp and c.Name in ["G0", "G00"]:
                if opHorizRapid and opVertRapid:
                    command = "G1"
                else:
                    outstring.append("(TOOL CONTROLLER RAPID VALUES ARE UNSET)" + "\n")

            # suppress moves in fixture selection
            if pathobj.Label == "Fixture":
                if command == "G0":
                    continue

            # If tool a tap, we will thread tap, so stop the spindle
            # for now as there is no point in starting it to stop it
            # in the G74/G84 operation after S29.  This only trigger
            # when pathobj is a ToolController.
            if command == "M03" or command == "M3":
                if (
                    hasattr(pathobj, "Tool")
                    and getattr(pathobj.Tool, "ShapeType", "").lower() == "tap"
                ):
                    tapSpeed = int(pathobj.SpindleSpeed)
                    continue

            # Handle thread tapping cycles.  Uses rigid tapping.
            # This only trigger when pathobj is a Operation.
            if command == "G74" or command == "G84":
                pitch_mm = float(c.Parameters["F"])
                # Convert pitch to inches if needed
                if UNITS == "G20":  # imperial
                    pitch = pitch_mm / 25.4
                else:
                    pitch = pitch_mm
                paramstring = ""
                for param in ["X", "Y"]:
                    if param in c.Parameters:
                        if (
                            (not OUTPUT_DOUBLES)
                            and (param in currLocation)
                            and (currLocation[param] == c.Parameters[param])
                        ):
                            continue
                        else:
                            pos = Units.Quantity(c.Parameters[param], FreeCAD.Units.Length)
                            paramstring += (
                                " "
                                + param
                                + format(
                                    float(pos.getValueAs(UNIT_FORMAT)),
                                    precision_string,
                                )
                            )
                if paramstring != "":
                    out += linenumber() + "G00" + paramstring + "\n"

                if "S" in c.Parameters:
                    tapSpeed = int(c.Parameters["S"])
                out += "M29 S" + str(tapSpeed) + "\n"

                for param in ["Z", "R"]:
                    if param in c.Parameters:
                        if (
                            (not OUTPUT_DOUBLES)
                            and (param in currLocation)
                            and (currLocation[param] == c.Parameters[param])
                        ):
                            continue
                        else:
                            pos = Units.Quantity(c.Parameters[param], FreeCAD.Units.Length)
                            paramstring += (
                                " "
                                + param
                                + format(
                                    float(pos.getValueAs(UNIT_FORMAT)),
                                    precision_string,
                                )
                            )

                # Calculate feed rate as distance per minute
                if tapSpeed is not None:
                    feed_rate = pitch * tapSpeed
                    speed = Units.Quantity(feed_rate, UNIT_SPEED_FORMAT)
                    paramstring += " F" + format(
                        float(speed.getValueAs(UNIT_SPEED_FORMAT)), precision_string
                    )
                else:
                    # No spindle speed found, output pitch as F
                    paramstring += " F" + format(pitch, precision_string)

                # P is the dwell time in seconds at the bottom of the thread
                # Q is the peck depth of the threading operation
                for param in ["P", "Q"]:
                    if param in c.Parameters:
                        value = Units.Quantity(c.Parameters[param], FreeCAD.Units.Length)
                        paramstring += (
                            " "
                            + param
                            + format(
                                float(value.getValueAs(UNIT_FORMAT)),
                                precision_string,
                            )
                        )

                out += linenumber() + command + paramstring + "\n"
                out += linenumber() + "G80\n"  # End tapping cycle
                continue

            outstring.append(command)

            # if modal: suppress the command if it is the same as the last one
            if MODAL is True:
                if command == lastcommand:
                    outstring.pop(0)

            # suppress a G80 between two identical command
            if command == "G80" and lastcommand == nextcommand:
                continue

            if c.Name.startswith("(") and not OUTPUT_COMMENTS:  # command is a comment
                continue

            # Now add the remaining parameters in order
            for param in params:
                if param in c.Parameters:
                    if param == "F" and (
                        currLocation[param] != c.Parameters[param] or OUTPUT_DOUBLES
                    ):
                        if c.Name not in [
                            "G0",
                            "G00",
                        ]:  # fanuc doesn't use rapid speeds
                            speed = Units.Quantity(c.Parameters["F"], FreeCAD.Units.Velocity)
                            if speed.getValueAs(UNIT_SPEED_FORMAT) > 0.0:
                                outstring.append(
                                    param
                                    + format(
                                        float(speed.getValueAs(UNIT_SPEED_FORMAT)),
                                        precision_string,
                                    )
                                )
                            else:
                                continue
                    elif param == "T":
                        outstring.append(param + str(int(c.Parameters["T"])))
                    elif param == "H":
                        outstring.append(param + str(int(c.Parameters["H"])))
                    elif param == "D":
                        outstring.append(param + str(int(c.Parameters["D"])))
                    elif param == "S":
                        outstring.append(param + str(int(c.Parameters["S"])))
                    elif param in ("I", "J", "K") and c.Name in LINEAR_COMMANDS:
                        # the tool axis vector. A direction, so it is not converted into the units
                        # of the output the way a length is, and it is written every time: a
                        # direction that repeats is a tool that is still pointing the same way, and
                        # a reader that has to remember the last one it saw is a reader that can be
                        # wrong about which move it belongs to.
                        outstring.append(
                            param + format(float(c.Parameters[param]), vector_string))
                    else:
                        if (
                            (not OUTPUT_DOUBLES)
                            and (param in currLocation)
                            and currLocation[param] == c.Parameters[param]
                            and (
                                command not in DRILL_OPERATION
                                or (command in DRILL_OPERATION and param not in DRILL_PARAM_REQ)
                            )
                        ):
                            continue
                        else:
                            pos = Units.Quantity(c.Parameters[param], FreeCAD.Units.Length)
                            outstring.append(
                                param + format(float(pos.getValueAs(UNIT_FORMAT)), precision_string)
                            )

            if adaptiveOp and c.Name in ["G0", "G00"]:
                if opHorizRapid and opVertRapid:
                    if "Z" not in c.Parameters:
                        outstring.append(
                            "F"
                            + format(
                                float(opHorizRapid.getValueAs(UNIT_SPEED_FORMAT)),
                                precision_string,
                            )
                        )
                    else:
                        outstring.append(
                            "F"
                            + format(
                                float(opVertRapid.getValueAs(UNIT_SPEED_FORMAT)),
                                precision_string,
                            )
                        )

            # store the latest command
            lastcommand = command
            currLocation.update(c.Parameters)

            # Check for Tool Change:
            if command == "M6":
                # stop the spindle
                out += linenumber() + "M05\n"
                for line in TOOL_CHANGE.splitlines(True):
                    out += linenumber() + line

                # add height offset
                if USE_TLO:
                    outsuffix.append("G91 G0 G43 G54 Z-[#[2000+#4120]] H#4120")
                    outsuffix.append("G90")

            if command == "message":
                if OUTPUT_COMMENTS is False:
                    out = []
                else:
                    outstring.pop(0)  # remove the command

            # prepend a line number and append a newline
            if len(outstring) >= 1:
                if OUTPUT_LINE_NUMBERS:
                    outstring.insert(0, (linenumber()))

                # append the line to the final output
                out += COMMAND_SPACE.join(outstring).upper()
                out = out.strip() + "\n"
            if len(outsuffix) >= 1:
                for line in outsuffix:
                    out += linenumber() + line + "\n"

        return out


# print(__name__ + " gcode postprocessor loaded.")
