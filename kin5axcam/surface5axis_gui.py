"""The task panel page of the 3D Surface (5axis) operation, and the command that creates one.

The form is built in code rather than loaded from a .ui file: there are five
fields, and a file of Qt XML to keep in step with them would be the larger half
of this module.

The page carries the tool controller and the coolant, as every operation's page does. The rest of
the task dialog - the base geometry page that picks the face, the depths, the heights - is put there
by the task panel itself, from the features the operation declares in opFeatures.

Importing this module registers the command CAM_Surface5Axis with FreeCAD. It does not put it on a
toolbar: the toolbars of a workbench belong to that workbench and no command can be added to them
from outside, so the way to have a button is Tools, Customize, Toolbars, and a toolbar of your own
in the CAM workbench. Or run it from the Python console:

    FreeCADGui.runCommand("CAM_Surface5Axis")
"""

import os

import FreeCAD
import FreeCADGui
import Path.Op.Gui.Base as PathOpGui
from PySide import QtCore, QtGui

import Path.Base.SetupSheet as PathSetupSheet
import Path.Op.Gui.Selection as PathSelection

from kin5axcam import surface5axis

translate = FreeCAD.Qt.translate
QT_TRANSLATE_NOOP = QtCore.QT_TRANSLATE_NOOP

#the icon of the command: a toolpath on the aerofoil of a turbine blade, drawn in the colours the
#operations of the CAM workbench use
ICON_NAME = "kin5axcam_Surface5Axis"
ICON_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "Resources", "icons", "Surface5Axis.svg")


def icon():
    """The name the icon is registered under, or the file itself when it cannot be registered.

    FreeCAD keeps icons in a registry a command looks its picture up in, and an addon puts its own
    there with addIcon. A FreeCAD without that call, or a name already taken, leaves the file path,
    which the command resources also accept.
    """
    if not os.path.isfile(ICON_FILE):
        FreeCAD.Console.PrintWarning("kin5axcam: the icon is missing from %s\n" % ICON_FILE)
        return "CAM_3DSurface"                   #the icon of the three-axis surface operation
    try:
        FreeCADGui.addIcon(ICON_NAME, ICON_FILE)
        return ICON_NAME
    except Exception:
        return ICON_FILE


class TaskPanelOpPage(PathOpGui.TaskPanelPage):
    """The page of the operation: how dense the zigzag is, which way it runs, which side of the face."""

    def getForm(self):
        form = QtGui.QWidget()
        layout = QtGui.QFormLayout(form)

        #The tool and the coolant belong to the page of the operation, as they do in every other one.
        #The combo box has to be called toolController: the base class looks for that name to wire
        #the tool up and to keep it in step when the job's tools change.
        form.toolController = QtGui.QComboBox(form)
        form.toolController.setToolTip(translate(
            "Surface5Axis", "The tool this operation cuts with. Any shape of tool will do; a "
            "ball nose one follows a curved surface the closest."))
        layout.addRow(translate("Surface5Axis", "Tool controller"), form.toolController)

        form.coolantController = QtGui.QComboBox(form)
        form.coolantController.setToolTip(translate(
            "Surface5Axis", "The coolant mode the job offers"))
        layout.addRow(translate("Surface5Axis", "Coolant"), form.coolantController)

        self.rows = QtGui.QSpinBox(form)
        self.rows.setRange(1, 100000)
        self.rows.setToolTip(translate(
            "Surface5Axis", "How many passes are laid across the face, counted in the parameter "
            "space of the surface"))
        layout.addRow(translate("Surface5Axis", "Passes"), self.rows)

        self.pointsPerRow = QtGui.QSpinBox(form)
        self.pointsPerRow.setRange(2, 1000000)
        self.pointsPerRow.setToolTip(translate(
            "Surface5Axis", "How many points are put along each pass"))
        layout.addRow(translate("Surface5Axis", "Points per pass"), self.pointsPerRow)

        self.pathDirection = QtGui.QComboBox(form)
        self.pathDirection.addItems(["U", "V"])
        self.pathDirection.setToolTip(translate(
            "Surface5Axis", "Which parameter of the surface a pass sweeps"))
        layout.addRow(translate("Surface5Axis", "Passes sweep"), self.pathDirection)

        self.zigZag = QtGui.QCheckBox(translate("Surface5Axis", "There and back"), form)
        self.zigZag.setToolTip(translate(
            "Surface5Axis", "Each pass runs against the one before it, so the tool cuts in both "
            "directions instead of returning through the air"))
        layout.addRow("", self.zigZag)

        self.invertNormal = QtGui.QCheckBox(translate("Surface5Axis", "Other side of the face"), form)
        self.invertNormal.setToolTip(translate(
            "Surface5Axis", "The tool goes to the side the normal of the face points at; tick this "
            "when that is the wrong side"))
        layout.addRow("", self.invertNormal)

        return form

    def getTitle(self, obj):
        return translate("Surface5Axis", "3D Surface (5axis)")

    def getFields(self, obj):
        """The form into the operation."""
        self.updateToolController(obj, self.form.toolController)
        self.updateCoolant(obj, self.form.coolantController)
        if obj.Rows != self.rows.value():
            obj.Rows = self.rows.value()
        if obj.PointsPerRow != self.pointsPerRow.value():
            obj.PointsPerRow = self.pointsPerRow.value()
        direction = str(self.pathDirection.currentText())
        if obj.PathDirection != direction:
            obj.PathDirection = direction
        if obj.ZigZag != self.zigZag.isChecked():
            obj.ZigZag = self.zigZag.isChecked()
        if obj.InvertNormal != self.invertNormal.isChecked():
            obj.InvertNormal = self.invertNormal.isChecked()

    def setFields(self, obj):
        """The operation into the form."""
        self.setupToolController(obj, self.form.toolController)
        self.setupCoolant(obj, self.form.coolantController)
        self.rows.setValue(obj.Rows)
        self.pointsPerRow.setValue(obj.PointsPerRow)
        index = self.pathDirection.findText(obj.PathDirection, QtCore.Qt.MatchFixedString)
        if index >= 0:
            self.pathDirection.setCurrentIndex(index)
        self.zigZag.setChecked(obj.ZigZag)
        self.invertNormal.setChecked(obj.InvertNormal)

    def getSignalsForUpdate(self, obj):
        #not the tool controller: the base class connects that one itself, by the name of the widget
        return [
            self.form.coolantController.currentIndexChanged,
            self.rows.valueChanged,
            self.pointsPerRow.valueChanged,
            self.pathDirection.currentIndexChanged,
            self.zigZag.stateChanged,
            self.invertNormal.stateChanged,
        ]


