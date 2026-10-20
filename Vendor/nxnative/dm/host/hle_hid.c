// nn::hid (controller): on the real device shared memory is read through the hid service; the host takes the current state written by the front end (Mac keyboard / controller, iOS virtual gamepad / controller).
// Generic, game-independent version: one standard controller. DM_OPMODE=0 (handheld) → handheld controller (Npad id 0x20); otherwise → 1P full-key controller (id 0).
// Vibration, six-axis, mouse, keyboard: not provided by the host (device count 0 / not connected); the controller applet reports "1 player, current controller selected".
#include "hle.h"
#include "dm_input.h"
#include "front.h"
#include <stdatomic.h>
#include <unistd.h>
#include <strings.h>
#include <pthread.h>
#include <time.h>

enum { NPAD_NO1 = 0, NPAD_HANDHELD = 0x20 };
enum { STYLE_FULLKEY = 1u << 0, STYLE_HANDHELD = 1u << 1, STYLE_JOYDUAL = 1u << 2, STYLE_JOYLEFT = 1u << 3, STYLE_JOYRIGHT = 1u << 4 };
enum { ATTR_CONNECTED = 1u << 0, ATTR_WIRED = 1u << 1, ATTR_LEFT_CONN = 1u << 2, ATTR_LEFT_WIRED = 1u << 3, ATTR_RIGHT_CONN = 1u << 4, ATTR_RIGHT_WIRED = 1u << 5 };
// Stick direction pseudo-buttons (NpadButton 16..23): derived from the stick values, threshold about half travel
enum { STICK_THRESH = 0x4000 };

// nn::hid::NpadFullKeyState / Handheld / JoyDual / JoyLeft / JoyRight share one layout (0x28)
typedef struct { int64_t sampling; uint64_t buttons; int32_t lx, ly, rx, ry; uint32_t attributes, _pad; } NpadState;
_Static_assert(sizeof(NpadState) == 0x28, "NpadState");

