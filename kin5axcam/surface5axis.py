"""The 3D Surface (5axis) operation: a zigzag over the parameter space of one face.

This is the FreeCAD side of it - the properties, the face, the tool and the
commands. The geometry is in pathgen.py, which knows nothing about FreeCAD.

How the tool is held is the ToolAxis property. Vertical is the three-axis
reading of the operation: the tool stands up and the commands say nothing about
its orientation, which is unambiguous. Normal leans the tool over from the
surface normal by LeanAngle, in a direction LeanRotation measured round the
normal from the way the tool travels, and every cutting move then carries the
axis as I, J and K alongside X, Y and Z - the vector output convention, and what
the kin5ax postprocessor solves for.

The commands carry the tip of the tool, which is what a control programs. Where
the tip goes follows from the contact point, the normal there and the axis, and
that is pathgen.py.

Any tool cuts here, but only the sphere at the end of it is taken into account -
half the diameter of a ball nose tool, the corner radius of a bull nose one,
nothing at all of the sides or the flat of an end mill. The path is therefore
right for a ball nose tool and an approximation for every other, which the
operation says in the report view rather than leaving it to be discovered.
"""

import math

import FreeCAD
import Path
from Path.Op import Base as PathOp

from kin5axcam import pathgen

if hasattr(FreeCAD, "Qt"):
    translate = FreeCAD.Qt.translate
else:                                       # pragma: no cover - a FreeCAD without the Qt layer
    def translate(context, text, *args):
        return text

__title__ = "3D Surface (5axis) operation"
__author__ = "kin5ax"

PROPERTY_GROUP = "Surface5Axis"

#the shapes of tool whose end is a half sphere of the full diameter: the plain ball nose one and the
#tapered one, whose taper is above the ball and does not change it
BALL_NOSED_SHAPES = ("ballend", "ballnose", "taperedballnose")

#what the ToolAxis property may say, and the way pathgen knows each of them by
TOOL_AXIS_MODES = (("Vertical", pathgen.AXIS_VERTICAL), ("Normal", pathgen.AXIS_NORMAL))


def tool_shape_name(tool):
    """The shape of a tool bit in lower case ("ballend", "endmill"), or "" when it does not say.

    A bit of the tool library of FreeCAD 1.1 carries ShapeType; older ones and
    some others carry ShapeName. Neither is there on a tool that is not a bit.
    """
    for attribute in ("ShapeName", "ShapeType"):
        value = getattr(tool, attribute, None)
        if value:
            return str(value).lower()
    return ""


def quantity_value(value):
    """A length property as a plain number of millimetres."""
    return float(getattr(value, "Value", value))


