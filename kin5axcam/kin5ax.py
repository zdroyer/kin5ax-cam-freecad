"""kin5ax from Python: the C interface of the library, reached through ctypes. No FreeCAD in it.

The library solves the inverse kinematics of a five-axis machine: given where the
programmed point of the tool has to be and which way the tool has to point, in
the frame of the material, it answers with the five joint values that put it
there - or with the reason there are none. This module is that interface and
nothing more; the names follow ``kin5axc/include/kin5ax.h``, which is the one
authority on what each call means.

    from kin5axcam import kin5ax
    with kin5ax.Chain("Reiden_RX10.kc.json") as chain:
        tool = kin5ax.Tool(kin5ax.TOOL_BALL_NOSE, rz=0.008, r=0.008, cutting_height=0.040,
                           shank_length=0.030, holder_length=0.050, holder_radius=0.030)
        path = chain.postprocess_locations(positions, axes, kin5ax.Settings.default(), tool)
        for location in path.locations():
            if location.has_solution:
                print(location.q)

**Lengths are in the unit of the chain file**, which is metres for every machine
shipped with the library, and the files do not say so themselves. Nothing here
converts: the caller scales on the way in and on the way out, and says what it
scaled by. Angles are radians.

**Where the shared library is.** ``kin5axc.dll`` or ``libkin5axc.so`` is looked
for in this order: the path in the environment variable ``KIN5AXC_LIBRARY``; the
``lib`` folder of the addon; the build trees of a checkout of the repository,
for development; and finally wherever the system loader finds a library of that
name. ``library_candidates()`` lists them and the error of a failed load names
every one that was tried.
"""

import ctypes
import ctypes.util
import os
import sys

AXES = 5                                #the five joints of a five-axis machine
NAME_MAX = 64                           #the longest name of a link, terminating zero included

#k5_status: what a call can answer
OK = 0
ERROR_ARGUMENT = 1
ERROR_BUFFER_TOO_SMALL = 2
ERROR_FILE = 3
ERROR_CHAIN = 4
ERROR_SOLVER = 5
ERROR_UNKNOWN = 6

#k5_solve_status: why a cutter location has the solutions it has
SOLVED = 0
NO_ORIENTATION = 1
NO_POSITION = 2
LIMITS_EXCEEDED = 3
COLLISION = 4
SINGULAR_UNSOLVED = 5

SOLVE_STATUS_NAMES = {
    SOLVED: "solved",
    NO_ORIENTATION: "no joint angles put the tool axis where it was asked for",
    NO_POSITION: "angles found, but the linear axes reach the point for none of them",
    LIMITS_EXCEEDED: "every configuration is out of the joint limits",
    COLLISION: "every configuration within the limits collides",
    SINGULAR_UNSOLVED: "a location of a singular section the interpolated angle did not solve",
}

#k5_location_origin: where a location of a solved path came from
FROM_FILE = 0
INTERPOLATED = 1
SINGULAR_SECTION = 2

#k5_link_type
LINK_PRISMATIC = 0
LINK_REVOLUTE = 1

#k5_chain_part
PART_TOOL = 0
PART_MATERIAL_HOLDER = 1

#k5_tool_shape
TOOL_BALL_NOSE = 0                      #a ball of radius r at the tip, programmed at its centre
TOOL_FLAT_END = 1                       #a cylinder of radius rz, programmed at the tip

#k5_start_criterion: how the first configuration of a trajectory is chosen
START_SHORTEST_PATH = 0
START_MIN = 1
START_MAX = 2
START_MIN_ABS = 3
START_RANDOM = 4


class Kin5axError(Exception):
    """A call of the library that did not return OK, with the message it left behind."""

    def __init__(self, status, message, call=""):
        Exception.__init__(self, "%s%s (status %d)" % (call + ": " if call else "", message, status))
        self.status = status
        self.message = message


class LibraryNotFound(Kin5axError):
    """The shared library is nowhere this module knows to look."""

    def __init__(self, tried):
        message = ("the kin5axc shared library was not found. Looked for: %s. Set KIN5AXC_LIBRARY to "
                   "the file, or put it in the lib folder of the addon." % ", ".join(tried))
        Kin5axError.__init__(self, ERROR_FILE, message)
        self.tried = tried


# ---------------------------------------------------------------- the structures of the header

