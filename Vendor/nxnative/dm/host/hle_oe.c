// nn::oe (application operating environment): on the real device the console state is queried through the am/oe services; the host gives fixed state directly.
// oe::Initialize is in hle_sdkinit.c, not here.
// Environment switches: DM_OPMODE=0 handheld / 1 console (default: the profile's op_mode, console unless set; console corresponds to the console-mode render profile); DM_LANG=language code (default en-US).
#include "hle.h"
#include "dm_uiscreen.h"

// The operation mode is runtime state (the front end can change it: iOS overheat downgrade switches to handheld): the single source is here, taken once from DM_OPMODE at startup, the environment variable is not read again afterwards
#include <stdatomic.h>
static _Atomic int g_opmode = -1;
int dm_opmode(void) {
    int m = g_opmode;
    if (m < 0) { const char *e = getenv("DM_OPMODE"); int v = e ? atoi(e) : DM_GAME_OPMODE; int exp = -1; atomic_compare_exchange_strong(&g_opmode, &exp, v); m = g_opmode; }
    return m;
}
// ---------- System notification queue (AppletMessage): front end state changes → fetched by the game every frame with TryPopNotificationMessage ----------
// Message numbers (those actually handled by the game at main 0xe10d30): 15 focus change, 30 operation mode change, 31 performance mode change
enum { MSG_FOCUS = 15, MSG_OPMODE = 30, MSG_PERFMODE = 31 };
#define MQ 32
static pthread_mutex_t g_mq_lock = PTHREAD_MUTEX_INITIALIZER; static pthread_cond_t g_mq_cond = PTHREAD_COND_INITIALIZER;   // cond: wakes the blocking PopNotificationMessage
static uint32_t g_mq[MQ]; static int g_mqh, g_mqn;
static _Atomic int g_ntf_opmode, g_ntf_perfmode;          // only pushed after the game turns it on with Set*NotificationEnabled
// Notification event (Hades main+0x3ed18c polls it every frame and pops one message each time it fires): the SDK's version returns the event oe::Initialize would have
// created, and the host's oe::Initialize is a no-op, so TryWaitSystemEvent asserted on it. A host-owned auto-clear SystemEvent instead, signalled while the queue holds a message
static uint8_t g_mq_ev[0x80] __attribute__((aligned(16)));
static _Atomic int g_mq_ev_on;
static void mq_ev_kick(void) {
    if (!atomic_load(&g_mq_ev_on)) return;
    pthread_mutex_lock(&g_mq_lock); int n = g_mqn; pthread_mutex_unlock(&g_mq_lock);
    if (n) hle_signal_system_event(g_mq_ev);
}
static void mq_push_(uint32_t m);
static void mq_push(uint32_t m) { mq_push_(m); mq_ev_kick(); }
static void mq_push_(uint32_t m) {
    pthread_mutex_lock(&g_mq_lock);
    // 15/30/31 are invalidation notifications meaning "query the current state", not events carrying historical values.
    // While one of the same type has not been taken yet, the first queue position is kept: the D2R consumer loop only reads the latest state, repeated notifications write back the same thing, and with the same size there is no further resize.
    // Only these three state notifications are merged; future per-occurrence events (such as Resume/Exit) must not use this rule.
    // Legitimate producers only send these three, so at most three items are pending, and any number of focus losses/restores no longer hits the 32-slot limit; after a pop, new changes are enqueued as usual.
    if (m == MSG_FOCUS || m == MSG_OPMODE || m == MSG_PERFMODE)
        for (int i = 0; i < g_mqn; i++)
            if (g_mq[(g_mqh + i) % MQ] == m) { pthread_mutex_unlock(&g_mq_lock); return; }
    if (g_mqn == MQ) die("oe notification queue overflow (is the game not popping?)");
    g_mq[(g_mqh + g_mqn++) % MQ] = m;
    pthread_cond_broadcast(&g_mq_cond);
    pthread_mutex_unlock(&g_mq_lock);
}
void dm_oe_res_changed(void) { if (getenv("DM_TEST_OE_FOCUS_FIRST")) mq_push(MSG_FOCUS);   /* Test: queue 31 behind a focus notification (the order at iOS app startup) */
    if (g_ntf_perfmode) mq_push(MSG_PERFMODE); else LOG("[RED] the resolution needs to change, but the game has not enabled performance mode change notifications"); }   // the render resolution should change (dm_uiscreen.c): make the game re-read the parameter bits
