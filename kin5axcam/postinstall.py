"""Puts the fanuc_tcp_kin5ax postprocessor where FreeCAD looks for postprocessors.

FreeCAD finds a postprocessor by looking for ``*_post.py`` in a few folders of
its own - the macro folder, the CAM default path, and its own scripts folder -
and there is no way for an addon to add a folder to that list. So the file this
addon ships has to be copied into one of them, which is what this does:

    from kin5axcam import postinstall
    postinstall.install()

It prints where it put the file. Restart FreeCAD, or reopen the job, and
*fanuc_tcp_kin5ax* is in the **Post Processor** list of the job.

Copying rather than linking is on purpose: a symbolic link needs a privilege on
Windows that FreeCAD is not usually started with. The other side of that is that
the copy does not follow the addon when the addon is updated, so install() is
worth running again after a pull.
"""

import os
import shutil

#the postprocessor itself, in the addon
POST_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "post", "fanuc_tcp_kin5ax_post.py")


def target_directory():
    """The macro folder of this FreeCAD, which is one of the folders postprocessors are found in."""
    import FreeCAD

    return FreeCAD.getUserMacroDir(True)


def install(directory=None):
    """Copies the postprocessor into that folder, over whatever is there, and says where.

    directory: somewhere else to put it, such as the CAM default path - or, in a
    test, a folder that is thrown away afterwards.
    """
    if not os.path.isfile(POST_FILE):
        raise IOError("the postprocessor is missing from the addon: " + POST_FILE)
    if directory is None:
        directory = target_directory()
    if not os.path.isdir(directory):
        os.makedirs(directory)
    target = os.path.join(directory, os.path.basename(POST_FILE))
    shutil.copyfile(POST_FILE, target)
    _say("kin5axcam: the postprocessor is in %s. Restart FreeCAD and it is in the Post Processor "
         "list of the job as fanuc_tcp_kin5ax.\n" % target)
    return target


def _say(message):
    try:
        import FreeCAD

        FreeCAD.Console.PrintMessage(message)
    except ImportError:
        print(message)
