# Fate/hollow ataraxia REMASTERED: Cut Content Restoration

Restores the content of the 2005 PC release that was cut from **Fate/hollow ataraxia REMASTERED** (Steam): the four Eclipse H scenes, Caren's fifth scene in its 2005 version, the passages cut by the console censorship, the 2005 drinking scenes, the nude CGs and the H section of the CG gallery.

> ⚠️ **18+.** No game content is included: everything is built on your PC from your own 2005 game files.

## Requirements

- Fate/hollow ataraxia REMASTERED on Steam (version 1.0.4.729).
- The 2005 PC game with the fan patches (`patch3.xp3`, `patch_lang_english.xp3` and the `Android` folder). The fan demosaic patch (`patch_decensor.xp3`) is optional and adds uncensored CGs.
- About 2 GB of free space, and an internet connection the first time.

## Install

**Setup:** Require the Steam release of the Remaster and the original 2005 game with the fan-patch. You can find it at "sukebei.nyaa.si" and search "Fate/Hollow Ataraxia [English Patched, Voice Patch Final v1.0.0]". Run `FHA-Restoration-Launcher.exe`, locate your games files for Steam and the original. Choose original CGs, uncensored fan-CGs or Off, and click **Play**. The first run takes a few minutes. To use Steam's Play button instead, set the game's launch options to `"<path>\FHA-Restoration-Launcher.exe" %command%`. There's an optional launch tester that will take you straight to the h-scene if you press start in the game.

The only files you need from the 2005 data.xp3, image.xp3. fgimage.xp3, bgimage.xp3, sound.xp3, patch.xp3, patch2.xp3 and for the fan patches patch3.xp3, patch_lang_english.xp3 (the English patch), and Android\xp3filter.tjs (in the Android folder). The android patch is need because It’s the only place it gets the key to open the 2005 game’s archives, and without it the launcher can’t read the 2005 game at all. Optional: patch_decensor.xp3 (the fan demosaic patch). Without it, only the original CG option is offered.

The launcher adds two files to the game's `obb` folder and changes nothing else; **Off** removes them. Achievements work as normal. Restored lines use the 2005 Japanese and the Beast's Lair English translation; in Chinese mode they appear in Japanese or English. The Eclipse scenes are on the Eclipse map in the morning, once the 2005 conditions for each heroine are met.

**Text hookers (LunaHook):** attach to `hollow-win64vc14-release.exe`, not to the launcher. Restored lines hook like the rest of the game.

**Scene Tester (optional):** `FHA-Scene-Tester.exe` plays a chosen 18+ scene as soon as you start a new game, with achievements off. Click **Back to normal** when you're done.

## Not restored

Ema 37 and 38, changes that aren't censorship (a parody passage, a hanafuda variant, Caren's Avenger scenes) and a few pictures the remaster repainted. Restored CGs are the 2005 4:3 art, upscaled.

Restored lines are unvoiced: the 2005 game had no voices, and the remaster's recordings are of the censored wording. Lines that are the same in both keep their voice.

## Building from source (developers only)

Players don't need this; the `.exe` has everything built in. To build it yourself, install 64-bit Python 3.10 to 3.13 and run `build.bat`. Command line: `pip install -r requirements.txt`, then `python fha_restore.py --fan "<2005 game folder>" install`.

## Credits

TYPE-MOON (please support the official release); the Beast's Lair English patch team; the fan patch and voice patch teams (Quibi, Hintay, ニサンカタンソ, Jacktheinfinite101); the fan demosaic patch authors (Thorny Rose Studios); kurikomoe/FSNr_tools, DaZombieKiller/FatePackageManager and W.Dee's KiriKiri 2 for the file formats. Built with Claude Code (Claude Opus 5.5, Anthropic).

## License

MIT, except `fhar/epk.py` and `fhar/fpd.py` (see `THIRD_PARTY.md`). Unofficial; not affiliated with TYPE-MOON, Aniplex or the fan patch teams.
