"""FHA Scene Tester: check the restored 18+ scenes of Fate/hollow ataraxia REMASTERED in the game,
one at a time. An optional companion to the launcher, which does not need it.

Check the two folders (found automatically like the launcher does; Browse… to change them), pick a
scene and press "Play this scene". The tester backs up the save folder the first time, installs a
test pack that plays that scene right after Start (fhar/scenetest.py; every achievement trigger is
switched off in it) and starts the game through Steam the same way the launcher does. "Back to
normal" puts back what was installed before the first test; "Restore my save" puts the save folder
back as it was before the first test.

The folders are shared with the launcher (%LOCALAPPDATA%\\FHARestoration\\settings.json). The
engine is loaded when a button is pressed, with the folders shown then; after a folder change the
tester restarts itself to load it again and carries on with the button that was pressed.
"""
import os
import queue
import subprocess
import sys
import threading
import time
import traceback

import launcher

HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "fhar"))
from test_scenes import SCENES  # noqa: E402  (no engine import: the window lists them right away)

TITLE = "FHA Scene Tester"
MUTEX = "Local\\FHARestorationSceneTester"
STATE = os.path.join(launcher.WORK, "scenetest", "state.json")
STEPS = ("On the Entrance screen pick any slot and press Start.",
         "On the title screen press Start: the scene plays right away.",
         "Achievements are switched off in test mode.",
         "When the scene ends the game carries on with the prologue; just close it.")
POLL_MS = 3000
HOLD_S = 15  # a result or error line stays this long before the poll shows what is installed again


def test_state(game):
    """(scene installed for testing or None, save backup time or None), from the tester's notes
    (read only; the same rules as scenetest.current() and save_backup_time())."""
    s = launcher._read_json(STATE)
    sig = launcher._file_sig(os.path.join(game, "obb", "patch00m.bin")) if game else None
    scene = s.get("scene") if s.get("scene") and sig == s.get("sig") else None
    return scene, s.get("save_backup")


def relaunch(action, *args):
    """Start a fresh tester (it loads the engine again with the new folders) that carries on with
    the button that was pressed: --restart play <scene> <variant> <ck> / normal / save."""
    base = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(__file__)]
    subprocess.Popen(base + ["--restart", action, *args])


