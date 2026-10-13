"""The 3D Surface (5axis) operation: a zigzag over the parameter space of one face.

This is the FreeCAD side of it - the properties, the face, the tool and the
commands. The geometry is in pathgen.py, which knows nothing about FreeCAD.

Stage one, which is what this is: the tool stands up, as in any three-axis
operation, and the path is the ball centre of a ball nose tool moved one tool
radius along the surface normal. The orientation of the tool and the two angles
that lean it come in the stages after this one, and will ride in the commands as
I, J and K.

Mind the point the commands carry: it is the centre of the ball, not the tip of
the tool. That is the programmed point of a ball nose tool in cutter location
data and in kin5ax. Handed to an ordinary three-axis postprocessor, which
expects the tip, it cuts one radius too high.
"""

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

#the only shape of tool this operation cuts with
BALL_NOSE = "ballend"


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
    """A zigzag over the U,V space of a single face, cut with the ball of a ball nose tool."""

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

    def opSetDefaultValues(self, obj, job):
        """Something sensible to start from: twenty passes of sixty points, there and back."""
        obj.Rows = 20
        obj.PointsPerRow = 60
        obj.PathDirection = "U"
        obj.ZigZag = True
        obj.InvertNormal = False

    def opRejectAddBase(self, obj, base, sub):
        """Only a face of the model, and only one of them."""
        if not sub or not sub.startswith("Face"):
            return True
        return base not in self.model

    def opUpdateDepths(self, obj):
        """What the depths should be, left to the user to change: the top and bottom of the face.

        A start depth above the face and a final depth below it would have the
        operation cut nothing it would not cut anyway, so the face itself is the
        honest suggestion.
        """
        face = self.theFace(obj, quiet=True)
        if face is None:
            return
        obj.OpStartDepth = face.BoundBox.ZMax
        obj.OpFinalDepth = face.BoundBox.ZMin

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

    def ballRadius(self, obj):
        """The radius of the ball of the tool, or None when the tool is not a ball nose one."""
        tool = self.tool
        if tool is None:
            Path.Log.error(
                translate("Surface5Axis", "%s has no tool: pick a tool controller") % obj.Label)
            return None
        shape = tool_shape_name(tool)
        if shape and shape != BALL_NOSE:
            Path.Log.error(
                translate("Surface5Axis", "%s cuts with the ball of a ball nose tool, and the tool "
                          "of %s is a %s one") % (obj.Label, obj.Label, shape))
            return None
        if not shape:
            Path.Log.warning(
                translate("Surface5Axis", "the shape of the tool of %s does not say what it is; it "
                          "is taken for a ball nose tool of its diameter") % obj.Label)
        diameter = quantity_value(getattr(tool, "Diameter", 0.0))
        if diameter <= 0.0:
            Path.Log.error(
                translate("Surface5Axis", "the tool of %s has no diameter") % obj.Label)
            return None
        return 0.5 * diameter

    def opExecute(self, obj):
        """The passes of the zigzag, as commands."""
        Path.Log.track()
        face = self.theFace(obj)
        if face is None:
            return
        radius = self.ballRadius(obj)
        if radius is None:
            return
        parameters = pathgen.ZigZagParameters(
            tool_radius=radius,
            rows=obj.Rows,
            points_per_row=obj.PointsPerRow,
            direction=obj.PathDirection,
            zigzag=obj.ZigZag,
            flip_normal=obj.InvertNormal,
        )
        try:
            passes = pathgen.generate_passes(face, parameters)
        except ValueError as problem:
            Path.Log.error("%s: %s" % (obj.Label, problem))
            return
        passes = pathgen.in_layers(passes, quantity_value(obj.StepDown),
                                   quantity_value(obj.FinalDepth),
                                   quantity_value(obj.StartDepth), radius)
        if getattr(obj, "UseStartPoint", False):
            start = obj.StartPoint
            passes = pathgen.start_near(passes, (start.x, start.y, start.z))
        if not passes:
            Path.Log.warning(
                translate("Surface5Axis", "%s found nothing to cut on that face between the final "
                          "depth and the start depth") % obj.Label)
            return
        self.appendPasses(obj, passes)

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
            self.commandlist.append(Path.Command("G1", {"Z": first[2], "F": self.vertFeed}))
            for location in one[1:]:
                point = location.point
                self.commandlist.append(Path.Command(
                    "G1", {"X": point[0], "Y": point[1], "Z": point[2], "F": self.horizFeed}))
            #Up to clearance after every pass, the last one included: the base class of the
            #operation happens to append a retract of its own as well, and a duplicate rapid to a
            #height the tool is already at costs one line of G-code. An operation that leaves the
            #tool down in the material if that ever changes costs rather more.
            self.commandlist.append(Path.Command("G0", {"Z": clearance, "F": self.vertRapid}))


def SetupProperties():
    """The properties the setup sheet of a job may carry defaults for."""
    return ["Rows", "PointsPerRow", "PathDirection", "ZigZag", "InvertNormal"]


def Create(name, obj=None, parentJob=None):
    """Create(name) ... creates and returns a 3D Surface (5axis) operation."""
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectSurface5Axis(obj, name, parentJob)
    return obj
