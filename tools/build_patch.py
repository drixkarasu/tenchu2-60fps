r"""Tenchu 2: Birth of the Stealth Assassins (US, SLUS-00939) - 60fps + draw distance patch builder.

Assembles the patch (MIPS R3000, tiny built-in encoder) and writes:
  <out>.cht        DuckStation cheat file (release format, every write guarded)
  <out>.bin        raw patch code (loaded at 0x80600100, DuckStation 8 MB RAM area)
  <out>_patch.lua  the same patch as a Lua table for tools/timing_test.lua (PCSX-Redux)

Usage:  python build_patch.py [--exe path/to/GAME.EXE] [out_basename]
GAME.EXE is TENCHU2\GAME.EXE from your own US disc (extract it with mkpsxiso/dumpsxiso).
Default path: game/extracted/US/TENCHU2/GAME.EXE relative to the repository root, or $TENCHU2_GAME_EXE.

Internal build history: this is build "B17"; see docs/TECHNICAL.md.
"""
import struct, sys, os
_args = sys.argv[1:]
if '--exe' in _args:
    _i = _args.index('--exe'); EXE_PATH = _args[_i + 1]; del _args[_i:_i + 2]
else:
    EXE_PATH = os.environ.get('TENCHU2_GAME_EXE',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'game', 'extracted', 'US', 'TENCHU2', 'GAME.EXE'))
EXE = open(EXE_PATH, 'rb').read()
import hashlib
GAME_EXE_SHA1 = 'F6C70FFB2EF7564D1DBE4FF3AB4C1BF1321A081F'
if hashlib.sha1(EXE).hexdigest().upper() != GAME_EXE_SHA1:
    sys.exit('GAME.EXE does not match the US release (SHA-1 %s expected)' % GAME_EXE_SHA1)


R = {n:i for i,n in enumerate("zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra".split())}

# Game addresses (US GAME.EXE, see docs/TECHNICAL.md)
Camera_Update      = 0x80053AE8
Task_RunAll        = 0x8003A384
Frame_FlipAndWait  = 0x800171C8
Actor_DrawAll      = 0x8001C734   # = update pass + draw pass (see findings)
Actor_DrawPass     = 0x8001C79C   # second loop of Actor_DrawAll: draws the visible list only
Stage_Draw         = 0x8004B95C
HUD_DrawFirstPerson= 0x80055F18
HUD_DrawMain       = 0x80060A88
GsSetRefView2      = 0x800725D0
VIEW = 0x80092A48     # eye xyz, target xyz, rz (7 words)
TICK = 0x8008CED4
BASE = 0x80600100     # code: 8 MB area (game only knows 2 MB; its stack sits at the top of 8 MB)
STATE= 0x80608000     # CUR[7] @+0, PREV[7] @+0x20, VALID @+0x40
EIGHTMB_SIG = (0x80600082, 0x0000)  # 2 MB mirror would show the kernel's 0x3C1A here
Actor_Update       = 0x8001C9FC
ACTOR_LIST         = 0x800C1398   # master actor list; count = lh 0x372(gp)
TABLE              = 0x80610000   # 64 slots x 0x500 bytes (see slot layout below)
SLOT               = 0x500
MAXSLOT            = 64
MAXBONE            = 24
RotMatrixYXZ       = 0x8006EC80
RAND_SEED          = 0x800CEA20   # libc rand() state
DRAWDIST           = 0x8008CEC8   # game's distance variable: now the RENDER distance
DD_STOCK           = 0x80608200   # stock distance (stage loader writes here; gameplay reads here)
DD_FACTOR          = 0x80608204   # render = stock * factor / 4 (0 = 4 = 1x); set by preset cheats
FOG_K              = 0x80608208   # fog depth shift: band width = 256 << k (k = round(log2(factor/4)))
FOG_D              = 0x8060820C   # render distance the fog shift applies to (other D values: start kept)
Model_DrawPolys    = 0x80018DB0   # FUN_80018DB0: polygon packet builder with per-vertex fog
# every `srl tX,tX,n` that feeds a fog comparison (`subu tY,tX,s1`) in Model_DrawPolys' lit handlers
FOG_SITES = [  # t0-t3 per-vertex depths only. NOT the t6 polygon depths: t6 is reused as the ordering-table index (B10 bug)
             0x80019234,0x80019260,0x80019290,0x80019348,0x80019374,0x800193A4,0x800193D4,
             0x800194C4,0x80019510,0x80019564,0x800196DC,0x80019728,0x8001977C,0x800197D0,
             0x80019940,0x8001998C,0x800199E0,0x80019AF8,0x80019B44,0x80019B98,0x80019BEC]
FOG_S              = 0x80608210   # fog start in shifted units for the render distance
# lui/lw pairs redirected from DRAWDIST to DD_STOCK: (lui address, access address)
DD_REDIRECTS = [
    (0x8001DF88, 0x8001DF8C),  # Actor_ActivationManager: enemy activation radius
    (0x80063DEC, 0x80063DF0),  # Mission_MainLoop start: initial activation
    (0x8002F02C, 0x8002F030),  # FUN_8002ECD8: AI vision/awareness bands (0x800C2FB8)
    (0x8001E8F8, 0x8001E8FC),  # FUN_8001E858: sound volume falloff
    (0x800608D0, 0x800608D4),  # FUN_800603C8: sound volume falloff
    (0x8001B64C, 0x8001B650),  # FUN_8001B4F0: falloff value for objects set up at mission start
    (0x80059C24, 0x80059C28),  # FUN_80059A2C: projectile range
    (0x80047340, 0x80047344),  # stage loader writes
    (0x80048030, 0x80048034),
    (0x800492B0, 0x800492B4),
    (0x800492E4, 0x800492E8),  # area bonus read-modify-write
    (0x80049318, 0x8004931C),
    (0x80049334, 0x80049338),
]
Tutorial_Run       = 0x800CFCBC   # per-stage module call (tutorial on stage 0)
WORKBASE           = 0x800CD430   # libgs GsOUT_PACKET_P
CUR_OT             = 0x8008CECC   # -> current GsOT {len, org, offset, point, tag}
PKT_START          = 0x8008CED0   # start of current packet buffer
EXTRA              = 0x80608050   # B14: 1 while the extra (draw-only) frame runs Stage_Draw
OT_LEN             = 13           # B16: 8192-entry ordering tables (stock: 11 = 2048, overflowed past depth 32768)
OT0_ORG            = 0x806E0000   # B16: OT 0 (0x8000 bytes + 0x8000 spare)
OT1_ORG            = 0x806F0000   # B16: OT 1
GSOT               = 0x80092A20   # the game's two GsOT headers (0x14 bytes each)
GsClearOt          = 0x80071FC0
SKY_D              = 0x7FF        # Stage_Draw sets D to this while it draws the sky (0x8004BA18)
SKY_BIAS           = 0x1000       # B16: sky sorted 4096 entries further back than anything else
FARF               = 0x80608054   # B15: current stage object is beyond the stock range (draw only, no collision)
PROP_CAP           = 30000        # B15: max stage-object draw range (object offsets are 16-bit in FUN_8004E35C)
LSAVE              = 0x80638000   # B14: saved light/effect counters (+0x14, 0x18-byte entries)
OSAVE              = 0x80639000   # B14: saved stage-object counters (+0x6A, 0x78-byte entries)
PKT_BASE           = 0x80640000   # B13: 2 packet buffers (stock: 2 x 0x14000 at 0x80096AE8, the 2nd one ends at
PKT_SIZE           = 0x50000      #      the big-model vertex cache 0x800BEAE8 and overflows into it/the other buffer)
CAPBUF             = 0x80630000   # captured (bucket, prim) pairs
MAXCAP             = 4096
CAPST              = 0x80608100   # +0 count, +4 workbase before actor draw pass, +8 workbase after Stage_Draw
HCNT_PTR           = 0x8008472C   # pointer to root counter 1 (hblank) value
LAST_HCNT          = 0x80084730
VCOUNT             = 0x80085860
LAST_VCNT          = 0x80084734
ACTOR_SNAP         = 0x1000
GAME_SIG = (0x8006454A, 0x2404)  # upper half of `li a0,2` in Mission_MainLoop: GAME.EXE is loaded
SNAP_LIMIT = 0x1000   # camera move per logic frame above this = cut, no blending

