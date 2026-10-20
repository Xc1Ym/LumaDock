// swkbd software keyboard (system applet) → host native input box. MakePreset / SetInitialTextUtf8 / GetRequired*Size are left to run as is in the SDK,
// here we only read the ShowKeyboardArg they write and write back String per the output convention of the real swkbd applet.
// Layout sources (offsets in the original sdk 3.3.94012 image):
//   ShowKeyboard 0x3a6770 moves KeyboardConfig field by field into the applet arguments: +0x24 title u16[65], +0xa6 subtitle u16[129], +0x1a8 hint u16[257],
//     +0x3ac maximum length, +0x3b0 minimum length, +0x3bd isUseUtf8, +0x3c0 offset of the initial text within the work buffer, +0x3c4 UTF-16 length of the initial text;
//     work buffer pointer / size at +0x4d0 / +0x4d8 (handed to the applet together with CreateLargeStorage)
//   SetInitialTextUtf8 0x3a74c0: UTF-8 → UTF-16 written to work buffer+offset (offset 0x14, at most 500 characters + terminating 0)
//   ReadCloseResultAndString 0x3a63f0: output storage = u32 CloseResult + text area; the text area is copied as is into String{+0 pointer, +8 byte count}
//   ShowKeyboard wrap-up 0x3a6acc: CloseResult == 0 (OK) → Result 0, otherwise (cancel) → 0x29F; GetRequiredStringBufferSize = 0x7D4
// Game side (main 0xc6deac) sets isUseUtf8 = 1 after MakePreset and reads back as a C string (0x1b66640 strlen); UTF-16 output is supported as well per the original convention.
// No window and DM_KBD unset: return as cancel (no popup, no hang). DM_KBD="text": no popup, return that text directly as OK (windowless testing / lockstep comparison).
#include "hle.h"
#include <unistd.h>
#include "front.h"

enum { ARG_HEADER = 0x24, ARG_SUB = 0xa6, ARG_GUIDE = 0x1a8, ARG_MAXLEN = 0x3ac, ARG_MINLEN = 0x3b0, ARG_UTF8 = 0x3bd,
       ARG_INIT_OFF = 0x3c0, ARG_INIT_LEN = 0x3c4, ARG_WORKBUF = 0x4d0,
       HEADER_N = 65, SUB_N = 129, GUIDE_N = 257 };
#define SWKBD_RESULT_CANCELED 0x29Fu   // swkbd module 159 / description 1: the constant the SDK returns when CloseResult != 0

// UTF-16 (at most n units, stops at 0) → UTF-8, written to out (cap includes the terminating 0), returns the number of bytes written
size_t swkbd_u16_to_u8(const uint16_t *s, size_t n, char *out, size_t cap) {
    size_t o = 0;
    for (size_t i = 0; i < n && s[i]; i++) {
        uint32_t c = s[i];
        if (c >= 0xD800 && c < 0xDC00 && i + 1 < n && s[i + 1] >= 0xDC00 && s[i + 1] < 0xE000) c = 0x10000 + ((c - 0xD800) << 10) + (s[++i] - 0xDC00);
        char b[4]; int k = c < 0x80 ? (b[0] = (char)c, 1) : c < 0x800 ? (b[0] = (char)(0xC0 | c >> 6), b[1] = (char)(0x80 | (c & 63)), 2)
                 : c < 0x10000 ? (b[0] = (char)(0xE0 | c >> 12), b[1] = (char)(0x80 | (c >> 6 & 63)), b[2] = (char)(0x80 | (c & 63)), 3)
                 : (b[0] = (char)(0xF0 | c >> 18), b[1] = (char)(0x80 | (c >> 12 & 63)), b[2] = (char)(0x80 | (c >> 6 & 63)), b[3] = (char)(0x80 | (c & 63)), 4);
        if (o + k + 1 > cap) break;
        memcpy(out + o, b, k); o += k;
    }
    if (cap) out[o] = 0;
    return o;
}
// UTF-8 → UTF-16, at most max_units units (surrogate pairs are not split), written to out (cap units including the terminating 0), returns the unit count
size_t swkbd_u8_to_u16(const char *s, size_t max_units, uint16_t *out, size_t cap) {
    size_t o = 0; const uint8_t *p = (const uint8_t *)s;
    while (*p) {
        uint32_t c; int k = *p < 0x80 ? 1 : *p < 0xE0 ? 2 : *p < 0xF0 ? 3 : 4;
        c = k == 1 ? *p : k == 2 ? *p & 31 : k == 3 ? *p & 15 : *p & 7;
        for (int j = 1; j < k; j++) { if ((p[j] & 0xC0) != 0x80) { k = j; break; } c = c << 6 | (p[j] & 63); }
        size_t need = c >= 0x10000 ? 2 : 1;
        if (o + need > max_units || o + need + 1 > cap) break;
        if (need == 2) { c -= 0x10000; out[o++] = (uint16_t)(0xD800 | c >> 10); out[o++] = (uint16_t)(0xDC00 | (c & 0x3FF)); }
        else out[o++] = (uint16_t)c;
        p += k;
    }
    if (cap) out[o] = 0;
    return o;
}

