"""Fate/hollow ataraxia REMASTERED - cut content restoration (command line).

    python fha_restore.py --fan "<2005 game folder>" install [--cg original|demosaic] [--ck ja|en]
    python fha_restore.py off
    python fha_restore.py status
    python fha_restore.py --fan "<2005 game folder>" build

Options (before the command):
    --fan   your 2005 Fate/hollow ataraxia PC folder with the fan patches (needed for install/build)
    --game  the remaster folder (default: found through Steam)
    --work  where the keys, caches and builds are kept (default: %LOCALAPPDATA%\\FHARestoration,
            the same folder the launcher uses)
The --fan/--game values are remembered in settings.json inside that folder after the first run.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORK = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "FHARestoration")  # shared with the launcher


def save_json(path, data):
    """Atomic write: the launcher may read or write the same settings file."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix="settings.", suffix=".fhar-tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main():
    args, rest, opts = sys.argv[1:], [], {}
    i = 0
    while i < len(args):
        if args[i] in ("--fan", "--game", "--work") and i + 1 < len(args):
            opts[args[i][2:]] = os.path.abspath(args[i + 1])
            i += 2
        else:
            rest.append(args[i])
            i += 1
    work = opts.pop("work", None) or DEFAULT_WORK
    os.makedirs(work, exist_ok=True)
    settings_path = os.path.join(work, "settings.json")
    try:
        saved = json.load(open(settings_path, encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    saved.update(opts)
    if not saved.get("game"):  # find the Steam install the same way the launcher does
        try:
            sys.path.insert(0, HERE)
            from launcher import find_game
            saved["game"] = find_game() or ""
        except Exception:  # noqa: BLE001
            pass
    if opts or saved.get("game"):
        save_json(settings_path, saved)
    os.environ["FHAR_WORK"] = work
    os.environ["FHAR_FAN"] = saved.get("fan", "")
    if saved.get("game"):
        os.environ["FHAR_GAME"] = saved["game"]
    sys.path.insert(0, os.path.join(HERE, "fhar"))
    import restore  # noqa: E402  (reads the environment set above)
    if not rest:
        print(__doc__)
        return
    restore.main(rest)


if __name__ == "__main__":
    main()