class Asm:
    def __init__(s, org): s.org=org; s.items=[]; s.labels={}
    def pc(s): return s.org+4*len(s.items)
    def L(s,name): s.labels[name]=s.pc()
    def emit(s,f): s.items.append(f)
    def I(s,op,rs,rt,imm): s.emit(lambda pc:(op<<26)|(R[rs]<<21)|(R[rt]<<16)|(imm&0xffff))
    def Rr(s,rs,rt,rd,sh,fn): s.emit(lambda pc:(R[rs]<<21)|(R[rt]<<16)|(R[rd]<<11)|(sh<<6)|fn)
    def addiu(s,rt,rs,imm): s.I(9,rs,rt,imm)
    def slti(s,rt,rs,imm): s.I(10,rs,rt,imm)
    def andi(s,rt,rs,imm): s.I(12,rs,rt,imm)
    def ori(s,rt,rs,imm): s.I(13,rs,rt,imm)
    def lui(s,rt,imm): s.I(15,'zero',rt,imm)
    def lh(s,rt,off,rs): s.I(0x21,rs,rt,off)
    def sh(s,rt,off,rs): s.I(0x29,rs,rt,off)
    def lw(s,rt,off,rs): s.I(0x23,rs,rt,off)
    def sw(s,rt,off,rs): s.I(0x2b,rs,rt,off)
    def slt(s,rd,rs,rt): s.Rr(rs,rt,rd,0,0x2a)
    def and_(s,rd,rs,rt): s.Rr(rs,rt,rd,0,0x24)
    def or_(s,rd,rs,rt): s.Rr(rs,rt,rd,0,0x25)
    def sltu(s,rd,rs,rt): s.Rr(rs,rt,rd,0,0x2b)
    def srl(s,rd,rt,sh): s.Rr('zero',rt,rd,sh,2)
    def bgtz(s,rs,l): s.emit(lambda pc:(7<<26)|(R[rs]<<21)|(((s.labels[l]-pc-4)>>2)&0xffff))
    def blez(s,rs,l): s.emit(lambda pc:(6<<26)|(R[rs]<<21)|(((s.labels[l]-pc-4)>>2)&0xffff))
    def mult(s,rs,rt): s.Rr(rs,rt,'zero',0,0x18)
    def mflo(s,rd): s.Rr('zero','zero',rd,0,0x12)
    def addu(s,rd,rs,rt): s.Rr(rs,rt,rd,0,0x21)
    def subu(s,rd,rs,rt): s.Rr(rs,rt,rd,0,0x23)
    def move(s,rd,rs): s.addu(rd,rs,'zero')
    def sll(s,rd,rt,sh): s.Rr('zero',rt,rd,sh,0)
    def sra(s,rd,rt,sh): s.Rr('zero',rt,rd,sh,3)
    def jr(s,rs): s.Rr(rs,'zero','zero',0,8)
    def srlv(s,rd,rt,rs): s.Rr(rs,rt,rd,0,6)
    def srav(s,rd,rt,rs): s.Rr(rs,rt,rd,0,7)
    def sllv(s,rd,rt,rs): s.Rr(rs,rt,rd,0,4)
    def word(s,w): s.emit(lambda pc,w=w:w)
    def xori(s,rt,rs,imm): s.I(14,rs,rt,imm)
    def la_l(s,r,lbl):   # la of a label (resolved at the end)
        s.emit(lambda pc:(15<<26)|(R[r]<<16)|(((s.labels[lbl]+0x8000)>>16)&0xffff))
        s.emit(lambda pc:(9<<26)|(R[r]<<21)|(R[r]<<16)|(s.labels[lbl]&0xffff))
    def jalr(s,rd,rs): s.Rr(rs,'zero',rd,0,9)
    def nop(s): s.emit(lambda pc:0)
    def jal(s,t): s.emit(lambda pc:(3<<26)|((t&0x0fffffff)>>2))
    def jal_l(s,lbl): s.emit(lambda pc:(3<<26)|((s.labels[lbl]&0x0fffffff)>>2))
    def j_abs(s,t): s.emit(lambda pc:(2<<26)|((t&0x0fffffff)>>2))
    def j(s,lbl): s.emit(lambda pc:(2<<26)|((s.labels[lbl]&0x0fffffff)>>2))
    def br(s,op,rs,rt,lbl): s.emit(lambda pc:(op<<26)|(R[rs]<<21)|(R[rt]<<16)|(((s.labels[lbl]-pc-4)>>2)&0xffff))
    def beq_(s,rs,rt,l): s.br(4,rs,rt,l)
    def bne(s,rs,rt,l): s.br(5,rs,rt,l)
    def b(s,l): s.br(4,'zero','zero',l)
    def beqz(s,rs,l): s.br(4,rs,'zero',l)
    def bnez(s,rs,l): s.br(5,rs,'zero',l)
    def bgez(s,rs,l): s.emit(lambda pc:(1<<26)|(R[rs]<<21)|(1<<16)|(((s.labels[l]-pc-4)>>2)&0xffff))
    def la(s,r,addr):
        hi=(addr+0x8000)>>16; lo=addr&0xffff
        s.lui(r,hi&0xffff); s.addiu(r,r,lo if lo<0x8000 else lo-0x10000)
    def copy7(s,src,dst,tag):  # copies 7 words src->dst, clobbers t3,t5,t6,t7
        s.addiu('t5','zero',7); s.move('t6',src); s.move('t7',dst)
        s.L(tag); s.lw('t3',0,'t6'); s.addiu('t6','t6',4); s.addiu('t5','t5',-1)
        s.sw('t3',0,'t7'); s.bnez('t5',tag); s.addiu('t7','t7',4)
    def words(s): return [f(s.org+4*i) & 0xffffffff for i,f in enumerate(s.items)]