// Core (called directly by unit tests): decode the display parameters from arg, get the user text through input (returns 1 OK / 0 cancel / -1 no window), write back out per the arg convention
// The game's offline character name rule (original image, judged byte by byte): 2–15 bytes, first and last must be a "letter", '-' and '_' at most one in total, the rest must be letters. The original game only accepts ASCII letters;
// hle_charname.c also lets bytes ≥0x80 through (Chinese names), so the rule becomes: English letters or Chinese characters, at most 15 UTF-8 bytes in total (3 bytes per Chinese character, at most 5).
// While the naming panel is open the front end blocks on the spot by this rule and writes the rule in the dialog. diag.c maintains this flag from UI messages.
int g_swkbd_name_panel;
int g_swkbd_numeric_max = -1;   // ≥0 = this input is a quantity box, value = upper limit (set by dm_textinput.c, read by the front end input box, set back to -1 after use)
int (*g_swkbd_unfilter)(void);   // registered by the host (dm_charname_unfilter in hle_charname.c; NULL in unit tests): keyboard requests from the naming panel bypass the game's ASCII typing filter
typedef int (*swkbd_input_fn)(const char *title, const char *sub, const char *guide, const char *initial, int max_chars, char *out, int out_cap);
Result swkbd_show(void *out, const void *arg_, swkbd_input_fn input) {
    const uint8_t *arg = arg_;
    char title[HEADER_N * 3 + 1], sub[SUB_N * 3 + 1], guide[GUIDE_N * 3 + 1], init[501 * 3 + 1] = "", text[1002 * 3 + 1];
    swkbd_u16_to_u8((const uint16_t *)(arg + ARG_HEADER), HEADER_N, title, sizeof title);
    swkbd_u16_to_u8((const uint16_t *)(arg + ARG_SUB), SUB_N, sub, sizeof sub);
    swkbd_u16_to_u8((const uint16_t *)(arg + ARG_GUIDE), GUIDE_N, guide, sizeof guide);
    int32_t maxlen, ilen, ioff; memcpy(&maxlen, arg + ARG_MAXLEN, 4); memcpy(&ilen, arg + ARG_INIT_LEN, 4); memcpy(&ioff, arg + ARG_INIT_OFF, 4);
    const uint8_t *work; memcpy(&work, arg + ARG_WORKBUF, 8);
    if (ilen > 0 && work) swkbd_u16_to_u8((const uint16_t *)(work + ioff), (size_t)ilen, init, sizeof init);

    const char *script = getenv("DM_KBD");
    // Freeze the guest clock while the keyboard is up (in offline single-player, monsters should not keep attacking while the player types, nor should ticks be caught up on return; this follows the native iOS experience, not the original game's Switch semantics of "the clock keeps running while an applet holds the foreground")
    if (!script) guest_clock_freeze_for(2, 1);
    int r = script ? (snprintf(text, sizeof text, "%s", script), 1) : input(title, sub, guide, init, maxlen > 0 ? maxlen : 0, text, sizeof text);
    if (!script) guest_clock_freeze_for(2, 0);
    g_swkbd_numeric_max = -1;   // the numeric box mark applies to this one time only (set by dm_textinput.c before bringing up the keyboard)
    LOG("swkbd: title '%s' initial '%s' limit %d → %s%s%s", title, init, maxlen,
        r > 0 ? "OK '" : r == 0 ? "cancel" : "no window, treated as cancel", r > 0 ? text : "", r > 0 ? "'" : "");
    if (r <= 0) return SWKBD_RESULT_CANCELED;
    if (g_swkbd_name_panel && g_swkbd_unfilter && g_swkbd_unfilter()) LOG("swkbd: naming panel -- turned off the game's ASCII input filter on the returned string (Chinese names allowed, see hle_charname.c)");

    uint8_t *buf; uint64_t cap; memcpy(&buf, (uint8_t *)out, 8); memcpy(&cap, (uint8_t *)out + 8, 8);
    if (!buf || !cap) return RES_OK;                         // same as the SDK: if String has no buffer, the text is not read
    memset(buf, 0, cap);
    uint16_t u16[1003]; size_t n = swkbd_u8_to_u16(text, maxlen > 0 ? (size_t)maxlen : 1002, u16, 1003);   // truncate to the character limit (counted in UTF-16 units)
    if (arg[ARG_UTF8]) swkbd_u16_to_u8(u16, n, (char *)buf, cap);
    else memcpy(buf, u16, (n + 1) * 2 <= cap ? n * 2 : (cap / 2 - 1) * 2);
    { char fin[64]; swkbd_u16_to_u8(u16, n, fin, sizeof fin); void dm_ui_text_entered(const char *text); dm_ui_text_entered(n > 0 ? fin : NULL); }
    { const char *lag = getenv("DM_TEST_SWKBD_LAG_MS"); if (lag) usleep((useconds_t)atoi(lag) * 1000); }   // test: slow down "keyboard handed back → the game's thread gets the result" to verify that auto-accept does not jump the gun   // front end path cleanup (dm_cursor.c): auto-accept after the name is typed on the naming page
    return RES_OK;
}

