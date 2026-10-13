"""Teaches FreeCAD which selection mode this operation wants.

Before the CAM workbench opens the task dialog of an operation it asks
``Path.Op.Gui.Selection.select(name)`` for the selection gate that operation
works with - the thing that decides what the user may click on while the dialog
is open. That function ends in::

    return opsel[op]

a plain lookup in a table written into the file, with no default and no way for
an operation from outside to put itself in it. An addon's operation is therefore
a KeyError, and the KeyError is raised inside ``ViewProvider.setEdit`` *before*
the dialog is shown - so there is no dialog at all, no buttons, and nothing said
about why. That is the whole of the bug this module exists for.

So the function is wrapped: anything FreeCAD knows is answered by FreeCAD, and
only the name of this operation is caught and answered with the gate the Face
operation uses, which is the one that lets a face be picked. Upstream the fix is
one character - ``opsel.get(op, ...)`` - and if a later FreeCAD makes it, this
wrapper quietly stops being needed, because it only ever handles the name it
knows and re-raises everything else.
"""

#the name the operation is registered under, which is the key FreeCAD looks up
OPERATION_NAME = "Surface5Axis"

#the gate of the Face operation: a face may be picked, which is what this operation works on
GATE = "pocketselect"


def install(module=None, operation_name=OPERATION_NAME, gate=GATE):
    """Wraps the select function of the given module - FreeCAD's own by default.

    Returns True when the wrapper is in place, False when there was nothing to
    wrap or it was wrapped already. Wrapping twice does nothing: the wrapper
    carries a mark and is recognised by it.
    """
    if module is None:
        import Path.Op.Gui.Selection as module             # noqa: N813 - FreeCAD's module

    original = getattr(module, "select", None)
    if original is None:
        return False
    if getattr(original, "kin5axcam_wrapped", False):
        return False
    gate_function = getattr(module, gate, None)
    if gate_function is None:
        return False

    def select(name):
        try:
            return original(name)
        except KeyError:
            if name == operation_name:
                return gate_function
            raise                                           # somebody else's problem, not ours

    select.kin5axcam_wrapped = True
    select.kin5axcam_original = original
    module.select = select
    return True


def uninstall(module=None):
    """Puts back whatever was there before. For the tests, and for tidiness."""
    if module is None:
        import Path.Op.Gui.Selection as module

    current = getattr(module, "select", None)
    original = getattr(current, "kin5axcam_original", None)
    if original is None:
        return False
    module.select = original
    return True