class Tester:
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk
        self.tk = tk
        self.s = launcher.load_settings()
        self.titles = {sc: title for sc, title, _, _ in SCENES}

        launcher.dpi_aware()
        self.root = tk.Tk()
        self.root.title(TITLE)
        launcher.set_icon(self.root)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda e: self.close())
        self.q = queue.Queue()
        self.busy = self.searching = False
        self.lines, self.details = [], None
        self.hold_until = 0.0  # the status line keeps a result or an error until then
        self.pending = ()      # the action being worked on, for a restart

        f = ttk.Frame(self.root, padding=(16, 14, 16, 14))
        f.grid(row=0, column=0, sticky="nsew")
        ttk.Label(f, text=TITLE, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="Check the restored 18+ scenes in the game, one at a time", foreground="#555").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self.game_var = tk.StringVar(value=launcher.saved_game(self.s))
        self.fan_var = tk.StringVar(value=self.s.get("fan") or "")
        self.game_show, self.fan_show = tk.StringVar(), tk.StringVar()
        self.game_var.trace_add("write", lambda *a: self.game_show.set(launcher._short(self.game_var.get()) or "(not found)"))
        self.fan_var.trace_add("write", lambda *a: self.fan_show.set(launcher._short(self.fan_var.get()) or "(not found)"))
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

        self.scene = tk.StringVar(value=SCENES[0][0])
        row, boxes = 5, {}
        for sc, title, group, note in SCENES:
            if group not in boxes:
                boxes[group] = ttk.LabelFrame(f, text=group, padding=(10, 4, 10, 6))
                boxes[group].grid(row=row, column=0, columnspan=3, sticky="we", pady=(6 if row == 5 else 4, 2))
                row += 1
            line = ttk.Frame(boxes[group])
            line.grid(sticky="w")
            ttk.Radiobutton(line, text=f"{title} — {note}", variable=self.scene, value=sc).pack(side="left")
            ttk.Label(line, text=sc, foreground="#888").pack(side="left", padx=(8, 0))

        opts = ttk.Frame(f)
        opts.grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.variant = tk.StringVar(value=self.s.get("choice") if self.s.get("choice") in ("original", "demosaic") else "original")
        ttk.Label(opts, text="CGs:").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(opts, text="Original (mosaic)", variable=self.variant, value="original").grid(
            row=0, column=1, sticky="w", padx=(8, 0))
        self.demo_btn = ttk.Radiobutton(opts, text="Uncensored (fan demosaic)", variable=self.variant, value="demosaic")
        self.demo_btn.grid(row=0, column=2, sticky="w", padx=(12, 0))
        self.ck = tk.StringVar(value=self.s.get("ck", "ja"))
        self.ck.trace_add("write", lambda *a: self.update_variants())  # what is prepared depends on it
        ttk.Label(opts, text="Chinese mode:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Radiobutton(opts, text="Japanese 日本語", variable=self.ck, value="ja").grid(
            row=1, column=1, sticky="w", padx=(8, 0), pady=(4, 0))
        ttk.Radiobutton(opts, text="English 英语", variable=self.ck, value="en").grid(
            row=1, column=2, sticky="w", padx=(12, 0), pady=(4, 0))
        row += 1

        how = ttk.LabelFrame(f, text="In the game", padding=(10, 4, 10, 6))
        how.grid(row=row, column=0, columnspan=3, sticky="we", pady=(10, 0))
        for step in STEPS:
            ttk.Label(how, text="•  " + step).grid(sticky="w")
        row += 1

        self.status = tk.StringVar()
        ttk.Label(f, textvariable=self.status, foreground="#444", width=74).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(10, 4))
        self.progress = ttk.Progressbar(f, mode="determinate", value=0)
        self.progress.grid(row=row + 1, column=0, columnspan=3, sticky="we")
        bar = ttk.Frame(f)
        bar.grid(row=row + 2, column=0, columnspan=3, sticky="we", pady=(10, 0))
        ttk.Button(bar, text="Details…", command=self.show_details).pack(side="left")
        self.save_btn = ttk.Button(bar, text="Restore my save…", command=self.restore_save)
        self.save_btn.pack(side="left", padx=(8, 0))
        self.play_btn = ttk.Button(bar, text="▶  Play this scene", command=self.play, default="active")
        self.play_btn.pack(side="right")
        self.normal_btn = ttk.Button(bar, text="Back to normal", command=self.back_to_normal)
        self.normal_btn.pack(side="right", padx=8)

        self.picture = launcher.SidePicture(self.root, f, self.fan_var.get())
        self.update_variants()
        if not self.fan_var.get():
            self.searching = True
            self.write("Looking for your 2005 Fate/hollow ataraxia folder…\n")
            threading.Thread(target=lambda: self.q.put(("found", launcher.find_fan())), daemon=True).start()
        self.root.after(30, self.picture.draw)
        self.refresh()
        self.root.after(100, self.pump)
        self.root.after(POLL_MS, self.poll)

    # ---- folders
    def game_ok(self):
        g = self.game_var.get()
        return bool(g) and os.path.exists(os.path.join(g, launcher.GAME_EXE))

    def update_variants(self):
        """The uncensored CGs need patch_decensor.xp3 in the 2005 folder, or a prepared demosaic
        build while that folder is not there (the launcher's rule)."""
        fan = self.fan_var.get()
        if not fan or launcher.has_decensor(fan) or \
                (not launcher.looks_like_fan(fan) and launcher.prepared("demosaic", self.ck.get())):
            self.demo_btn.state(["!disabled"])
        else:
            self.demo_btn.state(["disabled"])
            if self.variant.get() == "demosaic":
                self.variant.set("original")

    def found_fan(self, d):
        self.searching = False
        if self.fan_var.get():  # picked with Browse… in the meantime
            return
        if d:
            self.fan_var.set(d)
            self.write(f"Found: {d}\n")
            self.update_variants()
            self.picture.draw(d)
        else:
            self.write("Not found automatically — use Browse… next to 2005 game.\n")
            self.update_variants()
        self.refresh()

    def browse_game(self):
        from tkinter import filedialog, messagebox
        d = filedialog.askdirectory(title=f"Select the Fate/hollow ataraxia REMASTERED folder (contains {launcher.GAME_EXE})")
        if d:
            if os.path.exists(os.path.join(d, launcher.GAME_EXE)):
                self.game_var.set(os.path.normpath(d))
                self.hold_until = 0.0
                self.refresh()
            else:
                messagebox.showerror(TITLE, "That folder does not contain the game.")

    def browse_fan(self):
        from tkinter import filedialog, messagebox
        d = filedialog.askdirectory(title="Select your 2005 Fate/hollow ataraxia folder (contains patch3.xp3)")
        if d:
            if launcher.looks_like_fan(d):
                self.fan_var.set(os.path.normpath(d))
                self.update_variants()
                self.picture.draw(self.fan_var.get())
            else:
                messagebox.showerror(TITLE, "That folder is not a 2005 Fate/hollow ataraxia install with the fan "
                                            "patches (it needs " + ", ".join(launcher.FAN_NEEDED) + ").")

    def save_folders(self):
        """Remember the folders for the launcher and the next start (the choice stays the launcher's)."""
        s = launcher.load_settings()
        s.update({"game": self.game_var.get(), "fan": self.fan_var.get()})
        launcher.save_settings(s)

    # ---- state
    def refresh(self):
        """Buttons and the status line from what is installed and backed up now."""
        if self.busy:
            return
        current, backup = test_state(self.game_var.get())
        self.normal_btn.state(["!disabled"] if current else ["disabled"])
        self.save_btn.state(["!disabled"] if backup else ["disabled"])
        if time.time() < self.hold_until:  # a result or an error is still being read
            return
        if not self.game_ok():
            self.status.set("Game not found: use Browse… next to Game (Steam).")
        elif self.searching:
            self.status.set("Looking for your 2005 Fate/hollow ataraxia folder…")
        elif current:
            self.status.set(f"Installed now: test scene {self.titles.get(current, current)} ({current})")
        else:
            self.status.set("Installed now: " + launcher.installed_summary(self.game_var.get())[1])

    def poll(self):
        self.refresh()
        self.root.after(POLL_MS, self.poll)

    def write(self, text):
        self.lines.append(text)
        last = [l for l in text.splitlines() if l.strip()]
        if last:
            self.status.set(launcher._pretty(last[-1])[:90])
        if self.details and self.details.alive():
            self.details.add(text)

    def show_details(self):
        if self.details and self.details.alive():
            self.details.win.lift()
        else:
            self.details = launcher.Details(self.root, self.lines)

    def set_busy(self, on):
        self.busy = on
        for b in (self.play_btn, self.normal_btn, self.save_btn):
            b.state(["disabled"] if on else ["!disabled"])
        if on:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)

    def close(self):
        from tkinter import messagebox
        if self.busy:
            messagebox.showinfo(TITLE, "Please wait until the current step has finished.")
            return
        self.root.destroy()

    def pump(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.write(val)
                elif kind == "found":
                    self.found_fan(val)
                elif kind == "done":
                    self.finish(*val)
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def refuse_running(self):
        """True (after telling the user) while the game is running."""
        from tkinter import messagebox
        if launcher.game_running():
            messagebox.showinfo(TITLE, "Close Fate/hollow ataraxia REMASTERED first, then try again.")
            return True
        return False

    # ---- work
    def start_work(self, action, *args):
        self.save_folders()
        self.pending, self.hold_until = (action,) + args, 0.0
        self.set_busy(True)
        self.status.set("Getting ready…")
        threading.Thread(target=self.work, args=(action, self.game_var.get(), self.fan_var.get(), args),
                         daemon=True).start()

    def work(self, action, game, fan, args):
        q = self.q

        class W:
            def write(self, t):
                q.put(("log", t))

            def flush(self):
                pass
        sys.stdout = sys.stderr = W()
        try:
            launcher.init_engine(game, fan)  # the folders shown; the same environment as the launcher
            import scenetest as st
            if action == "play":
                scene, variant, ck = args
                print(f"[test] {self.titles[scene]} ({scene}): {variant} CGs, Chinese mode {ck}")
                n = st.start(scene, variant, ck)
                print(f"[test] test pack installed ({n} achievement triggers switched off)")
            elif action == "normal":
                st.finish()
                print("[test] the version you had before testing is installed again")
            elif action == "save":
                st.restore_save()
                print("[test] the save folder is back as it was before the first test")
            q.put(("done", (action, None)))
        except launcher.PathsChanged:
            q.put(("done", (action, "__relaunch__")))
        except SystemExit as ex:
            q.put(("done", (action, str(ex))))
        except Exception as ex:  # noqa: BLE001
            traceback.print_exc()
            q.put(("done", (action, str(ex))))

    def finish(self, action, error):
        from tkinter import messagebox
        self.set_busy(False)
        if error == "__relaunch__":  # other folders than the engine was loaded with: start afresh
            relaunch(*self.pending)
            self.root.destroy()
            return
        self.refresh()
        self.hold_until = time.time() + HOLD_S
        if error:
            failed = "That didn't work. Details… shows the full output."
            self.status.set(failed)
            messagebox.showerror(TITLE, error)
            self.status.set(failed)  # and for a while after the message is closed (polls ran meanwhile)
            self.hold_until = time.time() + HOLD_S
            return
        if action == "play":
            launcher.start_game([])  # through Steam, exactly as the launcher starts it
            self.status.set("Starting the game through Steam: follow the steps under 'In the game'.")
        elif action == "normal":
            self.status.set("The version you had before testing is installed again.")
        elif action == "save":
            self.status.set("Your save is back as it was before the first test.")

    def resume(self, request):
        """After a restart for other folders, do what was asked in the old window, with the same
        checks as a click (the game must still be closed; restoring the save asks again)."""
        action, args = (request[0], list(request[1:])) if request else ("", [])
        self.status.set("The folders changed, so the tester restarted with them.")
        self.hold_until = time.time() + HOLD_S
        if action == "play" and len(args) == 3 and args[0] in self.titles \
                and args[1] in ("original", "demosaic") and args[2] in ("ja", "en"):
            scene, variant, ck = args
            self.scene.set(scene)
            self.ck.set(ck)  # (checks the CG options again)
            self.variant.set(variant)
            self.update_variants()
            if self.variant.get() == variant:  # still offered with these folders
                self.play()
                return
        elif action == "normal":
            if test_state(self.game_var.get())[0]:  # nothing to do once no test pack is installed
                self.back_to_normal()
            return
        elif action == "save":
            self.restore_save()
            return
        self.status.set("The folders changed, so the tester restarted with them. Click the button again.")

    # ---- actions
    def play(self):
        from tkinter import messagebox
        if self.busy:
            return
        if not self.game_ok():
            messagebox.showerror(TITLE, "Fate/hollow ataraxia REMASTERED was not found. Use Browse… next to Game (Steam).")
            return
        variant, ck = self.variant.get(), self.ck.get()
        if not launcher.looks_like_fan(self.fan_var.get()) and not launcher.prepared(variant, ck):
            messagebox.showerror(TITLE, "Still looking for your 2005 folder; wait a moment or use Browse…."
                                 if self.searching else
                                 "Select your 2005 Fate/hollow ataraxia folder first (Browse… next to 2005 game).")
            return
        if variant == "demosaic" and not launcher.has_decensor(self.fan_var.get()) and not launcher.prepared(variant, ck):
            messagebox.showerror(TITLE, "The uncensored CGs need patch_decensor.xp3 in your 2005 folder.")
            return
        if self.refuse_running():
            return
        self.start_work("play", self.scene.get(), variant, ck)

    def back_to_normal(self):
        if self.busy or self.refuse_running():
            return
        self.start_work("normal")

    def restore_save(self):
        from tkinter import messagebox
        when = test_state(self.game_var.get())[1]
        if self.busy or not when or self.refuse_running():
            return
        if messagebox.askyesno(TITLE, f"Put your save folder back exactly as it was on {when}, before the first "
                                      "scene test?\n\nThis removes the read marks, unlocked CGs and Scene Replay "
                                      "entries the tests added (and anything else saved in the game since then).",
                               icon="warning", default="no"):
            self.start_work("save")

    def run(self):
        self.root.mainloop()


def main():
    import multiprocessing
    multiprocessing.freeze_support()  # first: the image builder's worker processes start here
    launcher.reset_frozen_environment()  # Steam and our restart must not inherit our temporary folder
    argv = sys.argv[1:]
    restart = "--restart" in argv
    if not launcher.single_instance(wait=20 if restart else 0, name=MUTEX):
        launcher.message("The FHA Scene Tester is already open.")
        return
    t = Tester()
    if restart:  # restarted after a folder change: carry on with the button that was pressed
        t.root.after(500, lambda: t.resume(argv[argv.index("--restart") + 1:]))
    t.run()


if __name__ == "__main__":
    main()
