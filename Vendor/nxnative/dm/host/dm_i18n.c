// String lookup for the UI text we added ourselves. Our own UI text is English only, whatever language the game is set to.
// Table: dm_i18n_tab.h (key, English), kept by hand and compiled into this file.
//   - dm_str: text drawn inside the game (layouts write "@key") goes through the original string lookup at main+0x7f5630 first and falls back to the
//     table when the game's string tables lack the key.
//   - dm_ui: places the game cannot draw (UIKit alerts, the asset download page, shared file names, bottom-bar glyphs) read the table directly.
// The game's own language (dm_lang_index, a separate matter from our text): once the game has set it (SetLanguage observation gate), that value wins;
// before that (asset download page, before entering the front end) read "Language" from Settings/Settings.json in the save data;
//   no settings file = first install, use the iOS system language (dm_sys_lang).
#include "dm_i18n.h"
#include "dm_i18n_tab.h"
#include <TargetConditionals.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

_Atomic int g_dm_lang = -1;

#if TARGET_OS_IPHONE
#include <CoreFoundation/CoreFoundation.h>
#endif
// Language tag (BCP 47, e.g. en-US, zh-Hans-CN, zh-Hant-TW, yue-Hant-HK) → the original game's language index. Only two outcomes: a language code that
// is Chinese (zh) or a Chinese variety
// (yue Cantonese, wuu Wu, hak Hakka, nan Min Nan, cmn Mandarin, gan Gan, hsn Xiang, lzh Literary Chinese) → 8 Simplified Chinese, regardless of script
// and region; everything else → 0 English, because nobody has verified the original game's other languages such as German / Japanese. Empty tag = English
int dm_lang_from_tag(const char *t) {
    if (!t || !*t) return 0;
    char l[4] = { 0 }; int i = 0; while (i < 3 && t[i] && t[i] != '-' && t[i] != '_') { l[i] = (char)(t[i] | 0x20); i++; }
    static const char *const zh[] = { "zh", "yue", "wuu", "hak", "nan", "cmn", "gan", "hsn", "lzh" };
    for (unsigned k = 0; k < sizeof zh / sizeof *zh; k++) if (!strcmp(l, zh[k])) return 8;
    return 0;
}
// Language on first install (no settings file yet): by the first entry of the iOS preferred languages (CFLocaleCopyPreferredLanguages, through dm_lang_from_tag: Chinese and Sinitic varieties → Simplified Chinese, everything else → English).
// It used to be always Simplified Chinese (back then the touch version had no way to change the language, and a Chinese player whose system was in English got the English version on a fresh install and could not change it back); the Custom page title row now has a language switch (dm_custom.c lang_en), so this is opened up.
// DM_LANG (host / test simulation, same as hle_oe.c) takes priority; a non-iOS host has no system language to ask and uses English, the default game language
int dm_sys_lang(void) {
    const char *e = getenv("DM_LANG"); if (e && *e) return dm_lang_from_tag(e);
#if TARGET_OS_IPHONE
    int r = 0; CFArrayRef a = CFLocaleCopyPreferredLanguages();
    if (a) { if (CFArrayGetCount(a) > 0) { char t[64]; if (CFStringGetCString((CFStringRef)CFArrayGetValueAtIndex(a, 0), t, sizeof t, kCFStringEncodingUTF8)) r = dm_lang_from_tag(t); } CFRelease(a); }
    return r;
#else
    return 0;
#endif
}

static int settings_lang(void) {   // "Language" in the settings file; file missing = first install, use the system language (hle_fs.c writes the same value when it first creates the settings file); file present but key missing = -1
    const char *sv = getenv("DM_SAVE"); if (!sv) return dm_sys_lang();
    char path[1200]; snprintf(path, sizeof path, "%s/Settings/Settings.json", sv);
    FILE *f = fopen(path, "rb"); if (!f) return dm_sys_lang();
    char buf[8192]; size_t n = fread(buf, 1, sizeof buf - 1, f); fclose(f); buf[n] = 0;
    const char *k = strstr(buf, "\"Language\""); if (!k) return -1;
    k = strchr(k + 10, ':'); return k ? atoi(k + 1) : -1;
}

int dm_lang_index(void) {
    int l = atomic_load(&g_dm_lang); if (l >= 0) return l;
    static _Atomic int file = -2; int f = atomic_load(&file); if (f == -2) { f = settings_lang(); atomic_store(&file, f); }
    return f < 0 ? 0 : f;   // settings file exists but has no language entry = the game default (the host reports en-US)
}

const char *dm_ui(const char *key) {   // our own UI text is English only; a key missing from the table comes back as it is
    for (unsigned i = 0; i < sizeof k_dm_i18n / sizeof *k_dm_i18n; i++) if (!strcmp(k_dm_i18n[i].k, key)) return k_dm_i18n[i].en;
    return key;
}

const char *dm_str(uint8_t *b, const char *key) {
    if (!b) return dm_ui(key);
    struct { const char *k; uint64_t n; } s = { key, strlen(key) };
    const char *r = ((const char *(*)(void *))(b + 0x7f5630))(&s);
    return r && *r && strcmp(r, key) ? r : dm_ui(key);   // if the game's string tables lack this key, fall back to the compile-time table
}
