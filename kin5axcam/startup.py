"""Puts CAM_Surface5Axis in place once the CAM workbench has been loaded.

This is a module rather than code in InitGui.py for two reasons, both learnt the hard way.

FreeCAD runs a startup file with separate globals and locals, so a class or a def written in one
cannot be seen from inside any function of the same file. A module has one namespace and no such
trap.

And whatever a startup file leaves behind is dropped the moment it finishes. A timer kept only there
has nothing holding it, forms an unreachable cycle with whatever it calls, and is collected before
it ever fires - which is exactly what happened: the command never appeared, while importing it by
hand in the console worked at once. A module stays in sys.modules for the life of the session, so
what it holds stays alive.

The CAM workbench cannot be imported while FreeCAD is starting, so registration waits. It does not
wait on the workbenchActivated signal of the main window: that signal only appears once the Qt event
loop runs, and FreeCAD's own Tux addon has to poll for it anyway. Polling for the one thing that
actually matters - the CAM workbench being loaded - is shorter and has fewer ways to go wrong.
"""

import sys

#how often to look, in milliseconds. Each look is a dictionary lookup until CAM is loaded.
INTERVAL = 2000

_timer = None
_done = False
_complained = False


def is_registered():
    """Has the command been put in place?"""
    return _done


def register(*ignored):
    """Registers the command when CAM is there to register it with. True when it is in place."""
    global _done, _complained
    if _done:
        return True
    if "Path" not in sys.modules:
        return False                        # the CAM workbench has not been loaded yet
    try:
        from kin5axcam import surface5axis_gui   # noqa: F401 - the import registers the command
    except Exception as problem:
        if not _complained:
            _complained = True
            _say_error("kin5axcam: the 3D Surface (5axis) operation could not be registered: "
                       "%s: %s" % (type(problem).__name__, problem))
        return False
    try:
        from kin5axcam import machine_gui        # noqa: F401 - the machine and the simulation
    except Exception as problem:
        #the operation is in place either way; the machine needs the shared library at run time,
        #not at registration, so a failure here is a bug and is said so
        _say_error("kin5axcam: the machine commands could not be registered: %s: %s"
                   % (type(problem).__name__, problem))
    _done = True
    stop()
    _say_log("kin5axcam: CAM_Surface5Axis, CAM_Kin5axMachine and CAM_Kin5axSimulate registered")
    return True


def start(interval=INTERVAL):
    """Starts looking. Does nothing twice, and nothing at all without a user interface."""
    global _timer
    if _done or _timer is not None:
        return False
    try:
        import FreeCADGui
        from PySide import QtCore
    except ImportError:
        return False                        # no interface: there is nothing to register with
    if register():
        return True                         # CAM was loaded already
    window = getattr(FreeCADGui, "getMainWindow", lambda: None)()
    #the window as parent keeps the timer alive on the C++ side as well as in this module
    _timer = QtCore.QTimer(window) if window is not None else QtCore.QTimer()
    _timer.timeout.connect(register)
    _timer.start(interval)
    return True


def stop():
    """Stops looking."""
    global _timer
    if _timer is not None:
        _timer.stop()
        _timer = None


def _say_log(message):
    try:
        import FreeCAD

        FreeCAD.Console.PrintLog(message + "\n")
    except Exception:
        pass


def _say_error(message):
    try:
        import FreeCAD

        FreeCAD.Console.PrintError(message + "\n")
    except Exception:
        pass