// Operation mode reported to GetOperationMode only (used to make the game reload layouts when switching between controller / touch layouts, dm_padmode.c):
// m ≥ 0 reports m and pushes one operation-mode notification; m < 0 reports the true value again and pushes one more.
// The controller style (hle_hid.c connected_id) and performance mode keep their true values, so no "Reconnect controller" prompt appears and the render
// resolution does not change
static _Atomic int g_ui_opmode = -1;
static _Atomic int g_ui_armed; static _Atomic uint32_t g_ui_reads;   // Counts once when the game first comes to read the operation mode after a notification has been pushed: the switch transaction uses it to read back "the game received it"
uint32_t dm_oe_ui_opmode_reads(void) { return atomic_load(&g_ui_reads); }
void dm_oe_ui_opmode(int m) { g_ui_opmode = m < 0 ? -1 : m; atomic_store(&g_ui_armed, 1); if (g_ntf_opmode) mq_push(MSG_OPMODE); }
void dm_set_opmode(int m) {   // called by the front end (overheat downgrade etc.): change the state and push 30 / 31 according to the switches the game has turned on
    int old = dm_opmode(); if (old == m) return;
    g_opmode = m;
    LOG("oe operation mode %d → %d", old, m);
    if (g_ntf_opmode) mq_push(MSG_OPMODE);
    if (g_ntf_perfmode) mq_push(MSG_PERFMODE);
}
// FocusState: 1 InFocus, 2 OutOfFocus, 3 Background. The front end calls dm_focus_set (iOS lifecycle / Mac window losing focus)
static _Atomic int g_focus = 1; static _Atomic uint64_t g_focus_in_ns;   // time of the most recent entry into InFocus
int dm_focus_now(void) { return atomic_load(&g_focus); }
uint64_t dm_focus_in_since(void) { return atomic_load(&g_focus_in_ns); }   // graphics layer display link watchdog: stalls are only computed while active, counted from activation (nvn_mtl.m mtl_present_wait)
void dm_focus_set(int st) {
    if (st < 1 || st > 3) die("dm_focus_set: invalid state %d", st);
    if (st == 1) atomic_store(&g_focus_in_ns, now_ns());
    if (atomic_exchange(&g_focus, st) == st) return;
    LOG("oe focus state → %d", st);
    mq_push(MSG_FOCUS);
}
static int opmode(void) { return dm_opmode(); }

