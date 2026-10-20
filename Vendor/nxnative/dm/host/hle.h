// HLE common: register host implementations by Switch mangled name.
// Note the differences between Apple AAPCS64 and Switch: Apple requires the caller to extend <32-bit arguments (bool/char/short), Switch code does not extend ⇒
// such parameters are always declared as int/unsigned and truncated by ourselves. Variadic arguments go on the stack on Apple and in registers on Switch ⇒ variadic functions cannot use C's "..." directly.
#pragma once
#include "dm.h"
typedef struct { const char *name; void *fn; } hle_ent;
#define HLE(mangled, ret, cname, ...)                                                             \
    static ret cname(__VA_ARGS__);                                                                \
    __attribute__((used, section("__DATA,swhle"))) static const hle_ent hle_ent_##cname = {mangled, (void *)cname}; \
    static ret cname(__VA_ARGS__)

typedef uint32_t Result;   // nn::Result: w0, 0 = success
#define RES_OK 0u
#define RES_FAIL 0x2A2u      // Generic failure (cut features such as networking uniformly return this)

// Guest address → host object side table
void *objmap_get(const void *guest);
void objmap_put(const void *guest, void *host);
void *objmap_del(const void *guest);
uint64_t now_ns(void);
// This thread is doing the host's own heavy work (NVN submit / present: encoding Metal commands; on hardware that is the GPU's business and does not occupy a guest core). The same-core preemption approximation (hle_thread.c) does not count it as "running"
extern __thread _Atomic int dm_host_work;
uint64_t guest_ns(void);              // Guest clock (hle_os.c; does not advance while DM_TICK_HOLD is frozen)
int dm_detclock_enabled(void);
void dm_guest_clock_advanced(void);
uint64_t dm_guest_frame(void);        // Incremented each time the host presents a frame; unaffected by machine load
uint64_t dm_server_tick(void);        // In-run server tick; returns UINT64_MAX when not in a run or while DM_TICK_HOLD is frozen
void guest_clock_freeze(int on);
void guest_clock_freeze_for(int reason, int on);   // Freeze by reason (1 background, 2 system keyboard); see hle_os.c

// Forced takeover: even if the SDK module has a definition, all references to that symbol at load time (JUMP_SLOT/GLOB_DAT/ABS64) are resolved to the host implementation.
// Used only for the service-layer nn:: (service clients of fs/oe/aoc/pctl...); the SDK's libc++ and nn::os internals do not go into this table.
// Every entry must state the reason for the takeover; an entry in the table that no module references makes loading report a failure and abort (a wrong list must fail loudly).
typedef struct { const char *name; void *fn; const char *why; } hle_force_ent;
#define HLE_FORCE(mangled, why, ret, cname, ...)                                                   \
    static ret cname(__VA_ARGS__);                                                                \
    __attribute__((used, section("__DATA,swforce"))) static const hle_force_ent hle_force_##cname = {mangled, (void *)cname, why}; \
    static ret cname(__VA_ARGS__)