HLE_FORCE("_ZN2nn5swkbd12ShowKeyboardEPNS0_6StringERKNS0_15ShowKeyboardArgE", "software keyboard applet → host native input box (DM_KBD gives the text directly)",
          Result, h_swkbd_Show, void *out, const void *arg) {
    return swkbd_show(out, arg, front_text_input);
}

// ---------- InlineKeyboard (Super Mario 3D World + Bowser's Fury) ----------
// On hardware Initialize starts a resident keyboard applet (swkbd::detail::InlineKeyboardImpl::Launch -> applet::CreateLibraryApplet); after that Calc collects its results every frame and calls the callbacks the game registered,
// Appear / Disappear / SetInputText / SetCursorPos send requests through applet storage, and GetImage takes the keyboard picture from shared memory. The host has no applet proxy: entering the save select after the character select, Initialize crashed on a null pointer in CreateLibraryApplet.
// Every entry that touches the applet is taken over here and behaves as a keyboard the player always cancels right away: Appear arms one cancel, and the next Calc (on hardware the callbacks are called from Calc too) calls the game's cancel callback; no picture (GetImage reports none).
// The constructor, GetRequiredWorkBufferSize / GetImageMemoryRequirement / GetRequiredStringBufferSize and InputText::Set are pure computations and keep running in the SDK
typedef void (*ikb_cb0)(void);
static struct { const void *kb; ikb_cb0 cancel; int pending; } g_ikb[4];
static pthread_mutex_t g_ikb_mu = PTHREAD_MUTEX_INITIALIZER;
static int ikb_slot(const void *kb) {   // the caller holds the lock
    for (int i = 0; i < 4; i++) if (g_ikb[i].kb == kb) return i;
    for (int i = 0; i < 4; i++) if (!g_ikb[i].kb) { g_ikb[i].kb = kb; return i; }
    return -1;
}
HLE_FORCE("_ZN2nn5swkbd14InlineKeyboard10InitializeEPv", "inline keyboard: no applet started (the host has no applet proxy), reports success", unsigned, h_ikb_Init, void *kb, void *work) {
    (void)work; pthread_mutex_lock(&g_ikb_mu); int i = ikb_slot(kb); pthread_mutex_unlock(&g_ikb_mu);
    LOG("swkbd: inline keyboard Initialize %p (the host starts no applet; Appear always counts as the player cancelling)%s", kb, i < 0 ? "[RED] registration table full" : "");
    return 1;
}
HLE_FORCE("_ZN2nn5swkbd14InlineKeyboard8FinalizeEv", "inline keyboard: no applet started, nothing to close", void, h_ikb_Fin, void *kb) {
    pthread_mutex_lock(&g_ikb_mu); for (int i = 0; i < 4; i++) if (g_ikb[i].kb == kb) memset(&g_ikb[i], 0, sizeof g_ikb[i]); pthread_mutex_unlock(&g_ikb_mu);
}
HLE_FORCE("_ZN2nn5swkbd14InlineKeyboardD1Ev", "inline keyboard destructor: no applet started, only clears the registration", void, h_ikb_Dtor, void *kb) { h_ikb_Fin(kb); }
HLE_FORCE("_ZN2nn5swkbd14InlineKeyboard24SetDecidedCancelCallbackEPFvvE", "inline keyboard: records the cancel callback", void, h_ikb_SetCancel, void *kb, ikb_cb0 fn) {
    pthread_mutex_lock(&g_ikb_mu); int i = ikb_slot(kb); if (i >= 0) g_ikb[i].cancel = fn; pthread_mutex_unlock(&g_ikb_mu);
}
#define IKB_IGNORE_CB(mangled, cname) \
    HLE_FORCE(mangled, "inline keyboard: callbacks are recorded, never called (the keyboard never confirms / edits text / moves the cursor)", void, cname, void *kb, void *fn) { (void)kb; (void)fn; }