a = Asm(BASE)
# ---- B1_CamHook: replaces `jal Camera_Update` in Mission_MainLoop ----
a.L('B1_CamHook')
a.addiu('sp','sp',-24); a.sw('ra',20,'sp')
# B16: bigger ordering tables in 8 MB. GAME.EXE's init is patched too; this catches an init that ran before the cheat applied
a.lui('t0',GSOT>>16); a.lw('t1',GSOT&0xFFFF,'t0'); a.nop(); a.addiu('t2','zero',OT_LEN)
a.beq_('t1','t2','ot_ok'); a.nop()
a.sw('t2',(GSOT&0xFFFF),'t0'); a.sw('t2',(GSOT&0xFFFF)+0x14,'t0')
a.lui('t1',OT0_ORG>>16); a.sw('t1',(GSOT&0xFFFF)+4,'t0'); a.lui('t1',OT1_ORG>>16); a.sw('t1',(GSOT&0xFFFF)+0x18,'t0')
a.move('a0','zero'); a.move('a1','zero'); a.jal(GsClearOt); a.addiu('a2','t0',GSOT&0xFFFF)
a.lui('a2',GSOT>>16); a.move('a0','zero'); a.move('a1','zero'); a.jal(GsClearOt); a.addiu('a2','a2',(GSOT&0xFFFF)+0x14)
a.L('ot_ok')
# draw distance: render = stock * factor / 4 (only once the stage loader has set a stock value)
a.la('t0',DD_STOCK); a.lw('t1',0,'t0'); a.lw('t2',4,'t0'); a.nop()
a.bnez('t1','dd_have'); a.nop()
a.lui('t4',0x8009); a.lw('t1',DRAWDIST-0x80090000,'t4'); a.nop()   # no stock value yet (patched after the stage loaded):
a.beqz('t1','dd_skip'); a.nop(); a.sw('t1',0,'t0')                  # the game's current value is still stock
a.L('dd_have')
a.bnez('t2','dd_fac'); a.nop(); a.addiu('t2','zero',4)
a.L('dd_fac'); a.mult('t1','t2'); a.mflo('t3'); a.sra('t3','t3',2)
a.lui('t4',0x8009); a.sw('t3',DRAWDIST-0x80090000,'t4')
# B11 fog: start S = stock D - 256 (as stock), black by the new D: k = floor(log2((Dnew - S) / 256))
a.sw('t3',FOG_D-DD_STOCK,'t0')
a.addiu('t5','t1',-0x100); a.subu('t6','t3','t5'); a.srl('t6','t6',9); a.move('t8','zero')
a.L('k_l'); a.beqz('t6','k_d'); a.nop(); a.srl('t6','t6',1); a.b('k_l'); a.addiu('t8','t8',1)
a.L('k_d')
a.sw('t8',FOG_K-DD_STOCK,'t0')
a.srav('t5','t5','t8'); a.sw('t5',FOG_S-DD_STOCK,'t0')
a.sll('t8','t8',6)                                   # shift-amount field delta
a.lui('t9',0xFFFF); a.ori('t9','t9',0xF83F)          # mask without the shift-amount field
a.la_l('t5','FOGTAB')
a.addiu('t6','zero',len(FOG_SITES))
a.L('fog_l')
a.lw('a0',0,'t5'); a.lw('a1',4,'t5'); a.nop()
a.lw('a2',0,'a0'); a.addu('a3','a1','t8')
a.and_('v0','a1','t9'); a.and_('v1','a2','t9')
a.bne('v1','v0','fog_n'); a.nop()                    # not the expected instruction: leave it
a.beq_('a2','a3','fog_n'); a.nop()
a.sw('a3',0,'a0')
a.L('fog_n')
a.addiu('t6','t6',-1); a.bnez('t6','fog_l'); a.addiu('t5','t5',8)
a.L('dd_skip')
a.jal(Camera_Update); a.nop()
a.la('t0',VIEW); a.la('t1',STATE)
a.copy7('t0','t1','c1')                         # CUR = VIEW
a.lw('t4',0x40,'t1'); a.nop()
a.beqz('t4','snap'); a.nop()                    # no valid PREV yet
a.addiu('t5','zero',6); a.move('t6','t1'); a.addiu('t7','t1',0x20)
a.L('c2'); a.lw('t3',0,'t6'); a.lw('t4',0,'t7'); a.addiu('t6','t6',4)
a.subu('t3','t3','t4'); a.bgez('t3','pos'); a.addiu('t7','t7',4)
a.subu('t3','zero','t3')
a.L('pos'); a.slti('t2','t3',SNAP_LIMIT); a.beqz('t2','snap'); a.addiu('t5','t5',-1)
a.bnez('t5','c2'); a.nop()
a.j('mid'); a.nop()
a.L('snap'); a.addiu('t2','t1',0x20); a.copy7('t1','t2','c3')   # PREV = CUR (camera cut)
a.addiu('t4','zero',1); a.sw('t4',0x40,'t1')
a.L('mid'); a.addiu('t5','zero',7); a.move('t6','t1'); a.addiu('t7','t1',0x20); a.move('t2','t0')
a.L('c4'); a.lw('t3',0,'t6'); a.lw('t4',0,'t7'); a.addiu('t6','t6',4); a.addiu('t7','t7',4)
a.addu('t3','t3','t4'); a.sra('t3','t3',1); a.addiu('t5','t5',-1); a.sw('t3',0,'t2')
a.bnez('t5','c4'); a.addiu('t2','t2',4)         # VIEW = (PREV+CUR)/2
a.jal(GsSetRefView2); a.move('a0','t0')
a.lw('ra',20,'sp'); a.nop(); a.jr('ra'); a.addiu('sp','sp',24)

# ---- B1_PreLogic: replaces `jal Task_RunAll` (restore the real camera before game logic) ----
a.L('B1_PreLogic')
a.addiu('sp','sp',-24); a.sw('ra',20,'sp')
a.la('t0',VIEW); a.la('t1',STATE)
a.copy7('t1','t0','c5')                         # VIEW = CUR
a.jal(GsSetRefView2); a.move('a0','t0')
a.jal(Task_RunAll); a.nop()
a.lw('ra',20,'sp'); a.nop(); a.jr('ra'); a.addiu('sp','sp',24)

# ---- B1_Flip: replaces `jal Frame_FlipAndWait(2)` ----
a.L('B1_Flip')
a.addiu('sp','sp',-32); a.sw('ra',28,'sp'); a.sw('s0',24,'sp')
a.jal_l('B4_Capture'); a.nop()                            # frame is complete: capture everything to replay (incl. map)
a.jal_l('B3_Flip0'); a.nop()                              # show the blended frame
a.lui('a0',0x8009); a.jal(GsSetRefView2); a.addiu('a0','a0',0x2A48)
a.jal_l('B1_ActorDrawOnly'); a.nop()           # draw the extra frame at the real camera (no actor update)
a.lui('t0',0x8009); a.lw('t1',-0x312C,'t0'); a.nop(); a.sw('t1',16,'sp')     # save tick
a.ori('t1','t1',1); a.sw('t1',-0x312C,'t0')                                  # odd tick: sky spin (even ticks only) skips this frame
a.lui('t2',0x800D); a.lw('t3',RAND_SEED-0x800D0000,'t2'); a.nop(); a.sw('t3',20,'sp')   # save rand() seed
a.la('t0',EXTRA); a.addiu('t1','zero',1); a.sw('t1',0,'t0')                  # B14: logic in Stage_Draw is gated on this
a.jal(Stage_Draw); a.nop()
a.la('t0',EXTRA); a.sw('zero',0,'t0')
a.lui('t0',0x8009); a.lw('t1',16,'sp'); a.nop(); a.sw('t1',-0x312C,'t0')     # restore tick
a.lui('t2',0x800D); a.lw('t3',20,'sp'); a.nop(); a.sw('t3',RAND_SEED-0x800D0000,'t2')   # restore seed
a.jal_l('B4_Replay'); a.nop()                              # HUD, map, effects, tutorial: replayed, not re-run
a.lui('t0',0x8009); a.lw('s0',-0x312C,'t0')     # save tick
a.jal_l('B3_Flip0'); a.nop()                              # show the extra frame
a.lui('t0',0x8009); a.sw('s0',-0x312C,'t0')            # extra frame does not advance the game clock
a.la('t0',VIEW); a.la('t1',STATE+0x20)
a.copy7('t0','t1','c6')                                 # PREV = VIEW
a.lw('ra',28,'sp'); a.lw('s0',24,'sp'); a.jr('ra'); a.addiu('sp','sp',32)

