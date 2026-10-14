"""The console side of the addon: the modules a saved document may need, imported before any restore.

A document with an operation, a machine or a simulation of this addon in it
carries their proxies as pickled Python objects, and FreeCAD refuses to import a
module during a restore unless it is already there - so a document opened from
a script, or on a machine with no interface, lost its objects. Importing the
three here, where FreeCAD runs this file at start-up with or without an
interface, puts them in place. The commands and the panels are InitGui.py's.
"""

try:
    from kin5axcam import surface5axis, machine, simulation     # noqa: F401 - imported to be there
except Exception as problem:                                      # pragma: no cover - a FreeCAD too old
    import FreeCAD

    FreeCAD.Console.PrintLog("kin5axcam: the modules could not be imported at start-up: %s\n" % problem)