// Front-end publishing: the keyboard / touch path (dm_input_set) and the physical controller path (dm_pad_set) are ORed; press edges are latched until the game's next read so short presses are not lost
static _Atomic uint64_t g_btn, g_axes, g_latch, g_pad_btn, g_pad_axes, g_pad_latch;
static _Atomic int64_t g_sampling = 1 << 16;   // starts high so the history entries below the newest keep positive sampling numbers
static uint64_t pack(int32_t lx, int32_t ly, int32_t rx, int32_t ry) {
    return (uint64_t)(uint16_t)lx | (uint64_t)(uint16_t)ly << 16 | (uint64_t)(uint16_t)rx << 32 | (uint64_t)(uint16_t)ry << 48;
}
void dm_input_set(uint64_t buttons, int32_t lx, int32_t ly, int32_t rx, int32_t ry) {
    uint64_t old = atomic_exchange(&g_btn, buttons); atomic_fetch_or(&g_latch, buttons & ~old); atomic_store(&g_axes, pack(lx, ly, rx, ry));
}
void dm_pad_set(uint64_t buttons, int32_t lx, int32_t ly, int32_t rx, int32_t ry) {
    uint64_t old = atomic_exchange(&g_pad_btn, buttons); atomic_fetch_or(&g_pad_latch, buttons & ~old); atomic_store(&g_pad_axes, pack(lx, ly, rx, ry));
}
uint64_t dm_input_samples(void) { return (uint64_t)atomic_load(&g_sampling); }
// DM_KEYS scripted input (for tests): "seconds:key[+key][~hold seconds][*count/interval seconds],...", e.g. "8:A,12:A,15:Down~0.5,16:A+B,40:A*80/2" (A every 2 s from 40 s on, 80 times). Key names A B X Y LS RS L R ZL ZR (plus the sticks LLeft LUp LRight LDown and RLeft RUp RRight RDown) Plus Minus Left Up Right Down, left stick LLeft LUp LRight LDown,
//   and T<x>x<y> = a touch at normalized picture coordinates (origin top left) for the hold time;
//   held 0.15 s by default, at most 1024 steps (counted after repeats are expanded). Goes through the controller path (dm_pad_set), ORed with keyboard / touch, neither overrides the other. Times are counted from host start.
//   An f before the time means a presented frame number ("f7600:A", and the repeat interval counts frames too): when the machine is busy seconds drift from the game's progress, frame numbers do not (used for the Zelda BotW opening route)
typedef struct { double at, hold; uint64_t btn; int32_t lx, ly, rx, ry; int frame, tap; float tx, ty; } key_step;   // tap: a touch at (tx, ty), normalized
#define KEY_STEPS 1024
static key_step g_steps[KEY_STEPS]; static int g_nsteps;
static void *keys_main(void *arg) {
    (void)arg; struct timespec t0; clock_gettime(CLOCK_MONOTONIC, &t0);
    for (int i = 0; i < g_nsteps; i++) {
        for (;;) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); double el = (t.tv_sec - t0.tv_sec) + (t.tv_nsec - t0.tv_nsec) / 1e9;
                   if (g_steps[i].frame ? (double)dm_guest_frame() >= g_steps[i].at : el >= g_steps[i].at) break; usleep(5000); }
        LOG("DM_KEYS: %s%.2f press %#llx (hold %.2f s)", g_steps[i].frame ? "frame " : "", g_steps[i].at, (unsigned long long)g_steps[i].btn, g_steps[i].hold);
        if (g_steps[i].tap) { dm_touch t = {0, g_steps[i].tx, g_steps[i].ty}; dm_touch_set(&t, 1); }
        dm_pad_set(g_steps[i].btn, g_steps[i].lx, g_steps[i].ly, g_steps[i].rx, g_steps[i].ry); usleep((useconds_t)(g_steps[i].hold * 1e6)); dm_pad_set(0, 0, 0, 0, 0);
        if (g_steps[i].tap) dm_touch_set(NULL, 0);
    }
    return NULL;
}
void hid_keys_init(void) {
    const char *e = getenv("DM_KEYS"); if (!e || !*e) return;
    static const char *names[16] = {"A", "B", "X", "Y", "LS", "RS", "L", "R", "ZL", "ZR", "Plus", "Minus", "Left", "Up", "Right", "Down"};
    char buf[4096]; snprintf(buf, sizeof buf, "%s", e);
    for (char *tok = strtok(buf, ","); tok && g_nsteps < KEY_STEPS; tok = strtok(NULL, ",")) {
        char *c = strchr(tok, ':'); if (!c) { LOG("[RED] DM_KEYS step lacks 'seconds:': %s", tok); continue; }
        *c = 0; int fr = (tok[0] == 'f' || tok[0] == 'F'); key_step st = {atof(tok + fr), 0.15, 0}; st.frame = fr;
        int rep = 1; double every = 0;
        char *r = strchr(c + 1, '*'); if (r) { *r = 0; rep = atoi(r + 1); char *sl = strchr(r + 1, '/'); every = sl ? atof(sl + 1) : 1; if (rep < 1) rep = 1; }
        char *h = strchr(c + 1, '~'); if (h) { *h = 0; st.hold = atof(h + 1); }
        for (char *k = c + 1; k && *k;) { char *plus = strchr(k, '+'); if (plus) *plus = 0;
            int found = 0; for (int b = 0; b < 16; b++) if (!strcasecmp(k, names[b])) { st.btn |= 1ull << b; found = 1; }
            // left stick fully pushed: LLeft LUp LRight LDown (for games that move on the map by stick only, such as Super Mario 3D World)
            static const char *const sticks[4] = {"LLeft", "LUp", "LRight", "LDown"};
            static const int sx[4] = {-32767, 0, 32767, 0}, sy[4] = {0, 32767, 0, -32767};
            for (int d = 0; d < 4; d++) if (!strcasecmp(k, sticks[d])) { if (sx[d]) st.lx = sx[d]; if (sy[d]) st.ly = sy[d]; found = 1; }
            // right stick the same way: RLeft RUp RRight RDown (camera; Super Mario Odyssey's first hint asks for it)
            static const char *const rsticks[4] = {"RLeft", "RUp", "RRight", "RDown"};
            for (int d = 0; d < 4; d++) if (!strcasecmp(k, rsticks[d])) { if (sx[d]) st.rx = sx[d]; if (sy[d]) st.ry = sy[d]; found = 1; }
            // a touch: T<x>x<y> with x, y normalized on the picture, origin top left ("f3000:T0.31x0.62", Super Mario Galaxy's file select in handheld mode)
            float tx, ty; if ((k[0] == 'T' || k[0] == 't') && sscanf(k + 1, "%fx%f", &tx, &ty) == 2) { st.tap = 1; st.tx = tx; st.ty = ty; found = 1; }
            if (!found) LOG("[RED] DM_KEYS unknown key name: %s", k);
            k = plus ? plus + 1 : NULL; }
        for (int i = 0; i < rep && g_nsteps < KEY_STEPS; i++) { g_steps[g_nsteps] = st; g_steps[g_nsteps++].at = st.at + i * every; }
    }
    // Steps run in time order, so repeated groups interleave ("290:A*200/3,291:Left*200/3,291.5:A*200/3" = A, Left, A every 3 s): they used to run in list order, one group after the
    // other, and a group listed after a long repeat waited for all of it. A stable sort keeps the listed order of steps at the same time; times and frame numbers are not comparable, so a list
    // that mixes them keeps its listed order
    int mixed = 0; for (int i = 1; i < g_nsteps; i++) mixed |= g_steps[i].frame != g_steps[0].frame;
    if (!mixed) for (int i = 1; i < g_nsteps; i++) { key_step s = g_steps[i]; int j = i; while (j > 0 && g_steps[j - 1].at > s.at) { g_steps[j] = g_steps[j - 1]; j--; } g_steps[j] = s; }
    pthread_t th; if (g_nsteps && !pthread_create(&th, NULL, keys_main, NULL)) { pthread_detach(th); LOG("DM_KEYS: %d steps", g_nsteps); }
}

