"""The commands and the player of the machine simulation.

Two commands, registered with FreeCAD when this module is imported:

- **CAM_Kin5axMachine** asks for a chain file of kin5ax and puts the machine in
  the active document, standing at zero.
- **CAM_Kin5axSimulate** takes the job and the machine - the selected ones, or
  the only ones in the document - makes a simulation of the one on the other,
  runs it, and opens the player.

The player is a task panel: a slider over the locations of the trajectory, play
and pause on a timer, a step either way, run to the end, and the report of the
solve. It moves ``Step`` of the simulation and nothing else; the simulation
moves the machine.
"""

import os

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui

from kin5axcam import machine, simulation

translate = FreeCAD.Qt.translate
QT_TRANSLATE_NOOP = QtCore.QT_TRANSLATE_NOOP

ICONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Resources", "icons")


def icon(name):
    """The icon registered under that name, or the file itself, or nothing when there is no file."""
    path = os.path.join(ICONS, name + ".svg")
    if not os.path.isfile(path):
        return ""
    registered = "kin5axcam_" + name
    try:
        FreeCADGui.addIcon(registered, path)
        return registered
    except Exception:
        return path


def jobs_of(document):
    return [o for o in document.Objects if hasattr(o, "Proxy") and o.TypeId == "Path::FeaturePython"
            and o.Proxy.__class__.__name__ == "ObjectJob"]


def machines_of(document):
    return [o for o in document.Objects if isinstance(getattr(o, "Proxy", None), machine.ObjectMachine)]


def simulations_of(document):
    return [o for o in document.Objects
            if isinstance(getattr(o, "Proxy", None), simulation.ObjectSimulation)]


def the_one(candidates, selected, what):
    """The selected one of the candidates, or the only one, or None with a message saying which."""
    chosen = [o for o in selected if o in candidates]
    if len(chosen) == 1:
        return chosen[0]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        FreeCAD.Console.PrintError(translate("Kin5axMachine", "there is no %s in the document\n") % what)
    else:
        FreeCAD.Console.PrintError(translate("Kin5axMachine", "select which %s: there are %d\n")
                                   % (what, len(candidates)))
    return None


