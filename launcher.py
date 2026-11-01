"""Fate/hollow ataraxia REMASTERED - Restoration Launcher.

Before each start it asks how you want to play (restored 2005 content with the original or the
demosaiced CGs, or Off), puts the matching files in place and starts the game through Steam.

Can also be used as a Steam launch option so Steam's own Play button shows it:
    "C:\\path\\to\\FHA-Restoration-Launcher.exe" %command%
"""
import contextlib
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback

APP_NAME = "FHA Restoration"
APP_ID = "2396990"
GAME_EXE = "hollow-win64vc14-release.exe"
WORK = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "FHARestoration")
SETTINGS = os.path.join(WORK, "settings.json")
HANDOFF = os.path.join(WORK, "handoff.json")  # "we just started Steam ourselves"
MUTEX = "Local\\FHARestorationLauncher"
# what a 2005 Fate/hollow ataraxia folder with the fan patches must contain
FAN_NEEDED = ("data.xp3", "patch.xp3", "patch2.xp3", "patch3.xp3", "patch_lang_english.xp3", "image.xp3",
              "fgimage.xp3", "bgimage.xp3", "sound.xp3", os.path.join("Android", "xp3filter.tjs"))  # = restore.FAN_REQUIRED
FAN_KEYWORDS = ("hollow", "ataraxia", "fha", "fate", "type-moon", "typemoon")
_MUTEX = []