# ---- B1_ActorDrawOnly: same prologue as Actor_DrawAll, then jump into its draw pass ----
a.L('B1_ActorDrawOnly')
a.addiu('sp','sp',-0x48)
for reg,off in (('s5',0x34),('ra',0x44),('fp',0x40),('s7',0x3c),('s6',0x38),('s4',0x30),('s3',0x2c),('s2',0x28),('s1',0x24),('s0',0x20)):
    a.sw(reg,off,'sp')
a.j_abs(Actor_DrawPass); a.nop()   # its epilogue restores everything and returns to our caller

# ---- B3_Flip0: Frame_FlipAndWait(0), then reset the 'last vblank' timestamps (fixes the stock catch-up bug) ----
a.L('B3_Flip0')
a.addiu('sp','sp',-24); a.sw('ra',20,'sp')
a.jal(Frame_FlipAndWait); a.addiu('a0','zero',0)
a.lui('t0',0x8008); a.lw('t1',HCNT_PTR-0x80080000,'t0'); a.nop()
a.L('rdh'); a.lw('t2',0,'t1'); a.lw('t3',0,'t1'); a.nop(); a.bne('t2','t3','rdh'); a.nop()
a.sw('t2',LAST_HCNT-0x80080000,'t0')
a.lw('t4',VCOUNT-0x80080000,'t0'); a.nop(); a.sw('t4',LAST_VCNT-0x80080000,'t0')
a.lw('ra',20,'sp'); a.nop(); a.jr('ra'); a.addiu('sp','sp',24)

# ---- B3_ActorHook: replaces `jal Actor_UpdateAndDrawAll` ----
# slot layout (0x500): +0 actor, +4 model, +0x10 rootT prev, +0x1C rootT cur, +0x28 hipT prev, +0x34 hipT cur,
#   +0x40 angles prev[25] (8 B each), +0x108 angles cur[25], +0x1D0 angles mid[25], +0x298 saved matrices[25] (20 B each)
# block k (0 = root, 1.. = bones) lives at model+4+k*0x58: flg +0, matrix +4, t +0x18, angles +0x50
a.L('B3_ActorHook')
a.addiu('sp','sp',-48)
for reg,off in (('ra',44),('s0',40),('s1',36),('s2',32),('s3',28),('s4',24),('s5',20),('s6',16),('s7',12)): a.sw(reg,off,'sp')
a.lh('s1',0x372,'gp'); a.sh('zero',0x36E,'gp')
a.addiu('s0','zero',0); a.la('s2',ACTOR_LIST)
a.L('p1'); a.slt('t0','s0','s1'); a.beqz('t0','p1done'); a.nop()
a.lw('a0',0,'s2'); a.jal(Actor_Update); a.addiu('s2','s2',4)
a.b('p1'); a.addiu('s0','s0',1)
a.L('p1done')

def slot_loop(tag, body):
    a.addiu('s0','zero',0); a.la('s2',ACTOR_LIST); a.la('s3',TABLE)
    a.L(tag); a.slt('t0','s0','s1'); a.beqz('t0',tag+'done'); a.slti('t0','s0',MAXSLOT); a.beqz('t0',tag+'done'); a.nop()
    a.lw('t1',0,'s2'); a.nop(); a.beqz('t1',tag+'next'); a.nop()
    a.lw('s4',0x60,'t1'); a.nop(); a.beqz('s4',tag+'next'); a.nop()
    a.lw('t0',0,'s4'); a.nop(); a.lh('s5',6,'t0'); a.nop()           # bone count
    a.slti('t0','s5',MAXBONE+1); a.bnez('t0',tag+'nbok'); a.nop(); a.addiu('s5','zero',MAXBONE)
    a.L(tag+'nbok'); a.addiu('s5','s5',1)                              # blocks = bones + root
    body(tag)
    a.L(tag+'next'); a.addiu('s2','s2',4); a.addiu('s3','s3',SLOT); a.b(tag); a.addiu('s0','s0',1)
    a.L(tag+'done')

def k_loop(tag, body):   # s6 = k, s7 = block ptr
    a.addiu('s6','zero',0); a.addiu('s7','s4',4)
    a.L(tag); body(tag)
    a.addiu('s6','s6',1); a.slt('t0','s6','s5'); a.bnez('t0',tag); a.addiu('s7','s7',0x58)

def angptr(r):  # r = s3 + 0x40 + k*8
    a.sll(r,'s6',3); a.addu(r,r,'s3'); a.addiu(r,r,0x40)
def matptr(r):  # r = s3 + 0x298 + k*20
    a.sll(r,'s6',4); a.sll('t0','s6',2); a.addu(r,r,'t0'); a.addu(r,r,'s3'); a.addiu(r,r,0x298)

