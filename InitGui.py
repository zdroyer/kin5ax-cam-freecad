# Hands the work to kin5axcam.startup and gets out of the way.
#
# Nothing of substance belongs in this file. FreeCAD runs a startup file with separate globals and
# locals, so a class or a def written here cannot be seen from inside any function written here; and
# whatever this file leaves behind is dropped as soon as it finishes, so a timer kept here is
# collected before it ever fires. Both of those cost an evening. A module in the package has one
# namespace and lives in sys.modules for the session, so that is where the work is.

try:
    from kin5axcam import startup

    startup.start()
except Exception as problem:                 # a startup file that throws takes startup with it
    try:
        import FreeCAD

        FreeCAD.Console.PrintError(
            "kin5axcam: %s: %s\n" % (type(problem).__name__, problem))
    except Exception:
        pass                                 # not even a console to complain to