static uint32_t connected_id(void) { return dm_opmode() == 0 ? NPAD_HANDHELD : NPAD_NO1; }
uint32_t hle_hid_connected_npad(void) { return connected_id(); }   // nfp's NFC device sits on this controller (hle_sdk16.c)
static uint32_t style_of(uint32_t id) { return id != connected_id() ? 0 : id == NPAD_HANDHELD ? STYLE_HANDHELD : STYLE_FULLKEY; }
static int32_t ax(uint64_t v, int i) { return (int16_t)(v >> (16 * i)); }
static int32_t pick(int32_t a, int32_t b) { return (a < 0 ? -a : a) >= (b < 0 ? -b : b) ? a : b; }   // whichever of the two paths is deflected more

static void fill(NpadState *s, uint32_t id, uint32_t style) {
    memset(s, 0, sizeof *s);
    s->sampling = atomic_fetch_add(&g_sampling, 1) + 1;
    if (!(style_of(id) & style)) return;   // no controller of this id / style: attributes = 0
    uint64_t b = atomic_load(&g_btn) | atomic_exchange(&g_latch, 0) | atomic_load(&g_pad_btn) | atomic_exchange(&g_pad_latch, 0);
    uint64_t k = atomic_load(&g_axes), p = atomic_load(&g_pad_axes);
    s->lx = pick(ax(k, 0), ax(p, 0)); s->ly = pick(ax(k, 1), ax(p, 1)); s->rx = pick(ax(k, 2), ax(p, 2)); s->ry = pick(ax(k, 3), ax(p, 3));
    b &= 0xffffull;
    if (s->lx < -STICK_THRESH) b |= 1u << 16;
    if (s->ly > STICK_THRESH) b |= 1u << 17;
    if (s->lx > STICK_THRESH) b |= 1u << 18;
    if (s->ly < -STICK_THRESH) b |= 1u << 19;
    if (s->rx < -STICK_THRESH) b |= 1u << 20;
    if (s->ry > STICK_THRESH) b |= 1u << 21;
    if (s->rx > STICK_THRESH) b |= 1u << 22;
    if (s->ry < -STICK_THRESH) b |= 1u << 23;
    s->buttons = b;
    s->attributes = ATTR_CONNECTED | (id == NPAD_HANDHELD ? ATTR_WIRED | ATTR_LEFT_CONN | ATTR_LEFT_WIRED | ATTR_RIGHT_CONN | ATTR_RIGHT_WIRED : ATTR_LEFT_CONN | ATTR_RIGHT_CONN);
}
// GetNpadStates(out, n, id): newest first, n entries: the current state repeated with consecutive sampling numbers. The host keeps no history, but on hardware the
// 16-entry history is always full, and games read all of it whatever count comes back: Super Mario Odyssey (main+0x93fc20) polls every controller slot each frame, which advances
// the shared sampling number by about 16 per frame, and with only entry 0 written neither stick did anything in play (the camera did not turn at its first hint) while buttons
// and menus (the stick's direction bits) worked; with every entry written the camera turns
static int states(NpadState *out, int n, uint32_t id, uint32_t style) {
    if (n <= 0) return 0;
    fill(out, id, style);
    for (int i = 1; i < n; i++) { out[i] = out[0]; out[i].sampling = out[0].sampling - i; }
    return n;
}

HLE_FORCE("_ZN2nn3hid14InitializeNpadEv", "connect to the hid service; the host takes input from the front-end state", void, h_hid_InitNpad, void) {}
HLE_FORCE("_ZN2nn3hid22SetSupportedNpadIdTypeEPKjm", "supported controller ids; fixed by the host", void, h_hid_SetIds, const uint32_t *ids, uint64_t n) { (void)ids; (void)n; }
static uint32_t g_styles_supported = 0xffffffffu;
HLE_FORCE("_ZN2nn3hid24SetSupportedNpadStyleSetENS_4util10BitFlagSetILi32ENS0_12NpadStyleTagEEE", "supported controller styles; the host records them and picks the reported style from them", void, h_hid_SetStyles, uint32_t styles) {
    if (styles != g_styles_supported) LOG("hid supported controller styles %#x", styles); g_styles_supported = styles; }