// Same as above, but the implementation runs on this thread's big host stack (hle_bigstack.c): what is registered is a stub generated at compile time (the implementation's address goes into x16, then a jump to dm_bigstack_enter).
// For take-overs with large stack use (the file system sizes its buffers by PATH_MAX): a game thread's stack can be as small as 8 KB. Only register arguments are carried over (<= 8 integer, <= 8 floating point); not for variadic functions
#define HLE_FORCE_BIG(mangled, why, ret, cname, ...)                                               \
    static ret cname(__VA_ARGS__) __attribute__((used));                                          \
    extern const char cname##_bs[];                                                               \
    __asm__(".text\n.p2align 2\n.globl _" #cname "_bs\n.private_extern _" #cname "_bs\n_" #cname "_bs:\n" \
            "    adrp x16, _" #cname "@PAGE\n    add x16, x16, _" #cname "@PAGEOFF\n    b _dm_bigstack_enter\n"); \
    __attribute__((used, section("__DATA,swforce"))) static const hle_force_ent hle_force_##cname = {mangled, (const void *)cname##_bs, why}; \
    static ret cname(__VA_ARGS__)

// Operation mode (0 handheld / 1 docked): owned by hle_oe.c, and the hid controller style follows it; the front end can switch it at runtime
int dm_opmode(void);
void dm_3d_scale_hot(int hot);      // When overheating, lower the 3D render scale to 0.70 (UI untouched); 0 = restore
ssize_t dm_data_pread(int fd, void *buf, size_t n, off_t off);   // Resource archive reads: zero-stripped archives with a ".holes" extent table are translated through the table (hle_fs.c)
void dm_data_note_fd(int fd, const char *hostpath);
int dm_overlay_file(const char *rel, char *out, size_t n);   // File in the overlay: DM_ROMFS_OVERLAY may have several layers (colon-separated, earlier ones take priority); look for <layer>/<rel> layer by layer, and on a hit write it to out and return 1 (hle_fs.c)
void dm_set_opmode(int m);          // On change, push notification 30 / 31 according to the switches the game has turned on
// Focus (1 foreground / 2 focus lost / 3 background): called by the front end on lifecycle changes; a change pushes notification 15
void dm_focus_set(int st);
// Audio pause / resume following the lifecycle (called by the front end on going to background / returning to foreground)
void dm_audio_suspend(int on);
uint64_t dm_audio_render_calls(void);   // Cumulative sound card callback count (the silent sink is not counted)

// ---------- Host call number registry (a cut replaces a game-internal function entry with `svc #number; ret`, and the rewriter turns it into a host gate) ----------
// Horizon's SVC numbers only go up to 0x7F; 0x80 onward is reserved for host calls. New ones must be registered here and numbers must not repeat; dispatch is in hle_svc.c → svc_host_call.
//   No.    Purpose                                      File            Cut (main offset)
//   0x80   TACT BLTE block zlib decode → libdeflate           hle_tact.c      0x1b0ee60 (DecodeZlib entry)
//   0x81   Client command packet delivery (receive pump → server receive)         diag.c          0x5d3a88 (bl 0x632510 call site; forwarded as is by default, dropped under DM_C2S_REPLAY)
//   0x82   System-class client message delivery (receive pump → 0x6310b0)       diag.c          0x5d39c8 (bl 0x6310b0 call site; forwarded as is by default, dropped from the file's first tick on under DM_C2S_REPLAY)
//   0x83   Granny section per-block decode (section read 0x11f0110)           hle_granny.c    0x11f02dc (bl 0x11f4af0 call site; by default replaced with the pre-decoded candidate, forwarded as is if it does not check out)
//   0x84   Granny fixup table per-block decode (section read 0x11f07d0)       hle_granny.c    0x11f0914 (bl 0x11f4af0 call site; same as above)
//   0x85   Private skill HUD self-draw query (read-only, writes x8)          hle_tact.c      0x3e443c (branch gate: x8≠0 jumps to 0x3e4460, otherwise executes the original instruction and returns to 0x3e4440; touch-only private gate)
//   0x86   Private skill ground direction (forwards to the original 0x2b4ef8, then redirects by the right stick) hle_private_aim.c 0x2faf04 (bl 0x2b4ef8 call site; touch-only private gate)
//   0x87   Ground item appearance path (forwards to the original 0xa14dc4, then repoints by rule to the lit variant) dm_dropfilter.c 0x8fa590 (bl 0xa14dc4 call site; only items in mode 3 / 5 are changed, output in the x8 string)
//   0x88   Item landing drop sound (forwards to the original 0x470c20, then swaps tier-one items to a notification sound) dm_dropfilter.c 0x468f2c (bl 0x470c20 call site; writes x0 = sound id)
//   0x89   Rift exit rerouting (in a rift run the destination is replaced with the next map, writes x2 / x3 / x8) dm_rift.c      0x7cc1e0 (branch gate: x8≠0 jumps to 0x634000, otherwise executes the original instruction and returns to 0x7cc1e4)
//   0x8a   Spawn point for the player on run entry (forwards to the original 0x5596c0; replaced with a point next to the waypoint when entering in town)  dm_townwp.c     0x5d8040 (bl 0x5596c0 call site; in the player join function 0x5d7f70)
//   0x8b   Drop point for the corpse on run entry (same as above, the same point as the player gets)                      dm_townwp.c     0x5d8400 (bl 0x5596c0 call site; in the same function)
//   0x8c   Current act saved while in a rift (when the character is in a rift map w9 is replaced with 4 = Act V, writes x9; x8 always 0) dm_rift.c      0x6fa9d0 (branch gate: x8≠0 jumps to 0x6fa9d4, otherwise executes the original instruction and returns to 0x6fa9d4)
//   0x8d   Extra mercenary equipment slots (mercenary + rift level ≥10 + belt / boots / gloves / ring / amulet: w0 is replaced with 1, writes x0; x8 always 0) dm_rift.c      0x64a34c (branch gate: x8≠0 jumps to 0x64a350, otherwise executes the original instruction and returns to 0x64a350)
//   0x8e   Client-side check for the extra mercenary equipment slots (rift level ≥10 + the item is a belt / boots / gloves / ring / amulet: w1 is replaced with the item's own type number, writes x1; x8 always 0) dm_rift.c      0x3beb58 (branch gate: x8≠0 jumps to 0x3beb5c, otherwise executes the original instruction and returns to 0x3beb5c)
enum { SVC_HOST_TACT_ZLIB = 0x80, SVC_HOST_C2S_DELIVER = 0x81, SVC_HOST_C2S_SYS = 0x82, SVC_HOST_GRANNY_A = 0x83, SVC_HOST_GRANNY_B = 0x84, SVC_HOST_PRIVATE_SKILL_RENDER = 0x85, SVC_HOST_PRIVATE_SKILL_AIM = 0x86, SVC_HOST_GROUND_ASSET = 0x87, SVC_HOST_DROP_SOUND = 0x88, SVC_HOST_RIFT_EXIT = 0x89, SVC_HOST_JOIN_SPAWN = 0x8a, SVC_HOST_JOIN_CORPSE = 0x8b, SVC_HOST_SAVE_ACT = 0x8c, SVC_HOST_MERC_SLOT = 0x8d, SVC_HOST_MERC_SLOT_CL = 0x8e };   // 0x87: fetch the model path for ground items (dm_dropfilter.c drop light)   // 0x83/0x84: Granny per-block decode call sites (hle_granny.c)
