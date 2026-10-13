# Registers the 3D Surface (5axis) operation with the CAM workbench.
#
# Two things make this file fussier than it looks.
#
# FreeCAD runs a startup file with separate globals and locals, so a class or a def written here
# lands in the locals while a function body looks its names up in the globals: a method of this file
# cannot see anything else in this file, and reaching for it raises NameError. Everything a method
# needs is therefore either reached through cls or imported inside the method, and only the lines at
# the bottom - which are module level, and do see the class - start anything off.
#
# And the timing: while FreeCAD is starting, the CAM workbench cannot be imported yet and the main
# window has no workbenchActivated signal to wait on, because that signal appears only once the Qt
# event loop runs. FreeCAD's own Tux addon polls with a timer until the window reports an event loop
# (Mod/Tux/PersistentToolbarsGui.py); this follows that. A failure is reported once and retried on
# every workbench change, never swallowed.


class Kin5axCam:
    """Puts CAM_Surface5Axis in place as soon as the CAM workbench can be imported."""

    done = False
    complained = False
    timer = None
    window = None

    @classmethod
    def register(cls, *ignored):
        """Imports the command, which registers it. True when it is in place."""
        import FreeCAD

        if cls.done:
            return True
        try:
            from kin5axcam import surface5axis_gui   # noqa: F401 - the import registers the command
            cls.done = True
            FreeCAD.Console.PrintLog("kin5axcam: CAM_Surface5Axis registered\n")
            return True
        except Exception as problem:
            #CAM is not importable this early, which is ordinary; say so once and keep trying
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

    @classmethod
    def start(cls):
        """Starts the timer that waits for the window."""
        import FreeCADGui
        from PySide import QtCore

        cls.window = FreeCADGui.getMainWindow()
        if cls.window is None:
            return
        cls.timer = QtCore.QTimer()
        cls.timer.timeout.connect(cls.whenTheWindowIsReady)
        cls.timer.start(500)


try:
    Kin5axCam.start()
except Exception as problem:                         # a startup file that throws takes startup with it
    try:
        import FreeCAD

        FreeCAD.Console.PrintError("kin5axcam: %s: %s\n" % (type(problem).__name__, problem))
    except Exception:
        pass                                         # not even a console to complain to