// Screenshot / video recording switches: the host has no system screenshot service, no-op
HLE_FORCE("_ZN2nn2oe17FinishStartupLogoEv", "dismiss the system boot screen (through the am application proxy); the host has no boot screen", void, h_oe_FinishLogo, void) {}   // Metroid Dread calls it at main+0xadfed0
HLE_FORCE("_ZN2nn2oe44SetUserInactivityDetectionTimeExtendedUnsafeEb", "auto screen-off time on inactivity (through am); the host does not turn the screen off", void, h_oe_InactivityExt, int on) { (void)on; }
HLE_FORCE("_ZN2nn2oe15EnableRecordingEv", "video recording switch; the host has no system recording", void, h_oe_EnableRec, void) {}
// Applet resource user ID (ARUID, the number am assigns to this process): the host has no am, and the SDK's own getter returns 0. SDK 20's OpenAudioRenderer (the CPU rendering + manual execution path, sdk+0x221730)
//   aborts when it gets 0 (The Legend of Zelda: Breath of the Wild 1.9.0); SDK 16 did not check. Report a fixed non-zero ID, used only as an identifier
HLE_FORCE("_ZN2nn6applet23GetAppletResourceUserIdEv", "applet resource user ID; the host returns a fixed non-zero value", uint64_t, h_applet_Aruid, void) { return 0x80; }
// Launch parameter (present only when another program launched this one with one; returns bool): the host never passes one
HLE_FORCE("_ZN2nn2oe21TryPopLaunchParameterEPmPvm", "launch parameter: none", unsigned, h_oe_PopLaunchParam, size_t *out, void *buf, size_t n) { (void)buf; (void)n; if (out) *out = 0; return 0; }
// Tears of the Kingdom (SDK 20.5.22): the index of the program that launched this one in a multi-program application. The SDK asks the applet proxy, which the host never opens
// (null read in applet::GetPreviousProgramIndex right after the window setup); -1 = launched from the home menu
HLE_FORCE("_ZN2nn2oe23GetPreviousProgramIndexEv", "previous program index: launched from HOME, -1", int, h_oe_PrevProgram, void) { return -1; }
HLE_FORCE("_ZN2nn2oe16DisableRecordingEv", "video recording switch; the host has no system recording", void, h_oe_DisableRec, void) {}
HLE_FORCE("_ZN2nn2oe16EnableScreenShotEv", "screenshot switch; the host has no system screenshot", void, h_oe_EnableShot, void) {}
HLE_FORCE("_ZN2nn2oe17DisableScreenShotEv", "screenshot switch; the host has no system screenshot", void, h_oe_DisableShot, void) {}
// Super Mario Odyssey: HOME button blocking around its own menus, screenshot orientation, and the auto-sleep query (all through am)
HLE_FORCE("_ZN2nn2oe23BeginBlockingHomeButtonEv", "temporarily block the HOME button (through am); the host has no HOME button", void, h_oe_BlockHome, void) {}
HLE_FORCE("_ZN2nn2oe21EndBlockingHomeButtonEv", "restore the HOME button (through am)", void, h_oe_UnblockHome, void) {}
HLE_FORCE("_ZN2nn2oe29SetScreenShotImageOrientationENS_5album16ImageOrientationE", "screenshot orientation (through am); the host has no system screenshot", void, h_oe_ShotOrient, int o) { (void)o; }
HLE_FORCE("_ZN2nn2oe37IsUserInactivityDetectionTimeExtendedEv", "whether auto screen-off on inactivity is extended; the host does not turn the screen off, reports no", unsigned, h_oe_InactivityExtQ, void) { return 0; }
// Hyrule Warriors: Age of Calamity (SDK 9.6.0, main+0x8d1238): the copyright frame buffer, an overlay the system draws only into screenshots and recordings. The SDK hands the buffer to am as transfer memory
// (svcCreateTransferMemory, then a null applet proxy). The host has no system capture, so it keeps nothing
HLE_FORCE("_ZN2nn2oe30InitializeCopyrightFrameBufferEPvm", "copyright overlay buffer (for screenshots / recording, through am); the host has no system screenshot", void, h_oe_CopyrightInit, void *buf, size_t n) { (void)buf; (void)n; }
HLE_FORCE("_ZN2nn2oe17SetCopyrightImageEPKvmiiiiNS0_16WindowOriginModeE", "copyright overlay image; the host has no system screenshot", void, h_oe_CopyrightImage, const void *p, size_t n, int x, int y, int w, int h, int origin) { (void)p; (void)n; (void)x; (void)y; (void)w; (void)h; (void)origin; }
HLE_FORCE("_ZN2nn2oe22SetCopyrightVisibilityEb", "copyright overlay visibility; the host has no system screenshot", void, h_oe_CopyrightVisible, int on) { (void)on; }