# ---------------------------------------------------------------- detection
def _reg(root, path, name):
    try:
        import winreg
        with winreg.OpenKey(root, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def find_game():
    """Locate the remaster through Steam's own library list (a real Steam install of app 2396990)."""
    import winreg
    steam = _reg(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath") or \
        _reg(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")
    if not steam:
        return None
    libs = [os.path.normpath(steam)]
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf):
        text = open(vdf, encoding="utf-8", errors="ignore").read()
        libs += [os.path.normpath(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', text)]
    for lib in dict.fromkeys(libs):
        acf = os.path.join(lib, "steamapps", f"appmanifest_{APP_ID}.acf")
        if os.path.exists(acf):
            m = re.search(r'"installdir"\s+"([^"]+)"', open(acf, encoding="utf-8", errors="ignore").read())
            if m:
                d = os.path.join(lib, "steamapps", "common", m.group(1))
                if os.path.exists(os.path.join(d, GAME_EXE)):
                    return d
    return None


def looks_like_fan(d):
    return bool(d) and all(os.path.exists(os.path.join(d, f)) for f in FAN_NEEDED)


def has_decensor(d):
    """The fan demosaic patch is optional: without it only the original CGs are offered."""
    return bool(d) and os.path.exists(os.path.join(d, "patch_decensor.xp3"))


def game_running():
    """The game's process is running: restore.game_running() for the windows, which don't load the
    engine for it. tasklist in CSV keeps the full image name (its table cuts it to 25 characters;
    the exe's has 28), and the output is compared as bytes (it is in the console code page)."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH", "/FI", f"IMAGENAME eq {GAME_EXE}"],
                             capture_output=True, creationflags=flags).stdout
    except OSError:
        return False
    return b'"' + GAME_EXE.lower().encode("ascii") + b'"' in out.lower()


def _listdir(d):
    try:
        return os.listdir(d)
    except OSError:
        return []


def _search(root, depth=2):
    """A fan folder below root: a folder whose name looks like the game (searched `depth` levels
    down), or any folder directly inside one (e.g. ...\\TYPE-MOON\\<game folder>)."""
    for name in _listdir(root):
        d = os.path.join(root, name)
        if not any(k in name.lower() for k in FAN_KEYWORDS) or not os.path.isdir(d):
            continue
        if looks_like_fan(d):
            return d
        hit = next((os.path.join(d, n) for n in _listdir(d) if looks_like_fan(os.path.join(d, n))), None)
        if not hit and depth > 1:
            hit = _search(d, depth - 1)
        if hit:
            return hit
    return None


def find_fan():
    """Look for the 2005 Fate/hollow ataraxia folder: Windows uninstall entries, then common folders."""
    import winreg
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for base in (r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
                     r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
            try:
                with winreg.OpenKey(root, base) as k:
                    for i in range(winreg.QueryInfoKey(k)[0]):
                        sub = winreg.EnumKey(k, i)
                        name = (_reg(root, base + "\\" + sub, "DisplayName") or "").lower()
                        if "hollow" in name or "ataraxia" in name:
                            loc = _reg(root, base + "\\" + sub, "InstallLocation")
                            if looks_like_fan(loc):
                                return os.path.normpath(loc)
            except OSError:
                pass
    home = os.path.expanduser("~")
    roots = [os.path.join(home, x) for x in ("Downloads", "Desktop", "Documents", "Games")]
    roots += [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
    roots += [f"{d}:\\" for d in "CDEFG" if os.path.exists(f"{d}:\\")]
    roots += [f"{d}:\\Games" for d in "CDEFG" if os.path.exists(f"{d}:\\Games")]
    for r in roots:
        hit = _search(r)
        if hit:
            return os.path.normpath(hit)
    return None


# ---------------------------------------------------------------- settings
def load_settings():
    try:
        return json.load(open(SETTINGS, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def saved_game(s):
    """The game folder from the settings, found again through Steam when it is not set or no
    longer holds the game (e.g. Steam's 'Move install folder')."""
    g = s.get("game")
    if not g or not os.path.exists(os.path.join(g, GAME_EXE)):
        g = find_game() or g or ""
    return g


def save_settings(s):
    """Atomic write (temp file + rename): the launcher and the command-line tool share the file."""
    os.makedirs(WORK, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=WORK, prefix="settings.", suffix=".fhar-tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
        os.replace(tmp, SETTINGS)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


_ENGINE_PATHS = None


class PathsChanged(Exception):
    """The engine modules were already loaded with other folders; the launcher must restart."""


def init_engine(game, fan):
    """Load the engine for these folders. The engine reads its folders once at import time, so a
    different pair of folders in the same process means: restart the launcher (PathsChanged)."""
    global _ENGINE_PATHS
    if _ENGINE_PATHS is not None and _ENGINE_PATHS != (game, fan or ""):
        raise PathsChanged()
    os.environ["FHAR_WORK"] = WORK
    os.environ["FHAR_GAME"] = game
    os.environ["FHAR_FAN"] = fan or ""
    here = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(here, "fhar"))
    import restore
    _ENGINE_PATHS = (game, fan or "")
    return restore


def relaunch():
    """Start a fresh launcher process (same arguments) and let this one exit."""
    rest = [a for a in sys.argv[1:] if a != "--autoplay"]
    if getattr(sys, "frozen", False):
        args = [sys.executable, "--autoplay"] + rest
    else:
        args = [sys.executable, os.path.abspath(__file__), "--autoplay"] + rest
    subprocess.Popen(args)


@contextlib.contextmanager
def _system_dll_search():
    """In the frozen exe the onefile bootloader points the DLL search at this process's temporary
    folder, and processes we start inherit it: the game would load our bundled VCRUNTIME140
    instead of Windows' own and keep it locked, so the folder can't be removed when we exit (a
    warning box). Windows' normal search while the game or Steam is being started."""
    if not getattr(sys, "frozen", False):
        yield
        return
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.SetDllDirectoryW(None)
    try:
        yield
    finally:
        k32.SetDllDirectoryW(sys._MEIPASS)  # the scene tester keeps running and loads bundled DLLs


def _game_environment():
    """The game's environment: in the frozen exe, ours without the bootloader's own variables
    (_PYI_*, the Tcl/Tk paths into our temporary folder, the reset flag)."""
    if not getattr(sys, "frozen", False):
        return None
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("_PYI")
            and k.upper() not in ("TCL_LIBRARY", "TK_LIBRARY", "PYINSTALLER_RESET_ENVIRONMENT")}


def start_game(command):
    with _system_dll_search():
        if command:  # launched by Steam as a launch option: run the game command we were given
            subprocess.Popen(command, cwd=os.path.dirname(command[0]) or None, env=_game_environment())
        else:
            # if the user also set the launcher as Steam's launch option, Steam will start us again
            # with %command%; the handoff marker makes that second start skip the window
            try:
                os.makedirs(WORK, exist_ok=True)
                json.dump({"time": time.time()}, open(HANDOFF, "w"))
            except OSError:
                pass
            os.startfile(f"steam://rungameid/{APP_ID}")


def desktop_folder():
    """The user's Desktop folder as Windows reports it (it may be redirected, e.g. to OneDrive)."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0:  # CSIDL_DESKTOPDIRECTORY
            return buf.value
    except (OSError, AttributeError):
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def create_shortcut(fan):
    """A desktop shortcut to this launcher with Caren's face as its icon. The icon is cut from the
    player's own 2005 files (side_art.py), so the download itself carries no game art; without
    the 2005 folder the shortcut gets the launcher's own icon. Returns the shortcut's path."""
    import side_art
    if getattr(sys, "frozen", False):
        target, args, workdir = sys.executable, "", os.path.dirname(sys.executable)
    else:
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        target = pyw if os.path.exists(pyw) else sys.executable
        args, workdir = f'"{os.path.abspath(__file__)}"', os.path.dirname(os.path.abspath(__file__))
    icon = side_art.icon_file(fan) or target
    lnk = os.path.join(desktop_folder(), "FHA Restoration.lnk")
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:FHAR_L);"
          "$s.TargetPath=$env:FHAR_T;$s.Arguments=$env:FHAR_A;$s.WorkingDirectory=$env:FHAR_W;"
          "$s.IconLocation=$env:FHAR_I+',0';$s.Description='Fate/hollow ataraxia REMASTERED cut content restoration';"
          "$s.Save()")
    env = dict(_game_environment() or os.environ, FHAR_L=lnk, FHAR_T=target, FHAR_A=args, FHAR_W=workdir, FHAR_I=icon)
    with _system_dll_search():
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                           env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 or not os.path.exists(lnk):
        raise RuntimeError("Windows could not create the shortcut: "
                           + (r.stderr.decode("utf-8", "replace").strip()[-300:] or "unknown error"))
    return lnk


def just_handed_off():
    try:
        t0 = json.load(open(HANDOFF))["time"]
        os.remove(HANDOFF)
        return time.time() - t0 < 600  # Steam may first update and log in; the marker is used once
    except (OSError, ValueError, KeyError):
        return False


def single_instance(wait=0.0, name=MUTEX):
    """Hold a named mutex for the life of this process; False when another launcher holds it
    (after waiting up to `wait` seconds, e.g. for the launcher that is restarting us). The scene
    tester passes its own name."""
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = ctypes.c_void_p
        k32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        h = k32.CreateMutexW(None, False, name)
        if not h:
            return True
        if k32.WaitForSingleObject(h, int(wait * 1000)) in (0, 0x80):  # acquired / abandoned
            _MUTEX.append(h)
            return True
        return False
    except (OSError, AttributeError):
        return True


def message(text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x40)
    except (OSError, AttributeError):
        print(text)


# ---------------------------------------------------------------- UI
PICTURE_W = 250  # width of the picture on the right, in pixels at 100 % display scale


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _file_sig(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [st.st_size, int(st.st_mtime)]


def installed_summary(game):
    """What the game's obb folder holds now, judged from the notes the engine keeps in WORK (read
    only: no hashing, nothing written; Play checks it properly). Returns (tone, text, choice, ck)."""
    if not game or not os.path.exists(os.path.join(game, GAME_EXE)):
        return "unknown", "Game not found", None, None
    obb = os.path.join(game, "obb")
    packs = {p: _file_sig(os.path.join(obb, p)) for p in ("patch00m.bin", "patch01d.bin")}
    if not any(packs.values()):
        return "off", "Off · unmodified remaster", "off", None
    test = _read_json(os.path.join(WORK, "scenetest", "state.json"))
    if test.get("scene") and packs["patch00m.bin"] == test.get("sig"):
        return "test", f"Test · {test['scene']}", "test", test.get("ck")
    applied = _read_json(os.path.join(WORK, "restore_state.json")).get("applied") or {}
    sig = applied.get("sig") or {}
    now = dict(packs, pack00m=_file_sig(os.path.join(obb, "pack00m.bin")),
               pack10d=_file_sig(os.path.join(obb, "pack10d.bin")), exe=_file_sig(os.path.join(game, GAME_EXE)))
    if applied.get("choice") in ("original", "demosaic") and all(sig.get(k) == v for k, v in now.items()):
        cg = "original CGs" if applied["choice"] == "original" else "uncensored CGs"
        return "on", f"Restored · {cg}", applied["choice"], applied.get("ck")
    return "unknown", "Not checked yet", None, None


def _pretty(line):
    """'[build] packing patch00m.ja.bin' -> 'Packing patch00m.ja.bin' for the status line."""
    line = re.sub(r"^\[[a-z]+\]\s*", "", line.strip())
    return line[:1].upper() + line[1:]


def _short(path, n=56):
    """A folder path as Windows spells it (Steam stores it in lower case), with its middle cut
    out when it is longer than about n characters."""
    try:
        real = os.path._getfinalpathname(path) if path else path
        path = real[4:] if real.startswith("\\\\?\\") else real
    except (OSError, AttributeError, ValueError):
        pass
    return path if len(path) <= n else path[:n // 2 - 2] + "…" + path[-(n // 2 - 1):]


def dpi_aware():
    """Sharp text on high-DPI screens: Tk then sizes its fonts from the display setting."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (OSError, AttributeError):
        pass


def set_icon(root):
    """Window and taskbar icon (bundled into the exe; assets/ when run from source)."""
    try:
        here = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        root.iconbitmap(default=os.path.join(here, "assets", "launcher.ico"))
    except Exception:  # noqa: BLE001
        pass


class SidePicture:
    """The picture down the right edge and Caren's face as the window icon (side_art.py: both
    are cut from the player's own 2005 files), the picture as tall as the window's content."""

    def __init__(self, root, content, fan):
        import tkinter as tk
        self.root, self.content, self.fan = root, content, fan
        self.label = tk.Label(root, bd=0, highlightthickness=0, bg="#1c1630")
        self.label.grid(row=0, column=1, sticky="ns")
        self.photo, self.real, self.icons = None, False, None

    def draw(self, fan=None):
        """Draw (again) for the current 2005 folder and the content's height now; keeps the 2005
        picture once it has it, cut again when the content changed height (e.g. a note line)."""
        if fan is not None:
            self.fan = fan
        if not self.icons:
            try:
                from PIL import ImageTk
                import side_art
                ims = side_art.icon_images(self.fan)
                if ims:
                    self.icons = [ImageTk.PhotoImage(i) for i in ims]
                    self.root.iconphoto(True, *self.icons)
            except Exception:  # noqa: BLE001  (the original icon stays)
                pass
        try:
            from PIL import ImageTk
            import side_art
            self.root.update_idletasks()
            scale = self.root.winfo_fpixels("1i") / 96
            w, h = round(PICTURE_W * scale), self.content.winfo_reqheight()
            if self.real and self.photo is not None and (self.photo.width(), self.photo.height()) == (w, h):
                return
            im, real = side_art.picture(self.fan, w, h)
            if self.real and not real:
                return
            self.photo, self.real = ImageTk.PhotoImage(im), real
            self.label.configure(image=self.photo, width=w, height=h)
        except Exception:  # noqa: BLE001  (no picture is better than no launcher)
            pass


class Details:
    """The full output, in a separate window that opens only when asked for."""

    def __init__(self, root, lines):
        import tkinter as tk
        from tkinter import ttk
        self.win = tk.Toplevel(root)
        self.win.title(f"{APP_NAME} - details")
        self.text = tk.Text(self.win, width=96, height=22, font=("Consolas", 9), wrap="word")
        bar = ttk.Scrollbar(self.win, command=self.text.yview)
        self.text.configure(yscrollcommand=bar.set)
        self.text.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.text.insert("end", "".join(lines))
        self.text.see("end")
        self.text.configure(state="disabled")

    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except Exception:  # noqa: BLE001
            return False

    def add(self, text):
        self.text.configure(state="normal")
        self.text.insert("end", text)
        self.text.see("end")
        self.text.configure(state="disabled")


class Launcher:
    def __init__(self, command):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.command = command
        self.s = load_settings()
        dpi_aware()
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        set_icon(self.root)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.resizable(False, False)
        self.root.bind("<Return>", lambda e: self.play())
        self.root.bind("<Escape>", lambda e: self.close())
        self.q = queue.Queue()
        self.busy = self.searching = False
        self.lines, self.details = [], None

        f = ttk.Frame(self.root, padding=(16, 14, 16, 14))
        f.grid(row=0, column=0, sticky="nsew")
        self.content = f
        ttk.Label(f, text="Fate/hollow ataraxia REMASTERED", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="2005 cut content restoration", foreground="#555").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))

        self.game_var = tk.StringVar(value=saved_game(self.s))
        self.fan_var = tk.StringVar(value=self.s.get("fan") or "")
        self.game_show, self.fan_show = tk.StringVar(), tk.StringVar()
        self.game_var.trace_add("write", lambda *a: self.game_show.set(_short(self.game_var.get()) or "(not found)"))
        self.fan_var.trace_add("write", lambda *a: self.fan_show.set(_short(self.fan_var.get()) or "(not found)"))
        self.game_var.set(self.game_var.get())
        self.fan_var.set(self.fan_var.get())
        ttk.Label(f, text="Game (Steam):").grid(row=2, column=0, sticky="w")
        ttk.Label(f, textvariable=self.game_show, width=54).grid(row=2, column=1, sticky="w", padx=(8, 0))
        ttk.Button(f, text="Browse…", command=self.browse_game).grid(row=2, column=2, padx=(8, 0), pady=2)
        ttk.Label(f, text="2005 game:").grid(row=3, column=0, sticky="w")
        ttk.Label(f, textvariable=self.fan_show, width=54).grid(row=3, column=1, sticky="w", padx=(8, 0))
        ttk.Button(f, text="Browse…", command=self.browse_fan).grid(row=3, column=2, padx=(8, 0), pady=2)
        ttk.Label(f, text="Your 2005 Fate/hollow ataraxia PC folder with the fan patches",
                  foreground="#666").grid(row=4, column=1, columnspan=2, sticky="w", padx=(8, 0))

        box = ttk.LabelFrame(f, text="How do you want to play?", padding=(10, 6, 10, 8))
        box.grid(row=5, column=0, columnspan=3, sticky="we", pady=(12, 8))
        self.mode = tk.StringVar(value=self.s.get("choice", "original"))
        ttk.Radiobutton(box, text="Restored 2005 content — original CGs (mosaic)", variable=self.mode,
                        value="original").grid(sticky="w", pady=1)
        self.demo_btn = ttk.Radiobutton(box, text="Restored 2005 content — uncensored CGs (fan demosaic)",
                                        variable=self.mode, value="demosaic")
        self.demo_btn.grid(sticky="w", pady=1)
        self.demo_note = ttk.Label(box, text="", foreground="#666")
        self.demo_note.grid(sticky="w", padx=(22, 0))
        ttk.Radiobutton(box, text="Off — play the unmodified remaster", variable=self.mode,
                        value="off").grid(sticky="w", pady=1)
        ttk.Label(box, text="Chinese mode (中文模式): restored lines have no Chinese translation; show them in\n"
                            "恢复的内容没有中文翻译，显示为：").grid(sticky="w", pady=(8, 0))
        ckbox = ttk.Frame(box)
        ckbox.grid(sticky="w")
        self.ck = tk.StringVar(value=self.s.get("ck", "ja"))
        self.ck.trace_add("write", lambda *a: self.update_variants())  # what is prepared depends on it
        ttk.Radiobutton(ckbox, text="Japanese 日本語", variable=self.ck, value="ja").pack(side="left")
        ttk.Radiobutton(ckbox, text="English 英语", variable=self.ck, value="en").pack(side="left", padx=(16, 0))
        self.ask = tk.BooleanVar(value=self.s.get("ask", True))
        ttk.Checkbutton(f, text="Ask me every time I start the game", variable=self.ask).grid(
            row=6, column=0, columnspan=3, sticky="w")

        self.status = tk.StringVar()
        ttk.Label(f, textvariable=self.status, foreground="#444", width=70).grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(12, 4))
        self.progress = ttk.Progressbar(f, mode="determinate", value=0)
        self.progress.grid(row=8, column=0, columnspan=3, sticky="we")
        bar = ttk.Frame(f)
        bar.grid(row=9, column=0, columnspan=3, sticky="we", pady=(10, 0))
        ttk.Button(bar, text="Details…", command=self.show_details).pack(side="left")
        ttk.Button(bar, text="Desktop shortcut", command=self.shortcut).pack(side="left", padx=(8, 0))
        self.play_btn = ttk.Button(bar, text="▶  Play", command=self.play, default="active")
        self.play_btn.pack(side="right")
        self.quit_btn = ttk.Button(bar, text="Quit", command=self.close)
        self.quit_btn.pack(side="right", padx=8)

        self.picture = SidePicture(self.root, f, self.fan_var.get())
        self.update_variants()
        self.refresh_status()
        if not self.game_var.get():
            self.write("Fate/hollow ataraxia REMASTERED was not found in your Steam libraries.\n")
        if not self.fan_var.get():
            self.searching = True
            self.write("Looking for your 2005 Fate/hollow ataraxia folder…\n")
            threading.Thread(target=lambda: self.q.put(("found", find_fan())), daemon=True).start()
        self.root.after(30, self.picture.draw)
        self.root.after(100, self.pump)

    # ---- helpers
    def close(self):
        from tkinter import messagebox
        if self.busy:
            messagebox.showinfo(APP_NAME, "Please wait until the current step has finished.")
            return
        self.root.destroy()

    def write(self, text):
        self.lines.append(text)
        last = [l for l in text.splitlines() if l.strip()]
        if last:
            self.status.set(_pretty(last[-1])[:90])
        if self.details and self.details.alive():
            self.details.add(text)

    def show_details(self):
        if self.details and self.details.alive():
            self.details.win.lift()
        else:
            self.details = Details(self.root, self.lines)

    def shortcut(self):
        from tkinter import messagebox
        try:
            create_shortcut(self.fan_var.get())
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror(APP_NAME, str(ex))
            return
        icon = "Caren's face as its icon" if self.picture.icons else "the launcher's icon (Caren's appears once your 2005 folder is found)"
        messagebox.showinfo(APP_NAME, f"A shortcut \"FHA Restoration\" is now on your desktop, with {icon}.")

    def refresh_status(self):
        if not self.busy:
            self.status.set("Installed now: " + installed_summary(self.game_var.get())[1])

    def pump(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.write(val)
                elif kind == "found":
                    self.found_fan(val)
                elif kind == "done":
                    self.finish(val)
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def found_fan(self, d):
        self.searching = False
        if self.fan_var.get():  # picked with Browse… in the meantime
            return
        if d:
            self.fan_var.set(d)
            self.write(f"Found: {d}\n")
            self.update_variants()  # first: its note line changes the height the picture is cut to
            self.picture.draw(d)
        else:
            self.write("Not found automatically — use Browse… to select it.\n")
            self.update_variants()
        self.refresh_status()

    def update_variants(self):
        """The demosaic choice needs patch_decensor.xp3 in the selected folder, or, while that folder
        is not there (an unplugged drive), a prepared demosaic build."""
        fan = self.fan_var.get()
        if not fan or has_decensor(fan) or (not looks_like_fan(fan) and prepared("demosaic", self.ck.get())):
            self.demo_btn.state(["!disabled"])
            self.demo_note.grid_remove()
        else:
            self.demo_btn.state(["disabled"])
            self.demo_note.configure(text="(needs the fan patch patch_decensor.xp3 in your folder)")
            self.demo_note.grid()
            if self.mode.get() == "demosaic":
                self.mode.set("original")

    def browse_game(self):
        from tkinter import filedialog, messagebox
        d = filedialog.askdirectory(title=f"Select the Fate/hollow ataraxia REMASTERED folder (contains {GAME_EXE})")
        if d:
            if os.path.exists(os.path.join(d, GAME_EXE)):
                self.game_var.set(os.path.normpath(d))
                self.refresh_status()
            else:
                messagebox.showerror(APP_NAME, "That folder does not contain the game.")

    def browse_fan(self):
        from tkinter import filedialog, messagebox
        d = filedialog.askdirectory(title="Select your 2005 Fate/hollow ataraxia folder (contains patch3.xp3)")
        if d:
            if looks_like_fan(d):
                self.fan_var.set(os.path.normpath(d))
                self.update_variants()
                self.picture.draw(self.fan_var.get())
            else:
                messagebox.showerror(APP_NAME, "That folder is not a 2005 Fate/hollow ataraxia install with the fan "
                                               "patches (it needs " + ", ".join(FAN_NEEDED) + ").")

    # ---- actions
    def play(self):
        from tkinter import messagebox
        if self.busy:
            return
        game, fan, choice, ck = self.game_var.get(), self.fan_var.get(), self.mode.get(), self.ck.get()
        if not game or not os.path.exists(os.path.join(game, GAME_EXE)):
            messagebox.showerror(APP_NAME, "Fate/hollow ataraxia REMASTERED (Steam) was not found. Use Browse… next to Game.")
            return
        if choice != "off" and not looks_like_fan(fan) and not prepared(choice, ck):
            messagebox.showerror(APP_NAME, "Still looking for your 2005 folder; wait a moment or use Browse…."
                                 if self.searching else
                                 "Select your 2005 Fate/hollow ataraxia folder first (Browse… next to 2005 game).")
            return
        if choice == "demosaic" and not has_decensor(fan) and not prepared(choice, ck):
            messagebox.showerror(APP_NAME, "The uncensored CGs need patch_decensor.xp3 in your Fate/hollow ataraxia folder.")
            return
        self.s.update({"game": game, "fan": fan, "choice": choice, "ck": ck, "ask": self.ask.get()})
        save_settings(self.s)
        self.busy = True
        self.play_btn.configure(state="disabled")
        self.quit_btn.configure(state="disabled")
        self.status.set("Getting ready…")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        threading.Thread(target=self.work, args=(game, fan, choice, ck), daemon=True).start()

    def work(self, game, fan, choice, ck):
        q = self.q

        class W:
            def write(self, t):
                q.put(("log", t))

            def flush(self):
                pass
        sys.stdout = sys.stderr = W()
        try:
            run_choice(game, fan, choice, ck)
            q.put(("done", None))
        except PathsChanged:
            q.put(("done", "__relaunch__"))
        except SystemExit as ex:
            q.put(("done", str(ex)))
        except Exception as ex:  # noqa: BLE001
            traceback.print_exc()
            q.put(("done", str(ex)))

    def finish(self, error):
        from tkinter import messagebox
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0 if error else 100)
        self.busy = False
        if error == "__relaunch__":  # folders changed: continue in a fresh launcher process
            relaunch()
            self.root.destroy()
            return
        if error:
            self.play_btn.configure(state="normal")
            self.quit_btn.configure(state="normal")
            self.status.set("That didn't work. Details… shows the full output.")
            messagebox.showerror(APP_NAME, error)
            return
        self.status.set("Starting the game…")
        start_game(self.command)
        self.root.after(800, self.root.destroy)  # Play and Quit stay disabled until then

    def run(self):
        self.root.mainloop()