def capture(tag):
    # translations: root (block0 t) and hip (block1 t, only if a bone exists)
    a.lw('t1',0,'s2'); a.nop()
    for prev,cur,src in ((0x10,0x1C,0x1C),):
        for c in range(3):
            a.lw('t3',cur+4*c,'s3'); a.lw('t4',src+4*c,'s4'); a.sw('t3',prev+4*c,'s3'); a.sw('t4',cur+4*c,'s3')
    a.slti('t0','s5',2); a.bnez('t0',tag+'nohip'); a.nop()
    for c in range(3):
        a.lw('t3',0x34+4*c,'s3'); a.lw('t4',0x74+4*c,'s4'); a.sw('t3',0x28+4*c,'s3'); a.sw('t4',0x34+4*c,'s3')
    a.L(tag+'nohip')
    def cap_k(t):
        angptr('t8'); matptr('t9')
        a.lw('t3',0xC8,'t8'); a.lw('t4',0xCC,'t8'); a.sw('t3',0,'t8'); a.sw('t4',4,'t8')          # prev = cur
        a.lw('t3',0x50,'s7'); a.lw('t4',0x54,'s7'); a.sw('t3',0xC8,'t8'); a.sw('t4',0xCC,'t8')    # cur = block angles
        for w in range(5):
            a.lw('t3',4+4*w,'s7'); a.nop(); a.sw('t3',4*w,'t9')                                     # save matrix
    k_loop(tag+'k', cap_k)
    # snap if slot changed owner/model or root jumped
    a.lw('t1',0,'s2'); a.lw('t6',0,'s3'); a.nop(); a.bne('t6','t1',tag+'snap'); a.nop()
    a.lw('t6',4,'s3'); a.nop(); a.bne('t6','s4',tag+'snap'); a.nop()
    for c in range(3):
        a.lw('t3',0x1C+4*c,'s3'); a.lw('t4',0x10+4*c,'s3'); a.nop(); a.subu('t7','t3','t4')
        a.bgez('t7',tag+'ab%d'%c); a.nop(); a.subu('t7','zero','t7')
        a.L(tag+'ab%d'%c); a.slti('t7','t7',ACTOR_SNAP); a.beqz('t7',tag+'snap'); a.nop()
    a.b(tag+'mid'); a.nop()
    a.L(tag+'snap')
    a.sw('t1',0,'s3'); a.sw('s4',4,'s3')
    for c in range(6):
        a.lw('t3',0x1C+4*c if c<3 else 0x34+4*(c-3),'s3'); a.nop(); a.sw('t3',0x10+4*c if c<3 else 0x28+4*(c-3),'s3')
    def snap_k(t):
        angptr('t8'); a.lw('t3',0xC8,'t8'); a.lw('t4',0xCC,'t8'); a.sw('t3',0,'t8'); a.sw('t4',4,'t8')
    k_loop(tag+'sk', snap_k)
    a.L(tag+'mid')
    # blended translations
    for c in range(3):
        a.lw('t3',0x10+4*c,'s3'); a.lw('t4',0x1C+4*c,'s3'); a.nop(); a.addu('t3','t3','t4'); a.sra('t3','t3',1); a.sw('t3',0x1C+4*c,'s4')
    a.slti('t0','s5',2); a.bnez('t0',tag+'nohip2'); a.nop()
    for c in range(3):
        a.lw('t3',0x28+4*c,'s3'); a.lw('t4',0x34+4*c,'s3'); a.nop(); a.addu('t3','t3','t4'); a.sra('t3','t3',1); a.sw('t3',0x74+4*c,'s4')
    a.L(tag+'nohip2')
    def mid_k(t):
        angptr('t8')
        for c in range(3):
            a.lh('t3',0xC8+2*c,'t8'); a.lh('t4',2*c,'t8'); a.nop()
            a.subu('t5','t3','t4'); a.addiu('t5','t5',2048); a.andi('t5','t5',4095); a.addiu('t5','t5',-2048)
            a.sra('t5','t5',1); a.addu('t5','t4','t5'); a.sh('t5',0x190+2*c,'t8')
        a.addiu('a0','t8',0x190); a.jal(RotMatrixYXZ); a.addiu('a1','s7',4)
        a.sw('zero',0,'s7')                                                # flg = 0
    k_loop(tag+'mk', mid_k)

def restore(tag):
    for c in range(3):
        a.lw('t3',0x1C+4*c,'s3'); a.nop(); a.sw('t3',0x1C+4*c,'s4')
    a.slti('t0','s5',2); a.bnez('t0',tag+'nohip'); a.nop()
    for c in range(3):
        a.lw('t3',0x34+4*c,'s3'); a.nop(); a.sw('t3',0x74+4*c,'s4')
    a.L(tag+'nohip')
    def res_k(t):
        matptr('t9')
        for w in range(5):
            a.lw('t3',4*w,'t9'); a.nop(); a.sw('t3',4+4*w,'s7')
        a.sw('zero',0,'s7')
    k_loop(tag+'k', res_k)

slot_loop('cap', capture)
a.lui('t1',0x800D); a.lw('t1',WORKBASE-0x800D0000,'t1'); a.la('t0',CAPST); a.sw('t1',4,'t0')   # replay range 1 ends here
a.jal_l('B1_ActorDrawOnly'); a.nop()                     # draw at blended positions/poses
slot_loop('res', restore)
for reg,off in (('ra',44),('s0',40),('s1',36),('s2',32),('s3',28),('s4',24),('s5',20),('s6',16),('s7',12)): a.lw(reg,off,'sp')
a.jr('ra'); a.addiu('sp','sp',48)

# ---- B5_StageHook: replaces `jal Stage_Draw` in the loop; replay range 2 starts after it ----
a.L('B5_StageHook')
a.addiu('sp','sp',-24); a.sw('ra',20,'sp')
a.jal(Stage_Draw); a.nop()
a.lui('t1',0x800D); a.lw('t1',WORKBASE-0x800D0000,'t1'); a.la('t0',CAPST); a.sw('t1',8,'t0')
a.lw('ra',20,'sp'); a.nop(); a.jr('ra'); a.addiu('sp','sp',24)

# ---- B4_Capture: walk the current OT, record packets allocated in [p0, p1) with their bucket ----
a.L('B4_Capture')
a.la('t0',CAPST)
a.lui('t1',0x800D); a.lw('t1',WORKBASE-0x800D0000,'t1')         # p1
a.lw('t2',8,'t0')                                                  # range 2 start (after Stage_Draw)
a.nop()
a.lui('t3',0x8009); a.lw('t3',CUR_OT-0x80090000,'t3'); a.nop()
a.lw('t4',4,'t3'); a.lw('t5',16,'t3'); a.nop()                     # org, tag
a.lw('t6',0,'t3'); a.addiu('a0','zero',4); a.nop()
a.sllv('t6','a0','t6'); a.addu('t6','t4','t6')                     # org end = org + 4 << length (B16+: 8192 entries)
a.la('t7',CAPBUF); a.addiu('t8','zero',0); a.addiu('t9','zero',0)
a.lui('v1',4)                                                       # step guard (0x40000: OT entries + packets)
a.L('wl')
a.sltu('v0','t5','t4'); a.bnez('v0','notot'); a.nop()
a.sltu('v0','t5','t6'); a.beqz('v0','notot'); a.nop()
a.subu('t9','t5','t4'); a.srl('t9','t9',2); a.b('wnext'); a.nop()  # OT entry: new bucket
a.L('notot')
a.sltu('v0','t5','t2'); a.bnez('v0','tryr1'); a.nop()
a.sltu('v0','t5','t1'); a.bnez('v0','keep'); a.nop()
a.L('tryr1')
a.lui('a0',0x8009); a.lw('a0',PKT_START-0x80090000,'a0'); a.lw('a1',4,'t0'); a.nop()
a.sltu('v0','t5','a0'); a.bnez('v0','wnext'); a.nop()
a.sltu('v0','t5','a1'); a.beqz('v0','wnext'); a.nop()
a.L('keep')
a.slti('v0','t8',MAXCAP); a.beqz('v0','wnext'); a.nop()
a.sw('t9',0,'t7'); a.sw('t5',4,'t7'); a.addiu('t7','t7',8); a.addiu('t8','t8',1)
a.L('wnext')
a.lw('a0',0,'t5'); a.addiu('v1','v1',-1); a.beqz('v1','wdone'); a.nop()
a.lui('a1',0x00FF); a.ori('a1','a1',0xFFFF); a.and_('a2','a0','a1'); a.beq_('a2','a1','wdone'); a.nop()
a.lui('a3',0x8000); a.or_('t5','a2','a3'); a.b('wl'); a.nop()
a.L('wdone'); a.jr('ra'); a.sw('t8',0,'t0')

