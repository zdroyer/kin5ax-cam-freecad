"""kin5axcam.startup: the waiting that puts the command in place, without a user interface in sight.

The command went missing twice, and neither time did it need FreeCAD to find out
why: once because a startup file cannot see its own names from inside a
function, once because a timer kept only in a startup file is collected before
it fires. Both are checked here, where there is nothing to wait for.
"""

import os
import sys
import unittest

from kin5axcam import startup


class BeforeTheWorkbenchIsThere(unittest.TestCase):
    """Nothing may happen, loudly or otherwise, until the CAM workbench is loaded."""

    def setUp(self):
        self.had_path = "Path" in sys.modules
        startup._done = False
        startup._complained = False

    def tearDown(self):
        startup.stop()
        startup._done = False
        startup._complained = False

    def test_registering_without_cam_is_a_no_and_not_a_throw(self):
        if self.had_path:
            self.skipTest("the CAM workbench is loaded in this session, so there is nothing to wait for")
        self.assertFalse(startup.register())
        self.assertFalse(startup.is_registered())

    def test_it_can_be_asked_twice(self):
        if self.had_path:
            self.skipTest("the CAM workbench is loaded in this session")
        self.assertFalse(startup.register())
        self.assertFalse(startup.register())

    def test_starting_without_an_interface_does_nothing_and_says_so(self):
        try:
            import FreeCADGui                       # noqa: F401
        except ImportError:
            self.assertFalse(startup.start(), "without an interface there is nothing to start")
            return
        self.skipTest("this FreeCAD has an interface module, so starting is not a no-op")

    def test_stopping_what_was_never_started_is_allowed(self):
        startup.stop()
        startup.stop()


class TheStartupFile(unittest.TestCase):
    """InitGui.py: FreeCAD runs it with separate globals and locals, and drops what it leaves."""

    def setUp(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "InitGui.py"), encoding="utf-8") as f:
            self.source = f.read()
        self.code = compile(self.source, "InitGui.py", "exec")

    def tearDown(self):
        startup.stop()

    def test_it_defines_nothing_of_its_own(self):
        """A def or a class here could not see the rest of the file, and would be dropped with it.

        Looking for the word in the text would find it in this very explanation, so the question is
        put to the compiler: a def or a class compiles to a code object among the constants.
        """
        import types

        defined = [c.co_name for c in self.code.co_consts if isinstance(c, types.CodeType)]
        self.assertEqual([], defined,
                         "InitGui.py defines %s; whatever they are, they belong in the module, "
                         "where they have a namespace and a life beyond this file" % defined)

    def test_it_hands_the_work_to_the_module(self):
        self.assertIn("from kin5axcam import startup", self.source)

    def test_it_survives_separate_globals_and_locals(self):
        """How FreeCAD runs it. A name of its own reached from a function would raise NameError."""
        try:
            exec(self.code, {}, {})
        except Exception as problem:
            self.fail("InitGui.py let %s out: %s" % (type(problem).__name__, problem))

    def test_it_survives_one_namespace_too(self):
        try:
            exec(self.code, {})
        except Exception as problem:
            self.fail("InitGui.py let %s out: %s" % (type(problem).__name__, problem))


if __name__ == "__main__":
    unittest.main()
