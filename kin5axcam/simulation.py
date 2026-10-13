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

With ``Cut`` on, the stock of the job becomes a block of voxels in the library
and every step cuts it: the surface of what is left is a point cloud in the
frame of the material, the removed volume and the gouges - the shank or the
holder in material that was still there - are properties, and the first gouge
is a marker. The cut is rudimentary and says so: the tool is stamped once per
location, so the interpolation is made as dense as the voxels. Stepping
backwards starts the cut again from a whole block. The cut needs the solved
paths of the library, which live only while the document is open: after a
restore, recompute the simulation to cut again.
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

        obj.addProperty("App::PropertyBool", "Cut", PROPERTY_GROUP,
                        "Cut the stock of the job as the machine goes, and show what is left")
        obj.addProperty("App::PropertyLength", "VoxelSize", PROPERTY_GROUP,
                        "The side of a voxel of the stock; 0 picks one from the size of the stock")
        obj.addProperty("App::PropertyInteger", "RefreshEvery", PROPERTY_GROUP,
                        "How many cut steps between two redraws of what is left of the stock")
        obj.addProperty("App::PropertyFloat", "RemovedVolume", PROPERTY_GROUP,
                        "The volume cut off the stock so far, in cubic millimetres")
        obj.addProperty("App::PropertyInteger", "Gouges", PROPERTY_GROUP,
                        "How many locations so far had the shank or the holder in material still there")
        obj.addProperty("App::PropertyVector", "FirstGouge", PROPERTY_GROUP,
                        "Where the first of them was, in the frame of the part")
        obj.addProperty("App::PropertyLink", "Cloud", PROPERTY_GROUP,
                        "The surface of what is left of the stock, as points")
        obj.addProperty("App::PropertyLink", "GougeMarker", PROPERTY_GROUP,
                        "The marker of the first gouge")
        for name in ("StepCount", "Joints", "Solved", "Statuses", "Tips", "StepOperations", "Report",
                     "Tool", "Holder", "Workpiece", "Unreachable", "RemovedVolume", "Gouges",
                     "FirstGouge", "Cloud", "GougeMarker"):
            obj.setEditorMode(name, 1)
        obj.Cut = True
        obj.VoxelSize = 0.0
        obj.RefreshEvery = 5

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
        self.forget()

    def forget(self):
        """The state that lives only while the document is open: nothing of it is pickled."""
        self._shown_operation = None
        self._runs = None               #the trajectories of the operations, paths and tools kept
        self._block = None              #the material of the library
        self._cuts = None               #a cutting simulation of the library per run
        self._cut_to = -1               #the last step the cut was taken to, -1 for a whole block
        self._cut_since_refresh = 0

    def dumps(self):
        return None

    def loads(self, state):
        self.forget()

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        self.forget()

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
        max_step = _quantity(obj.MaxStep) or None
        if max_step is None and getattr(obj, "Cut", False) and self.stockBox(obj) is not None:
            #a cut is a stamp per location, so the locations have to be as dense as the voxels
            max_step = self.voxelSize(obj)
        return solve.Options(
            unit_in_mm=unit,
            holder_length_mm=_quantity(obj.HolderLength),
            holder_radius_mm=_quantity(obj.HolderRadius),
            check_limits=obj.CheckLimits,
            check_collisions=obj.CheckCollisions,
            interpolate=obj.Interpolate,
            max_step_mm=max_step,
            max_turn_degrees=_quantity(obj.MaxTurn) or None,
            start=obj.Start,
        )

    def stockBox(self, obj):
        """The bounding box of the stock of the job, in the frame of the part, or None without a stock."""
        stock = getattr(obj.Job, "Stock", None) if obj.Job is not None else None
        shape = getattr(stock, "Shape", None)
        if shape is None or shape.isNull():
            return None
        return shape.BoundBox

    def voxelSize(self, obj):
        """The side of a voxel in mm: the property, or a hundred and fiftieth of the stock's longest side."""
        size = _quantity(obj.VoxelSize)
        if size > 0.0:
            return size
        box = self.stockBox(obj)
        if box is None:
            return 1.0
        longest = max(box.XLength, box.YLength, box.ZLength)
        return min(max(longest / 150.0, 0.1), 5.0)

    # ---------------------------------------------------------------- the batch

    def execute(self, obj):
        """Solves every operation on the machine and keeps the trajectory in the properties."""
        machine_object = obj.Machine
        if machine_object is None or obj.Job is None:
            raise ValueError("the simulation needs a machine and a job")
        chain = machine_object.Proxy.chain(machine_object)
        options = self.options(obj)
        self.forgetCut()
        joints, solved, statuses, tips, operations_of_steps = [], [], [], [], []
        reports = []
        runs = []
        for index, operation in enumerate(self.operations(obj)):
            moves = solve.moves_of(operation)
            if not moves:
                continue
            model = solve.tool_model_of(operation, options)
            trajectory = solve.solve(chain, moves, model, options, keep=obj.Cut)
            first = len(solved)
            for step in trajectory.steps:
                joints.extend(step.q if step.solved else [0.0] * kin5ax.AXES)
                solved.append(1 if step.solved else 0)
                statuses.append(step.status)
                tips.extend(step.move.point)
                operations_of_steps.append(index)
            runs.append((first, len(solved), trajectory))
            reports.append("%s: %s" % (operation.Label, trajectory.describe()))
        self._runs = runs
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
        self.prepareCut(obj)
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

    # ---------------------------------------------------------------- the cut

    def forgetCut(self):
        """Releases what the library holds for the cut: the simulations, the block, the paths."""
        for cut in (self._cuts or []):
            cut.close()
        self._cuts = None
        if self._block is not None:
            self._block.close()
            self._block = None
        for _, _, trajectory in (self._runs or []):
            trajectory.close()
        self._runs = None
        self._cut_to = -1
        self._cut_since_refresh = 0

    def prepareCut(self, obj):
        """The block of the library from the stock of the job, and a cutting simulation per run."""
        obj.RemovedVolume = 0.0
        obj.Gouges = 0
        if not obj.Cut or not self._runs:
            self.removeCloud(obj)
            return
        box = self.stockBox(obj)
        if box is None:
            obj.Report = obj.Report + "\nno stock in the job to cut"
            self.removeCloud(obj)
            return
        unit = obj.Machine.UnitInMillimetres
        voxel = self.voxelSize(obj)
        try:
            self._block = kin5ax.Material(
                (box.XLength / unit, box.YLength / unit, box.ZLength / unit), voxel / unit,
                (box.XMin / unit, box.YMin / unit, box.ZMin / unit))
        except kin5ax.Kin5axError as problem:
            obj.Report = obj.Report + "\nthe stock cannot be cut: %s" % problem
            self._block = None
            self.removeCloud(obj)
            return
        chain = obj.Machine.Proxy.chain(obj.Machine)
        self._cuts = []
        for _, _, trajectory in self._runs:
            if trajectory.path is None or trajectory.tool is None:
                self._cuts.append(None)
                continue
            self._cuts.append(kin5ax.Simulation(chain, trajectory.tool, trajectory.path, self._block))
        self._cut_to = -1
        self.refreshCloud(obj)

    def cutTo(self, obj, step):
        """Takes the cut up to that step, from a whole block again when the step is behind the cut."""
        if self._block is None or not self._cuts:
            return
        if step < self._cut_to:
            self._block.reset()
            for cut in self._cuts:
                if cut is not None:
                    cut.reset()
            self._cut_to = -1
        if step == self._cut_to:
            return
        advanced = 0
        for (first, end, _), cut in zip(self._runs, self._cuts):
            if cut is None or end <= self._cut_to + 1:
                continue
            if first > step:
                break
            #how many locations of this run to pass: up to the step, or all of them when it lies beyond
            target = min(step, end - 1) - first + 1
            passed, _, _ = cut.progress()
            while passed < target:
                if not cut.step():
                    break
                passed, _, _ = cut.progress()
                advanced += 1
            #the locations without a solution are passed by the library without a cut; the count
            #it reports is of locations passed, the way it is here
        self._cut_to = step
        self._cut_since_refresh += advanced
        unit = obj.Machine.UnitInMillimetres
        total, removed = self._block.volumes()
        obj.RemovedVolume = removed * unit ** 3
        gouges, first_point = 0, None
        for cut in self._cuts:
            if cut is None:
                continue
            count, _, point = cut.gouges()
            if count and first_point is None:
                first_point = point
            gouges += count
        obj.Gouges = gouges
        if first_point is not None:
            obj.FirstGouge = FreeCAD.Vector(first_point[0] * unit, first_point[1] * unit,
                                            first_point[2] * unit)
        self.markGouge(obj, first_point is not None)
        finished = step >= obj.StepCount - 1
        if self._cut_since_refresh >= max(obj.RefreshEvery, 1) or finished or advanced == 0:
            self.refreshCloud(obj)

    def refreshCloud(self, obj):
        """The surface of what is left of the block, as points at the centres of its voxels."""
        import Points

        if self._block is None:
            return
        unit = obj.Machine.UnitInMillimetres
        half = 0.5 * self._block.voxel * unit
        surface = self._block.surface()
        points = [FreeCAD.Vector(surface[3 * i] * unit + half, surface[3 * i + 1] * unit + half,
                                 surface[3 * i + 2] * unit + half) for i in range(len(surface) // 3)]
        cloud = obj.Cloud
        if cloud is None:
            cloud = obj.Document.addObject("Points::Feature", obj.Name + "Cloud")
            cloud.Label = "What is left of the stock"
            obj.Machine.Material.addObject(cloud)
            obj.Cloud = cloud
            view = getattr(cloud, "ViewObject", None)
            if view is not None:
                view.PointSize = 3.0
                view.ShapeColor = (0.9, 0.75, 0.3)
        kept = Points.Points()
        kept.addPoints(points)
        cloud.Points = kept
        self._cut_since_refresh = 0

    def removeCloud(self, obj):
        for name in ("Cloud", "GougeMarker"):
            marker = getattr(obj, name)
            if marker is not None:
                obj.Document.removeObject(marker.Name)
                setattr(obj, name, None)

    def markGouge(self, obj, there_is_one):
        import Part

        marker = obj.GougeMarker
        if not there_is_one:
            if marker is not None:
                obj.Document.removeObject(marker.Name)
                obj.GougeMarker = None
            return
        if marker is None:
            marker = obj.Document.addObject("Part::Feature", obj.Name + "Gouge")
            marker.Label = "First gouge"
            obj.Machine.Material.addObject(marker)
            view = getattr(marker, "ViewObject", None)
            if view is not None:
                view.PointColor = (1.0, 0.3, 0.0)
                view.PointSize = 10.0
            obj.GougeMarker = marker
        marker.Shape = Part.Vertex(obj.FirstGouge)

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
        if obj.Cut:
            self.cutTo(obj, step)

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
        self.forget()


def Create(name, machine_object, job, document=None):
    """A simulation of the job on the machine, not yet run: recompute it, then step it."""
    if document is None:
        document = FreeCAD.ActiveDocument
    obj = document.addObject("App::FeaturePython", name)
    ObjectSimulation(obj, machine_object, job)
    return obj