# ---- B4_Replay: copy captured packets into the current buffer and link them into the same buckets ----
a.L('B4_Replay')
a.la('t0',CAPST); a.lw('t8',0,'t0'); a.nop(); a.blez('t8','rdone'); a.nop()
a.lui('t1',0x800D); a.lw('t1',WORKBASE-0x800D0000,'t1')           # base
a.lui('t2',0x8009); a.lw('t2',PKT_START-0x80090000,'t2')           # packet buffer start
a.lui('t3',0x8009); a.lw('t3',CUR_OT-0x80090000,'t3'); a.nop()
a.lw('t3',4,'t3')                                                  # org
a.lui('a3',(PKT_SIZE-0x800)>>16); a.ori('a3','a3',(PKT_SIZE-0x800)&0xFFFF); a.addu('t2','t2','a3')    # limit = start + size - 0x800
a.la('t7',CAPBUF); a.sll('a0','t8',3); a.addu('t7','t7','a0')
a.L('rl')
a.addiu('t7','t7',-8); a.lw('t9',0,'t7'); a.lw('t5',4,'t7'); a.nop()
a.lw('t6',0,'t5'); a.nop()
a.srl('a0','t6',24); a.addiu('a1','a0',1); a.sll('a2','a1',2)     # len, words, bytes
a.addu('a3','t1','a2'); a.sltu('v0','t2','a3'); a.bnez('v0','rexit'); a.nop()
a.addiu('v1','zero',1)
a.L('cl'); a.slt('v0','v1','a1'); a.beqz('v0','cdone'); a.nop()
a.sll('a3','v1',2); a.addu('v0','t5','a3'); a.lw('v0',0,'v0'); a.addu('a3','t1','a3'); a.sw('v0',0,'a3')
a.b('cl'); a.addiu('v1','v1',1)
a.L('cdone')
a.sll('a3','t9',2); a.addu('a3','t3','a3'); a.lw('v0',0,'a3')     # OT entry
a.lui('v1',0x00FF); a.ori('v1','v1',0xFFFF)
a.and_('v0','v0','v1'); a.sll('a0','a0',24); a.or_('v0','v0','a0'); a.sw('v0',0,'t1')   # new tag -> old head
a.lw('v0',0,'a3'); a.lui('a0',0xFF00); a.and_('v0','v0','a0'); a.and_('t6','t1','v1'); a.or_('v0','v0','t6'); a.sw('v0',0,'a3')  # head -> new
a.addu('t1','t1','a2'); a.addiu('t8','t8',-1); a.bgtz('t8','rl'); a.nop()
a.L('rexit'); a.lui('t0',0x800D); a.sw('t1',WORKBASE-0x800D0000,'t0')
a.la('t0',CAPST); a.sw('zero',0,'t0')                              # one replay per capture
a.L('rdone'); a.jr('ra'); a.nop()

# ---- B10_FogStart: called from Model_DrawPolys' prologue with jalr t3 (leaf function: ra is live) ----
# in: s2 = draw distance; out: s1 = fog start in the shifted depth units; clobbers t4-t6
a.L('B10_FogStart')
# out: s1 = fog start in shifted units; s2 = the same start in unshifted units, ((s1+1)<<k)-1, for the
# per-polygon early-out compares (their t6 depth is also the OT index, so it can't be shifted)
FHI=(FOG_K+0x8000)>>16
a.lui('t4',FHI); a.lw('t5',FOG_K-(FHI<<16),'t4'); a.lw('t6',FOG_D-(FHI<<16),'t4'); a.nop()
a.bne('t6','s2','fs_other'); a.nop()
a.lw('s1',FOG_S-(FHI<<16),'t4'); a.b('fs_fin'); a.nop()     # render distance: precomputed start
a.L('fs_other')
a.addiu('s1','s2',-0x100); a.srav('s1','s1','t5')             # any other D (e.g. 0x7FF override): same start
a.addiu('t6','zero',SKY_D); a.bne('s2','t6','fs_fin'); a.nop()
a.addiu('t2','t2',SKY_BIAS)                                    # B16: sky -> behind everything (t2 = OT bias, live here)
a.L('fs_fin')
a.addiu('t6','s1',1); a.sllv('t6','t6','t5'); a.jr('t3'); a.addiu('s2','t6',-1)
# ---- B14: Stage_Draw tail on the extra frame ----
def skip_stub(name,target):
    a.L(name); a.la('t0',EXTRA); a.lw('t0',0,'t0'); a.nop()
    a.beqz('t0',name+'_go'); a.nop(); a.jr('ra'); a.nop()
    a.L(name+'_go'); a.j_abs(target); a.nop()
skip_stub('B14_SkipObjLogic',0x8004D318)    # stage objects: triggers, breakables, spawns
skip_stub('B14_SkipObjMotion',0x800507A4)   # stage objects: motion, timers
skip_stub('B14_SkipMusic',0x8004AECC)       # music fade
def save_loop(tag,cnt_off,base_off,field,stride,buf,store):
    # t1 = count (capped 0x7FF), t2 = entry ptr, t3 = buffer
    a.lui('t0',0x8009); a.lh('t1',cnt_off,'t0'); a.lw('t2',base_off,'t0'); a.la('t3',buf)
    a.slti('t4','t1',0x800); a.bnez('t4',tag+'_l'); a.nop(); a.addiu('t1','zero',0x7FF)
    a.L(tag+'_l'); a.blez('t1',tag+'_d'); a.nop()
    if store:  # entry -> buffer
        a.lh('t4',field,'t2'); a.nop(); a.sh('t4',0,'t3')
    else:      # buffer -> entry
        a.lh('t4',0,'t3'); a.nop(); a.sh('t4',field,'t2')
    a.addiu('t1','t1',-1); a.addiu('t2','t2',stride); a.b(tag+'_l'); a.addiu('t3','t3',2)
    a.L(tag+'_d')