class ObjectSurface5Axis(PathOp.ObjectOp):
    """A zigzag over the U,V space of a single face, the commands carrying the tip of the tool."""

    def opFeatures(self, obj):
        """What this operation has, which is also what the task dialog is made of.

        The base geometry page comes from FeatureBaseFaces, the depths and the
        step down from FeatureDepths and FeatureStepDown, the heights from
        FeatureHeights, and the tool and the coolant sit on the page of the
        operation itself.

        Not here: FeatureFinishDepth, which is the depth of the last pass of a
        roughing sequence. This operation follows the surface, so its last band
        is the finish already and a separate finish depth would mean nothing.
        """
        return (
            PathOp.FeatureTool
            | PathOp.FeatureDepths
            | PathOp.FeatureStepDown
            | PathOp.FeatureHeights
            | PathOp.FeatureStartPoint
            | PathOp.FeatureCoolant
            | PathOp.FeatureBaseFaces
        )

    def initOperation(self, obj):
        """The properties of the operation, the first time one is made."""
        self.ensureProperties(obj)

    def opOnDocumentRestored(self, obj):
        """A document saved by an older version of this addon may be missing a property.

        Adding what is missing rather than assuming it is there is what lets an
        operation saved last month open today. The enumeration needs its list of
        values back as well: the chosen value survives in the file, the list of
        what could have been chosen does not.
        """
        self.ensureProperties(obj)

    def ensureProperties(self, obj):
        """Adds whatever property is not there yet, and leaves the values of those that are."""
        if not hasattr(obj, "Rows"):
            obj.addProperty(
                "App::PropertyInteger", "Rows", PROPERTY_GROUP,
                translate("Surface5Axis", "How many passes are laid across the face. Counted in "
                          "the parameter space of the surface, so a face whose parameters run "
                          "unevenly gets unevenly spaced passes."))
        if not hasattr(obj, "PointsPerRow"):
            obj.addProperty(
                "App::PropertyInteger", "PointsPerRow", PROPERTY_GROUP,
                translate("Surface5Axis", "How many points are put along each pass. The path is a "
                          "chain of straight moves between them, so more points follow the surface "
                          "more closely and make a longer program."))
        if not hasattr(obj, "PathDirection"):
            obj.addProperty(
                "App::PropertyEnumeration", "PathDirection", PROPERTY_GROUP,
                translate("Surface5Axis", "Which parameter of the surface a pass sweeps: U for "
                          "passes at constant v, V for passes at constant u."))
        if not hasattr(obj, "ZigZag"):
            obj.addProperty(
                "App::PropertyBool", "ZigZag", PROPERTY_GROUP,
                translate("Surface5Axis", "Cut there and back, each pass running against the one "
                          "before it. Switched off, every pass runs the same way and the tool "
                          "returns through the air."))
        if not hasattr(obj, "ToolAxis"):
            obj.addProperty(
                "App::PropertyEnumeration", "ToolAxis", PROPERTY_GROUP,
                translate("Surface5Axis", "How the tool is held. Vertical stands it up, which is "
                          "the three-axis reading of this operation. Normal points it along the "
                          "surface normal, leaned over by the two angles, and writes the axis into "
                          "every cutting move as I, J and K."))
        if not hasattr(obj, "LeanAngle"):
            obj.addProperty(
                "App::PropertyAngle", "LeanAngle", PROPERTY_GROUP,
                translate("Surface5Axis", "How far the axis of the tool leans away from the "
                          "surface normal. Zero holds it along the normal. Only read while the "
                          "tool axis is Normal."))
        if not hasattr(obj, "LeanRotation"):
            obj.addProperty(
                "App::PropertyAngle", "LeanRotation", PROPERTY_GROUP,
                translate("Surface5Axis", "Which way the tool leans, measured round the surface "
                          "normal from the direction the pass runs in. Zero leans it along the "
                          "travel, which is a lead angle; 90 degrees leans it to the side of the "
                          "travel, which is a tilt."))
        if not hasattr(obj, "InvertNormal"):
            obj.addProperty(
                "App::PropertyBool", "InvertNormal", PROPERTY_GROUP,
                translate("Surface5Axis", "Put the tool on the other side of the face. The normal "
                          "of a face can point either way depending on how the shape was built, "
                          "and the tool goes to the side it points at."))
        #The values the enumeration may take. Setting the list clears the choice, so the choice goes
        #back afterwards - on a restored document that is the one the file carried.
        chosen = obj.PathDirection if hasattr(obj, "PathDirection") else None
        obj.PathDirection = ["U", "V"]
        if chosen:
            obj.PathDirection = chosen
        chosen = obj.ToolAxis if hasattr(obj, "ToolAxis") else None
        obj.ToolAxis = [name for name, mode in TOOL_AXIS_MODES]
        if chosen:
            obj.ToolAxis = chosen

    def opSetDefaultValues(self, obj, job):
        """Something sensible to start from: twenty passes of sixty points, there and back."""
        obj.Rows = 20
        obj.PointsPerRow = 60
        obj.PathDirection = "U"
        obj.ZigZag = True
        obj.InvertNormal = False
        obj.ToolAxis = "Vertical"
        obj.LeanAngle = 0.0
        obj.LeanRotation = 0.0

    def opRejectAddBase(self, obj, base, sub):
        """Only a face of the model, and only one of them."""
        if not sub or not sub.startswith("Face"):
            return True
        return base not in self.model

    def opUpdateDepths(self, obj):
        """What the depths should be, left to the user to change: the face, and room for the tool.

        The bottom of the face is the final depth: a final depth below it would
        have the operation cut nothing it would not cut anyway. The start depth
        is the top of the face plus however far above the face the tip of the
        tool can be, since the depths hold the tip and a leaning tool lifts its
        tip off the surface - without that room a lean of any size would put the
        whole path above the start depth and leave nothing to cut.
        """
        face = self.theFace(obj, quiet=True)
        if face is None:
            return
        obj.OpStartDepth = face.BoundBox.ZMax + self.tipClearance(obj)
        obj.OpFinalDepth = face.BoundBox.ZMin

    def tipClearance(self, obj):
        """How far above the surface the tip of the tool can get, for the start depth to allow.

        The tip is the contact point plus the tip radius times (normal - axis),
        so its height above the surface is that radius times the difference of
        the two heights. A tool standing up can only be level with the contact
        point or below it, the axis standing no further from the vertical than
        the normal does, which is nothing to allow for. Leaning it by an angle
        makes the worst case the radius times (1 - cos lean + sin lean), which
        is what a normal and an axis that far apart can do to the height.
        """
        if self.axisMode(obj) == pathgen.AXIS_VERTICAL:
            return 0.0
        radius = self.tipRadius(obj, quiet=True)
        if not radius:
            return 0.0
        lean = math.radians(quantity_value(getattr(obj, "LeanAngle", 0.0)))
        return radius * (1.0 - math.cos(lean) + abs(math.sin(lean)))

    def theFace(self, obj, quiet=False):
        """The one face this operation works on, or None with a message saying why there is none.

        quiet: for the moments when there is no face yet and that is not news,
        such as working out what the depths should be while the operation is
        still being set up.
        """
        faces = []
        for base, subs in obj.Base:
            for sub in subs:
                if not sub.startswith("Face"):
                    if not quiet:
                        Path.Log.warning(
                            translate("Surface5Axis", "%s is not a face and is ignored") % sub)
                    continue
                faces.append((base, sub))
        if not faces:
            if not quiet:
                Path.Log.warning(
                    translate("Surface5Axis", "%s has no face to work on: pick one in Base Geometry")
                    % obj.Label)
            return None
        if len(faces) > 1:
            if not quiet:
                Path.Log.error(
                    translate("Surface5Axis", "%s works on a single face, and %d are picked")
                    % (obj.Label, len(faces)))
            return None
        base, sub = faces[0]
        shape = base.Shape.getElement(sub)
        if shape.ShapeType != "Face":
            if not quiet:
                Path.Log.error(
                    translate("Surface5Axis", "%s of %s is a %s, not a face")
                    % (sub, base.Label, shape.ShapeType))
            return None
        return shape

    def tipRadius(self, obj, quiet=False):
        """The radius of the sphere at the end of the tool, or None when there is no tool to ask.

        A bull nose tool, and any other the library builds from a shape with a
        rounded corner, says so in CornerRadius. A ball nose one is a corner
        radius of half its diameter, which it does not spell out. Anything else -
        an end mill, a V bit, a drill, a tool whose shape does not say what it is
        - has nothing rounded to offset, and a radius of zero puts the tip of it
        on the surface.

        That sphere is all this operation knows of the tool, so anything but a
        ball nose one gets a warning with the path: the sides and the flat of an
        end mill, and the shank above the corner of a bull nose one, are not
        taken into account anywhere.
        """
        tool = self.tool
        if tool is None:
            if not quiet:
                Path.Log.error(
                    translate("Surface5Axis", "%s has no tool: pick a tool controller") % obj.Label)
            return None
        shape = tool_shape_name(tool)
        if shape not in BALL_NOSED_SHAPES and not quiet:
            Path.Log.warning(
                translate("Surface5Axis", "%s works out its path for the ball of a ball nose tool, "
                          "and the tool of this operation is %s. Only the sphere at the end of it "
                          "is taken into account, so the path is an approximation: check it before "
                          "cutting.") % (obj.Label, shape if shape else "of an unknown shape"))
        corner = quantity_value(getattr(tool, "CornerRadius", 0.0))
        if corner > 0.0:
            return corner
        if shape in BALL_NOSED_SHAPES:
            diameter = quantity_value(getattr(tool, "Diameter", 0.0))
            if diameter <= 0.0:
                if not quiet:
                    Path.Log.error(
                        translate("Surface5Axis", "the ball nose tool of %s has no diameter, so "
                                  "the ball it cuts with has no size") % obj.Label)
                return None
            return 0.5 * diameter
        return 0.0

    def axisMode(self, obj):
        """What pathgen calls the ToolAxis of the operation, standing the tool up if it says nothing."""
        chosen = getattr(obj, "ToolAxis", None)
        for name, mode in TOOL_AXIS_MODES:
            if chosen == name:
                return mode
        return pathgen.AXIS_VERTICAL

    def opExecute(self, obj):
        """The passes of the zigzag, as commands."""
        Path.Log.track()
        face = self.theFace(obj)
        if face is None:
            return
        radius = self.tipRadius(obj)
        if radius is None:
            return
        parameters = pathgen.ZigZagParameters(
            tip_radius=radius,
            rows=obj.Rows,
            points_per_row=obj.PointsPerRow,
            direction=obj.PathDirection,
            zigzag=obj.ZigZag,
            flip_normal=obj.InvertNormal,
            axis_mode=self.axisMode(obj),
            lean_angle=quantity_value(getattr(obj, "LeanAngle", 0.0)),
            lean_rotation=quantity_value(getattr(obj, "LeanRotation", 0.0)),
        )
        try:
            passes = pathgen.generate_passes(face, parameters)
        except ValueError as problem:
            Path.Log.error("%s: %s" % (obj.Label, problem))
            return
        passes = pathgen.in_layers(passes, quantity_value(obj.StepDown),
                                   quantity_value(obj.FinalDepth),
                                   quantity_value(obj.StartDepth))
        if getattr(obj, "UseStartPoint", False):
            start = obj.StartPoint
            passes = pathgen.start_near(passes, (start.x, start.y, start.z), parameters)
        if not passes:
            Path.Log.warning(
                translate("Surface5Axis", "%s found nothing to cut on that face between the final "
                          "depth and the start depth") % obj.Label)
            return
        self.appendPasses(obj, passes)

    def orientation(self, obj, location):
        """The axis of the tool as the parameters of a move, which is nothing at all when it stands up.

        I, J and K are the vector output convention: the axis of the tool as a
        unit vector in the coordinates of the part, which is what the kin5ax
        postprocessor takes. A move without them is a move of a tool standing
        up, so the three-axis path stays the three-axis path it was, readable by
        anything that reads G-code.
        """
        if self.axisMode(obj) == pathgen.AXIS_VERTICAL:
            return {}
        return {"I": location.axis[0], "J": location.axis[1], "K": location.axis[2]}

    def appendPasses(self, obj, passes):
        """A pass becomes: up to the clearance height, across, down, cut, up again."""
        clearance = quantity_value(obj.ClearanceHeight)
        safe = quantity_value(obj.SafeHeight)
        self.commandlist.append(Path.Command("G0", {"Z": clearance, "F": self.vertRapid}))
        for one in passes:
            first = one[0].point
            self.commandlist.append(
                Path.Command("G0", {"X": first[0], "Y": first[1], "F": self.horizRapid}))
            self.commandlist.append(Path.Command("G0", {"Z": safe, "F": self.vertRapid}))
            plunge = {"Z": first[2], "F": self.vertFeed}
            plunge.update(self.orientation(obj, one[0]))
            self.commandlist.append(Path.Command("G1", plunge))
            for location in one[1:]:
                point = location.point
                move = {"X": point[0], "Y": point[1], "Z": point[2], "F": self.horizFeed}
                move.update(self.orientation(obj, location))
                self.commandlist.append(Path.Command("G1", move))
            #Up to clearance after every pass, the last one included: the base class of the
            #operation happens to append a retract of its own as well, and a duplicate rapid to a
            #height the tool is already at costs one line of G-code. An operation that leaves the
            #tool down in the material if that ever changes costs rather more.
            self.commandlist.append(Path.Command("G0", {"Z": clearance, "F": self.vertRapid}))


def SetupProperties():
    """The properties the setup sheet of a job may carry defaults for."""
    return ["Rows", "PointsPerRow", "PathDirection", "ZigZag", "InvertNormal",
            "ToolAxis", "LeanAngle", "LeanRotation"]


def Create(name, obj=None, parentJob=None):
    """Create(name) ... creates and returns a 3D Surface (5axis) operation."""
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectSurface5Axis(obj, name, parentJob)
    return obj
