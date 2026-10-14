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

With no machine - ``Machine`` left empty - there is nothing to solve: the path
itself is the trajectory, made as dense as the voxels by the library, and the
tool is drawn in the frame of the part at the tip and the axis of each
location, leaning the way the operation said. This is the cutting simulation
FreeCAD's own cannot do, and it needs no machine file at all.

With ``Cut`` on, the stock of the job becomes a block of voxels in the library
and every step cuts it: what is left is a mesh of the exposed voxel faces in
the frame of the material - the library says which faces are exposed, so no
face a renderer could not see is drawn - the removed volume and the gouges -
the shank or the holder in material that was still there - are properties, and
the first gouge is a marker. The cut is rudimentary and says so: the tool is stamped once per
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
        obj.addProperty("App::PropertyLink", "Machine", PROPERTY_GROUP,
                        "The machine the job runs on; none, and the path is played as it is, the tool "
                        "leaning in the frame of the part")
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
        obj.addProperty("App::PropertyFloatList", "Axes", PROPERTY_GROUP,
                        "Which way the tool was asked to point, three values per location")
        obj.addProperty("App::PropertyLink", "ToolFrame", PROPERTY_GROUP,
                        "Without a machine: the part the tool hangs from, placed at every location")
        obj.addProperty("App::PropertyLink", "PartFrame", PROPERTY_GROUP,
                        "Without a machine: the part holding what is left of the stock and the markers")
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
        obj.addProperty("App::PropertyLink", "Surface", PROPERTY_GROUP,
                        "What is left of the stock, as a mesh of the exposed faces of its voxels")
        obj.addProperty("App::PropertyLink", "GougeMarker", PROPERTY_GROUP,
                        "The marker of the first gouge")
        for name in ("StepCount", "Joints", "Solved", "Statuses", "Tips", "Axes", "StepOperations",
                     "Report", "Tool", "Holder", "Workpiece", "Unreachable", "RemovedVolume", "Gouges",
                     "FirstGouge", "Surface", "GougeMarker", "ToolFrame", "PartFrame"):
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

    def unit(self, obj):
        """Millimetres per length unit of the picture: the chain file's, or 1 when there is no machine."""
        machine_object = obj.Machine
        return machine_object.UnitInMillimetres if machine_object is not None else 1.0

    def toolHolderPart(self, obj):
        """The part the tool hangs from: the tool mount of the machine, or a frame of this object's own."""
        if obj.Machine is not None:
            return obj.Machine.ToolMount
        frame = obj.ToolFrame
        if frame is None:
            frame = obj.Document.addObject("App::Part", obj.Name + "ToolFrame")
            frame.Label = "Tool"
            obj.ToolFrame = frame
        return frame

    def materialPart(self, obj):
        """The part in the frame of the material: the machine's, or the frame of the part itself."""
        if obj.Machine is not None:
            return obj.Machine.Material
        frame = obj.PartFrame
        if frame is None:
            frame = obj.Document.addObject("App::Part", obj.Name + "PartFrame")
            frame.Label = "Stock on the path"
            obj.PartFrame = frame
        return frame

    def options(self, obj):
        unit = self.unit(obj)
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
        if obj.Job is None:
            raise ValueError("the simulation needs a job")
        machine_object = obj.Machine
        chain = machine_object.Proxy.chain(machine_object) if machine_object is not None else None
        options = self.options(obj)
        if not self.pictureBelongsToTheMachine(obj):
            self.clearPicture(obj)
        self.forgetCut()
        joints, solved, statuses, tips, axes, operations_of_steps = [], [], [], [], [], []
        reports = []
        runs = []
        for index, operation in enumerate(self.operations(obj)):
            moves = solve.moves_of(operation)
            if not moves:
                continue
            model = solve.tool_model_of(operation, options)
            first = len(solved)
            if chain is not None:
                trajectory = solve.solve(chain, moves, model, options, keep=obj.Cut)
                for step in trajectory.steps:
                    joints.extend(step.q if step.solved else [0.0] * kin5ax.AXES)
                    solved.append(1 if step.solved else 0)
                    statuses.append(step.status)
                    tips.extend(step.move.point)
                    axes.extend(step.move.axis)
                    operations_of_steps.append(index)
                runs.append((first, len(solved), trajectory))
                reports.append("%s: %s" % (operation.Label, trajectory.describe()))
            else:
                #no machine: the path is the trajectory, made dense by the library, every location of
                #it reachable by definition
                dense = self.densify(obj, moves, model, options)
                for point, axis in dense:
                    solved.append(1)
                    statuses.append(kin5ax.SOLVED)
                    tips.extend(point)
                    axes.extend(axis)
                    operations_of_steps.append(index)
                runs.append((first, len(solved), (moves, model)))
                reports.append("%s: %d locations of the path, %d with those invented between"
                               % (operation.Label, len(moves), len(dense)))
        self._runs = runs
        obj.Joints = joints
        obj.Solved = solved
        obj.Statuses = statuses
        obj.Tips = tips
        obj.Axes = axes
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

    def densify(self, obj, moves, model, options):
        """The moves made as dense as the voxels, by the library: a list of (tip, axis) in mm.

        The library densifies programmed points, so a ball nose tool's path goes
        over as ball centres and comes back as tips - the same shift the solve
        makes, and nothing invented in Python.
        """
        tool = model.to_kin5ax(1.0) if model is not None else None
        if tool is None:
            raise ValueError("there is no tool to cut with: pick a tool controller")
        try:
            with kin5ax.Material((1.0, 1.0, 1.0), 1.0, (0.0, 0.0, 0.0)) as nothing:
                with kin5ax.Simulation.from_locations(
                        tool, options.settings(),
                        [model.programmed_point(m.point, m.axis) for m in moves],
                        [m.axis for m in moves], nothing) as dense:
                    lift = model.radius_mm if model.ball_nosed else 0.0
                    out = []
                    for position, axis, _, _ in dense.locations():
                        out.append((tuple(position[i] - lift * axis[i] for i in range(3)), tuple(axis)))
                    return out
        finally:
            tool.close()

    OWNED = ("Tool", "Holder", "Unreachable", "Surface", "GougeMarker", "ToolFrame", "PartFrame")

    def clearPicture(self, obj):
        """Takes every object this simulation put in the document out again.

        The tool and the holder hang from the machine's mount or from a frame of
        this object's own, the cloud and the markers sit in the material part or
        in the part frame: whichever it was, a change of machine makes it the
        wrong parent, and the next recompute builds them again under the right
        one. Called when the machine changes and when the simulation is deleted.
        """
        document = obj.Document
        for link in list(obj.Workpiece):
            if link is not None and link.Document is not None:
                document.removeObject(link.Name)
        obj.Workpiece = []
        for name in self.OWNED:
            owned = getattr(obj, name, None)
            if owned is not None:
                setattr(obj, name, None)
                if owned.Document is not None:
                    document.removeObject(owned.Name)
        self._shown_operation = None
        self.forgetCut()

    def pictureBelongsToTheMachine(self, obj):
        """Whether the tool hangs where this simulation's machine - or the lack of one - says it should."""
        tool = obj.Tool
        if tool is None:
            return True
        if obj.Machine is not None:
            return tool in obj.Machine.ToolMount.Group
        return obj.ToolFrame is not None and tool in obj.ToolFrame.Group

    def placeWorkpiece(self, obj):
        """Links to the model and the stock of the job, in the part of the material frame.

        Without a machine the frame of the part is the frame of the document,
        where the model and the stock sit already: nothing to link.
        """
        if obj.Machine is None:
            for stale in obj.Workpiece:
                obj.Document.removeObject(stale.Name)
            obj.Workpiece = []
            return
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
            #the placement of the model or the stock is part of where it is: a link leaves it out
            #unless told to carry it, and then the stock sat at the origin while the cut did not
            link.LinkTransform = True
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
            self.materialPart(obj).addObject(marker)
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
            if cut is not None:
                tool = getattr(cut, "tool", None)
                cut.close()
                if tool is not None and cut.chain is None:
                    tool.close()
        self._cuts = None
        if self._block is not None:
            self._block.close()
            self._block = None
        for _, _, trajectory in (self._runs or []):
            if hasattr(trajectory, "close"):
                trajectory.close()
        self._runs = None
        self._cut_to = -1
        self._cut_since_refresh = 0

    def prepareCut(self, obj):
        """The block of the library from the stock of the job, and a cutting simulation per run."""
        obj.RemovedVolume = 0.0
        obj.Gouges = 0
        if not obj.Cut or not self._runs:
            self.removeSurface(obj)
            return
        box = self.stockBox(obj)
        if box is None:
            obj.Report = obj.Report + "\nno stock in the job to cut"
            self.removeSurface(obj)
            return
        unit = self.unit(obj)
        voxel = self.voxelSize(obj)
        try:
            self._block = kin5ax.Material(
                (box.XLength / unit, box.YLength / unit, box.ZLength / unit), voxel / unit,
                (box.XMin / unit, box.YMin / unit, box.ZMin / unit))
        except kin5ax.Kin5axError as problem:
            obj.Report = obj.Report + "\nthe stock cannot be cut: %s" % problem
            self._block = None
            self.removeSurface(obj)
            return
        self._cuts = []
        if obj.Machine is not None:
            chain = obj.Machine.Proxy.chain(obj.Machine)
            for _, _, trajectory in self._runs:
                if trajectory.path is None or trajectory.tool is None:
                    self._cuts.append(None)
                    continue
                self._cuts.append(kin5ax.Simulation(chain, trajectory.tool, trajectory.path, self._block))
        else:
            options = self.options(obj)
            for _, _, (moves, model) in self._runs:
                tool = model.to_kin5ax(1.0)
                cut = kin5ax.Simulation.from_locations(
                    tool, options.settings(), [model.programmed_point(m.point, m.axis) for m in moves],
                    [m.axis for m in moves], self._block)
                cut.tool = tool             #kept alive with the simulation, closed with it
                self._cuts.append(cut)
        self._cut_to = -1
        self.refreshSurface(obj)

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
        unit = self.unit(obj)
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
            self.refreshSurface(obj)

    def refreshSurface(self, obj):
        """What is left of the block as a mesh: the exposed faces of its voxels, from the library.

        The library hands over the faces as triangles already wound outwards -
        every side of a material voxel with nothing behind it, and no other -
        so the only work here is handing them to the mesh.
        """
        import Mesh

        if self._block is None:
            return
        unit = self.unit(obj)
        t = self._block.surface_triangles()
        facets = [((t[i] * unit, t[i + 1] * unit, t[i + 2] * unit),
                   (t[i + 3] * unit, t[i + 4] * unit, t[i + 5] * unit),
                   (t[i + 6] * unit, t[i + 7] * unit, t[i + 8] * unit)) for i in range(0, len(t), 9)]
        surface = obj.Surface
        if surface is None:
            surface = obj.Document.addObject("Mesh::Feature", obj.Name + "Surface")
            surface.Label = "What is left of the stock"
            self.materialPart(obj).addObject(surface)
            obj.Surface = surface
            view = getattr(surface, "ViewObject", None)
            if view is not None:
                view.ShapeColor = (0.9, 0.75, 0.3)
                view.Lighting = "One side"
        surface.Mesh = Mesh.Mesh(facets)
        self._cut_since_refresh = 0

    def removeSurface(self, obj):
        for name in ("Surface", "GougeMarker"):
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
            self.materialPart(obj).addObject(marker)
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
        """The machine at the configuration of the step - or, without one, the tool at its location."""
        if obj.StepCount == 0:
            return
        step = max(0, min(obj.Step, obj.StepCount - 1))
        self.showTool(obj, obj.StepOperations[step])
        machine_object = obj.Machine
        if machine_object is not None:
            q = self.configurationAt(obj, step)
            if q is not None:
                machine_object.Configuration = q
        else:
            self.placeToolFrame(obj, step)
        if obj.Cut:
            self.cutTo(obj, step)

    def placeToolFrame(self, obj, step):
        """The tool frame at the tip and the axis of the step: Z along the axis, the mount up it.

        The tool and the holder hang below the origin of the frame by the length
        of the assembly, as they do from a machine's mount, so the frame goes
        where the mount would be: the tip plus the assembly along the axis.
        """
        tip = FreeCAD.Vector(obj.Tips[3 * step], obj.Tips[3 * step + 1], obj.Tips[3 * step + 2])
        axis = FreeCAD.Vector(obj.Axes[3 * step], obj.Axes[3 * step + 1], obj.Axes[3 * step + 2])
        if axis.Length < 1e-12:
            axis = FreeCAD.Vector(0, 0, 1)
        axis.normalize()
        operations = self.operations(obj)
        index = obj.StepOperations[step]
        hang = 0.0
        if index < len(operations):
            model = solve.tool_model_of(operations[index], self.options(obj))
            if model is not None:
                hang = model.assembly_length_mm
        frame = self.toolHolderPart(obj)
        frame.Placement = FreeCAD.Placement(tip + axis * hang, FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), axis))

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
        mount = self.toolHolderPart(obj)
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
        if "Restore" in obj.State:
            return
        if prop == "Step" and getattr(obj, "StepCount", 0):
            try:
                self.pose(obj)
            except Exception as problem:
                FreeCAD.Console.PrintError("kin5axcam: the simulation cannot be posed: %s\n" % problem)
        elif prop == "Machine" and hasattr(obj, "Tool") and not self.pictureBelongsToTheMachine(obj):
            #the old picture hangs from the old machine: down with it, the recompute builds it anew
            self.clearPicture(obj)

    def onDocumentRestored(self, obj):
        self.forget()


class ViewProviderSimulation(object):
    """The tree side of a simulation: its own frames as children, and its picture gone with it."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def claimChildren(self):
        obj = getattr(self, "Object", None)
        if obj is None:
            return []
        return [o for o in (getattr(obj, "ToolFrame", None), getattr(obj, "PartFrame", None))
                if o is not None]

    def onDelete(self, vobj, subelements):
        obj = vobj.Object
        proxy = getattr(obj, "Proxy", None)
        if isinstance(proxy, ObjectSimulation):
            try:
                proxy.clearPicture(obj)
            except Exception as problem:
                FreeCAD.Console.PrintWarning("kin5axcam: the picture of the simulation is left behind: "
                                             "%s\n" % problem)
        return True

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


def Create(name, machine_object, job, document=None):
    """A simulation of the job on the machine, not yet run: recompute it, then step it."""
    if document is None:
        document = FreeCAD.ActiveDocument
    obj = document.addObject("App::FeaturePython", name)
    ObjectSimulation(obj, machine_object, job)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderSimulation(obj.ViewObject)
    return obj