HLE_FORCE("_ZN2nn3hid15GetNpadStyleSetERKj", "controller style query; follows DM_OPMODE", uint32_t, h_hid_GetStyle, const uint32_t *id) { return style_of(*id); }
HLE_FORCE("_ZN2nn3hid13GetNpadStatesEPNS0_16NpadFullKeyStateEiRKj", "full-key controller states", int, h_hid_StatesFullKey, NpadState *s, int n, const uint32_t *id) { return states(s, n, *id, STYLE_FULLKEY); }
HLE_FORCE("_ZN2nn3hid13GetNpadStatesEPNS0_17NpadHandheldStateEiRKj", "handheld controller states", int, h_hid_StatesHandheld, NpadState *s, int n, const uint32_t *id) { return states(s, n, *id, STYLE_HANDHELD); }
HLE_FORCE("_ZN2nn3hid13GetNpadStatesEPNS0_16NpadJoyDualStateEiRKj", "dual Joy-Con states (not connected on the host)", int, h_hid_StatesJoyDual, NpadState *s, int n, const uint32_t *id) { return states(s, n, *id, STYLE_JOYDUAL); }
HLE_FORCE("_ZN2nn3hid13GetNpadStatesEPNS0_16NpadJoyLeftStateEiRKj", "left Joy-Con states (not connected on the host)", int, h_hid_StatesJoyLeft, NpadState *s, int n, const uint32_t *id) { return states(s, n, *id, STYLE_JOYLEFT); }
HLE_FORCE("_ZN2nn3hid13GetNpadStatesEPNS0_17NpadJoyRightStateEiRKj", "right Joy-Con states (not connected on the host)", int, h_hid_StatesJoyRight, NpadState *s, int n, const uint32_t *id) { return states(s, n, *id, STYLE_JOYRIGHT); }
HLE_FORCE("_ZN2nn3hid14DisconnectNpadERKj", "disconnect a controller; ignored by the host", void, h_hid_Disconnect, const uint32_t *id) { (void)id; }
static uint32_t g_hold_type;
HLE_FORCE("_ZN2nn3hid18SetNpadJoyHoldTypeENS0_15NpadJoyHoldTypeE", "Joy-Con hold orientation; the host only records it", void, h_hid_HoldType, int t) { g_hold_type = (uint32_t)t; }
HLE_FORCE("_ZN2nn3hid20GetNpadJoyAssignmentERKj", "Joy-Con assignment: dual", int, h_hid_GetJoyAssign, const uint32_t *id) { (void)id; return 0; }
HLE_FORCE("_ZN2nn3hid30SetNpadJoyAssignmentModeSingleERKj", "Joy-Con single assignment; ignored by the host", void, h_hid_JoySingle, const uint32_t *id) { (void)id; }
HLE_FORCE("_ZN2nn3hid18SwapNpadAssignmentERKjS2_", "swap controller ids; ignored by the host", void, h_hid_Swap, const uint32_t *a, const uint32_t *b) { (void)a; (void)b; }
HLE_FORCE("_ZN2nn3hid21StartLrAssignmentModeEv", "L/R assignment mode; ignored by the host", void, h_hid_LrStart, void) {}
HLE_FORCE("_ZN2nn3hid20StopLrAssignmentModeEv", "L/R assignment mode; ignored by the host", void, h_hid_LrStop, void) {}
// Controller applet (system UI): report "1 player, current controller selected" directly. ControllerSupportResultInfo = { int playerCount; uint32_t selectedId; }
HLE_FORCE("_ZN2nn3hid21ShowControllerSupportEPNS0_27ControllerSupportResultInfoERKNS0_20ControllerSupportArgE", "controller applet; the host reports a selection right away",
          Result, h_hid_ShowCtrl, int32_t *info, const void *arg) { (void)arg; if (info) { info[0] = 1; info[1] = (int32_t)connected_id(); } return RES_OK; }
// Six-axis: handles are handed out, but no states can be read (0 entries)
HLE_FORCE("_ZN2nn3hid23GetSixAxisSensorHandlesEPNS0_19SixAxisSensorHandleEiRKjNS_4util10BitFlagSetILi32ENS0_12NpadStyleTagEEE", "six-axis sensor handles",
          int, h_hid_SixHandles, uint32_t *h, int n, const uint32_t *id, uint32_t style) { (void)style; int k = n < 2 ? n : 2; for (int i = 0; i < k; i++) h[i] = (*id << 8) | (uint32_t)i; return k; }
HLE_FORCE("_ZN2nn3hid18StartSixAxisSensorERKNS0_19SixAxisSensorHandleE", "six-axis sensor; not provided by the host", void, h_hid_SixStart, const uint32_t *h) { (void)h; }
HLE_FORCE("_ZN2nn3hid22GetSixAxisSensorStatesEPNS0_18SixAxisSensorStateEiRKNS0_19SixAxisSensorHandleE", "six-axis sensor states; not provided by the host (0 entries)",
          int, h_hid_SixStates, void *out, int n, const uint32_t *h) { (void)out; (void)n; (void)h; return 0; }