class ViewProvider(PathOpGui.ViewProvider):
    """The generic view provider of an operation, with the two things it cannot know settled here.

    **The selection gate.** Before showing the task dialog, setEdit asks the view provider which
    gate the operation wants - what the user may click on while the dialog is open - and the generic
    answer looks the operation's name up in a table written into Path/Op/Gui/Selection.py. That
    table has no room for an operation from outside and the lookup has no default, so the name of
    this one raised KeyError inside setEdit, one line before the dialog would have been shown: no
    page, no OK, no Cancel, and no message, because setEdit is called from C++ which swallows it.
    (Still so on the main branch of FreeCAD, looked at on 2026-10-13.) Answering the question here
    means the table is never consulted. The answer is the gate the Face operation uses, which lets a
    face be picked, and a face is what this operation works on.

    **The icon.** The generic view provider builds ":/icons/<name>.svg" out of the name the command
    was registered with and asks for that, which resolves for a picture compiled into FreeCAD and
    for nothing an addon can offer - so the operation had no icon in the tree. The file itself goes
    in instead, which the tree and the task page both take.
    """

    def __init__(self, vobj, resources):
        super(ViewProvider, self).__init__(vobj, resources)
        if os.path.isfile(ICON_FILE):
            self.OpIcon = ICON_FILE

    def getSelectionFactory(self):
        """The gate of the Face operation, rather than a lookup this operation cannot be in."""
        return PathSelection.pocketselect


class Command(PathOpGui.CommandPathOp):
    """What the button does: FreeCAD's own, with the view provider above put in place of the generic one.

    Everything that matters about creating an operation - the transaction, choosing the job when
    there is more than one, what to do when there is no tool controller - belongs to FreeCAD and is
    left to it. The only thing changed is which class is used for the view provider, and only for
    the length of this call, because the name of that class is how PathOpGui.Create reaches it and
    there is no argument for it.
    """

    def Activated(self):
        generic = PathOpGui.ViewProvider
        PathOpGui.ViewProvider = ViewProvider
        try:
            return PathOpGui.CommandPathOp.Activated(self)
        finally:
            PathOpGui.ViewProvider = generic


Resources = PathOpGui.CommandResources(
    "Surface5Axis",
    surface5axis.Create,
    TaskPanelOpPage,
    icon(),
    QT_TRANSLATE_NOOP("CAM_Surface5Axis", "3D Surface (5axis)"),
    None,
    QT_TRANSLATE_NOOP("CAM_Surface5Axis",
                      "Zigzag over the U,V space of a single face"),
)

#what PathOpGui.SetupOperation would do, done here because the command is this one and not the generic
Command = Command(Resources)
FreeCADGui.addCommand("CAM_Surface5Axis", Command)
PathSetupSheet.RegisterOperation("Surface5Axis", surface5axis.Create, surface5axis.SetupProperties)

FreeCAD.Console.PrintLog("Loading kin5axcam 3D Surface (5axis)... done\n")