IKB_IGNORE_CB("_ZN2nn5swkbd14InlineKeyboard22SetMovedCursorCallbackEPFvPKNS0_14MovedCursorArgEE", h_ikb_SetMoved)
IKB_IGNORE_CB("_ZN2nn5swkbd14InlineKeyboard23SetDecidedEnterCallbackEPFvPKNS0_15DecidedEnterArgEE", h_ikb_SetEnter)
IKB_IGNORE_CB("_ZN2nn5swkbd14InlineKeyboard24SetChangedStringCallbackEPFvPKNS0_16ChangedStringArgEE", h_ikb_SetChanged)
IKB_IGNORE_CB("_ZN2nn5swkbd14InlineKeyboard27SetFinishedKeyboardCallbackEPFvvE", h_ikb_SetFinished)
HLE_FORCE("_ZN2nn5swkbd14InlineKeyboard6AppearERKNS0_9AppearArgE", "inline keyboard appears: the host does not show it, the next Calc counts as the player cancelling", void, h_ikb_Appear, void *kb, const void *arg) {
    (void)arg; pthread_mutex_lock(&g_ikb_mu); int i = ikb_slot(kb); if (i >= 0) g_ikb[i].pending = 1; pthread_mutex_unlock(&g_ikb_mu);
    LOG("swkbd: inline keyboard Appear %p → cancel on the next tick", kb);
}
HLE_FORCE("_ZN2nn5swkbd14InlineKeyboard9DisappearEv", "inline keyboard hidden: the host never showed it", void, h_ikb_Disappear, void *kb) {
    pthread_mutex_lock(&g_ikb_mu); int i = ikb_slot(kb); if (i >= 0) g_ikb[i].pending = 0; pthread_mutex_unlock(&g_ikb_mu);
}
HLE_FORCE("_ZN2nn5swkbd14InlineKeyboard4CalcEv", "inline keyboard per-frame update: calls the game's cancel callback when a cancel is pending", void, h_ikb_Calc, void *kb) {
    ikb_cb0 fn = NULL; pthread_mutex_lock(&g_ikb_mu); int i = ikb_slot(kb);
    if (i >= 0 && g_ikb[i].pending) { g_ikb[i].pending = 0; fn = g_ikb[i].cancel; }
    pthread_mutex_unlock(&g_ikb_mu);
    if (fn) fn();   // guest code, called on the guest thread that called Calc (as on hardware)
}
HLE_FORCE("_ZN2nn5swkbd14InlineKeyboard12SetInputTextERKNS0_9InputTextE", "inline keyboard: set text (the host does not show it, ignored)", void, h_ikb_SetText, void *kb, const void *t) { (void)kb; (void)t; }
HLE_FORCE("_ZN2nn5swkbd14InlineKeyboard12SetCursorPosEi", "inline keyboard: set cursor (the host does not show it, ignored)", void, h_ikb_SetCursor, void *kb, int pos) { (void)kb; (void)pos; }
HLE_FORCE("_ZN2nn5swkbd14InlineKeyboard8GetImageEPvm", "inline keyboard image: none (returns false)", unsigned, h_ikb_GetImage, void *kb, void *buf, size_t n) { (void)kb; (void)buf; (void)n; return 0; }
HLE_FORCE("_ZNK2nn5swkbd14InlineKeyboard13GetWindowSizeEPiS2_", "inline keyboard window size: 0 × 0", void, h_ikb_WinSize, const void *kb, int *w, int *h) { (void)kb; if (w) *w = 0; if (h) *h = 0; }