// OperationMode: 0 Handheld, 1 Console; PerformanceMode: 0 Normal, 1 Boost (one-to-one with the operation mode)
HLE_FORCE("_ZN2nn2oe16GetOperationModeEv", "operation mode query; a fixed value from DM_OPMODE", int, h_oe_GetOpMode, void) { int u = g_ui_opmode; if (atomic_exchange(&g_ui_armed, 0)) atomic_fetch_add(&g_ui_reads, 1); return u >= 0 ? u : opmode(); }
HLE_FORCE("_ZN2nn2oe18GetPerformanceModeEv", "performance mode query; same as the operation mode", int, h_oe_GetPerfMode, void) { return opmode(); }
// apm performance configurations: Normal 0x00010000 (CPU 1020 / GPU 384 / EMC 1600 MHz, the handheld default), Boost 0x00010001 (GPU 768 MHz, the docked default)
HLE_FORCE("_ZN2nn2oe27GetPerformanceConfigurationENS0_15PerformanceModeE", "query the CPU/GPU clock config (through apm); reports the default for the mode", int, h_oe_GetPerfCfg, int mode) { return mode == 1 ? 0x00010001 : 0x00010000; }
HLE_FORCE("_ZN2nn2oe24SetAlbumImageOrientationENS_5album16ImageOrientationE", "screenshot orientation (through am); the host has no system screenshot", void, h_oe_AlbumOrient, int o) { (void)o; }
HLE_FORCE("_ZN2nn2oe27SetPerformanceConfigurationENS0_15PerformanceModeEi", "set the CPU/GPU clock config; the host does not scale clocks", void, h_oe_SetPerfCfg, int mode, int cfg) {
    LOG("oe::SetPerformanceConfiguration mode=%d cfg=%#x (ignored)", mode, cfg);
}

// Scripted state changes (verify lifecycle / overheat downgrade without a window): DM_OE_SCRIPT="focus=3@10,focus=1@20,opmode=0@30" (second N); bg=1 / bg=0 run the whole background round trip (see script_bg)
// Time counts from the game's first notification fetch; "@ingame+N" = N seconds after the loading screen is taken down for the K-th time (K = number of preceding @ingame items + 1, the first one is run entry) (event-based, not affected by load). Coexists with front end calls.
#include <unistd.h>
static _Atomic int g_ls_unloads;   // number of times the loading screen was taken down (the UIMSG handler in diag.c calls dm_note_loadscreen_unload)
void dm_note_loadscreen_unload(void) { atomic_fetch_add(&g_ls_unloads, 1); }
// bg=1 / bg=0: the whole "to background / back to foreground" sequence, in the same order as the scene lifecycle in front_ios.m (resign active -> enter background; enter foreground -> become active), minus the audio session reset iOS does on returning.
// Used to reproduce "after going to the background and back" problems on the Mac (audio take-over and resume, guest clock freeze, graphics suspend); to imitate the process being suspended as well, send dmhost SIGSTOP / SIGCONT between the two items
static void script_bg(int on) {
    if (on) { dm_focus_set(2); dm_focus_set(3); dm_audio_suspend(1); guest_clock_freeze_for(1, 1); dm_gfx_suspend(1); }
    else { dm_gfx_suspend(0); guest_clock_freeze_for(1, 0); dm_audio_suspend(0); dm_focus_set(2); dm_focus_set(1); }
}
static void *oe_script(void *arg) {
    char *buf = arg; uint64_t t0 = now_ns();
    for (char *save, *tok = strtok_r(buf, ",", &save); tok; tok = strtok_r(NULL, ",", &save)) {
        char key[16]; int v; double at;
        if (sscanf(tok, "%15[a-z]=%d@ingame+%lf", key, &v, &at) == 3) {
            static int need;
            need++; while (atomic_load(&g_ls_unloads) < need) usleep(20000);
            usleep((useconds_t)(at * 1e6));
        } else {
            if (sscanf(tok, "%15[a-z]=%d@%lf", key, &v, &at) != 3) die("DM_OE_SCRIPT entry '%s' should be key=value@seconds or key=value@ingame+seconds", tok);
            uint64_t due = t0 + (uint64_t)(at * 1e9), now = now_ns();
            if (due > now) usleep((useconds_t)((due - now) / 1000));
        }
        if (!strcmp(key, "focus")) dm_focus_set(v);
        else if (!strcmp(key, "opmode")) dm_set_opmode(v);
        else if (!strcmp(key, "bg")) script_bg(v);
        else die("DM_OE_SCRIPT unknown key '%s' (focus / opmode / bg)", key);
    }
    return NULL;
}
static void oe_script_start(void) {
    const char *e = getenv("DM_OE_SCRIPT"); if (!e) return;
    pthread_t th; if (pthread_create(&th, NULL, oe_script, strdup(e))) die("DM_OE_SCRIPT thread");
    pthread_detach(th);
}
static pthread_once_t g_oe_once = PTHREAD_ONCE_INIT;