def already_set(restore, choice, ck):
    if choice == "off":
        return restore.current() == "off"
    return restore.detect() == (choice, ck) and restore.cache_stamp() is not None


def run_choice(game, fan, choice, ck="ja"):
    restore = init_engine(game, fan)
    if already_set(restore, choice, ck):
        print(f"Game files already set ({choice}). Starting the game.")
        return
    if choice == "off":
        restore.off()
        print("Starting the unmodified game.")
        return
    bad = restore.foreign()  # an official update's own pack: say so before any rebuild
    if bad:
        raise restore.foreign_error(bad)
    s = restore.cache_stamp()
    if s and choice in s["variants"] and ck in s["cks"]:  # already prepared: no 2005 folder needed
        restore.install(choice, ck)
        print("Starting the game.")
        return
    if not looks_like_fan(fan):  # Play went by the stamp, but the build is out of date
        raise RuntimeError(restore.NEED_FAN)
    restore.prepare()
    restore.ensure_built()  # every variant the folder supports, so switching later is instant
    restore.install(choice, ck)
    print("Starting the game.")


def prepared(choice, ck):
    """True when the finished build in WORK already holds this choice (read only; Play checks it
    properly), so the 2005 folder isn't needed to switch to it."""
    s = _read_json(os.path.join(WORK, "cache", "stamp.json"))
    return choice in (s.get("variants") or []) and ck in (s.get("cks") or [])