class Settings(ctypes.Structure):
    """k5_settings: the settings of a run."""

    _fields_ = [
        ("check_limits", ctypes.c_int),
        ("check_collisions", ctypes.c_int),
        ("interpolate", ctypes.c_int),
        ("max_position_difference", ctypes.c_double),
        ("max_orientation_difference_degrees", ctypes.c_double),
        ("angle_distance_weight", ctypes.c_double),
        ("displacement_weight", ctypes.c_double),
        ("start_criterion", ctypes.c_int),
        ("start_count_from_tool", ctypes.c_int),
        ("start_random_seed", ctypes.c_uint),
    ]

    @classmethod
    def default(cls, library=None):
        """The settings the library recommends: both checks on, interpolation on, start closest to zero."""
        settings = cls()
        load(library).k5_settings_default(ctypes.byref(settings))
        return settings


class Link(ctypes.Structure):
    """k5_link: one joint of the machine."""

    _fields_ = [
        ("type", ctypes.c_int),
        ("constrained", ctypes.c_int),
        ("minimum", ctypes.c_double),
        ("maximum", ctypes.c_double),
        ("value", ctypes.c_double),
        ("_name", ctypes.c_char * NAME_MAX),
    ]

    @property
    def name(self):
        return self._name.decode("utf-8", "replace")

    @property
    def is_revolute(self):
        return self.type == LINK_REVOLUTE

    def __repr__(self):
        return "Link(%r, %s%s)" % (self.name, "revolute" if self.is_revolute else "prismatic",
                                   ", %g..%g" % (self.minimum, self.maximum) if self.constrained else "")


class Location(ctypes.Structure):
    """k5_location: one location of a solved path and what became of it."""

    _fields_ = [
        ("status", ctypes.c_int),
        ("origin", ctypes.c_int),
        ("file_location", ctypes.c_size_t),
        ("file_line", ctypes.c_size_t),
        ("_has_solution", ctypes.c_int),
        ("_q", ctypes.c_double * AXES),
    ]

    @property
    def has_solution(self):
        return bool(self._has_solution)

    @property
    def q(self):
        """The joint values chosen for this location, in the order of Chain.links(), or None."""
        return tuple(self._q) if self._has_solution else None

    @property
    def status_name(self):
        return SOLVE_STATUS_NAMES.get(self.status, "status %d" % self.status)

    def __repr__(self):
        return "Location(%s, origin %d, from %d, q=%r)" % (self.status_name, self.origin,
                                                           self.file_location, self.q)


class GcodeAxes(ctypes.Structure):
    """k5_gcode_axes: which joint is which word of a G-code line."""

    _fields_ = [
        ("x", ctypes.c_size_t),
        ("y", ctypes.c_size_t),
        ("z", ctypes.c_size_t),
        ("angle1", ctypes.c_size_t),
        ("angle2", ctypes.c_size_t),
        ("_angle1_letter", ctypes.c_char),
        ("_angle2_letter", ctypes.c_char),
        ("degrees", ctypes.c_int),
    ]

    @property
    def angle1_letter(self):
        return self._angle1_letter.decode("ascii")

    @angle1_letter.setter
    def angle1_letter(self, letter):
        self._angle1_letter = letter.encode("ascii")

    @property
    def angle2_letter(self):
        return self._angle2_letter.decode("ascii")

    @angle2_letter.setter
    def angle2_letter(self, letter):
        self._angle2_letter = letter.encode("ascii")


#the opaque handles
_chain_t = ctypes.c_void_p
_tool_t = ctypes.c_void_p
_path_t = ctypes.c_void_p
_material_t = ctypes.c_void_p
_simulation_t = ctypes.c_void_p
_double_p = ctypes.POINTER(ctypes.c_double)
_size_p = ctypes.POINTER(ctypes.c_size_t)
_int_p = ctypes.POINTER(ctypes.c_int)


# ---------------------------------------------------------------- finding and loading the library

def library_file_name():
    if sys.platform.startswith("win"):
        return "kin5axc.dll"
    if sys.platform == "darwin":
        return "libkin5axc.dylib"
    return "libkin5axc.so"