// Vibration: no devices
HLE_FORCE("_ZN2nn3hid20IsVibrationPermittedEv", "vibration permission; not supported by the host", unsigned, h_hid_VibPermit, void) { return 0; }
HLE_FORCE("_ZN2nn3hid25GetVibrationDeviceHandlesEPNS0_21VibrationDeviceHandleEiRKjNS_4util10BitFlagSetILi32ENS0_12NpadStyleTagEEE", "vibration devices: 0",
          int, h_hid_VibHandles, void *h, int n, const uint32_t *id, uint32_t style) { (void)h; (void)n; (void)id; (void)style; return 0; }
HLE_FORCE("_ZN2nn3hid25InitializeVibrationDeviceERKNS0_21VibrationDeviceHandleE", "vibration; not supported by the host", void, h_hid_InitVib, const void *h) { (void)h; }
HLE_FORCE("_ZN2nn3hid18SendVibrationValueERKNS0_21VibrationDeviceHandleERKNS0_14VibrationValueE", "vibration; not supported by the host", void, h_hid_SendVib, const void *h, const void *v) { (void)h; (void)v; }
// Values queued by the vibration graph (VibrationNode::Update) reach it from the sdk's internal FlushEnqueuedVibrationValues through the PLT, into the hid service proxy (sm abort). Metroid Dread
// sets handles on its VibrationTargets even when the host reports 0 devices, so values get queued; return success and the flush clears its count as usual
HLE_FORCE("_ZN2nn3hid6detail19SendVibrationValuesEPKNS0_21VibrationDeviceHandleEPKNS0_14VibrationValueEi", "vibration (batch, used by the vibration-pattern flush); not supported by the host", Result, h_hid_SendVibs, const void *h, const void *v, int n) { (void)h; (void)v; (void)n; return 0; }
// Mouse / keyboard: not connected
HLE_FORCE("_ZN2nn3hid15InitializeMouseEv", "mouse; not provided by the host", void, h_hid_InitMouse, void) {}
HLE_FORCE("_ZN2nn3hid14GetMouseStatesEPNS0_10MouseStateEi", "mouse states: 0 entries", int, h_hid_MouseStates, void *out, int n) { (void)out; (void)n; return 0; }
// Single state (13 Sentinels calls it every frame; without the hook the sdk aborts on its uninitialized mouse resource): MouseState is 0x28 bytes {sampling number i64, x, y, dx, dy, wheel dx, dy, buttons, attributes}; attributes 0 = not connected
HLE_FORCE("_ZN2nn3hid13GetMouseStateEPNS0_10MouseStateE", "mouse state: not connected (MouseState 0x28 bytes zeroed)", void, h_hid_MouseState, void *s) {
    memset(s, 0, 0x28); ((int64_t *)s)[0] = atomic_fetch_add(&g_sampling, 1) + 1;
}
HLE_FORCE("_ZN2nn3hid18InitializeKeyboardEv", "keyboard; not provided by the host", void, h_hid_InitKbd, void) {}
HLE_FORCE("_ZN2nn3hid16GetKeyboardStateEPNS0_13KeyboardStateE", "keyboard state: not connected (KeyboardState 0x30 bytes zeroed)", void, h_hid_KbdState, void *s) {
    memset(s, 0, 0x30); ((int64_t *)s)[0] = atomic_fetch_add(&g_sampling, 1) + 1;
}

// ---------- SDK 12 interfaces (Engage): single GetNpadState, mode queries / setters, touch screen, gestures, six-axis details, controller colors, etc. ----------
// In the original all of these read hid shared memory or go through the hid service; the host has no shared memory and answers from the same front-end state as above. Library functions that only modify the game's own buffers (vibration file parse / generate, ControllerSupportArg SetDefault / SetExplainText) keep running in the SDK
HLE_FORCE("_ZN2nn3hid12GetNpadStateEPNS0_16NpadFullKeyStateERKj", "full-key controller current state", void, h_hid_StateFullKey, NpadState *s, const uint32_t *id) { fill(s, *id, STYLE_FULLKEY); }
HLE_FORCE("_ZN2nn3hid12GetNpadStateEPNS0_17NpadHandheldStateERKj", "handheld controller current state", void, h_hid_StateHandheld, NpadState *s, const uint32_t *id) { fill(s, *id, STYLE_HANDHELD); }
HLE_FORCE("_ZN2nn3hid12GetNpadStateEPNS0_16NpadJoyDualStateERKj", "dual Joy-Con current state (not connected on the host)", void, h_hid_StateJoyDual, NpadState *s, const uint32_t *id) { fill(s, *id, STYLE_JOYDUAL); }
HLE_FORCE("_ZN2nn3hid12GetNpadStateEPNS0_16NpadJoyLeftStateERKj", "left Joy-Con current state (not connected on the host)", void, h_hid_StateJoyLeft, NpadState *s, const uint32_t *id) { fill(s, *id, STYLE_JOYLEFT); }
HLE_FORCE("_ZN2nn3hid12GetNpadStateEPNS0_17NpadJoyRightStateERKj", "right Joy-Con current state (not connected on the host)", void, h_hid_StateJoyRight, NpadState *s, const uint32_t *id) { fill(s, *id, STYLE_JOYRIGHT); }