def quick_start(command, s):
    """'Don't ask' mode: start straight away when the game files already match the saved choice.
    Anything that needs work (first build, a Steam update, a different choice) opens the window."""
    try:
        if not os.path.exists(os.path.join(s["game"], GAME_EXE)):  # moved: the window finds it again
            return False
        restore = init_engine(s["game"], s.get("fan", ""))
        if already_set(restore, s.get("choice", "original"), s.get("ck", "ja")):
            start_game(command)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def shift_held():
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000)
    except Exception:  # noqa: BLE001
        return False


def reset_frozen_environment():
    """In the frozen exe: processes we start (our own relaunch, and Steam, which later starts us
    again through the launch option) must unpack their own copy of the program instead of using
    this process's temporary folder, which is deleted when we exit (PyInstaller 6.9+)."""
    if getattr(sys, "frozen", False):
        os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"


def main():
    import multiprocessing
    multiprocessing.freeze_support()  # first: the image builder's worker processes start here
    reset_frozen_environment()
    autoplay = "--autoplay" in sys.argv[1:]
    command = [a for a in sys.argv[1:] if a != "--autoplay"]
    command = command if command and command[0].lower().endswith(".exe") else []
    s = load_settings()
    if command and just_handed_off():  # second start by Steam right after we started it
        start_game(command)
        return
    if not single_instance(wait=20 if autoplay else 0):
        message("The FHA Restoration launcher is already open.")
        return
    if s.get("game") and not s.get("ask", True) and not shift_held():
        if quick_start(command, s):
            return
    app = Launcher(command)
    if autoplay:  # restarted after a folder change: continue with Play right away
        app.root.after(500, app.play)
    app.run()


if __name__ == "__main__":
    main()