def library_candidates():
    """Where the shared library is looked for, in order. Only the first that exists is loaded."""
    name = library_file_name()
    #the real path: the addon may be reached through a junction from FreeCAD's Mod folder, and the
    #build trees sit next to where the files really are
    here = os.path.dirname(os.path.realpath(__file__))
    addon = os.path.dirname(here)
    repository = os.path.dirname(addon)
    candidates = []
    if os.environ.get("KIN5AXC_LIBRARY"):
        candidates.append(os.environ["KIN5AXC_LIBRARY"])
    candidates.append(os.path.join(addon, "lib", name))
    #the build trees of a checkout, for development: MSVC puts the configuration in the path
    for build in ("build", "build-win32", "build-linux"):
        for configuration in ("Release", "RelWithDebInfo", "Debug", ""):
            candidates.append(os.path.join(repository, build, "kin5axc", configuration, name))
    candidates.append(os.path.join(os.path.expanduser("~"), "kin5ax-build", "kin5axc", name))
    return candidates


_library = None


def load(path=None):
    """The library, loaded once and kept. path names the file to load instead of searching for it."""
    global _library
    if _library is not None and path is None:
        return _library
    tried = []
    if path is not None:
        tried.append(path)
        library = _load_file(path)
    else:
        library = None
        for candidate in library_candidates():
            tried.append(candidate)
            if os.path.isfile(candidate):
                library = _load_file(candidate)
                break
        if library is None:
            found = ctypes.util.find_library("kin5axc")
            tried.append("the system loader")
            if found:
                library = _load_file(found)
    if library is None:
        raise LibraryNotFound(tried)
    _declare(library)
    _library = library
    return library


def _load_file(path):
    try:
        return ctypes.CDLL(path)
    except OSError as problem:
        raise Kin5axError(ERROR_FILE, "%s cannot be loaded: %s" % (path, problem))


