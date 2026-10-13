"""selectionmode: the wrapper that stops FreeCAD's hard-coded table from killing the task dialog.

FreeCAD looks an operation's selection gate up in a table written into
Path/Op/Gui/Selection.py and ends with ``return opsel[op]`` - no default. The
lookup happens inside ViewProvider.setEdit before the dialog is shown, so an
operation from outside raises KeyError there and the dialog never appears at
all: no page, no OK, no Cancel, no message.

FreeCAD is not needed to check the wrapper: a stand-in module with the same two
functions says everything.
"""

import types
import unittest

from kin5axcam import selectionmode


def a_selection_module():
    """A stand-in for Path.Op.Gui.Selection: a module with plain functions, as the real one is.

    A module and not an object with methods, because a bound method is made afresh on every
    attribute access and would compare unequal to itself, which says nothing about the wrapper.
    """
    module = types.ModuleType("Selection")

    def pocketselect():
        return "a face may be picked"

    def surfaceselect():
        return "a mesh or a face may be picked"

    known = {"MillFace": pocketselect, "Surface": surfaceselect}

    def select(name):
        return known[name]                      # exactly as FreeCAD does it: no default

    module.pocketselect = pocketselect
    module.surfaceselect = surfaceselect
    module.select = select
    return module


class TheWrapper(unittest.TestCase):

    def setUp(self):
        self.module = a_selection_module()
        self.original = self.module.select

    def test_without_it_an_operation_of_our_own_is_a_keyerror(self):
        with self.assertRaises(KeyError):
            self.module.select("Surface5Axis")

    def test_with_it_our_operation_gets_the_gate_of_the_face_operation(self):
        self.assertTrue(selectionmode.install(self.module))
        self.assertIs(self.module.pocketselect, self.module.select("Surface5Axis"))

    def test_everything_freecad_knows_is_still_answered_by_freecad(self):
        selectionmode.install(self.module)
        self.assertIs(self.module.pocketselect, self.module.select("MillFace"))
        self.assertIs(self.module.surfaceselect, self.module.select("Surface"))

    def test_somebody_elses_missing_operation_is_still_a_keyerror(self):
        selectionmode.install(self.module)
        with self.assertRaises(KeyError):
            self.module.select("SomeOtherAddonsOperation")

    def test_installing_twice_changes_nothing(self):
        self.assertTrue(selectionmode.install(self.module))
        wrapped = self.module.select
        self.assertFalse(selectionmode.install(self.module), "the second time has nothing to do")
        self.assertIs(wrapped, self.module.select)

    def test_it_can_be_taken_off_again(self):
        selectionmode.install(self.module)
        self.assertTrue(selectionmode.uninstall(self.module))
        self.assertIs(self.original, self.module.select)
        self.assertFalse(selectionmode.uninstall(self.module), "nothing left to take off")

    def test_a_module_without_what_it_needs_is_left_alone(self):
        empty = types.ModuleType("Empty")
        self.assertFalse(selectionmode.install(empty))
        self.assertFalse(hasattr(empty, "select"))

        #a module with a select but without the gate we would point at: nothing is touched
        no_gate = types.ModuleType("NoGate")
        no_gate.select = lambda name: None
        before = no_gate.select
        self.assertFalse(selectionmode.install(no_gate))
        self.assertIs(before, no_gate.select)


if __name__ == "__main__":
    unittest.main()
