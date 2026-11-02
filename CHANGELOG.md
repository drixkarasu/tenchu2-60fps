# Changelog

## 1.1.0 (2026-11-02)

- Fog now reaches full density at about 32,000 units, the furthest the game reliably keeps level geometry around the camera (blocks within two grid cells ahead). Before, at 3x and 4x the fog ended far beyond the last drawable block, so distant scenery looked thin and the world edge showed.
- Stage objects (props, boats, crates and similar) are drawn out to their original range x the draw distance preset (capped at 30,000 units) instead of always popping in at the original range. Beyond the original range they are drawn only: no collision, and their logic (falling objects, object fire effects) keeps the original range.
- Torches and other light/fire effects still appear at their original range (their animation and hazards are tied to it).

## 1.0.0 (2026-11-01)

First public release (internal build B14).

- 60fps gameplay with 30Hz logic: camera, character position and animation pose interpolation; the HUD, map, tutorial text and particles are replayed on the extra frame.
- Draw distance presets 2x / 3x / 4x. Gameplay distances (AI, activation, sound, projectiles) stay at the original values.
- Distance fog stretched to the new draw distance.
- GPU packet buffers moved to the 8 MB area and enlarged (fixes polygon corruption at long distances).
- Stage logic (traps, moving objects, hazard damage, music fades, object sounds) runs once per logic step; fire, smoke, rain and water animate at the original speed.
- VSync timeout fix for overclocked CPUs (cutscene and menu speed).
- Every write is guarded: the patch does nothing without 8 MB RAM, or on game code it doesn't recognise.