HLE_FORCE("_ZN2nn2oe20GetCurrentFocusStateEv", "foreground / background state; driven by the front end's dm_focus_set", int, h_oe_GetFocus, void) { return g_focus; }
HLE_FORCE("_ZN2nn2oe20SetFocusHandlingModeENS0_17FocusHandlingModeE", "focus handling mode; the game sets 1 (focus notifications), the host implements the notification semantics", void, h_oe_SetFocusMode, int m) { LOG("oe::SetFocusHandlingMode %d", m); }

// Notification: returns bool (w0), the host has no system notifications
// ---------- 3D internal render scale ----------
// The game has a static 3D render scale built in: renderer object (global pointer [main+0x31e0848]) member +0x66a4 (float, always 1.0 in the original game).
// The resolution change function main+0x8582f0(output width, output height) → main+0x1627ef0 rebuilds the 3D target as "scale × output width/height" (+0xee78 / +0xee7c),
// the UI layer and Final Result are still built at the output size (+0xee88 / +0xee8c), and at the end the game's own upscale shader ps_upsample_p brings it back to the output size.
// The boot flow does not call 0x8582f0, so it has to be called once actively; the call site must be where the game main thread fetches system notifications -- the same context in which the game itself handles mode switches
// (calling it in the present HLE self-deadlocks: the render lock is already held by the present path).
// Default: iOS 0.75, Mac host 1.0 (the screenshot gate compares against Switch ground truth); DM_3D_SCALE=0.5–1.0 overrides.
// The visual ruler ground truth phase (A / B of DM_NVN_RULER=1) forces 1.0, it only takes effect after switching to the mode under test.
// Dynamic scale (system throttling looks at utilization, the thermal state is only a coarse signal → adjust by actual dropped frames): the controller consumes the actual present intervals reported by the present thread
// (same source as perf.txt), three levels configured value (0.75) → 0.72 → 0.70; lower limit 0.70 (0.65 is visibly different). For the rules see scale3d_ctl_step.
// Switches: DM_3D_SCALE_DYN=0 off; DM_THERMAL_NOFALLBACK=1 (power / frame time measurement) also turns it off -- the scale must be pinned during measurement.
// DM_3D_SCALE_DYN_INJECT=start frame-end frame: diagnostic, within these frames every interval fed to the controller is taken as 25 ms (the Mac has no present timestamps, this is used to verify the whole lower / raise chain).
#include <TargetConditionals.h>
#define SCALE3D_MIN 0.70f
#define SCALE3D_MID 0.72f
// Pure-function controller (unit test t_oe.c feeds sequences directly): level 0 = configured value, larger is lower. Safety valve: only acts on perceptible dropped frames.
//   Window: one window per 2 seconds of accumulated present intervals, frame rate in the window = presented frames ÷ sum of intervals (frames dropped by the system are not counted, that time falls into the interval of the next presented frame).
//   Lower: frame rate of two consecutive windows both < target × 0.92 (55.2 at 60 fps) → lower one level.
//   Raise: frame rate of 10 consecutive windows (20 seconds) all ≥ target × 0.97 (58.2 at 60 fps) → raise one level; if knocked back within 10 seconds of going up, the next raise needs 30 consecutive windows (60 seconds).
//   Judging is suspended for 2 seconds after a level change (rebuilding the 3D target itself causes a hitch). Target frame rate = 1000 ÷ period_ms (0 = 60 fps).
// The old rule (lower as soon as slow frames > 5% in a 2-second window, raise needs 60 consecutive seconds with zero slow frames, knock-back ×3) lowered too easily and almost never came back up: on the test iPhone, of 582 run entries 33 were lowered and 0 came back up,
// and two real-device logs were also lowered to 0.70 at thermal state 2 with frame rate 59.8–60; the slow frame count is kept only in the diagnostic log and no longer takes part in the decision.
typedef struct { int level, max_level; double period_ms; uint64_t hold_until, last_up; double win_ms, last_fps; unsigned win_n; int bad_run, good_run, need_good; } scale3d_ctl;
#define S3_SEC 1000000000ull
static void scale3d_ctl_hold(scale3d_ctl *c, uint64_t now, uint64_t ns) {   // suspend judging for a while (after entering a run / returning to foreground / changing level): the window and the consecutive counts are cleared
    if (now + ns > c->hold_until) c->hold_until = now + ns;
    c->win_ms = 0; c->win_n = 0; c->bad_run = c->good_run = 0;
}
static int scale3d_ctl_step(scale3d_ctl *c, double iv_ms, uint64_t now) {   // returns the current level
    if (now < c->hold_until || iv_ms <= 0) return c->level;   // judging suspended / no reading (0) / dropped (−1)
    c->win_ms += iv_ms; c->win_n++;
    if (c->win_ms < 2000) return c->level;
    double tgt = 1000.0 / (c->period_ms > 0 ? c->period_ms : 1000.0 / 60), fps = c->win_n * 1000.0 / c->win_ms;
    c->last_fps = fps; c->win_ms = 0; c->win_n = 0;
    if (fps < tgt * 0.92) {
        c->good_run = 0;
        if (++c->bad_run >= 2 && c->level < c->max_level) {
            if (c->last_up && now - c->last_up < 10 * S3_SEC) c->need_good = 30;   // dropped again within 10 seconds of going up: the next raise needs 60 seconds
            c->level++; scale3d_ctl_hold(c, now, 2 * S3_SEC);
        }
    } else {
        c->bad_run = 0;
        if (fps >= tgt * 0.97) { if (++c->good_run >= (c->need_good ? c->need_good : 10) && c->level > 0) { c->level--; c->last_up = now; c->need_good = 0; scale3d_ctl_hold(c, now, 2 * S3_SEC); } }
        else c->good_run = 0;
    }
    return c->level;
}
static _Atomic int g_scale3d_level;
static _Atomic int g_scale3d_resumed;
void dm_3d_scale_resumed(void) { atomic_store(&g_scale3d_resumed, 1); }   // front end: just returned to foreground. Slow frames in the first few seconds back are recovery (surface rebuild, caches gone cold), not GPU pressure: suspend judging for 3 seconds
void dm_3d_scale_feed(double iv_ms) {   // called by the present thread every frame (forwarded from diag.c dm_perf_present): actual present interval in ms, −1 = dropped, 0 = no reading
    static scale3d_ctl c = {.max_level = 2}; static int on = -1; static long inj0 = -1, inj1 = -1;
    if (on < 0) { const char *e = getenv("DM_3D_SCALE_DYN"), *j = getenv("DM_3D_SCALE_DYN_INJECT"); on = !(e && !strcmp(e, "0")) && !getenv("DM_THERMAL_NOFALLBACK");
        if (j) { inj0 = atol(j); inj1 = strchr(j, '-') ? atol(strchr(j, '-') + 1) : inj0; } }
    if (!on) return;
    if (inj0 >= 0) { long f = (long)dm_nvn_frame_count(); iv_ms = f >= inj0 && f <= inj1 ? 25.0 : 16.7; }
    uint64_t now = now_ns();
    if (atomic_exchange(&g_scale3d_resumed, 0)) scale3d_ctl_hold(&c, now, 3 * S3_SEC);
    { static int was; int in = dm_ingame_now();   // not judged outside a run (menu / loading); not judged in the first 20 seconds of a run either (slow frames in the first ten-odd seconds of a run are loading, not GPU pressure)
      if (!in) { was = 0; scale3d_ctl_hold(&c, now, S3_SEC); return; }
      if (!was) { was = 1; if (inj0 < 0) scale3d_ctl_hold(&c, now, 20 * S3_SEC); } }
    { int mtl_fps_target(void); double p = mtl_fps_target() == 30 ? 1000.0 / 30 : 0; if (p != c.period_ms) { c.period_ms = p; scale3d_ctl_hold(&c, now, 2 * S3_SEC); } }   // power-saving mode (30 fps): the target period changes with it, judging is suspended for 2 seconds after the switch
    int was = c.level, lv = scale3d_ctl_step(&c, iv_ms, now);
    if (lv != was) LOG("3D scale control: window frame rate %.1f (target %.0f) → %s to level %d%s", c.last_fps, c.period_ms > 0 ? 1000.0 / c.period_ms : 60.0, lv > was ? "down" : "up", lv, c.need_good ? " (dropped right after going up: the next step up needs 60 s)" : "");
    atomic_store(&g_scale3d_level, lv);
}
void dm_3d_scale_hot(int hot) { (void)hot; }   // overheating no longer lowers the level directly (now by actual dropped frames); the symbol is kept for the front end
static _Atomic float g_scale3d_cur = 1.0f;
float dm_3d_scale_cur(void) { return atomic_load(&g_scale3d_cur); }
static void scale3d_tick(void) {
    static float want_cfg = -1, cur = 1.0f; static module_t *main;
    if (want_cfg < 0) {
        const char *e = getenv("DM_3D_SCALE"); want_cfg = TARGET_OS_IPHONE ? 0.75f : 1.0f;
        if (e) { char *end; float v = strtof(e, &end); if (end == e || *end || !(v >= 0.5f && v <= 1.0f)) die("DM_3D_SCALE invalid: %s (must be 0.5–1.0)", e); want_cfg = v; }
        for (int i = 0; i < g_nmod; i++) if (!strcmp(g_mod[i].name, "main")) main = &g_mod[i];
        // The addresses above (renderer global pointer, resolution change function, member offsets) all belong to D2R build db0507f3…; in other builds (every Mario version) the same addresses are unrelated data and code
        // (Mario v0's main+0x8582f0 is in the middle of a static initializer), so writing and calling them would corrupt memory. Only enabled on that build
        if (main && strcmp(main->build_id, "db0507f36b84200ac05f75d76ed5026f")) { LOG("3D render scale: main build %s has no known addresses, left alone (only D2R db0507f3… is known)", main->build_id[0] ? main->build_id : "(output has no build ID)"); main = NULL; }
    }
    int lv = atomic_load(&g_scale3d_level);   // dynamic level: 0 = configured value, 1 = 0.72, 2 = 0.70 (none higher than the configured value)
    float dyn = lv == 0 ? want_cfg : lv == 1 ? SCALE3D_MID : SCALE3D_MIN; if (dyn > want_cfg) dyn = want_cfg;
    float want = dm_nvn_ruler_truth() ? 1.0f : dyn;
    if (want == cur || !main || dm_nvn_frame_count() < 30) return;
    uintptr_t renderer = *(uintptr_t *)(main->base + 0x31e0848); if (!renderer) return;
    uint32_t ow = *(uint32_t *)(renderer + 0xee88), oh = *(uint32_t *)(renderer + 0xee8c); if (!ow || !oh) return;
    { extern void mtl_rt_force_full(int) __attribute__((weak)); if (mtl_rt_force_full) mtl_rt_force_full(4); }   // runtime extrapolation: the few frames before and after a scale change are all drawn in full (the frame where the main pass changes size cannot be extrapolated)
    float *scale = (float *)(renderer + 0x66a4); dm_guest_write_prepare(scale, sizeof *scale); *scale = want;
    ((void (*)(uint32_t, uint32_t))(main->base + 0x8582f0))(ow, oh);
    cur = want; atomic_store(&g_scale3d_cur, want);
    LOG("3D render scale %.2f: 3D target %ux%u, output %ux%u (frame %llu)", want, *(uint32_t *)(renderer + 0xee78), *(uint32_t *)(renderer + 0xee7c),
        *(uint32_t *)(renderer + 0xee88), *(uint32_t *)(renderer + 0xee8c), (unsigned long long)dm_nvn_frame_count());
}
HLE_FORCE("_ZN2nn2oe25TryPopNotificationMessageEPj", "system notification queue; front end state changes are queued", unsigned, h_oe_TryPopMsg, uint32_t *msg) {
    scale3d_tick();
    pthread_once(&g_oe_once, oe_script_start);
    pthread_mutex_lock(&g_mq_lock);
    int ok = g_mqn > 0;
    if (ok) { *msg = g_mq[g_mqh]; g_mqh = (g_mqh + 1) % MQ; g_mqn--; }
    pthread_mutex_unlock(&g_mq_lock);
    // The resolution parameter bits live in the thread slot, and the game reads them on the thread that fetches notifications to change the render size (on receiving 31 "performance mode changed", from main+0xe10ddc; 30 only updates a flag).
    // When they are read: each time the handler is entered, once after the first notification is fetched (0xe10d5c / 0xe10d60), and notifications fetched later in the loop still use the values from that read. So every time one is taken, the value due at this moment is written into the current thread's slot --
    // writing only when 31 is taken is not enough: when 31 is queued behind another notification (e.g. focus 15), the parameter bits have already been read after fetching 15 (iOS app: the front end did not switch to 16:9, in the Mac host run 31 happened to be queued first).
    if (ok) for (int i = 0; i < 2; i++) if (g_keyres[i]) pthread_setspecific(g_keyres[i], (void *)dm_game_res(i));
    if (ok && *msg == MSG_PERFMODE) dm_uiscreen_res_reread();
    if (ok) LOG("oe notification popped by the game: %u", *msg);   // state changes are rare, printing each one does not flood the log
    if (ok) mq_ev_kick();   // one message per signal: fire again for the next one
    return ok;
}
// The blocking form (Link's Awakening pops on a thread of its own, main+0xfa1ff8): the SDK's version waits on the system event oe::Initialize would have created,
// and the host's oe::Initialize is a no-op, so it aborted on an uninitialized event. Wait for the host queue instead, then take the message the Try path's way
HLE_FORCE("_ZN2nn2oe22PopNotificationMessageEv", "system notification queue (blocking); waits on the host queue", uint32_t, h_oe_PopMsg, void) {
    uint32_t m = 0;
    for (;;) {
        pthread_mutex_lock(&g_mq_lock);
        while (!g_mqn) pthread_cond_wait(&g_mq_cond, &g_mq_lock);
        pthread_mutex_unlock(&g_mq_lock);
        if (h_oe_TryPopMsg(&m)) return m;   // another thread may have taken it in between: wait again
    }
}
HLE_FORCE("_ZN2nn2oe27GetNotificationMessageEventEv", "notification event: the host's auto-clear SystemEvent, signalled while the queue holds notifications", void *, h_oe_GetMsgEv, void) {
    if (!atomic_load(&g_mq_ev_on)) { hle_bind_system_event(g_mq_ev, 1); atomic_store(&g_mq_ev_on, 1); mq_ev_kick(); }   // bound on the game's thread (it runs SDK code)
    return g_mq_ev;
}
// bool arguments: Switch callers do not extend them, declared as unsigned and only the low 8 bits are looked at
HLE_FORCE("_ZN2nn2oe28SetResumeNotificationEnabledEb", "resume notification switch; the host expresses resume as focus notification 15", void, h_oe_SetResumeNtf, unsigned on) { (void)on; }
HLE_FORCE("_ZN2nn2oe42SetOperationModeChangedNotificationEnabledEb", "operation mode change notification switch", void, h_oe_SetOpModeNtf, unsigned on) { g_ntf_opmode = on & 0xff; }
HLE_FORCE("_ZN2nn2oe44SetPerformanceModeChangedNotificationEnabledEb", "performance mode change notification switch", void, h_oe_SetPerfModeNtf, unsigned on) { g_ntf_perfmode = on & 0xff; }

// nn::settings::LanguageCode = struct { char string[8]; }, 8 bytes returned by value in x0
HLE_FORCE("_ZN2nn2oe18GetDesiredLanguageEv", "system language query; value from DM_LANG", uint64_t, h_oe_GetLang, void) {
    const char *e = getenv("DM_LANG");
    char code[8] = {0};
    strncpy(code, e && *e ? e : "en-US", sizeof code - 1);
    uint64_t v; memcpy(&v, code, 8);
    return v;
}

// nn::util::Uuid 16 bytes: a fixed local value (only used to tell devices apart locally, networking is cut)
HLE_FORCE("_ZN2nn2oe17GetPseudoDeviceIdEPNS_4util4UuidE", "pseudo device ID; a fixed host value", void, h_oe_GetDevId, uint8_t *uuid) {
    static const uint8_t k[16] = {0x78, 0x62, 0x6c, 0x00, 0x53, 0x57, 0x4e, 0x41, 0x54, 0x49, 0x56, 0x45, 0x31, 0x30, 0x30, 0x31};
    memcpy(uuid, k, 16);
}