static uint32_t g_comm_mode, g_hh_mode;
HLE_FORCE("_ZN2nn3hid18GetNpadJoyHoldTypeEv", "Joy-Con hold orientation: returns the value that was set", int, h_hid_GetHold, void) { return (int)g_hold_type; }
HLE_FORCE("_ZN2nn3hid24GetSupportedNpadStyleSetEv", "supported controller styles: all", uint32_t, h_hid_GetStyles, void) { return g_styles_supported; }
HLE_FORCE("_ZN2nn3hid24GetNpadCommunicationModeEv", "wireless communication mode: returns the value that was set", int, h_hid_GetComm, void) { return (int)g_comm_mode; }
HLE_FORCE("_ZN2nn3hid24SetNpadCommunicationModeENS0_21NpadCommunicationModeE", "wireless communication mode; the host only records it", void, h_hid_SetComm, int m) { g_comm_mode = (uint32_t)m; }
HLE_FORCE("_ZN2nn3hid29GetNpadHandheldActivationModeEv", "handheld activation mode: returns the value that was set", int, h_hid_GetHh, void) { return (int)g_hh_mode; }
HLE_FORCE("_ZN2nn3hid29SetNpadHandheldActivationModeENS0_26NpadHandheldActivationModeE", "handheld activation mode; the host only records it", void, h_hid_SetHh, int m) { g_hh_mode = (uint32_t)m; }
HLE_FORCE("_ZN2nn3hid28SetNpadJoyAssignmentModeDualERKj", "Joy-Con dual assignment; ignored by the host", void, h_hid_JoyDual, const uint32_t *id) { (void)id; }
HLE_FORCE("_ZN2nn3hid30SetNpadJoyAssignmentModeSingleERKjNS0_17NpadJoyDeviceTypeE", "Joy-Con single assignment (left or right given); ignored by the host", void, h_hid_JoySingleT, const uint32_t *id, int t) { (void)id; (void)t; }
HLE_FORCE("_ZN2nn3hid30SetNpadJoyAssignmentModeSingleEPjRKjNS0_17NpadJoyDeviceTypeE", "Joy-Con single assignment (returning the other half); ignored by the host, there is no other half", int, h_hid_JoySingleOut, uint32_t *out, const uint32_t *id, int t) { (void)out; (void)id; (void)t; return 0; }
HLE_FORCE("_ZN2nn3hid23MergeSingleJoyAsDualJoyERKjS2_", "merge single Joy-Cons; ignored by the host, reports success", Result, h_hid_Merge, const uint32_t *a, const uint32_t *b) { (void)a; (void)b; return RES_OK; }
// Bound and signalled once for the controller that is connected (the hid service reports the controller already attached at start the same way). Link's Awakening reads no controller state
// until this event has fired: without it GetNpadState was never called and the title's "Press L+R" never saw a press
HLE_FORCE("_ZN2nn3hid27BindNpadStyleSetUpdateEventERKjPNS_2os15SystemEventTypeENS3_14EventClearModeE", "controller style update event: bound, signaled once for the connected controller", void, h_hid_BindStyleEv,
          const uint32_t *id, void *ev, int clear) { hle_bind_system_event(ev, clear); if (*id == connected_id()) hle_signal_system_event(ev); }
HLE_FORCE("_ZN2nn3hid19GetPlayerLedPatternERKj", "player LED: LED 1", uint8_t, h_hid_Led, const uint32_t *id) { (void)id; return 1; }
// NpadControllerColor = { main RGBA, button RGBA }: grey body, black buttons
static void ctrl_color(uint32_t *c) { c[0] = 0xff828282u; c[1] = 0xff0f0f0fu; }
HLE_FORCE("_ZN2nn3hid22GetNpadControllerColorEPNS0_19NpadControllerColorERKj", "controller color", Result, h_hid_Color, uint32_t *c, const uint32_t *id) { (void)id; ctrl_color(c); return RES_OK; }
HLE_FORCE("_ZN2nn3hid22GetNpadControllerColorEPNS0_19NpadControllerColorES2_RKj", "left and right Joy-Con colors", Result, h_hid_Color2, uint32_t *l, uint32_t *r, const uint32_t *id) { (void)id; ctrl_color(l); ctrl_color(r); return RES_OK; }
HLE_FORCE("_ZN2nn3hid21ShowControllerSupportERKNS0_20ControllerSupportArgE", "controller applet (no result wanted); the host reports a selection right away", Result, h_hid_ShowCtrl0, const void *arg) { (void)arg; return RES_OK; }
HLE_FORCE("_ZN2nn3hid24ShowControllerStrapGuideEv", "strap guide applet; not shown by the host", Result, h_hid_Strap, void) { return RES_OK; }
HLE_FORCE("_ZN2nn3hid28ShowControllerFirmwareUpdateERKNS0_27ControllerFirmwareUpdateArgE", "controller firmware update applet; not shown by the host", Result, h_hid_FwUpd, const void *arg) { (void)arg; return RES_OK; }

