"""InitGui.py, run the way FreeCAD runs it.

FreeCAD executes a startup file with separate globals and locals. A class or a
def written at the top of such a file lands in the locals, while a function body
looks its names up in the globals - so a method of that file cannot see anything
else in that file, and reaching for one raises NameError at startup, where the
only sign of it is a notification nobody reads.

That is what happened, so this is the test that would have caught it. It needs
no FreeCAD: the point is the namespaces, not the interface.
"""

import os
import unittest


def initgui_source():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "InitGui.py"), encoding="utf-8") as f:
        return f.read()


class TheStartupFile(unittest.TestCase):

    def test_it_survives_separate_globals_and_locals(self):
        """Nothing in InitGui.py may reach for a name of its own from inside a function."""
        code = compile(initgui_source(), "InitGui.py", "exec")
        try:
            exec(code, {}, {})                      # how FreeCAD runs it
        except NameError as problem:
            self.fail("InitGui.py reaches for one of its own names from inside a function, which "
                      "FreeCAD's namespaces do not allow: %s" % problem)
        except Exception:
            pass        # without a user interface it cannot get far, and it says so for itself

    def test_it_survives_one_namespace_too(self):
        """And the ordinary way, in case a FreeCAD runs it like a module."""
        code = compile(initgui_source(), "InitGui.py", "exec")
        namespace = {}
        try:
            exec(code, namespace)
        except NameError as problem:
            self.fail("InitGui.py raised NameError even with one namespace: %s" % problem)
        except Exception:
            pass
        self.assertIn("Kin5axCam", namespace, "the class the command hangs on is defined")

    def test_nothing_escapes_it(self):
        """A startup file that throws takes the start of FreeCAD with it, so nothing may escape."""
        code = compile(initgui_source(), "InitGui.py", "exec")
        for namespaces in (({}, {}), ({},)):
            try:
                exec(code, *namespaces)
            except Exception as problem:
                self.fail("InitGui.py let %s out: %s" % (type(problem).__name__, problem))


if __name__ == "__main__":
    unittest.main()
