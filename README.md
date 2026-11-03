# Tenchu 2: 60fps + Draw Distance

A DuckStation cheat-file patch for **Tenchu 2: Birth of the Stealth Assassins** (PlayStation, **US version, SLUS-00939**) that:

- **Runs gameplay at 60fps.** Game logic still runs at its original 30Hz, so the game speed, AI, physics and timing all stay as they were. A second frame is drawn between each pair of logic steps, with the camera, character positions and animation poses interpolated.
- **Raises the draw distance** to 2×, 3× or 4× the original, with the distance fog stretched to match, so far geometry fades in instead of popping in.
- **Keeps gameplay distances unchanged.** Enemy activation, AI vision, sound falloff and projectile range use the original values. Seeing further doesn't mean enemies see you sooner.
- **Fixes the PsyQ VSync timeout bug,** which makes cutscenes and menus run too fast when the emulated CPU is overclocked.

> This project contains no game data, BIOS or copyrighted assets. You need your own copy of the game.

## Requirements

| | |
|---|---|
| Game | Tenchu 2: Birth of the Stealth Assassins, **US** (SLUS-00939). Other versions are not supported; the patch checks the game code before touching anything, so on another version it simply does nothing. |
| Emulator | [DuckStation](https://github.com/stenzek/duckstation), a recent version |
| 8 MB RAM | **Required.** The patch code, its tables and the larger drawing buffers live in DuckStation's 8 MB RAM expansion. Without it the patch stays inactive (it will not crash the game, it just won't do anything). |
| CPU overclock | **Required for a stable 60fps.** Drawing twice per logic step plus the longer draw distance is a lot of extra work for the emulated PS1 CPU. See [Performance](#performance). |
| Host PC | A fast CPU. DuckStation's CPU emulation is the bottleneck at high overclock settings. |

## Installation

1. Download `cheats/SLUS-00939.cht` from this repository (or from the latest release).
2. Copy it into DuckStation's **`cheats`** folder:
   - Windows (default install): `Documents\DuckStation\cheats\`
   - Portable mode: the `cheats` folder next to `duckstation-qt-x64-ReleaseLTCG.exe`
   - Linux: `~/.local/share/duckstation/cheats/`
   - If you already have a cheat file for this game there (named `SLUS-00939_<hash>.cht`), DuckStation may load both. Remove or rename the old one to avoid duplicate entries.
3. In DuckStation, right-click the game → **Properties**, and set (exact labels vary a little between DuckStation versions):
   - **Console:** enable **8 MB RAM**.
   - **CPU:** enable **clock speed control / overclocking**, and set it as described under [Performance](#performance).
   - **Cheats:** enable cheats, then tick:
     - `60fps + draw distance (8MB RAM required)`
     - `VSync timeout fix`
     - **one** of `Draw distance 2x`, `Draw distance 3x` or `Draw distance 4x` (optional; with none ticked you get 60fps at the original distance).
   - Optional: untick **Load Database Cheats** if you don't want DuckStation's built-in cheat list mixed in.
4. Start the game. The patch activates when a mission loads.

## Options

| Cheat | What it does |
|---|---|
| `60fps + draw distance (8MB RAM required)` | The main patch. Required for everything else except the VSync fix. |
| `VSync timeout fix` | Cutscenes and menus play at the correct speed with an overclocked CPU. Works with or without the main patch. |
| `Draw distance 2x` / `3x` / `4x` | Render distance multiplier, with the fog stretched to match. **Enable only one.** |

How far you can see is limited by the game itself: it only keeps the level blocks around the camera in memory, about two blocks (32,000+ units) ahead. 2x already reaches that edge on most stages. Higher presets push the fog further out, so the furthest blocks are less fogged, and draw stage objects (props) further out: about 2x their original range with `2x`, and the 30,000-unit maximum with `3x` and `4x` on most stages.

## Performance

The extra frame and the longer draw distance are processed by the *emulated* PS1 CPU, so the overclock you need depends on the draw distance and the stage.

| Setting | CPU overclock needed for a stable 60fps |
|---|---|
| 60fps + Draw distance 4x | ~350% (tested on every stage) |
| 60fps + Draw distance 3x | TBD |
| 60fps + Draw distance 2x | TBD |
| 60fps, original distance | TBD |

If the frame rate drops in big outdoor areas, raise the overclock or pick a lower draw distance. Frame drops are always clean slowdowns. The game logic never runs faster than intended.

## Known limitations

- **DuckStation only,** because of the 8 MB RAM requirement. It does not run on real hardware or on emulators without an 8 MB RAM option.
- **Torches and other light/fire effects appear at their original distance**, because their animation and hazards are tied to it.
- **Fire, smoke and other stage effects animate at 30fps,** like the original. They are drawn at the interpolated camera position on every frame, but their animation only advances on logic steps.
- **The HUD, map screen and some particle effects** are re-shown from the previous logic step on the extra frame rather than redrawn.
- **Save states** made with the patch active contain the patched code. Load them with the same patch version.

## Troubleshooting

- **Nothing changes in game:** check that 8 MB RAM is enabled, that the main cheat is ticked, and that your disc is the US version (SLUS-00939).
- **Cutscenes play too fast:** enable `VSync timeout fix`.
- **The frame rate drops below 60:** raise the CPU overclock or lower the draw distance preset.
- **Duplicate cheat entries:** remove any other `SLUS-00939*.cht` file from the `cheats` folder.

## Building from source

The cheat file is generated by `tools/build_patch.py` (Python 3, no dependencies). It contains a small MIPS R3000 assembler, and the patch is written in it as Python calls.

```
python tools/build_patch.py --exe path/to/TENCHU2/GAME.EXE cheats/SLUS-00939
```

`GAME.EXE` comes from your own US disc: extract the disc with [mkpsxiso](https://github.com/Lameguy64/mkpsxiso) (`dumpsxiso`). The script checks its SHA-1 (`F6C70FFB2EF7564D1DBE4FF3AB4C1BF1321A081F`), because it copies a few original instructions to use as guards. It writes the `.cht`, the raw code (`.bin`), and a Lua copy of the patch used by `tools/timing_test.lua`, a PCSX-Redux test that compares game speed with and without the patch.

See [docs/TECHNICAL.md](docs/TECHNICAL.md) for how the patch works.

## License

[MIT](LICENSE) for the code in this repository. Tenchu is a trademark of its respective owners; this project is not affiliated with or endorsed by them.
