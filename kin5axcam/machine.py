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
        for _, name in BRANCHES:
            obj.addProperty("App::PropertyLinkList", name + "Bodies", PROPERTY_GROUP,
                            "The parts holding the boxes of the segments of the %s branch" % name.lower())
            obj.addProperty("App::PropertyLinkList", name + "Arms", PROPERTY_GROUP,
                            "The parts holding the arms from each segment of the %s branch to the next"
                            % name.lower())
        obj.addProperty("App::PropertyLink", "ToolMount", PROPERTY_GROUP,
                        "The part at the tool mount of the machine: a simulation puts the tool in it")
        obj.addProperty("App::PropertyLink", "Material", PROPERTY_GROUP,
                        "The part at the frame of the material: a simulation puts the model and the "
                        "stock in it")
        obj.ChainFile = chain_file
        obj.UnitInMillimetres = float(unit_in_mm)
        obj.ArmRadius = 0.0
        self.build(obj)

    #the proxy is pickled into the document, and a handle of the library is not for pickling
    def dumps(self):
        return None

    def loads(self, state):
        self._chain = None

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        self._chain = None

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

    def build(self, obj):
        """The parts of the machine, once: boxes and arms for every segment, and the two end frames."""
        document = obj.Document
        chain = self.chain(obj)
        unit = obj.UnitInMillimetres
        chain.set_configuration(self.configuration(obj))
        arm_radius = obj.ArmRadius or self.automaticArmRadius(chain, unit)

        for part, name in BRANCHES:
            frames = chain.frames(part)
            bodies, arms = [], []
            for index in range(len(frames)):
                body = document.addObject("App::Part", "%s%sBody" % (obj.Name, name))
                body.Label = "%s %d" % (name, index + 1)
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

        mount = document.addObject("App::Part", obj.Name + "ToolMount")
        mount.Label = "Tool mount"
        material = document.addObject("App::Part", obj.Name + "Material")
        material.Label = "Material"
        obj.addObject(mount)
        obj.addObject(material)
        obj.ToolMount = mount
        obj.Material = material
        self.pose(obj)

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
        """Places every part by the frames of the chain at the configuration the machine stands at."""
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
                if index < len(arms):
                    arms[index].Placement = placement_of(output, unit)
            end = placement_of(frames[-1][1], unit)
            if part == kin5ax.PART_TOOL and obj.ToolMount is not None:
                obj.ToolMount.Placement = end
            if part == kin5ax.PART_MATERIAL_HOLDER and obj.Material is not None:
                obj.Material.Placement = end

    def onChanged(self, obj, prop):
        if prop == "Configuration" and "Restore" not in obj.State and getattr(obj, "ToolMount", None):
            try:
                self.pose(obj)
            except Exception as problem:
                FreeCAD.Console.PrintError("kin5axcam: the machine cannot be posed: %s\n" % problem)

    def execute(self, obj):
        self.pose(obj)

    def onDocumentRestored(self, obj):
        self._chain = None


def Create(name, chain_file, unit_in_mm=1000.0, document=None):
    """A machine group in the document, built from the chain file, standing at zero."""
    if document is None:
        document = FreeCAD.ActiveDocument
    if not os.path.isfile(chain_file):
        raise IOError("there is no chain file at %s" % chain_file)
    obj = document.addObject("App::DocumentObjectGroupPython", name)
    ObjectMachine(obj, chain_file, unit_in_mm)
    return obj
