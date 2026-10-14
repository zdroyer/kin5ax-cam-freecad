"""A machine of kin5ax in a FreeCAD document: its segments as parts, placed by the kinematic chain.

The machine is a group with one ``App::Part`` per segment of each branch of the
chain, holding the collision boxes of that segment exactly as the file gives
them and as the solver checks them - what is seen is what collides. A thin arm
joins each segment to the next, so that a machine whose file carries no boxes
on its joints is still a stick figure that moves the right way. Two more parts
mark the ends of the branches: the **tool mount**, where a simulation puts the
tool of a job, and the **material**, where it puts the model and the stock.

Set ``Configuration`` - the five joint values, in the order of the links of the
chain and in the units of its file - and every part is placed by the frames
kin5ax computes for that configuration. Nothing here knows about a path; that
is the simulation, which drives this.

Every joint shows its value the way the application of kin5ax draws it: a
revolute joint as a sector of a disc swept from zero to the angle it stands at,
a prismatic one as a box as long as its slide, magenta for a positive value and
cyan for a negative one, in the frame of the joint whose Z is its axis.
``JointSize`` is the radius of the disc and the side of the box, picked from
the size of the machine unless set; ``ShowJoints`` hides them.

Lengths cross from the unit of the chain file into millimetres through
``UnitInMillimetres``, 1000 for the metres the shipped machines are in.
"""

import math
import os

import FreeCAD

from kin5axcam import kin5ax

PROPERTY_GROUP = "Kin5axMachine"

#the two branches, in the order their parts are kept
BRANCHES = ((kin5ax.PART_TOOL, "Tool"), (kin5ax.PART_MATERIAL_HOLDER, "Material"))

#what a joint marker is painted: the sign of the value is the colour
POSITIVE = (1.0, 0.0, 1.0)              #magenta
NEGATIVE = (0.0, 1.0, 1.0)              #cyan
ZERO = (0.5, 0.5, 0.5)                  #nothing to sweep, nothing to slide
#the thickness of the disc of a revolute marker, as a fraction of its radius
DISC_THICKNESS = 0.08


def placement_of(frame, unit_in_mm):
    """A frame of kin5ax - 16 doubles in the layout OpenGL uses - as a FreeCAD Placement in mm."""
    m = frame
    s = unit_in_mm
    return FreeCAD.Placement(FreeCAD.Matrix(
        m[0], m[4], m[8], m[12] * s,
        m[1], m[5], m[9], m[13] * s,
        m[2], m[6], m[10], m[14] * s,
        0.0, 0.0, 0.0, 1.0))