class CommandMachine(object):
    """CAM_Kin5axMachine: a machine from a chain file."""

    def GetResources(self):
        return {
            "Pixmap": icon("Kin5axMachine"),
            "MenuText": QT_TRANSLATE_NOOP("CAM_Kin5axMachine", "Machine from kin5ax"),
            "ToolTip": QT_TRANSLATE_NOOP("CAM_Kin5axMachine",
                                         "Put a five-axis machine of kin5ax in the document, from its "
                                         "kinematic chain file (.kc or .kc.json)"),
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        path, _ = QtGui.QFileDialog.getOpenFileName(
            FreeCADGui.getMainWindow(), translate("Kin5axMachine", "The kinematic chain of the machine"),
            "", "kin5ax chain files (*.kc.json *.kc);;All files (*)")
        if not path:
            return
        document = FreeCAD.ActiveDocument
        document.openTransaction("Machine from kin5ax")
        try:
            obj = machine.Create("Machine", path, 1000.0, document)
            document.recompute()
        except Exception as problem:
            document.abortTransaction()
            FreeCAD.Console.PrintError("kin5axcam: the machine cannot be made: %s\n" % problem)
            return
        document.commitTransaction()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        return obj


class CommandSimulate(object):
    """CAM_Kin5axSimulate: the job on the machine, solved and stepped through."""

    def GetResources(self):
        return {
            "Pixmap": icon("Kin5axSimulate"),
            "MenuText": QT_TRANSLATE_NOOP("CAM_Kin5axSimulate", "Simulate on the machine"),
            "ToolTip": QT_TRANSLATE_NOOP("CAM_Kin5axSimulate",
                                         "Cut the stock with the operations of the job, the tool leaning "
                                         "as they say - on the machine of kin5ax in the document when "
                                         "there is one, else on the path as it is"),
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        document = FreeCAD.ActiveDocument
        selected = FreeCADGui.Selection.getSelection()
        existing = [s for s in simulations_of(document) if s in selected]
        if existing:
            sim = existing[0]
        else:
            job = the_one(jobs_of(document), selected, translate("Kin5axMachine", "job"))
            if job is None:
                return
            #a machine when there is one; none, and the path is played as it is, the tool leaning
            machines = machines_of(document)
            machine_object = None
            if machines:
                machine_object = the_one(machines, selected, translate("Kin5axMachine", "machine"))
                if machine_object is None:
                    return
            #one simulation per job: a machine that came later, or went, is a change of the one
            #simulation, not a second one with the old picture left in the view
            reuse = [s for s in simulations_of(document) if s.Job == job]
            sim = reuse[0] if reuse else None
            if sim is None:
                document.openTransaction("Simulation on the machine")
                sim = simulation.Create("Simulation", machine_object, job, document)
                document.commitTransaction()
            elif sim.Machine != machine_object:
                sim.Machine = machine_object
        try:
            document.recompute()
        except Exception as problem:
            FreeCAD.Console.PrintError("kin5axcam: the simulation cannot run: %s\n" % problem)
            return
        if "Invalid" in sim.State:
            FreeCAD.Console.PrintError("kin5axcam: the simulation did not run; see the report view\n")
            return
        Player.show(sim)


class Player(object):
    """The task panel that steps a simulation: slider, play, pause, step, run to the end, report."""

    INTERVAL_MS = 40

    def __init__(self, sim):
        self.simulation = sim
        self.form = QtGui.QWidget()
        self.form.setWindowTitle(translate("Kin5axMachine", "On the machine"))
        layout = QtGui.QVBoxLayout(self.form)

        self.title = QtGui.QLabel(self.form)
        layout.addWidget(self.title)

        self.slider = QtGui.QSlider(QtCore.Qt.Horizontal, self.form)
        self.slider.setRange(0, max(sim.StepCount - 1, 0))
        self.slider.setValue(min(sim.Step, max(sim.StepCount - 1, 0)))
        self.slider.valueChanged.connect(self.slide)
        layout.addWidget(self.slider)

        self.where = QtGui.QLabel(self.form)
        layout.addWidget(self.where)

        buttons = QtGui.QHBoxLayout()
        self.first = QtGui.QPushButton("|<", self.form)
        self.back = QtGui.QPushButton("<", self.form)
        self.play = QtGui.QPushButton(translate("Kin5axMachine", "Play"), self.form)
        self.forward = QtGui.QPushButton(">", self.form)
        self.last = QtGui.QPushButton(">|", self.form)
        for button in (self.first, self.back, self.play, self.forward, self.last):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.first.clicked.connect(lambda: self.goto(0))
        self.back.clicked.connect(lambda: self.goto(self.slider.value() - 1))
        self.forward.clicked.connect(lambda: self.goto(self.slider.value() + 1))
        self.last.clicked.connect(lambda: self.goto(self.slider.maximum()))
        self.play.clicked.connect(self.toggle)

        speed = QtGui.QHBoxLayout()
        speed.addWidget(QtGui.QLabel(translate("Kin5axMachine", "Locations per second"), self.form))
        self.rate = QtGui.QSpinBox(self.form)
        self.rate.setRange(1, 500)
        self.rate.setValue(25)
        speed.addWidget(self.rate)
        layout.addLayout(speed)

        #the joint markers of the machine: shown or not, larger or smaller
        if sim.Machine is not None:
            joints = QtGui.QHBoxLayout()
            self.showJoints = QtGui.QCheckBox(translate("Kin5axMachine", "Joints"), self.form)
            self.showJoints.setChecked(bool(sim.Machine.ShowJoints))
            self.showJoints.setToolTip(translate(
                "Kin5axMachine", "Every joint as a disc sector or a box the size of its value: "
                "magenta positive, cyan negative"))
            self.showJoints.stateChanged.connect(self.toggleJoints)
            joints.addWidget(self.showJoints)
            self.shrink = QtGui.QPushButton(translate("Kin5axMachine", "Smaller"), self.form)
            self.expand = QtGui.QPushButton(translate("Kin5axMachine", "Larger"), self.form)
            self.shrink.clicked.connect(lambda: self.resizeJoints(0.8))
            self.expand.clicked.connect(lambda: self.resizeJoints(1.25))
            joints.addWidget(self.shrink)
            joints.addWidget(self.expand)
            layout.addLayout(joints)

        self.report = QtGui.QPlainTextEdit(self.form)
        self.report.setReadOnly(True)
        self.report.setPlainText(sim.Report)
        self.report.setMaximumHeight(120)
        layout.addWidget(self.report)

        self.timer = QtCore.QTimer(self.form)
        self.timer.timeout.connect(self.tick)
        #a step in progress: a tick that arrives while one is being drawn is dropped, never nested
        self._busy = False
        self.describe()

    @classmethod
    def show(cls, sim):
        FreeCADGui.Control.closeDialog()
        panel = cls(sim)
        FreeCADGui.Control.showDialog(panel)
        return panel

    def describe(self):
        sim = self.simulation
        count = sim.StepCount
        step = self.slider.value()
        machine_name = sim.Machine.Label if sim.Machine is not None else translate(
            "Kin5axMachine", "the path as it is")
        self.title.setText(translate("Kin5axMachine", "%s on %s: %d locations")
                           % (sim.Job.Label if sim.Job is not None else "?", machine_name, count))
        if count == 0:
            self.where.setText(translate("Kin5axMachine", "nothing to show"))
            return
        solved = sim.Solved[step] if step < len(sim.Solved) else 0
        if solved and sim.Machine is None:
            tip = sim.Tips[3 * step:3 * step + 3]
            axis = sim.Axes[3 * step:3 * step + 3]
            text = translate("Kin5axMachine", "location %d of %d: tip %s, axis %s") % (
                step + 1, count, " ".join("%.3f" % v for v in tip), " ".join("%.3f" % v for v in axis))
        elif solved:
            q = sim.Joints[5 * step:5 * step + 5]
            text = translate("Kin5axMachine", "location %d of %d: %s") % (
                step + 1, count, "  ".join("%.3f" % v for v in q))
        else:
            from kin5axcam import kin5ax
            status = sim.Statuses[step] if step < len(sim.Statuses) else -1
            text = translate("Kin5axMachine", "location %d of %d: unreachable - %s") % (
                step + 1, count, kin5ax.SOLVE_STATUS_NAMES.get(status, "?"))
        if getattr(sim, "Cut", False) and sim.Surface is not None:
            text += "\n" + translate("Kin5axMachine", "cut: %.0f mm3 removed, %d gouges") % (
                sim.RemovedVolume, sim.Gouges)
        self.where.setText(text)

    def slide(self, value):
        """One step: the simulation poses the machine and cuts, the view repaints when this returns.

        Nothing here processes events. A call to updateGui() from inside this
        slot let the next tick of the timer in while the shapes and the mesh of
        the step were still being handed to the view, and FreeCAD went down in
        Qt with an access violation on the second operation of a job.
        """
        if self._busy:
            return
        self._busy = True
        try:
            sim = self.simulation
            if sim.Step != value:
                sim.Step = value
            self.describe()
        finally:
            self._busy = False

    def goto(self, value):
        self.slider.setValue(max(0, min(value, self.slider.maximum())))

    def toggleJoints(self, state):
        machine_object = self.simulation.Machine
        if machine_object is not None:
            machine_object.ShowJoints = bool(state)

    def resizeJoints(self, factor):
        machine_object = self.simulation.Machine
        if machine_object is not None:
            machine_object.JointSize = max(1.0, machine_object.JointSize * factor)

    def toggle(self):
        if self.timer.isActive():
            self.pause()
        else:
            if self.slider.value() >= self.slider.maximum():
                self.slider.setValue(0)
            self.timer.start(max(1, int(1000.0 / self.rate.value())))
            self.play.setText(translate("Kin5axMachine", "Pause"))

    def pause(self):
        self.timer.stop()
        self.play.setText(translate("Kin5axMachine", "Play"))

    def tick(self):
        self.timer.setInterval(max(1, int(1000.0 / self.rate.value())))
        if self._busy:
            return                              #the step before is still being drawn
        if self.slider.value() >= self.slider.maximum():
            self.pause()
            return
        self.slider.setValue(self.slider.value() + 1)

    def getStandardButtons(self):
        return QtGui.QDialogButtonBox.Close

    def reject(self):
        self.pause()
        FreeCADGui.Control.closeDialog()

    def accept(self):
        self.reject()


FreeCADGui.addCommand("CAM_Kin5axMachine", CommandMachine())
FreeCADGui.addCommand("CAM_Kin5axSimulate", CommandSimulate())
FreeCAD.Console.PrintLog("Loading kin5axcam machine commands... done\n")