a.L('B14_Effects')   # replaces `jal FUN_80050604(a0)` in Stage_Draw
a.la('t0',EXTRA); a.lw('t0',0,'t0'); a.nop()
a.bnez('t0','fx_extra'); a.nop(); a.j_abs(0x80050604); a.nop()   # normal frame: unchanged
a.L('fx_extra')      # extra frame: no hazard checks; draw lights/fire and objects, then undo their counters
a.addiu('sp','sp',-32); a.sw('ra',28,'sp'); a.sw('a0',24,'sp')
save_loop('ls',0x8008CFBC-0x80090000,0x8008CFC8-0x80090000,0x14,0x18,LSAVE,True)
save_loop('os',0x8008CFBA-0x80090000,0x8008CFC4-0x80090000,0x6A,0x78,OSAVE,True)
a.lui('t0',0x800C); a.lh('t1',0x46FE,'t0'); a.addiu('t2','zero',0x7FFF); a.sw('t1',20,'sp'); a.sh('t2',0x46FE,'t0')  # no fire-jet hitbox spawn
a.lui('t0',0x8009); a.lw('t1',0x8008CDA8-0x80090000,'t0'); a.nop(); a.sw('t1',16,'sp')                               # lightning vblank stamp
a.lw('a0',24,'sp'); a.jal(0x8004ED74); a.nop()
a.lw('a0',24,'sp'); a.jal(0x8004FFAC); a.nop()
save_loop('lr',0x8008CFBC-0x80090000,0x8008CFC8-0x80090000,0x14,0x18,LSAVE,False)
save_loop('or',0x8008CFBA-0x80090000,0x8008CFC4-0x80090000,0x6A,0x78,OSAVE,False)
a.lw('t1',20,'sp'); a.lui('t0',0x800C); a.sh('t1',0x46FE,'t0')
a.lw('t1',16,'sp'); a.lui('t0',0x8009); a.sw('t1',0x8008CDA8-0x80090000,'t0')
a.lw('ra',28,'sp'); a.nop(); a.jr('ra'); a.addiu('sp','sp',32)
a.L('B14_SndGate')   # entry of FUN_8001E858 (positional sound): silent on the extra frame
a.la('t0',EXTRA); a.lw('t0',0,'t0'); a.nop()
a.beqz('t0','snd_go'); a.nop(); a.jr('ra'); a.move('v0','zero')
a.L('snd_go'); a.addiu('sp','sp',-0x30); a.lui('v1',0x8009); a.j_abs(0x8001E860); a.nop()
# ---- B15: stage objects drawn out to stock range x factor (capped); beyond the stock range: no collision/logic ----
a.L('B15_Range')     # at 0x80050238 in FUN_8004FFAC. in: a0 = distance, s5 = stage range value. out: v0 = 1 if too far
a.sll('v1','s5',1); a.addu('v1','v1','s5'); a.sra('v1','v1',2)          # stock draw range = value * 3 / 4
a.slt('t0','v1','a0')                                                   # beyond stock range
a.la('t1',DD_FACTOR); a.lw('t2',0,'t1'); a.nop()
a.bnez('t2','pr_f'); a.nop(); a.addiu('t2','zero',4)
a.L('pr_f'); a.mult('v1','t2'); a.mflo('t2'); a.sra('t2','t2',2)
a.slti('t3','t2',PROP_CAP); a.bnez('t3','pr_c'); a.nop(); a.addiu('t2','zero',PROP_CAP)
a.L('pr_c'); a.slt('t3','t2','v1'); a.beqz('t3','pr_s'); a.nop(); a.move('t2','v1')   # never below stock
a.L('pr_s'); a.slt('v0','t2','a0')
a.xori('t3','v0',1); a.and_('t3','t3','t0')
a.la('t1',FARF); a.jr('ra'); a.sw('t3',0,'t1')
def far_gate(name, target, far_target=None):
    a.L(name); a.la('t0',FARF); a.lw('t0',0,'t0'); a.nop()
    a.bnez('t0',name+'_far'); a.nop(); a.j_abs(target); a.nop()
    a.L(name+'_far')
    if far_target: a.j_abs(far_target); a.nop()
    else: a.jr('ra'); a.nop()
far_gate('B15_Reg', 0x8004D094, 0x8004D2C8)   # far: unregister collision instead of registering
far_gate('B15_Fbb0', 0x8004FBB0)              # far: falling-object animation keeps its stock range
far_gate('B15_E944', 0x8004E944)              # far: object fire effect (and its hitbox) keeps its stock range
# ---- FOGTAB: (site address, original instruction) ----
a.L('FOGTAB')
for site in FOG_SITES:
    a.word(site); a.word(struct.unpack_from('<I',EXE,site-0x80012000+0x800)[0])

words = a.words()
labels = a.labels
def jal_word(t): return 0x0C000000 | ((t & 0x0FFFFFFF) >> 2)
def redirect_words():
    out=[]
    for lui_a, acc_a in DD_REDIRECTS:
        lw=struct.unpack_from('<I',EXE,lui_a-0x80012000+0x800)[0]; aw=struct.unpack_from('<I',EXE,acc_a-0x80012000+0x800)[0]
        assert lw & 0xFFFF == 0x8009 and aw & 0xFFFF == 0xCEC8, (hex(lui_a), hex(lw), hex(aw))
        hi=(DD_STOCK+0x8000)>>16; lo=(DD_STOCK-(hi<<16))&0xFFFF
        out.append((lui_a, lw, (lw & 0xFFFF0000) | hi, 'draw distance: stock redirect (lui)'))
        out.append((acc_a, aw, (aw & 0xFFFF0000) | lo, 'draw distance: stock redirect (access)'))
    return out
EXE=EXE
hooks = [  # (address, original word, new word, name)
    (0x80064184, 0x0C014EBA, jal_word(labels['B1_CamHook']),  'Camera_Update -> B1_CamHook'),
    (0x8006418C, 0x0C0071CD, jal_word(labels['B3_ActorHook']), 'Actor_UpdateAndDrawAll -> B3_ActorHook'),
    (0x80064194, 0x0C012E57, jal_word(labels['B5_StageHook']), 'Stage_Draw -> B5_StageHook'),
    (0x800641C4, 0x0C00E8E1, jal_word(labels['B1_PreLogic']), 'Task_RunAll -> B1_PreLogic'),
    (0x80064544, 0x0C005C72, jal_word(labels['B1_Flip']),     'Frame_FlipAndWait -> B1_Flip'),
]
hooks += redirect_words()
def fog_prologue():
    st=labels['B10_FogStart']; hi=st>>16; lo=st&0xFFFF
    new=[0x3C108009,           # lui  s0,0x8009
         0x8E12CEC8,           # lw   s2,-0x3138(s0)   draw distance
         0x8E10CED8,           # lw   s0,-0x3128(s0)   fog colour table
         0x3C0C0000|hi,        # lui  t4,hi(B10_FogStart)
         0x358C0000|lo,        # ori  t4,t4,lo
         0x01805809,           # jalr t3,t4            -> s1 = fog start
         0x8D0F0004]           # lw   t7,4(t0)         (moved; delay slot)
    out=[]
    for i,w in enumerate(new):
        ad=0x80018E00+4*i; o=struct.unpack_from('<I',EXE,ad-0x80012000+0x800)[0]
        out.append((ad,o,w,'fog: Model_DrawPolys prologue'))
    return out
hooks += fog_prologue()
def pkt_relocation():
    out=[]
    def w(a): return struct.unpack_from('<I',EXE,a-0x80012000+0x800)[0]
    for lui_a,add_a in ((0x80017118,0x8001711C),(0x800171EC,0x800171F0),(0x800173A0,0x800173A4),(0x80017428,0x8001742C),
                        (0x800183BC,0x800183C0),(0x80062BDC,0x80062BE0),(0x8006387C,0x80063880)):
        l,d=w(lui_a),w(add_a); assert l&0xFFFF==0x8009 and d&0xFFFF==0x6AE8
        out.append((lui_a,l,(l&0xFFFF0000)|(PKT_BASE>>16),'packet buffers: base (lui)'))
        out.append((add_a,d,(d&0xFFFF0000)|(PKT_BASE&0xFFFF),'packet buffers: base (addiu)'))
    sh={0x14000:0xE,0x50000:0x10}[PKT_SIZE]   # index*5 << sh
    for a in (0x80017208,0x80017244,0x8001739C,0x80017440,0x800174E4,0x800183DC,0x80062BD8,0x80063878):
        o=w(a); assert (o>>6)&31==0xE and o&0x3F==0
        out.append((a,o,(o&~(31<<6))|(sh<<6),'packet buffers: size'))
    for lui_a,ori_a,lim in ((0x800171E4,0x800171E8,PKT_SIZE-1),(0x80017420,0x80017424,PKT_SIZE-1),(0x800183B4,0x800183B8,PKT_SIZE)):
        l,o=w(lui_a),w(ori_a)
        out.append((lui_a,l,(l&0xFFFF0000)|(lim>>16),'packet buffers: limit (lui)'))
        out.append((ori_a,o,(o&0xFFFF0000)|(lim&0xFFFF),'packet buffers: limit (ori)'))
    return out