def _declare(lib):
    """The signatures, so that ctypes checks the arguments rather than guessing at them."""
    lib.k5_last_error.restype = ctypes.c_char_p
    lib.k5_last_error.argtypes = []
    lib.k5_version_string.restype = ctypes.c_char_p
    lib.k5_version_string.argtypes = []
    lib.k5_version.restype = None
    lib.k5_version.argtypes = [_int_p, _int_p, _int_p]
    lib.k5_settings_default.restype = None
    lib.k5_settings_default.argtypes = [ctypes.POINTER(Settings)]

    lib.k5_chain_open.restype = ctypes.c_int
    lib.k5_chain_open.argtypes = [ctypes.c_char_p, ctypes.POINTER(_chain_t)]
    lib.k5_chain_free.restype = None
    lib.k5_chain_free.argtypes = [_chain_t]
    lib.k5_chain_name.restype = ctypes.c_int
    lib.k5_chain_name.argtypes = [_chain_t, ctypes.c_char_p, ctypes.c_size_t]
    lib.k5_chain_is_5c.restype = ctypes.c_int
    lib.k5_chain_is_5c.argtypes = [_chain_t, _int_p]
    lib.k5_chain_link_count.restype = ctypes.c_int
    lib.k5_chain_link_count.argtypes = [_chain_t, _size_p]
    lib.k5_chain_link.restype = ctypes.c_int
    lib.k5_chain_link.argtypes = [_chain_t, ctypes.c_size_t, ctypes.POINTER(Link)]
    lib.k5_chain_first_rotary_axis.restype = ctypes.c_int
    lib.k5_chain_first_rotary_axis.argtypes = [_chain_t, ctypes.c_int, _size_p]
    lib.k5_chain_frames.restype = ctypes.c_int
    lib.k5_chain_frames.argtypes = [_chain_t, ctypes.c_int, _double_p, ctypes.c_size_t, _size_p]
    lib.k5_chain_segment_boxes.restype = ctypes.c_int
    lib.k5_chain_segment_boxes.argtypes = [_chain_t, ctypes.c_int, ctypes.c_size_t, _double_p,
                                           ctypes.c_size_t, _size_p]
    lib.k5_chain_set_configuration.restype = ctypes.c_int
    lib.k5_chain_set_configuration.argtypes = [_chain_t, _double_p]
    lib.k5_chain_tool_point.restype = ctypes.c_int
    lib.k5_chain_tool_point.argtypes = [_chain_t, _tool_t, _double_p, _double_p, _double_p]

    lib.k5_tool_create.restype = ctypes.c_int
    lib.k5_tool_create.argtypes = [ctypes.c_int, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                                   ctypes.c_double, ctypes.c_double, ctypes.c_double,
                                   ctypes.POINTER(_tool_t)]
    lib.k5_tool_free.restype = None
    lib.k5_tool_free.argtypes = [_tool_t]
    lib.k5_tool_assembly_length.restype = ctypes.c_int
    lib.k5_tool_assembly_length.argtypes = [_tool_t, _double_p]
    lib.k5_tool_mount_to_point_distance.restype = ctypes.c_int
    lib.k5_tool_mount_to_point_distance.argtypes = [_tool_t, _double_p]

    lib.k5_solve_location.restype = ctypes.c_int
    lib.k5_solve_location.argtypes = [_chain_t, _tool_t, ctypes.POINTER(Settings), _double_p,
                                      _double_p, _double_p, ctypes.c_size_t, _size_p, _int_p]
    lib.k5_postprocess_file.restype = ctypes.c_int
    lib.k5_postprocess_file.argtypes = [_chain_t, _tool_t, ctypes.POINTER(Settings), ctypes.c_char_p,
                                        ctypes.POINTER(_path_t)]
    lib.k5_postprocess_locations.restype = ctypes.c_int
    lib.k5_postprocess_locations.argtypes = [_chain_t, _tool_t, ctypes.POINTER(Settings), _double_p,
                                             _double_p, ctypes.c_size_t, ctypes.POINTER(_path_t)]

    lib.k5_path_free.restype = None
    lib.k5_path_free.argtypes = [_path_t]
    lib.k5_path_size.restype = ctypes.c_int
    lib.k5_path_size.argtypes = [_path_t, _size_p]
    lib.k5_path_location.restype = ctypes.c_int
    lib.k5_path_location.argtypes = [_path_t, ctypes.c_size_t, ctypes.POINTER(Location)]
    lib.k5_path_count_of_status.restype = ctypes.c_int
    lib.k5_path_count_of_status.argtypes = [_path_t, ctypes.c_int, _size_p]
    lib.k5_path_count_of_origin.restype = ctypes.c_int
    lib.k5_path_count_of_origin.argtypes = [_path_t, ctypes.c_int, _size_p]
    lib.k5_path_errors.restype = ctypes.c_int
    lib.k5_path_errors.argtypes = [_path_t, _double_p, _double_p]
    lib.k5_path_last_configuration.restype = ctypes.c_int
    lib.k5_path_last_configuration.argtypes = [_path_t, _double_p]
    lib.k5_material_create.restype = ctypes.c_int
    lib.k5_material_create.argtypes = [ctypes.c_double] * 7 + [ctypes.POINTER(_material_t)]
    lib.k5_material_free.restype = None
    lib.k5_material_free.argtypes = [_material_t]
    lib.k5_material_reset.restype = ctypes.c_int
    lib.k5_material_reset.argtypes = [_material_t]
    lib.k5_material_dimensions.restype = ctypes.c_int
    lib.k5_material_dimensions.argtypes = [_material_t, _size_p, _size_p, _size_p]
    lib.k5_material_volumes.restype = ctypes.c_int
    lib.k5_material_volumes.argtypes = [_material_t, _double_p, _double_p]
    lib.k5_material_surface.restype = ctypes.c_int
    lib.k5_material_surface.argtypes = [_material_t, _double_p, ctypes.c_size_t, _size_p]
    lib.k5_simulation_create.restype = ctypes.c_int
    lib.k5_simulation_create.argtypes = [_chain_t, _tool_t, _path_t, _material_t,
                                         ctypes.POINTER(_simulation_t)]
    lib.k5_simulation_free.restype = None
    lib.k5_simulation_free.argtypes = [_simulation_t]
    lib.k5_simulation_reset.restype = ctypes.c_int
    lib.k5_simulation_reset.argtypes = [_simulation_t]
    lib.k5_simulation_step.restype = ctypes.c_int
    lib.k5_simulation_step.argtypes = [_simulation_t, _int_p]
    lib.k5_simulation_run.restype = ctypes.c_int
    lib.k5_simulation_run.argtypes = [_simulation_t]
    lib.k5_simulation_progress.restype = ctypes.c_int
    lib.k5_simulation_progress.argtypes = [_simulation_t, _size_p, _size_p, _int_p]
    lib.k5_simulation_gouges.restype = ctypes.c_int
    lib.k5_simulation_gouges.argtypes = [_simulation_t, _size_p, _size_p, _double_p]
    lib.k5_chain_default_gcode_axes.restype = ctypes.c_int
    lib.k5_chain_default_gcode_axes.argtypes = [_chain_t, ctypes.POINTER(GcodeAxes)]
    lib.k5_path_write_gcode.restype = ctypes.c_int
    lib.k5_path_write_gcode.argtypes = [_path_t, ctypes.POINTER(GcodeAxes), ctypes.c_char_p]


