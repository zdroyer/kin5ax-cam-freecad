# The 3D Surface (5axis) operation is a part of the CAM workbench, not a workbench of its own, so
# this file waits until CAM is activated the first time and registers the command then. Importing
# the CAM Gui at startup would pull the whole workbench in before anybody asked for it, and a
# startup file that throws takes FreeCAD's startup with it - hence the try.

import FreeCAD


class Kin5axCam:
    """Registers CAM_Surface5Axis the first time the CAM workbench is activated."""

    registered = False

    @classmethod
    def register(cls, workbench_name=None):
        if cls.registered:
            return
        if workbench_name is not None and "CAM" not in str(workbench_name):
            return
        try:
            from kin5axcam import surface5axis_gui       # noqa: F401 - the import registers it
            cls.registered = True
            FreeCAD.Console.PrintLog("kin5axcam: CAM_Surface5Axis registered\n")
        except Exception as problem:
            FreeCAD.Console.PrintError(
                "kin5axcam: the 3D Surface (5axis) operation could not be registered: %s\n" % problem)
            cls.registered = True                        # once is enough; do not nag on every switch


def _connect():
    import FreeCADGui

    window = FreeCADGui.getMainWindow()
    if window is None:
        return False
    signal = getattr(window, "workbenchActivated", None)
    if signal is None:
        return False
    signal.connect(Kin5axCam.register)
    return True


try:
    if not _connect():
        #no main window, or a FreeCAD without that signal: register straight away
        Kin5axCam.register()
except Exception as problem:                             # pragma: no cover - startup must survive
    FreeCAD.Console.PrintError("kin5axcam: %s\n" % problem)
