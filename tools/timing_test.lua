-- Tenchu 2 (US) 60fps patch: timing test for PCSX-Redux (developer tool)
--
-- Compares stock and patched game timing from the same starting point, with identical input:
--   1. snapshot the current state
--   2. STOCK pass:   settle, hold UP (walk forward) for HOLD_VBLANKS, release, settle
--   3. reload the snapshot, apply the patch from tools/SLUS-00939_patch.lua (made by tools/build_patch.py)
--   4. PATCHED pass: same input
--   5. write per-vblank CSVs + summary to tests/results/
--
-- Pass/fail metric: distance walked per game tick (independent of CPU speed; catches double updates).
-- Informational: game ticks per second and frames per second (PCSX-Redux has no CPU overclock, so the
-- patched pass may be CPU-limited below 60 fps; the summary says so when it happens).
--
-- How to run: get into a mission with the player standing on open ground, facing a clear path at least
-- 10 seconds of walking long. Set ROOT below to your clone of this repository, then in the Lua console:
--   dofile('C:/path/to/tenchu2-60fps/tools/timing_test.lua')
-- PCSX-Redux setup: 8 MB RAM ("8Megs") on, and run with the interpreter (-interpreter) so patched code isn't hidden
-- by the dynarec. Results go to tools/results/ (create the folder first).

local ROOT          = 'C:/path/to/tenchu2-60fps/'   -- <- change to your clone (forward slashes, trailing slash)
local OUT_DIR       = ROOT .. 'tools/results/'
local PATCH_FILE    = ROOT .. 'tools/SLUS-00939_patch.lua'
local SETTLE        = 60     -- vblanks before input
local HOLD_VBLANKS  = 600    -- 10 s of walking
local TAIL          = 60     -- vblanks after release
local TOLERANCE     = 0.01   -- 1 %
local WARMUP        = 60     -- vblanks of walking ignored for distance (acceleration from standstill)

-- game addresses (US GAME.EXE, see docs/TECHNICAL.md)
local TICK          = 0x8008CED4
local PLAYER        = 0x8008CE00
local BUFIDX        = 0x8008CEC4   -- current draw buffer (u16), changes on every flip

local ffi = require('ffi')
local mem = PCSX.getMemPtr()
local function off(a) return bit.band(a, 0x1FFFFF) end
local function r32(a) return ffi.cast('uint32_t*', mem + off(a))[0] end
local function s32(a) return ffi.cast('int32_t*',  mem + off(a))[0] end
local function r16(a) return ffi.cast('uint16_t*', mem + off(a))[0] end
local function w32(a, v) ffi.cast('uint32_t*', mem + off(a))[0] = v end

local patch = dofile(PATCH_FILE)
local pad = PCSX.SIO0.slots[1].pads[1]
local UP = PCSX.CONSTS.PAD.BUTTON.UP

local function game_loaded() return r16(patch.sig[1]) == patch.sig[2] end

local function flush_code_cache()
  if PCSX.invalidateCache then PCSX.invalidateCache() end   -- only if this build exposes it
end

local function apply_patch()
  for i, w in ipairs(patch.code) do w32(patch.base + (i - 1) * 4, w) end
  for _, h in ipairs(patch.hooks) do
    if r32(h[1]) == h[2] then w32(h[1], h[3]) end
  end
  flush_code_cache()
end

local function remove_patch()
  for _, h in ipairs(patch.hooks) do
    if r32(h[1]) == h[3] then w32(h[1], h[2]) end
  end
  flush_code_cache()
end

local function player_pos()
  local p = r32(PLAYER)
  if bit.rshift(p, 24) ~= 0x80 then return nil end
  local pos = r32(p + 0x2C)
  if bit.rshift(pos, 24) ~= 0x80 then return nil end
  return s32(pos), s32(pos + 4), s32(pos + 8)
end

-- ---------------------------------------------------------------- run state
local stamp = os.date('%Y%m%d_%H%M%S')
local snapshot
local passes = { 'stock', 'patched' }
local pass_i, v, rows, results = 1, 0, {}, {}
local diag = { hooks = 0, maxcap = 0 }

local function start_pass()
  v, rows = 0, {}
  -- the patch is (re)applied on the first vblanks of the pass, after the save state has really loaded
  print(string.format('[timing] %s pass started', passes[pass_i]))
end