def last_error(library=None):
    """The message of the last call that failed on this thread; empty when none did."""
    return (load(library).k5_last_error() or b"").decode("utf-8", "replace")


def version(library=None):
    return load(library).k5_version_string().decode("ascii")


def _check(lib, status, call):
    if status != OK:
        raise Kin5axError(status, (lib.k5_last_error() or b"").decode("utf-8", "replace"), call)


def _doubles(values, count, what):
    """A ctypes array of count doubles out of any sequence, or an argument error that says what."""
    values = [float(v) for v in values]
    if len(values) != count:
        raise Kin5axError(ERROR_ARGUMENT, "%s needs %d values, not %d" % (what, count, len(values)))
    return (ctypes.c_double * count)(*values)


def _encode_path(file_path):
    return os.fsencode(file_path) if not isinstance(file_path, bytes) else file_path


# ---------------------------------------------------------------- the handles

class Tool(object):
    """A milling tool with its holder, all lengths in the unit of the chain file.

    rz is the radius of the shank, and of a flat end mill; r the radius of the
    ball of a ball nose tool; cutting_height how far the cutting part reaches up
    from the tip; shank_length the part above it; holder_length and
    holder_radius the holder between the tool and the tool mount. The programmed
    point follows the shape: the centre of the ball of a ball nose tool, the tip
    of a flat end mill.
    """

    def __init__(self, shape, rz, r, cutting_height, shank_length, holder_length, holder_radius,
                 library=None):
        self._lib = load(library)
        self._handle = _tool_t()
        _check(self._lib, self._lib.k5_tool_create(
            int(shape), float(rz), float(r), float(cutting_height), float(shank_length),
            float(holder_length), float(holder_radius), ctypes.byref(self._handle)), "k5_tool_create")
        self.shape = int(shape)
        self.r = float(r)

    @property
    def handle(self):
        return self._handle

    def assembly_length(self):
        """From the tip of the tool to the tool mount of the machine."""
        out = ctypes.c_double()
        _check(self._lib, self._lib.k5_tool_assembly_length(self._handle, ctypes.byref(out)),
               "k5_tool_assembly_length")
        return out.value

    def mount_to_point_distance(self):
        """How far below the tool mount the programmed point hangs."""
        out = ctypes.c_double()
        _check(self._lib, self._lib.k5_tool_mount_to_point_distance(self._handle, ctypes.byref(out)),
               "k5_tool_mount_to_point_distance")
        return out.value

    def close(self):
        if self._handle:
            self._lib.k5_tool_free(self._handle)
            self._handle = _tool_t()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _tool_handle(tool):
    return tool.handle if tool is not None else _tool_t()


class Path(object):
    """What a batch run produced: the trajectory and a record per location."""

    def __init__(self, lib, handle):
        self._lib = lib
        self._handle = handle

    def size(self):
        """How many locations the path holds: those handed over and those invented between them."""
        out = ctypes.c_size_t()
        _check(self._lib, self._lib.k5_path_size(self._handle, ctypes.byref(out)), "k5_path_size")
        return out.value

    def location(self, index):
        out = Location()
        _check(self._lib, self._lib.k5_path_location(self._handle, int(index), ctypes.byref(out)),
               "k5_path_location")
        return out

    def locations(self):
        for index in range(self.size()):
            yield self.location(index)

    def count_of_status(self, status):
        out = ctypes.c_size_t()
        _check(self._lib, self._lib.k5_path_count_of_status(self._handle, int(status), ctypes.byref(out)),
               "k5_path_count_of_status")
        return out.value

    def count_of_origin(self, origin):
        out = ctypes.c_size_t()
        _check(self._lib, self._lib.k5_path_count_of_origin(self._handle, int(origin), ctypes.byref(out)),
               "k5_path_count_of_origin")
        return out.value

    def report(self):
        """How many locations ended in each status, by name, leaving out the statuses nobody got."""
        counts = {}
        for status, name in SOLVE_STATUS_NAMES.items():
            count = self.count_of_status(status)
            if count:
                counts[name] = count
        return counts

    def errors(self):
        """The biggest position error and the biggest tool-axis error of the solutions of this run."""
        position, orientation = ctypes.c_double(), ctypes.c_double()
        _check(self._lib, self._lib.k5_path_errors(self._handle, ctypes.byref(position),
                                                   ctypes.byref(orientation)), "k5_path_errors")
        return position.value, orientation.value

    def last_configuration(self):
        """Where the machine is left standing, or None when no location had a solution."""
        q = (ctypes.c_double * AXES)()
        status = self._lib.k5_path_last_configuration(self._handle, q)
        if status != OK:
            return None
        return tuple(q)

    def write_gcode(self, axes, file_path):
        """One G1 line per solved location, in the unit of the chain file - see the header."""
        _check(self._lib, self._lib.k5_path_write_gcode(self._handle, ctypes.byref(axes),
                                                        _encode_path(file_path)), "k5_path_write_gcode")

    def close(self):
        if self._handle:
            self._lib.k5_path_free(self._handle)
            self._handle = _path_t()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


