"""Runs the tests of kin5axcam.

    py -3 run_tests.py                                   the geometry, no FreeCAD needed
    "<FreeCAD>/bin/freecadcmd.exe" run_tests.py          those and the ones that need FreeCAD

The tests that need FreeCAD say so and are skipped when it is not there, so both
ways end in a count and neither ends in an import error.

The work is done when this file is read, not under a __name__ == "__main__"
guard: freecadcmd executes a script under a name of its own, and the guard would
leave the whole thing silent.
"""

import os
import sys
import unittest


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    tests = unittest.defaultTestLoader.discover(os.path.join(here, "tests"), top_level_dir=here)
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(tests)
    return 0 if result.wasSuccessful() else 1


failed = main()
if failed:
    #a failure has to reach whoever started this, be it a shell or a build
    sys.exit(failed)
