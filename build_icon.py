"""Used by build.bat: cut the programs' icon (Caren's face) from your own 2005 game files, found
the way the launcher finds them, into build\\icon_caren.ico, and print its path. Prints nothing
when the 2005 folder isn't found; the programs then get Windows' default icon."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import launcher  # noqa: E402
import side_art  # noqa: E402

fan = launcher.load_settings().get("fan") or launcher.find_fan() or ""
path = side_art.icon_file(fan, os.path.join(HERE, "build", "icon_caren.ico")) if fan else None
print(path or "")
