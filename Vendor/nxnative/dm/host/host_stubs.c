// Hook points left behind by the game-specific modules split out of d2r-mobile (diagnostic tick gates, TACT/Granny, UI screen, touch UI interaction, ...):
// the generic host still calls them, and they get empty implementations here. When a feature is redone for this game, replace the matching stub with the real thing.
#include "dm.h"
#include "front.h"

void crash_sample_self(void) {}
void inflate_bench_maybe(void) {}
void ticks_install(void) {}
void target_rank_install(void) {}
void dm_padmode_boot(void) {}
void dm_prof_mark(const char *seg) { (void)seg; }
void dm_prof_add(int id, uint64_t ns, uint64_t bytes) { (void)id; (void)ns; (void)bytes; }
void tact_chk_init(void) {}
void tact_prefetch_start(const char *outdir) { (void)outdir; }
void tact_prefetch_stop(void) {}
void granny_prof_dump(void) {}
void uimsg_subscribe(void (*fn)(const char *cat, const char *act, const char *arg)) { (void)fn; }
void dm_ui_text_entered(const char *text) { (void)text; }
int dm_custom_lang_explicit(void) { return 0; }
int dm_ingame_now(void) { return 0; }
void dm_uiscreen_res_reread(void) {}
// Game resolution: whatever the front end gives (Mac window / iOS screen), without D2R's UI-screen rewriting
uint64_t dm_game_res(int docked) { return front_game_res(docked); }
int dm_screen_real(int *w, int *h) { *w = *h = 0; return 0; }
void dm_ui_rect(int *x, int *y, int *w, int *h) { *x = *y = *w = *h = 0; }
// svc #0x80.. host gates: only D2R's rewrite rules create them; they should not appear in this game's build output
uint64_t svc_host_call(int num, uint64_t *regs) { (void)regs; die("svc_host_call: this game has no host gate svc #%#x", num); }
