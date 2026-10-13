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

from kin5axcam import selectionmode, surface5axis

#Before the task dialog of an operation is shown, FreeCAD asks its selection table which gate this
#operation works with, and that table has no room for one from outside: the lookup raises KeyError
#inside ViewProvider.setEdit, before the dialog, so nothing appears at all. This puts this operation
#in reach of the answer. See kin5axcam/selectionmode.py.
selectionmode.install()

translate = FreeCAD.Qt.translate
QT_TRANSLATE_NOOP = QtCore.QT_TRANSLATE_NOOP

#the icon of the command: a toolpath on the aerofoil of a turbine blade, drawn in the colours the
#operations of the CAM workbench use
ICON_NAME = "kin5axcam_Surface5Axis"
#What Path.Op.Gui.Base.ViewProvider makes of that name when it wants the icon of the operation in
#the tree: it builds ":/icons/<name>.svg" and asks for that, so that name is registered as well.
TREE_ICON_NAME = ":/icons/%s.svg" % ICON_NAME
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
        #Twice, under two names, because two different things ask for this picture: the command asks
        #for the plain name, and the view provider of an operation asks for the resource path it
        #builds out of that name. Both are registered, and both find the same file.
        FreeCADGui.addIcon(ICON_NAME, ICON_FILE)
        FreeCADGui.addIcon(TREE_ICON_NAME, ICON_FILE)
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
            "Surface5Axis", "The tool this operation cuts with. It has to be a ball nose one."))
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


Command = PathOpGui.SetupOperation(
    "Surface5Axis",
    surface5axis.Create,
    TaskPanelOpPage,
    icon(),
    QT_TRANSLATE_NOOP("CAM_Surface5Axis", "3D Surface (5axis)"),
    QT_TRANSLATE_NOOP("CAM_Surface5Axis",
                      "Zigzag over the U,V space of a single face, cut with a ball nose tool"),
    surface5axis.SetupProperties,
)

FreeCAD.Console.PrintLog("Loading kin5axcam 3D Surface (5axis)... done\n")