class Chain(object):
    """A machine, read from a .kc (XML) or .kc.json file."""

    def __init__(self, file_path, library=None):
        self._lib = load(library)
        self._handle = _chain_t()
        self.file_path = file_path
        _check(self._lib, self._lib.k5_chain_open(_encode_path(file_path), ctypes.byref(self._handle)),
               "k5_chain_open")

    @property
    def handle(self):
        return self._handle

    def name(self):
        out = ctypes.create_string_buffer(NAME_MAX)
        _check(self._lib, self._lib.k5_chain_name(self._handle, out, NAME_MAX), "k5_chain_name")
        return out.value.decode("utf-8", "replace")

    def is_5c(self):
        out = ctypes.c_int()
        _check(self._lib, self._lib.k5_chain_is_5c(self._handle, ctypes.byref(out)), "k5_chain_is_5c")
        return bool(out.value)

    def link_count(self):
        out = ctypes.c_size_t()
        _check(self._lib, self._lib.k5_chain_link_count(self._handle, ctypes.byref(out)),
               "k5_chain_link_count")
        return out.value

    def link(self, index):
        out = Link()
        _check(self._lib, self._lib.k5_chain_link(self._handle, int(index), ctypes.byref(out)),
               "k5_chain_link")
        return out

    def links(self):
        """The joints, in the order of every q of this interface: material terminal to tool terminal."""
        return [self.link(i) for i in range(self.link_count())]

    def first_rotary_axis(self, part=PART_TOOL):
        out = ctypes.c_size_t()
        _check(self._lib, self._lib.k5_chain_first_rotary_axis(self._handle, int(part), ctypes.byref(out)),
               "k5_chain_first_rotary_axis")
        return out.value

    def frames(self, part=PART_TOOL):
        """The frames of the segments of one branch at the joint values the chain stands at.

        A list with one pair per segment: the frame the collision boxes of the
        segment are given in, then the frame after its joint motion. Each is a
        tuple of 16 doubles in the layout OpenGL and glTF use - basis vectors at
        0..2, 4..6, 8..10, the origin at 12..14.
        """
        count = ctypes.c_size_t()
        _check(self._lib, self._lib.k5_chain_frames(self._handle, int(part), None, 0, ctypes.byref(count)),
               "k5_chain_frames")
        doubles = 32 * count.value
        out = (ctypes.c_double * max(doubles, 1))()
        _check(self._lib, self._lib.k5_chain_frames(self._handle, int(part), out, doubles,
                                                    ctypes.byref(count)), "k5_chain_frames")
        pairs = []
        for i in range(count.value):
            start = 32 * i
            pairs.append((tuple(out[start:start + 16]), tuple(out[start + 16:start + 32])))
        return pairs

    def segment_boxes(self, part, index):
        """The collision boxes of one segment of a branch, in the first frame frames() gives for it.

        A list of (minimum corner, maximum corner), each a tuple of three; empty
        for a segment that carries no box. The segments are numbered as in
        frames(), the terminal included.
        """
        count = ctypes.c_size_t()
        _check(self._lib, self._lib.k5_chain_segment_boxes(self._handle, int(part), int(index), None, 0,
                                                           ctypes.byref(count)), "k5_chain_segment_boxes")
        doubles = 6 * count.value
        out = (ctypes.c_double * max(doubles, 1))()
        _check(self._lib, self._lib.k5_chain_segment_boxes(self._handle, int(part), int(index), out,
                                                           doubles, ctypes.byref(count)),
               "k5_chain_segment_boxes")
        return [(tuple(out[6 * i:6 * i + 3]), tuple(out[6 * i + 3:6 * i + 6])) for i in range(count.value)]

    def set_configuration(self, q):
        """Puts the chain into these joint values, limits unchecked; frames() and links() follow."""
        _check(self._lib, self._lib.k5_chain_set_configuration(self._handle, _doubles(q, AXES, "q")),
               "k5_chain_set_configuration")

    def tool_point(self, q, tool=None):
        """The forward kinematics: where the programmed point ends up, and the tool axis, for these joints."""
        position = (ctypes.c_double * 3)()
        axis = (ctypes.c_double * 3)()
        _check(self._lib, self._lib.k5_chain_tool_point(self._handle, _tool_handle(tool),
                                                        _doubles(q, AXES, "q"), position, axis),
               "k5_chain_tool_point")
        return tuple(position), tuple(axis)

    def solve_location(self, position, axis, settings, tool=None):
        """Every configuration that puts the tool there: a list of q tuples, and the status when it is empty."""
        p = _doubles(position, 3, "position")
        v = _doubles(axis, 3, "axis")
        count = ctypes.c_size_t()
        status = ctypes.c_int()
        _check(self._lib, self._lib.k5_solve_location(
            self._handle, _tool_handle(tool), ctypes.byref(settings), p, v, None, 0,
            ctypes.byref(count), ctypes.byref(status)), "k5_solve_location")
        if count.value == 0:
            return [], status.value
        q = (ctypes.c_double * (AXES * count.value))()
        _check(self._lib, self._lib.k5_solve_location(
            self._handle, _tool_handle(tool), ctypes.byref(settings), p, v, q, count.value,
            ctypes.byref(count), ctypes.byref(status)), "k5_solve_location")
        return [tuple(q[AXES * i:AXES * (i + 1)]) for i in range(count.value)], status.value

    def postprocess_locations(self, positions, axes, settings, tool=None):
        """A whole tool path held in memory, solved: positions and axes are sequences of 3-sequences.

        The axes need not be unit vectors; an axis of length zero is refused. The
        locations are numbered from 1 in the records of the result, the way the
        lines of a file are.
        """
        positions = list(positions)
        axes = list(axes)
        if len(positions) != len(axes):
            raise Kin5axError(ERROR_ARGUMENT, "%d positions and %d axes: a path needs one of each per "
                              "location" % (len(positions), len(axes)))
        count = len(positions)
        flat_positions = _doubles([c for p in positions for c in p], 3 * count, "positions")
        flat_axes = _doubles([c for a in axes for c in a], 3 * count, "axes")
        handle = _path_t()
        _check(self._lib, self._lib.k5_postprocess_locations(
            self._handle, _tool_handle(tool), ctypes.byref(settings),
            flat_positions if count else None, flat_axes if count else None, count,
            ctypes.byref(handle)), "k5_postprocess_locations")
        return Path(self._lib, handle)

    def postprocess_file(self, cl_file_path, settings, tool=None):
        """A cutter-location file (GOTO/x,y,z,i,j,k lines), solved."""
        handle = _path_t()
        _check(self._lib, self._lib.k5_postprocess_file(
            self._handle, _tool_handle(tool), ctypes.byref(settings), _encode_path(cl_file_path),
            ctypes.byref(handle)), "k5_postprocess_file")
        return Path(self._lib, handle)

    def default_gcode_axes(self):
        """Which joint is which word, from the structure of the chain; the letters A and C are a guess."""
        out = GcodeAxes()
        _check(self._lib, self._lib.k5_chain_default_gcode_axes(self._handle, ctypes.byref(out)),
               "k5_chain_default_gcode_axes")
        return out

    def close(self):
        if self._handle:
            self._lib.k5_chain_free(self._handle)
            self._handle = _chain_t()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


