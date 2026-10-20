// Language source of dm_i18n.c: once the game has set the language (the SetLanguage observation gate writes g_dm_lang), that value
// wins; if not, read "Language" from Settings/Settings.json in the save data;
// no settings file = first install, use the system language (simulated in tests with DM_LANG). Our own UI text (dm_ui, for UIKit text) is English
// in every language.
// Expected values come from the rule itself (for the language index table see the name table at main+0x20ae478 in diag.c), without running the game.
// Each case needs its own process (the file is read once and then cached), so this program runs one case per argv and the Makefile invokes them one
// by one.
#include "../dm_i18n.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
static int fails;
static void expect(const char *what, const char *got, const char *want) { int ok = !strcmp(got, want); if (!ok) fails++; printf("%s %s: expected '%s' → got '%s'\n", ok ? "✓" : "✗", what, want, got); }
int main(int argc, char **argv) {
    const char *mode = argc > 1 ? argv[1] : "";
    char dir[512]; snprintf(dir, sizeof dir, "%s/i18n_%s", getenv("TMPDIR") ? getenv("TMPDIR") : "/tmp", mode);
    char sd[600], f[700]; snprintf(sd, sizeof sd, "%s/Settings", dir); snprintf(f, sizeof f, "%s/Settings.json", sd);
    mkdir(dir, 0755); mkdir(sd, 0755); remove(f); setenv("DM_SAVE", dir, 1);
    if (!strcmp(mode, "en") || !strcmp(mode, "game")) { FILE *o = fopen(f, "w"); fputs("{\n    \"Item Name Display\": 1,\n    \"Language\": 0,\n    \"AutoMapMode\": 2\n}\n", o); fclose(o); }
    if (!strcmp(mode, "zh")) { FILE *o = fopen(f, "w"); fputs("{ \"Language\": 8 }", o); fclose(o); }
    if (!strcmp(mode, "en")) expect("settings file Language 0, game has not set it", dm_ui("dmConfirm"), "OK");
    else if (!strcmp(mode, "zh")) expect("settings file Language 8 (our text stays English)", dm_ui("dmConfirm"), "OK");
    else if (!strcmp(mode, "none")) { unsetenv("DM_LANG"); expect("no settings file, no system language given (Mac default English)", dm_ui("dmConfirm"), "OK"); }
    else if (!strcmp(mode, "sysen")) { setenv("DM_LANG", "en-US", 1); expect("no settings file (first install), system language en-US", dm_ui("dmConfirm"), "OK"); }
    else if (!strcmp(mode, "systw")) { setenv("DM_LANG", "zh-Hant-TW", 1); expect("no settings file, system language zh-Hant-TW (our text stays English)", dm_ui("dmConfirm"), "OK"); }
    else if (!strcmp(mode, "tags")) {   // language tag → the original game's language index
        static const struct { const char *t; int want; } c[] = { { "en-US", 0 }, { "en-GB", 0 }, { "zh-Hans-CN", 8 }, { "zh-Hans", 8 }, { "zh", 8 }, { "zh-Hans-HK", 8 }, { "zh-Hans-TW", 8 }, { "zh-Hans-MO", 8 },
            { "zh-Hant-TW", 8 }, { "zh-Hant-HK", 8 }, { "zh-Hant", 8 }, { "zh-HK", 8 }, { "zh_TW", 8 }, { "yue-Hant-HK", 8 }, { "yue-Hans-CN", 8 }, { "yue", 8 }, { "wuu-Hans-CN", 8 },
            { "de-DE", 0 }, { "es-ES", 0 }, { "es-419", 0 }, { "fr-CA", 0 }, { "it-IT", 0 }, { "ko-KR", 0 }, { "pl-PL", 0 }, { "ru-RU", 0 }, { "ja-JP", 0 }, { "pt-BR", 0 }, { "nl-NL", 0 }, { "ar", 0 }, { "zu-ZA", 0 } };
        for (unsigned i = 0; i < sizeof c / sizeof *c; i++) { char w[8], g[8]; snprintf(w, sizeof w, "%d", c[i].want); snprintf(g, sizeof g, "%d", dm_lang_from_tag(c[i].t)); expect(c[i].t, g, w); } }
    else if (!strcmp(mode, "game")) {   // the settings file says English, then the game switches to Simplified Chinese, zhTW (9) and deDE: our text stays English throughout
        expect("before the game sets it, the settings file decides", dm_ui("dmConfirm"), "OK");
        atomic_store(&g_dm_lang, 8); expect("game switches to zhCN (our text stays English)", dm_ui("dmConfirm"), "OK");
        atomic_store(&g_dm_lang, 9); expect("game switches to zhTW (our text stays English)", dm_ui("dmConfirm"), "OK");
        atomic_store(&g_dm_lang, 1); expect("game switches to deDE (English)", dm_ui("dmConfirm"), "OK");
        expect("a key missing from the table comes back as it is", dm_ui("dmNoSuchKey"), "dmNoSuchKey"); }
    else { fprintf(stderr, "usage: t_i18n en|zh|none|sysen|systw|tags|game\n"); return 2; }
    return fails ? 1 : 0;
}