local function summarise(name, rs)
  local hold0, hold1 = SETTLE + 1, SETTLE + HOLD_VBLANKS
  local meas0 = SETTLE + WARMUP + 1
  local flips, ticks, dist, steps, nsteps = 0, 0, 0, {}, 0
  for i = 2, #rs do
    local a, b = rs[i - 1], rs[i]
    if b.buf ~= a.buf then flips = flips + 1 end
    if i >= hold0 and i <= hold1 then
      local dt = b.tick - a.tick
      if dt ~= 0 then steps[dt] = (steps[dt] or 0) + 1 end
      ticks = ticks + dt
      if i >= meas0 then
        if dt ~= 0 then nsteps = nsteps + 1 end
        if a.x and b.x then
          local dx, dz = b.x - a.x, b.z - a.z
          dist = dist + math.sqrt(dx * dx + dz * dz)
        end
      end
    end
  end
  local secs = HOLD_VBLANKS / 60
  local s = {
    name = name,
    fps = flips / (#rs - 1) * 60,
    tps = ticks / secs,
    dist = dist,
    ticks = ticks,
    nsteps = nsteps,
    dist_per_step = nsteps > 0 and dist / nsteps or 0,
    steps = steps,
  }
  return s
end

local function write_csv(name, rs)
  local f = Support.File.open(OUT_DIR .. 'timing_' .. stamp .. '_' .. name .. '.csv', 'TRUNCATE')
  f:write('vblank,tick,buf,x,y,z,input\n')
  for i, r in ipairs(rs) do
    f:write(string.format('%d,%d,%d,%s,%s,%s,%d\n', i, r.tick, r.buf,
      tostring(r.x or ''), tostring(r.y or ''), tostring(r.z or ''), r.input))
  end
  f:close()
end

local function finish()
  local st, pt = results.stock, results.patched
  local lines = {}
  local function out(fmt, ...) local l = string.format(fmt, ...); print(l); lines[#lines + 1] = l end
  out('Tenchu 2 timing test %s', stamp)
  for _, s in ipairs({ st, pt }) do
    local sd = {}
    for k, n in pairs(s.steps) do sd[#sd + 1] = string.format('+%d x%d', k, n) end
    out('%-8s fps %.2f  ticks/s %.2f  steady walk %.0f units in %d logic steps = %.3f/step  tick steps: %s',
      s.name, s.fps, s.tps, s.dist, s.nsteps, s.dist_per_step, table.concat(sd, ' '))
  end
  local verdict = 'PASS'
  out('patch diagnostics: hooks installed %d/%d, camera hook ran: %s, most packets replayed in one frame: %d',
    diag.hooks, #patch.hooks, tostring(r32(patch.cam_valid) == 1), diag.maxcap)
  if st.dist_per_step <= 0 then
    verdict = 'INVALID (player did not move in the stock pass; face open ground and retry)'
  else
    local r = pt.dist_per_step / st.dist_per_step
    out('distance per logic step, patched / stock = %.4f (limit %.2f%%)', r, TOLERANCE * 100)
    if math.abs(r - 1) > TOLERANCE then verdict = 'FAIL (game logic moves a different amount per step)' end
    local rt = pt.tps / st.tps
    if pt.fps < 59 then
      out('ticks per second, patched / stock = %.4f  (patched pass CPU-limited at %.1f fps; real-time speed not judged)', rt, pt.fps)
    else
      out('ticks per second, patched / stock = %.4f', rt)
      if math.abs(rt - 1) > TOLERANCE and verdict == 'PASS' then verdict = 'FAIL (real-time speed differs)' end
    end
  end
  if diag.hooks < #patch.hooks then
    verdict = 'INVALID (patch hooks not installed: original instructions not found)'
  elseif r32(patch.cam_valid) ~= 1 then
    verdict = 'INVALID (hooks installed but patch code never ran: emulator code cache?)'
  end
  out('RESULT: %s', verdict)
  local f = Support.File.open(OUT_DIR .. 'timing_' .. stamp .. '_summary.txt', 'TRUNCATE')
  f:write(table.concat(lines, '\n') .. '\n'); f:close()
  pad.clearOverride(UP)
  _G.TENCHU_TIMING_LISTENER:remove()
  _G.TENCHU_TIMING_LISTENER = nil
end

local function on_vsync()
  v = v + 1
  if v <= 3 then
    if passes[pass_i] == 'patched' then
      if v == 1 then w32(patch.cam_valid, 0) end
      apply_patch()
      if v == 3 then
        diag.hooks = 0
        for _, h in ipairs(patch.hooks) do if r32(h[1]) == h[3] then diag.hooks = diag.hooks + 1 end end
      end
    else
      remove_patch()
    end
  end
  local input = 0
  if v == SETTLE + 1 then pad.setOverride(UP) end
  if v == SETTLE + HOLD_VBLANKS + 1 then pad.clearOverride(UP) end
  if v > SETTLE and v <= SETTLE + HOLD_VBLANKS then input = 1 end
  if passes[pass_i] == 'patched' then
    local c = r32(patch.cap_count)
    if c > diag.maxcap and c < 100000 then diag.maxcap = c end
  end
  local x, y, z = player_pos()
  rows[#rows + 1] = { tick = r32(TICK), buf = r16(BUFIDX), x = x, y = y, z = z, input = input }
  if v >= SETTLE + HOLD_VBLANKS + TAIL then
    local name = passes[pass_i]
    write_csv(name, rows)
    results[name] = summarise(name, rows)
    pass_i = pass_i + 1
    if pass_i > #passes then
      PCSX.nextTick(finish)
    else
      PCSX.nextTick(function()
        PCSX.pauseEmulator()
        PCSX.loadSaveState(snapshot)
        start_pass()
        PCSX.resumeEmulator()
      end)
    end
  end
end

-- ---------------------------------------------------------------- start
if not game_loaded() then
  print('[timing] GAME.EXE is not loaded: start a mission first')
  return
end
if _G.TENCHU_TIMING_LISTENER then _G.TENCHU_TIMING_LISTENER:remove() end
PCSX.pauseEmulator()
remove_patch()
snapshot = PCSX.createSaveState()
start_pass()
_G.TENCHU_TIMING_LISTENER = PCSX.Events.createEventListener('GPU::Vsync', on_vsync)
PCSX.resumeEmulator()
print('[timing] running: ~25 s total, do not touch the controller')