// Touch screen: TouchScreenState<N> = { int64 sampling number; int32 count; int32 reserved; TouchState[N] }, filled from the front end's touch points (hle_touch.c touch_fill_n:
// the Mac's mouse, the iPhone touches no gamepad control takes, DM_KEYS taps) in handheld mode, as on the Switch, whose screen is out of reach when docked: a game may read touches
// without checking the mode, so in console mode the state stays empty (only the header is written). Super Mario Galaxy's pointer is the touch screen in handheld mode
int touch_fill_n(void *out, int max, uint64_t now_ns);
static void touch_read(void *s, int n) {
    if (dm_opmode() == 0) { touch_fill_n(s, n, now_ns()); return; }
    int64_t *p = s; p[0] = atomic_fetch_add(&g_sampling, 1) + 1; ((int32_t *)s)[2] = 0; ((int32_t *)s)[3] = 0;
}
HLE_FORCE("_ZN2nn3hid21InitializeTouchScreenEv", "connect to the hid touch screen; the host takes touch points from the front end", void, h_hid_InitTouch, void) {}
// SDK 18 overload with two ints (Super Mario Galaxy); the SDK's own one opens the hid service and aborts in sm::Initialize
HLE_FORCE("_ZN2nn3hid21InitializeTouchScreenEii", "connect to the hid touch screen (SDK 18 two-argument version); the host takes touch points from the front end", void, h_hid_InitTouch2, int a, int b) { (void)a; (void)b; }
#define TOUCH(N) \
    HLE_FORCE("_ZN2nn3hid19GetTouchScreenStateILm" #N "EEEvPNS0_16TouchScreenStateIXT_EEE", "touch screen current state (touch points only in handheld mode)", void, h_hid_Touch1_##N, void *s) { touch_read(s, N); } \
    HLE_FORCE("_ZN2nn3hid20GetTouchScreenStatesILm" #N "EEEiPNS0_16TouchScreenStateIXT_EEEi", "touch screen states: 1 entry (touch points only in handheld mode)", int, h_hid_TouchN_##N, void *s, int n) { if (n <= 0) return 0; touch_read(s, N); return 1; }
TOUCH(1) TOUCH(2) TOUCH(3) TOUCH(4) TOUCH(5) TOUCH(6) TOUCH(7) TOUCH(8) TOUCH(9) TOUCH(10) TOUCH(11) TOUCH(12) TOUCH(13) TOUCH(14) TOUCH(15) TOUCH(16)
HLE_FORCE("_ZN2nn3hid17InitializeGestureEv", "gestures; not provided by the host", void, h_hid_InitGesture, void) {}
HLE_FORCE("_ZN2nn3hid16GetGestureStatesEPNS0_12GestureStateEi", "gesture states: 0 entries", int, h_hid_Gestures, void *out, int n) { (void)out; (void)n; return 0; }

// Six-axis details: at rest, fusion off; SixAxisSensorState 0x60 bytes zeroed (attributes = 0: not connected)
HLE_FORCE("_ZN2nn3hid17StopSixAxisSensorERKNS0_19SixAxisSensorHandleE", "six-axis sensor; not provided by the host", void, h_hid_SixStop, const uint32_t *h) { (void)h; }
HLE_FORCE("_ZN2nn3hid21GetSixAxisSensorStateEPNS0_18SixAxisSensorStateERKNS0_19SixAxisSensorHandleE", "six-axis sensor current state: not connected", void, h_hid_SixState, void *s, const uint32_t *h) { (void)h; memset(s, 0, 0x60); }
HLE_FORCE("_ZN2nn3hid21IsSixAxisSensorAtRestERKNS0_19SixAxisSensorHandleE", "six-axis sensor at rest: yes", unsigned, h_hid_SixRest, const uint32_t *h) { (void)h; return 1; }
// The console's own six-axis sensor (SevenSixAxisSensor, the body's orientation in handheld mode; The Legend of Zelda: Breath of the Wild): takes a work buffer and is switched through the hid service. The host provides none: switching succeeds, 0 states
HLE_FORCE("_ZN2nn3hid28InitializeSevenSixAxisSensorEPvm", "console six-axis sensor initialization; not provided by the host", Result, h_hid_SevenInit, void *buf, size_t n) { (void)buf; (void)n; return RES_OK; }
HLE_FORCE("_ZN2nn3hid26FinalizeSevenSixAxisSensorEv", "console six-axis sensor", Result, h_hid_SevenFini, void) { return RES_OK; }
HLE_FORCE("_ZN2nn3hid23StartSevenSixAxisSensorEv", "console six-axis sensor; not provided by the host", Result, h_hid_SevenStart, void) { return RES_OK; }
HLE_FORCE("_ZN2nn3hid22StopSevenSixAxisSensorEv", "console six-axis sensor", Result, h_hid_SevenStop, void) { return RES_OK; }
HLE_FORCE("_ZN2nn3hid32ResetSevenSixAxisSensorTimestampEv", "console six-axis sensor timestamp", void, h_hid_SevenReset, void) {}
HLE_FORCE("_ZN2nn3hid27GetSevenSixAxisSensorStatesEPNS0_23SevenSixAxisSensorStateEi", "console six-axis sensor states: 0 entries", int, h_hid_SevenStates, void *out, int n) { (void)out; (void)n; return 0; }
HLE_FORCE("_ZN2nn3hid26IsSevenSixAxisSensorAtRestEv", "console six-axis sensor at rest: yes (Super Mario Odyssey)", unsigned, h_hid_SevenRest, void) { return 1; }
// The development debug pad (Super Mario Odyssey initializes and polls it): never connected, all zero
HLE_FORCE("_ZN2nn3hid18InitializeDebugPadEv", "debug pad; the host has none", void, h_hid_DbgPadInit, void) {}
HLE_FORCE("_ZN2nn3hid16GetDebugPadStateEPNS0_13DebugPadStateE", "debug pad state: not connected (all 0)", void, h_hid_DbgPadState, void *st) { memset(st, 0, 32); }   // sampling number, attributes, buttons, two sticks
HLE_FORCE("_ZN2nn3hid25EnableSixAxisSensorFusionERKNS0_19SixAxisSensorHandleEb", "six-axis sensor fusion; ignored by the host", void, h_hid_SixFusionOn, const uint32_t *h, uint32_t on) { (void)h; (void)on; }
HLE_FORCE("_ZN2nn3hid28IsSixAxisSensorFusionEnabledERKNS0_19SixAxisSensorHandleE", "six-axis sensor fusion: off", unsigned, h_hid_SixFusionQ, const uint32_t *h) { (void)h; return 0; }
HLE_FORCE("_ZN2nn3hid25GetGyroscopeZeroDriftModeERKNS0_19SixAxisSensorHandleE", "gyroscope zero-drift mode: standard", int, h_hid_GyroGet, const uint32_t *h) { (void)h; return 1; }
HLE_FORCE("_ZN2nn3hid25SetGyroscopeZeroDriftModeERKNS0_19SixAxisSensorHandleERKNS0_22GyroscopeZeroDriftModeE", "gyroscope zero-drift mode; ignored by the host", void, h_hid_GyroSet, const uint32_t *h, const int *m) { (void)h; (void)m; }
HLE_FORCE("_ZN2nn3hid32GetSixAxisSensorFusionParametersEPfS1_RKNS0_19SixAxisSensorHandleE", "six-axis sensor fusion parameters: 0", void, h_hid_FusionGet, float *a, float *b, const uint32_t *h) { (void)h; *a = 0; *b = 0; }
HLE_FORCE("_ZN2nn3hid32SetSixAxisSensorFusionParametersERKNS0_19SixAxisSensorHandleEff", "six-axis sensor fusion parameters; ignored by the host", void, h_hid_FusionSet, const uint32_t *h, float a, float b) { (void)h; (void)a; (void)b; }
HLE_FORCE("_ZN2nn3hid34ResetSixAxisSensorFusionParametersERKNS0_19SixAxisSensorHandleE", "six-axis sensor fusion parameters; ignored by the host", void, h_hid_FusionReset, const uint32_t *h) { (void)h; }
HLE_FORCE("_ZN2nn3hid41IsFirmwareUpdateAvailableForSixAxisSensorERKNS0_19SixAxisSensorHandleE", "six-axis sensor firmware update: none", unsigned, h_hid_SixFw, const uint32_t *h) { (void)h; return 0; }
// Vibration device info / actual value: no device, zeroed
HLE_FORCE("_ZN2nn3hid22GetVibrationDeviceInfoEPNS0_19VibrationDeviceInfoERKNS0_21VibrationDeviceHandleE", "vibration device info: none", void, h_hid_VibInfo, uint32_t *info, const void *h) { (void)h; info[0] = 0; info[1] = 0; }
HLE_FORCE("_ZN2nn3hid23GetActualVibrationValueEPNS0_14VibrationValueERKNS0_21VibrationDeviceHandleE", "actual vibration value: 0", void, h_hid_VibActual, float *v, const void *h) { (void)h; memset(v, 0, 16); }