# ---------------------------------------------------------------- the cutting simulation

class Material(object):
    """A box of material in the frame of the material of the chain, all lengths in the unit of the file.

    size and start are 3-sequences; voxel is the side of one voxel. Everything
    is material to begin with. Rudimentary by design: the tool is stamped into
    it once per location with nothing swept between two, so the interpolation
    of the path has to be as dense as the voxels for a cut to look like one.
    """

    def __init__(self, size, voxel, start, library=None):
        self._lib = load(library)
        self._handle = _material_t()
        size = _doubles(size, 3, "size")
        start = _doubles(start, 3, "start")
        self.size = tuple(size)
        self.voxel = float(voxel)
        self.start = tuple(start)
        _check(self._lib, self._lib.k5_material_create(
            size[0], size[1], size[2], float(voxel), start[0], start[1], start[2],
            ctypes.byref(self._handle)), "k5_material_create")

    @property
    def handle(self):
        return self._handle

    def reset(self):
        """Whole again."""
        _check(self._lib, self._lib.k5_material_reset(self._handle), "k5_material_reset")

    def dimensions(self):
        """How many voxels along X, Y and Z."""
        nx, ny, nz = ctypes.c_size_t(), ctypes.c_size_t(), ctypes.c_size_t()
        _check(self._lib, self._lib.k5_material_dimensions(self._handle, ctypes.byref(nx), ctypes.byref(ny),
                                                           ctypes.byref(nz)), "k5_material_dimensions")
        return nx.value, ny.value, nz.value

    def volumes(self):
        """The volume of the block and the volume removed so far, in the unit of the file cubed."""
        total, removed = ctypes.c_double(), ctypes.c_double()
        _check(self._lib, self._lib.k5_material_volumes(self._handle, ctypes.byref(total),
                                                        ctypes.byref(removed)), "k5_material_volumes")
        return total.value, removed.value

    def surface(self):
        """The voxels of the surface of what is left, as a flat ctypes array of 3 doubles each.

        The corner of each voxel nearest the start of the block; the count is
        len(array) // 3. A flat array rather than tuples because a surface is a
        hundred thousand voxels and the host draws them, not reads them.
        """
        count = ctypes.c_size_t()
        _check(self._lib, self._lib.k5_material_surface(self._handle, None, 0, ctypes.byref(count)),
               "k5_material_surface")
        if not count.value:
            return (ctypes.c_double * 0)()
        out = (ctypes.c_double * (3 * count.value))()
        _check(self._lib, self._lib.k5_material_surface(self._handle, out, 3 * count.value,
                                                        ctypes.byref(count)), "k5_material_surface")
        return out

    def close(self):
        if self._handle:
            self._lib.k5_material_free(self._handle)
            self._handle = _material_t()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