hooks += pkt_relocation()
hooks += [
    (0x8004BDC0, 0x0C014181, jal_word(labels['B14_Effects']),      'Stage_Draw: FUN_80050604 -> B14_Effects'),
    (0x8004BDD8, 0x0C0134C6, jal_word(labels['B14_SkipObjLogic']), 'Stage_Draw: FUN_8004D318 -> skip on extra frame'),
    (0x8004BDE0, 0x0C0141E9, jal_word(labels['B14_SkipObjMotion']),'Stage_Draw: FUN_800507A4 -> skip on extra frame'),
    (0x8004BDE8, 0x0C012BB3, jal_word(labels['B14_SkipMusic']),    'Stage_Draw: FUN_8004AECC -> skip on extra frame'),
    (0x8001E858, 0x27BDFFD0, 0x08000000 | ((labels['B14_SndGate'] & 0x0FFFFFFF) >> 2), 'sound: gate on extra frame'),
    (0x8001E85C, 0x3C038009, 0x00000000, 'sound: (moved into gate)'),
]
def _w(ad): return struct.unpack_from('<I', EXE, ad - 0x80012000 + 0x800)[0]
hooks += [
    (0x80017130, _w(0x80017130), 0x24020000 | OT_LEN,              'ordering tables: length'),
    (0x8001713C, _w(0x8001713C), 0x3C020000 | (OT0_ORG >> 16),     'ordering tables: OT 0 (lui)'),
    (0x80017140, _w(0x80017140), 0x24420000 | (OT0_ORG & 0xFFFF),  'ordering tables: OT 0 (addiu)'),
    (0x80017148, _w(0x80017148), 0x3C020000 | (OT1_ORG >> 16),     'ordering tables: OT 1 (lui)'),
]
hooks += [(0x80050238, _w(0x80050238), jal_word(labels['B15_Range']), 'objects: draw range')]
hooks += [(ad, _w(ad), 0, 'objects: draw range (nop)') for ad in range(0x8005023C, 0x80050250, 4)]
hooks += [
    (0x80050334, _w(0x80050334), jal_word(labels['B15_Reg']),  'objects: collision register gate'),
    (0x8005035C, _w(0x8005035C), jal_word(labels['B15_Fbb0']), 'objects: falling object gate'),
    (0x800505B4, _w(0x800505B4), jal_word(labels['B15_E944']), 'objects: fire effect gate'),
]
# per-polygon fog early-out: `subu t4,t6,s1` -> `subu t4,t6,s2` (s2 = unshifted fog start, set by B10_FogStart)
for site in (0x80019224,0x80019338,0x800194B4,0x800196CC,0x80019930,0x80019AE8):
    o=struct.unpack_from('<I',EXE,site-0x80012000+0x800)[0]; assert o==0x01D16023
    hooks.append((site,o,0x01D26023,'fog: polygon early-out uses s2'))
# undo B10's bad shifts on the ordering-table depths (they survive in save states made with B10)
for site in (0x80019220,0x80019334,0x800194A8,0x800196C0,0x80019924,0x80019ADC):
    o=struct.unpack_from('<I',EXE,site-0x80012000+0x800)[0]
    for k in (1,2,3): hooks.append((site,(o+(k<<6))&0xffffffff,o,'undo B10 OT-depth shift'))

SIG = 'D0%06X %04X' % (EIGHTMB_SIG[0] & 0xFFFFFF, EIGHTMB_SIG[1])   # 8 MB RAM present (2 MB mirror shows the kernel here)
def release_hooks():
    return [h for h in hooks if not h[3].startswith('undo')]   # B10 clean-up lines are only for old dev save states
def cht_core(name):
    L = ['[%s]' % name, 'Type = Gameshark', 'Activation = EndFrame',
         'Description = 60fps (camera, character and pose interpolation) + longer draw distance with matching fog. Requires 8 MB RAM.']
    for i, w in enumerate(words):                      # patch code: only with 8 MB RAM
        L += [SIG, '90%06X %08X' % ((BASE + 4 * i) & 0xFFFFFF, w)]
    for addr, orig, new, _ in release_hooks():         # game code: only with 8 MB RAM AND the original instruction in place
        L += [SIG, 'A0%06X %08X' % (addr & 0xFFFFFF, orig), '90%06X %08X' % (addr & 0xFFFFFF, new)]
    return L
def cht_preset(name, factor):
    return ['[%s]' % name, 'Type = Gameshark', 'Activation = EndFrame',
            'Description = Render distance x%s (fog scaled to match). Enable only one draw distance option.' % name.split()[-1][:-1],
            SIG, '80%06X %04X' % (DD_FACTOR & 0xFFFFFF, factor)]
VSYNC = ['[VSync timeout fix]', 'Type = Gameshark', 'Activation = EndFrame',
         'Description = Fixes cutscenes and menus running too fast when the CPU is overclocked (also useful without the 60fps patch).',
         'D00699DC 2BC0', '800699DC 2D80', 'D0114BB0 2BC0', '80114BB0 2D80']
CORE_NAME = '60fps + draw distance (8MB RAM required)'

if __name__ == '__main__':
    out = _args[0] if _args else 'SLUS-00939'
    open(out + '.bin', 'wb').write(b''.join(struct.pack('<I', w) for w in words))
    L = cht_core(CORE_NAME) + [''] + VSYNC + ['']
    for n, f in (('Draw distance 2x', 8), ('Draw distance 3x', 12), ('Draw distance 4x', 16)):
        L += cht_preset(n, f) + ['']
    open(out + '.cht', 'w', newline='\n').write('\n'.join(L).rstrip('\n') + '\n')
    with open(out + '_patch.lua', 'w', newline='\n') as f:   # same patch as a Lua table, for tools/timing_test.lua
        f.write('-- generated by tools/build_patch.py\nreturn {\n')
        f.write('  base = 0x%08X,\n  sig = {0x%08X, 0x%04X},\n' % (BASE, GAME_SIG[0], GAME_SIG[1]))
        f.write('  code = {' + ','.join('0x%08X' % w for w in words) + '},\n')
        f.write('  hooks = {' + ','.join('{0x%08X,0x%08X,0x%08X}' % (h[0], h[1], h[2]) for h in release_hooks()) + '},\n')
        f.write('  cam_valid = 0x%08X,\n  cap_count = 0x%08X,\n}\n' % (STATE + 0x40, CAPST))
    print('%d code words, %d game hooks -> %s.cht' % (len(words), len(release_hooks()), out))
