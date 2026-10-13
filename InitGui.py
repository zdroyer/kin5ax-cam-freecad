# Registers the 3D Surface (5axis) operation with the CAM workbench.
#
# The timing is the whole difficulty here. This file is read while FreeCAD is still starting, and at
# that moment two things are not ready: the CAM workbench cannot be imported, and the main window has
# no workbenchActivated signal to wait on - that signal appears only once the Qt event loop runs.
# FreeCAD's own Tux addon works around the second by polling with a timer until the window reports an
# event loop (Mod/Tux/PersistentToolbarsGui.py), which is the pattern followed here.
#
# So: poll until the signal exists, then try to register on every workbench activation until it
# works. A failure is reported once and retried, never swallowed into "registered" - which is the
# mistake the first version of this file made, leaving the command missing and nothing saying why.

import FreeCAD

try:
    import FreeCADGui
    from PySide import QtCore
except ImportError:                                  # no user interface: nothing to register with
    FreeCADGui = None


class Kin5axCam:
    """Puts CAM_Surface5Axis in place as soon as the CAM workbench can be imported."""

    done = False
    complained = False
    timer = None
    window = None

    @classmethod
    def register(cls, *ignored):
        """Imports the command, which registers it. True when it is in place."""
        if cls.done:
            return True
        try:
            from kin5axcam import surface5axis_gui   # noqa: F401 - the import registers the command
            cls.done = True
            FreeCAD.Console.PrintLog("kin5axcam: CAM_Surface5Axis registered\n")
            return True
        except Exception as problem:
            #CAM is not importable yet, which is ordinary this early; say so once and keep trying
            if not cls.complained:
                cls.complained = True
                FreeCAD.Console.PrintLog(
                    "kin5axcam: not registered yet (%s: %s); waiting for the CAM workbench\n"
                    % (type(problem).__name__, problem))
            return False

    @classmethod
    def whenTheWindowIsReady(cls):
        """Called by the timer until the main window has the signal to hang the retry on."""
        if cls.done:
            cls.timer.stop()
            return
        try:
            if not cls.window.property("eventLoop"):
                return
            cls.window.workbenchActivated            # raises until the signal exists
        except Exception:
            return
        cls.timer.stop()
        cls.window.workbenchActivated.connect(cls.register)
        cls.register()                               # in case CAM is the workbench already up


def start():
    if FreeCADGui is None:
        return
    Kin5axCam.window = FreeCADGui.getMainWindow()
    if Kin5axCam.window is None:
        return
    Kin5axCam.timer = QtCore.QTimer()
    Kin5axCam.timer.timeout.connect(Kin5axCam.whenTheWindowIsReady)
    Kin5axCam.timer.start(500)


try:
    start()
except Exception as problem:                         # a startup file that throws takes startup with it
    FreeCAD.Console.PrintError("kin5axcam: %s: %s\n" % (type(problem).__name__, problem))