class Simulation(object):
    """The path cutting the material with the tool on the chain, one location at a time.

    The four are kept here for as long as the simulation lives, since the
    library expects the caller to keep them alive; the chain's joint values and
    the tool's position are changed by every step.
    """

    def __init__(self, chain, tool, path, material, library=None):
        self._lib = load(library)
        self._handle = _simulation_t()
        self.chain, self.tool, self.path, self.material = chain, tool, path, material
        _check(self._lib, self._lib.k5_simulation_create(
            chain.handle, tool.handle, path._handle, material.handle, ctypes.byref(self._handle)),
            "k5_simulation_create")

    def reset(self):
        """Back to the first location; the material is left as it is."""
        _check(self._lib, self._lib.k5_simulation_reset(self._handle), "k5_simulation_reset")

    def step(self):
        """The next location that has a solution, cut. False when the path is exhausted."""
        stepped = ctypes.c_int()
        _check(self._lib, self._lib.k5_simulation_step(self._handle, ctypes.byref(stepped)),
               "k5_simulation_step")
        return bool(stepped.value)

    def run(self):
        """All the remaining locations."""
        _check(self._lib, self._lib.k5_simulation_run(self._handle), "k5_simulation_run")

    def progress(self):
        """(locations passed, locations of the path, finished)."""
        index, count, finished = ctypes.c_size_t(), ctypes.c_size_t(), ctypes.c_int()
        _check(self._lib, self._lib.k5_simulation_progress(self._handle, ctypes.byref(index),
                                                           ctypes.byref(count), ctypes.byref(finished)),
               "k5_simulation_progress")
        return index.value, count.value, bool(finished.value)

    def gouges(self):
        """(count, first step, first point) of the gouges so far; the last two mean nothing at count 0."""
        count, first = ctypes.c_size_t(), ctypes.c_size_t()
        point = (ctypes.c_double * 3)()
        _check(self._lib, self._lib.k5_simulation_gouges(self._handle, ctypes.byref(count),
                                                         ctypes.byref(first), point), "k5_simulation_gouges")
        return count.value, first.value, tuple(point)

    def close(self):
        if self._handle:
            self._lib.k5_simulation_free(self._handle)
            self._handle = _simulation_t()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
