"""A job run on a machine of kin5ax: the operations solved, and the machine stepping through them.

The simulation is a document object that holds a machine, a job and the
trajectory the operations of the job solve to on that machine - five joint
values per location, the ones kin5ax invents between two moves included. Its
``Step`` is the location the machine is shown at: set it and the machine takes
that configuration, the tool of the operation hanging from the tool mount and
the model and the stock of the job sitting in the frame of the material. A
location the machine cannot reach is a marker where its tip would have been.

Recomputing the simulation solves the whole trajectory again - the batch; the
player of the task panel moves ``Step`` - the picture. Both run on
``kin5axcam.solve``, as the postprocessor does, so what is seen here is what is
written there.
"""

import FreeCAD

from kin5axcam import kin5ax, machine, solve

PROPERTY_GROUP = "Kin5axSimulation"

START_CHOICES = ["MIN_ABS", "MIN", "MAX", "SHORTEST"]


def _quantity(value):
    return float(getattr(value, "Value", value))


class ObjectSimulation(object):

    def __init__(self, obj, machine_object, job):
        obj.Proxy = self
        obj.addProperty("App::PropertyLink", "Machine", PROPERTY_GROUP, "The machine the job runs on")
        obj.addProperty("App::PropertyLink", "Job", PROPERTY_GROUP, "The job whose operations are run")
        obj.addProperty("App::PropertyLinkList", "Operations", PROPERTY_GROUP,
                        "The operations run, in this order; none means every active operation of the job")
        obj.addProperty("App::PropertyLength", "HolderLength", PROPERTY_GROUP,
                        "The holder between the tool and the spindle, which a tool bit does not describe")
        obj.addProperty("App::PropertyLength", "HolderRadius", PROPERTY_GROUP, "And its radius")
        obj.addProperty("App::PropertyBool", "CheckLimits", PROPERTY_GROUP,
                        "A configuration outside the joint limits is no solution")
        obj.addProperty("App::PropertyBool", "CheckCollisions", PROPERTY_GROUP,
                        "A configuration whose parts meet is no solution")
        obj.addProperty("App::PropertyBool", "Interpolate", PROPERTY_GROUP,
                        "Invent locations between two moves, as dense as the two bounds below")
        obj.addProperty("App::PropertyLength", "MaxStep", PROPERTY_GROUP,
                        "No invented step longer than this; 0 leaves it to kin5ax")
        obj.addProperty("App::PropertyAngle", "MaxTurn", PROPERTY_GROUP,
                        "Nor turning the tool axis further than this; 0 leaves it to kin5ax")
        obj.addProperty("App::PropertyEnumeration", "Start", PROPERTY_GROUP,
                        "Where the trajectory starts: the first rotary axis closest to zero, at its "
                        "minimum, at its maximum, or wherever makes the whole path shortest")
        obj.Start = START_CHOICES

        obj.addProperty("App::PropertyInteger", "Step", PROPERTY_GROUP,
                        "The location of the trajectory the machine is shown at")
        obj.addProperty("App::PropertyInteger", "StepCount", PROPERTY_GROUP,
                        "How many locations the trajectory has")
        obj.addProperty("App::PropertyFloatList", "Joints", PROPERTY_GROUP,
                        "Five joint values per location, in the order of the links of the chain")
        obj.addProperty("App::PropertyIntegerList", "Solved", PROPERTY_GROUP,
                        "1 for a location with a solution, 0 for one without")
        obj.addProperty("App::PropertyIntegerList", "Statuses", PROPERTY_GROUP,
                        "The status of kin5ax for every location")
        obj.addProperty("App::PropertyFloatList", "Tips", PROPERTY_GROUP,
                        "Where the tip of the tool was asked to be, three values per location, mm")
        obj.addProperty("App::PropertyIntegerList", "StepOperations", PROPERTY_GROUP,
                        "The index into Operations of the operation every location belongs to")
        obj.addProperty("App::PropertyString", "Report", PROPERTY_GROUP,
                        "What came of the solve: the counts by status and the largest errors")
        obj.addProperty("App::PropertyLink", "Tool", PROPERTY_GROUP, "The tool shown at the tool mount")
        obj.addProperty("App::PropertyLink", "Holder", PROPERTY_GROUP, "The holder shown above it")
        obj.addProperty("App::PropertyLinkList", "Workpiece", PROPERTY_GROUP,
                        "The links to the model and the stock of the job, in the frame of the material")
        obj.addProperty("App::PropertyLink", "Unreachable", PROPERTY_GROUP,
                        "The markers of the locations the machine cannot reach")
        for name in ("StepCount", "Joints", "Solved", "Statuses", "Tips", "StepOperations", "Report",
                     "Tool", "Holder", "Workpiece", "Unreachable"):
            obj.setEditorMode(name, 1)

        obj.Machine = machine_object
        obj.Job = job
        obj.HolderLength = 50.0
        obj.HolderRadius = 30.0
        obj.CheckLimits = True
        obj.CheckCollisions = True
        obj.Interpolate = True
        obj.MaxStep = 0.0
        obj.MaxTurn = 0.0
        obj.Start = "MIN_ABS"
        obj.Step = 0
        self._shown_operation = None

    def dumps(self):
        return None

    def loads(self, state):
        self._shown_operation = None

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        self._shown_operation = None

    # ---------------------------------------------------------------- what is run, and how

    def operations(self, obj):
        if obj.Operations:
            return list(obj.Operations)
        job = obj.Job
        if job is None or not hasattr(job, "Operations"):
            return []
        return [op for op in job.Operations.Group if getattr(op, "Active", True)]

    def options(self, obj):
        machine_object = obj.Machine
        unit = machine_object.UnitInMillimetres if machine_object is not None else 1000.0
        return solve.Options(
            unit_in_mm=unit,
            holder_length_mm=_quantity(obj.HolderLength),
            holder_radius_mm=_quantity(obj.HolderRadius),
            check_limits=obj.CheckLimits,
            check_collisions=obj.CheckCollisions,
            interpolate=obj.Interpolate,
            max_step_mm=_quantity(obj.MaxStep) or None,
            max_turn_degrees=_quantity(obj.MaxTurn) or None,
            start=obj.Start,
        )

    # ---------------------------------------------------------------- the batch

    def execute(self, obj):
        """Solves every operation on the machine and keeps the trajectory in the properties."""
        machine_object = obj.Machine
        if machine_object is None or obj.Job is None:
            raise ValueError("the simulation needs a machine and a job")
        chain = machine_object.Proxy.chain(machine_object)
        options = self.options(obj)
        joints, solved, statuses, tips, operations_of_steps = [], [], [], [], []
        reports = []
        for index, operation in enumerate(self.operations(obj)):
            moves = solve.moves_of(operation)
            if not moves:
                continue
            model = solve.tool_model_of(operation, options)
            trajectory = solve.solve(chain, moves, model, options)
            for step in trajectory.steps:
                joints.extend(step.q if step.solved else [0.0] * kin5ax.AXES)
                solved.append(1 if step.solved else 0)
                statuses.append(step.status)
                tips.extend(step.move.point)
                operations_of_steps.append(index)
            reports.append("%s: %s" % (operation.Label, trajectory.describe()))
        obj.Joints = joints
        obj.Solved = solved
        obj.Statuses = statuses
        obj.Tips = tips
        obj.StepOperations = operations_of_steps
        obj.StepCount = len(solved)
        obj.Report = "\n".join(reports) if reports else "nothing to run"
        self.placeWorkpiece(obj)
        self.markUnreachable(obj)
        self._shown_operation = None
        if obj.Step >= obj.StepCount:
            obj.Step = max(obj.StepCount - 1, 0)
        self.pose(obj)

    def placeWorkpiece(self, obj):
        """Links to the model and the stock of the job, in the part of the machine's material frame."""
        material = obj.Machine.Material
        wanted = []
        job = obj.Job
        if hasattr(job, "Model") and job.Model is not None:
            wanted.extend(job.Model.Group)
        if getattr(job, "Stock", None) is not None:
            wanted.append(job.Stock)
        existing = {link.LinkedObject.Name: link for link in obj.Workpiece if link.LinkedObject is not None}
        links = []
        for target in wanted:
            link = existing.pop(target.Name, None)
            if link is None:
                link = obj.Document.addObject("App::Link", obj.Name + "Workpiece")
                link.LinkedObject = target
                material.addObject(link)
                view = getattr(link, "ViewObject", None)
                if view is not None and target is getattr(job, "Stock", None):
                    view.Transparency = 70
            link.Label = "%s on the machine" % target.Label
            links.append(link)
        for stale in existing.values():
            obj.Document.removeObject(stale.Name)
        obj.Workpiece = links

    def markUnreachable(self, obj):
        """A vertex where the tip of every unreachable location would have been, in the part frame."""
        import Part

        points = [FreeCAD.Vector(obj.Tips[3 * i], obj.Tips[3 * i + 1], obj.Tips[3 * i + 2])
                  for i in range(obj.StepCount) if not obj.Solved[i]]
        marker = obj.Unreachable
        if not points:
            if marker is not None:
                obj.Document.removeObject(marker.Name)
                obj.Unreachable = None
            return
        if marker is None:
            marker = obj.Document.addObject("Part::Feature", obj.Name + "Unreachable")
            marker.Label = "Unreachable locations"
            obj.Machine.Material.addObject(marker)
            view = getattr(marker, "ViewObject", None)
            if view is not None:
                view.PointColor = (1.0, 0.0, 0.0)
                view.PointSize = 6.0
            obj.Unreachable = marker
        marker.Shape = Part.makeCompound([Part.Vertex(p) for p in points])

    # ---------------------------------------------------------------- the picture

    def configurationAt(self, obj, step):
        if step < 0 or step >= obj.StepCount or not obj.Solved[step]:
            return None
        return list(obj.Joints[kin5ax.AXES * step:kin5ax.AXES * (step + 1)])

    def pose(self, obj):
        """The machine at the configuration of the step, with the tool of the step's operation in it."""
        machine_object = obj.Machine
        if machine_object is None or obj.StepCount == 0:
            return
        step = max(0, min(obj.Step, obj.StepCount - 1))
        self.showTool(obj, obj.StepOperations[step])
        q = self.configurationAt(obj, step)
        if q is not None:
            machine_object.Configuration = q

    def showTool(self, obj, operation_index):
        """The tool of that operation at the mount: the bit's own solid when it has one, else a cylinder."""
        if operation_index == getattr(self, "_shown_operation", None):
            return
        operations = self.operations(obj)
        if operation_index >= len(operations):
            return
        import Part

        operation = operations[operation_index]
        options = self.options(obj)
        model = solve.tool_model_of(operation, options)
        if model is None:
            return
        mount = obj.Machine.ToolMount
        tool = obj.Tool
        if tool is None:
            tool = obj.Document.addObject("Part::Feature", obj.Name + "Tool")
            tool.Label = "Tool on the machine"
            mount.addObject(tool)
            obj.Tool = tool
            view = getattr(tool, "ViewObject", None)
            if view is not None:
                view.ShapeColor = (0.85, 0.85, 0.9)
        holder = obj.Holder
        if holder is None:
            holder = obj.Document.addObject("Part::Feature", obj.Name + "Holder")
            holder.Label = "Holder on the machine"
            mount.addObject(holder)
            obj.Holder = holder
            view = getattr(holder, "ViewObject", None)
            if view is not None:
                view.ShapeColor = (0.4, 0.4, 0.45)
        bit = getattr(getattr(operation, "ToolController", None), "Tool", None)
        shape = getattr(bit, "Shape", None)
        if shape is None or shape.isNull():
            shape = Part.makeCylinder(model.radius_mm, model.cutting_height_mm + model.shank_length_mm)
        tool.Shape = shape
        #the tip of a bit is at its origin and its shank runs up +Z; the tool hangs the length of
        #the assembly below the mount, along the -Z of the mount frame
        tool.Placement = FreeCAD.Placement(FreeCAD.Vector(0, 0, -model.assembly_length_mm),
                                           FreeCAD.Rotation())
        holder.Shape = Part.makeCylinder(model.holder_radius_mm, model.holder_length_mm)
        holder.Placement = FreeCAD.Placement(FreeCAD.Vector(0, 0, -model.holder_length_mm),
                                             FreeCAD.Rotation())
        self._shown_operation = operation_index

    def onChanged(self, obj, prop):
        if prop == "Step" and "Restore" not in obj.State and getattr(obj, "StepCount", 0):
            try:
                self.pose(obj)
            except Exception as problem:
                FreeCAD.Console.PrintError("kin5axcam: the simulation cannot be posed: %s\n" % problem)

    def onDocumentRestored(self, obj):
        self._shown_operation = None


def Create(name, machine_object, job, document=None):
    """A simulation of the job on the machine, not yet run: recompute it, then step it."""
    if document is None:
        document = FreeCAD.ActiveDocument
    obj = document.addObject("App::FeaturePython", name)
    ObjectSimulation(obj, machine_object, job)
    return obj