class ObjectMachine(object):
    """The proxy of the machine group: builds the parts once, places them on every configuration."""

    def __init__(self, obj, chain_file, unit_in_mm):
        obj.Proxy = self
        self._chain = None
        obj.addProperty("App::PropertyFile", "ChainFile", PROPERTY_GROUP,
                        "The kinematic chain file of kin5ax this machine is read from (.kc or .kc.json)")
        obj.addProperty("App::PropertyFloat", "UnitInMillimetres", PROPERTY_GROUP,
                        "How many millimetres one length unit of the chain file is: 1000 for metres")
        obj.addProperty("App::PropertyFloatList", "Configuration", PROPERTY_GROUP,
                        "The five joint values the machine stands at, in the order of the links of "
                        "the chain, in the units of its file and in radians")
        obj.addProperty("App::PropertyFloat", "ArmRadius", PROPERTY_GROUP,
                        "The radius of the arms drawn between the segments, in mm; 0 picks one from "
                        "the size of the machine")
        obj.addProperty("App::PropertyFloat", "JointSize", PROPERTY_GROUP,
                        "The radius of the disc a turning joint shows its angle with, and the side of "
                        "the box a sliding one shows its travel with, in mm; 0 picks one from the "
                        "size of the machine")
        obj.addProperty("App::PropertyBool", "ShowJoints", PROPERTY_GROUP,
                        "Show every joint's value as a disc sector or a box, magenta when positive, "
                        "cyan when negative")
        for _, name in BRANCHES:
            obj.addProperty("App::PropertyLinkList", name + "Bodies", PROPERTY_GROUP,
                            "The parts holding the boxes of the segments of the %s branch" % name.lower())
            obj.addProperty("App::PropertyLinkList", name + "Arms", PROPERTY_GROUP,
                            "The parts holding the arms from each segment of the %s branch to the next"
                            % name.lower())
            #a global link: the markers live inside the parts of the segments, and a link into a part
            #from outside it is out of scope for an ordinary one
            obj.addProperty("App::PropertyLinkListGlobal", name + "Joints", PROPERTY_GROUP,
                            "The markers of the joints of the %s branch, one per segment that has one"
                            % name.lower())
        obj.addProperty("App::PropertyLink", "ToolMount", PROPERTY_GROUP,
                        "The part at the tool mount of the machine: a simulation puts the tool in it")
        obj.addProperty("App::PropertyLink", "Material", PROPERTY_GROUP,
                        "The part at the frame of the material: a simulation puts the model and the "
                        "stock in it")
        obj.ChainFile = chain_file
        obj.UnitInMillimetres = float(unit_in_mm)
        obj.ArmRadius = 0.0
        obj.JointSize = 0.0
        obj.ShowJoints = True
        self.build(obj)

    #the proxy is pickled into the document, and a handle of the library is not for pickling
    def dumps(self):
        return None

    def loads(self, state):
        self._chain = None
        self._shown_joints = None

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        self._chain = None
        self._shown_joints = None

    def chain(self, obj):
        """The chain of the library, opened on first use and kept for the life of the proxy."""
        chain = getattr(self, "_chain", None)
        if chain is None or chain.file_path != obj.ChainFile:
            if chain is not None:
                chain.close()
            chain = kin5ax.Chain(obj.ChainFile)
            self._chain = chain
        return chain

    def configuration(self, obj):
        values = list(obj.Configuration)
        if len(values) != kin5ax.AXES:
            values = [0.0] * kin5ax.AXES
        return values

    def linkOfSegment(self, chain, part, index):
        """The index into the links of the chain - and into every q - of the joint of that segment, or None.

        The links run from the material terminal through the base to the tool
        terminal; the segments of a branch run from the base outwards, and the
        last of them is the terminal, which has no joint.
        """
        material_joints = len(chain.frames(kin5ax.PART_MATERIAL_HOLDER)) - 1
        tool_joints = len(chain.frames(kin5ax.PART_TOOL)) - 1
        if part == kin5ax.PART_TOOL:
            return material_joints + index if index < tool_joints else None
        return material_joints - 1 - index if index < material_joints else None

    def build(self, obj):
        """The parts of the machine, once: boxes and arms for every segment, and the two end frames."""
        document = obj.Document
        chain = self.chain(obj)
        unit = obj.UnitInMillimetres
        chain.set_configuration(self.configuration(obj))
        arm_radius = obj.ArmRadius or self.automaticArmRadius(chain, unit)
        if not obj.JointSize:
            obj.JointSize = self.automaticJointSize(chain, unit)

        for part, name in BRANCHES:
            frames = chain.frames(part)
            bodies, arms, joints = [], [], []
            for index in range(len(frames)):
                body = document.addObject("App::Part", "%s%sBody" % (obj.Name, name))
                body.Label = "%s %d" % (name, index + 1)
                if self.linkOfSegment(chain, part, index) is not None:
                    marker = document.addObject("Part::Feature", "%s%sJoint" % (obj.Name, name))
                    marker.Label = "%s %d joint" % (name, index + 1)
                    body.addObject(marker)
                    joints.append(marker)
                for b, (low, high) in enumerate(chain.segment_boxes(part, index)):
                    box = document.addObject("Part::Feature", "%s%sBox" % (obj.Name, name))
                    box.Label = "%s %d box %d" % (name, index + 1, b + 1)
                    size = [max((high[k] - low[k]) * unit, 1e-6) for k in range(3)]
                    import Part
                    box.Shape = Part.makeBox(size[0], size[1], size[2],
                                             FreeCAD.Vector(low[0] * unit, low[1] * unit, low[2] * unit))
                    self.paint(box, part, 0.4)
                    body.addObject(box)
                bodies.append(body)
                if index + 1 < len(frames):
                    arm = document.addObject("App::Part", "%s%sArm" % (obj.Name, name))
                    arm.Label = "%s %d arm" % (name, index + 1)
                    #from the output frame of this segment to the joint frame of the next: a constant
                    #of the machine, so the shape is made once, in the output frame
                    here = placement_of(frames[index][1], unit)
                    there = placement_of(frames[index + 1][0], unit).Base
                    reach = here.inverse().multVec(there)
                    if reach.Length > 1e-9:
                        import Part
                        stick = document.addObject("Part::Feature", "%s%sStick" % (obj.Name, name))
                        stick.Label = "%s %d stick" % (name, index + 1)
                        stick.Shape = Part.makeCylinder(arm_radius, reach.Length, FreeCAD.Vector(),
                                                        reach)
                        self.paint(stick, part, 0.0)
                        arm.addObject(stick)
                    arms.append(arm)
                obj.addObject(body)
            for arm in arms:
                obj.addObject(arm)
            setattr(obj, name + "Bodies", bodies)
            setattr(obj, name + "Arms", arms)
            setattr(obj, name + "Joints", joints)

        mount = document.addObject("App::Part", obj.Name + "ToolMount")
        mount.Label = "Tool mount"
        material = document.addObject("App::Part", obj.Name + "Material")
        material.Label = "Material"
        obj.addObject(mount)
        obj.addObject(material)
        obj.ToolMount = mount
        obj.Material = material
        self.pose(obj)

    def automaticJointSize(self, chain, unit):
        """A tenth of the reach of the machine - what the application of kin5ax draws - and twenty
        millimetres at the least."""
        return max(10.0 * self.automaticArmRadius(chain, unit), 20.0)

    def automaticArmRadius(self, chain, unit):
        """A hundredth of the reach of the machine, and never less than two millimetres."""
        reach = 0.0
        for part, _ in BRANCHES:
            for joint, output in chain.frames(part):
                for frame in (joint, output):
                    reach = max(reach, abs(frame[12]), abs(frame[13]), abs(frame[14]))
        return max(0.01 * reach * unit, 2.0)

    def paint(self, feature, part, transparency):
        """A colour per branch, in the interface only; the boxes see-through so the tool shows inside."""
        view = getattr(feature, "ViewObject", None)
        if view is None:
            return
        view.ShapeColor = (0.55, 0.62, 0.75) if part == kin5ax.PART_TOOL else (0.75, 0.68, 0.5)
        view.Transparency = int(transparency * 100)

    def pose(self, obj):
        """Places every part by the frames of the chain at the configuration the machine stands at.

        A placement set here is set from outside the part's own recompute, which
        leaves the part touched; the touch is purged, since nothing of the part
        depends on it - the placement is the whole of the change.
        """
        chain = self.chain(obj)
        unit = obj.UnitInMillimetres
        chain.set_configuration(self.configuration(obj))
        for part, name in BRANCHES:
            frames = chain.frames(part)
            bodies = getattr(obj, name + "Bodies")
            arms = getattr(obj, name + "Arms")
            for index, (joint, output) in enumerate(frames):
                if index < len(bodies):
                    bodies[index].Placement = placement_of(joint, unit)
                    bodies[index].purgeTouched()
                if index < len(arms):
                    arms[index].Placement = placement_of(output, unit)
                    arms[index].purgeTouched()
            end = placement_of(frames[-1][1], unit)
            if part == kin5ax.PART_TOOL and obj.ToolMount is not None:
                obj.ToolMount.Placement = end
                obj.ToolMount.purgeTouched()
            if part == kin5ax.PART_MATERIAL_HOLDER and obj.Material is not None:
                obj.Material.Placement = end
                obj.Material.purgeTouched()
        self.showJoints(obj, chain)

    def showJoints(self, obj, chain, everything=False):
        """Every joint marker shaped to the value its joint stands at, and painted by the sign of it.

        A marker whose joint has not moved since it was last shaped is left as
        it is: a shape handed to the view is work for the view, and a step of a
        path moves two or three joints of five, not all of them.
        """
        import Part

        links = chain.links()
        size = obj.JointSize or self.automaticJointSize(chain, obj.UnitInMillimetres)
        unit = obj.UnitInMillimetres
        shown = getattr(self, "_shown_joints", None)
        if shown is None or everything:
            shown = self._shown_joints = {}
        for part, name in BRANCHES:
            markers = getattr(obj, name + "Joints", [])
            for index, marker in enumerate(markers):
                link_index = self.linkOfSegment(chain, part, index)
                if link_index is None or link_index >= len(links):
                    continue
                link = links[link_index]
                value = link.value
                key = (marker.Name, round(value, 9), size, bool(obj.ShowJoints))
                if shown.get(marker.Name) == key:
                    continue
                shown[marker.Name] = key
                if link.is_revolute:
                    marker.Shape = self.sector(size, value)
                else:
                    marker.Shape = self.slide(size, value * unit)
                marker.purgeTouched()
                view = getattr(marker, "ViewObject", None)
                if view is not None:
                    view.ShapeColor = POSITIVE if value > 1e-9 else NEGATIVE if value < -1e-9 else ZERO
                    view.Transparency = 30
                    view.Visibility = bool(obj.ShowJoints)

    @staticmethod
    def sector(radius, angle_radians):
        """A sector of a disc swept from zero to the angle, about Z, with a thin full disc under it."""
        import Part

        thickness = DISC_THICKNESS * radius
        dial = Part.makeCylinder(0.35 * radius, 0.5 * thickness, FreeCAD.Vector(0, 0, -0.25 * thickness))
        degrees = math.degrees(angle_radians)
        if abs(degrees) < 1e-6:
            return dial
        sweep = Part.makeCylinder(radius, thickness, FreeCAD.Vector(0, 0, -0.5 * thickness),
                                  FreeCAD.Vector(0, 0, 1), min(abs(degrees), 360.0))
        if degrees < 0.0:
            #from the angle up to zero rather than from zero down: the same sector, turned to start
            #where the joint stands
            sweep.rotate(FreeCAD.Vector(), FreeCAD.Vector(0, 0, 1), degrees)
        return Part.makeCompound([dial, sweep])

    @staticmethod
    def slide(side, travel_mm):
        """A box as long as the travel, along Z from zero to it, with a thin square plate at zero."""
        import Part

        plate = Part.makeBox(1.2 * side, 1.2 * side, 0.04 * side,
                             FreeCAD.Vector(-0.6 * side, -0.6 * side, -0.02 * side))
        if abs(travel_mm) < 1e-9:
            return plate
        box = Part.makeBox(side, side, abs(travel_mm),
                           FreeCAD.Vector(-0.5 * side, -0.5 * side, min(0.0, travel_mm)))
        return Part.makeCompound([plate, box])

    def onChanged(self, obj, prop):
        if "Restore" in obj.State or not getattr(obj, "ToolMount", None):
            return
        if prop == "Configuration":
            try:
                self.pose(obj)
            except Exception as problem:
                FreeCAD.Console.PrintError("kin5axcam: the machine cannot be posed: %s\n" % problem)
        elif prop in ("JointSize", "ShowJoints"):
            try:
                self.showJoints(obj, self.chain(obj), everything=True)
            except Exception as problem:
                FreeCAD.Console.PrintError("kin5axcam: the joints cannot be shown: %s\n" % problem)

    def execute(self, obj):
        self.pose(obj)

    def onDocumentRestored(self, obj):
        self._chain = None
        self._shown_joints = None
        globalise(obj, {name + "Joints": "App::PropertyLinkListGlobal" for _, name in BRANCHES})


def globalise(obj, wanted):
    """Turns link properties of an older document into the global kind, keeping what they link to.

    A document saved before the links were global has them ordinary, which
    FreeCAD reports as out of scope on every restore; the property is replaced
    by one of the right kind with the same value.
    """
    for name, kind in wanted.items():
        if name not in obj.PropertiesList or obj.getTypeIdOfProperty(name) == kind:
            continue
        value = getattr(obj, name)
        group = obj.getGroupOfProperty(name)
        documentation = obj.getDocumentationOfProperty(name)
        obj.removeProperty(name)
        obj.addProperty(kind, name, group, documentation)
        setattr(obj, name, value)


def Create(name, chain_file, unit_in_mm=1000.0, document=None):
    """A machine group in the document, built from the chain file, standing at zero."""
    if document is None:
        document = FreeCAD.ActiveDocument
    if not os.path.isfile(chain_file):
        raise IOError("there is no chain file at %s" % chain_file)
    obj = document.addObject("App::DocumentObjectGroupPython", name)
    ObjectMachine(obj, chain_file, unit_in_mm)
    return obj
