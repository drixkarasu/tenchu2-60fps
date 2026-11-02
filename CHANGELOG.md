# Changelog

## 1.0.0 (2026-11-01)

First public release (internal build B14).

- 60fps gameplay with 30Hz logic: camera, character position and animation pose interpolation; the HUD, map, tutorial text and particles are replayed on the extra frame.
- Draw distance presets 2x / 3x / 4x. Gameplay distances (AI, activation, sound, projectiles) stay at the original values.
- Distance fog stretched to the new draw distance.
- GPU packet buffers moved to the 8 MB area and enlarged (fixes polygon corruption at long distances).
- Stage logic (traps, moving objects, hazard damage, music fades, object sounds) runs once per logic step; fire, smoke, rain and water animate at the original speed.
- VSync timeout fix for overclocked CPUs (cutscene and menu speed).
- Every write is guarded: the patch does nothing without 8 MB RAM, or on game code it doesn't recognise.
