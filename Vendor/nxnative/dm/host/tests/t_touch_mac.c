#include <stdio.h>
#include <stdlib.h>
#include "../dm.h"
#include "../touch_mac.c"
#include "../../ios/Sources/dm_touch_controls.c"

uint64_t now_ns(void) { return 0; }
void (*dm_pad_hook)(uint64_t, uint64_t *, int32_t *, int32_t *, int32_t *, int32_t *);
uint64_t guest_ns(void) { return 0; }
uint64_t dm_guest_frame(void) { return 0; }   // the UI mouse / front-end paths run on the presented-frame cadence; this unit test does not test them
int dm_world_has_target(void) { return 1; }   // stub for world tapping (dm_world.c): has a target = the primary button sends its key as usual
unsigned dm_world_tap(float nx, float ny) { (void)nx; (void)ny; return 0; }
int dm_shop_open(void) { return 0; }   // stub for the vendor page (dm_actions.c): not open
int dm_padmode_current(void) { return 0; }   // Stub for controller / touch mode (dm_padmode.c): touch
uint64_t dm_padmode_page_keys(uint64_t m) { (void)m; return 0; } void dm_padmode_legend_hide(const char *l, int a) { (void)l; (void)a; } int dm_padmode_busy(void) { return 0; } uint64_t dm_padmode_page_held(void) { return 0; } void dm_padmode_page_pulse(uint64_t m) { (void)m; } void dm_padmode_ident_hint(int on) { (void)on; } void dm_padmode_legend(int a, const char *t) { (void)a; (void)t; } const char *dm_str(uint8_t *b, const char *k) { (void)b; return k; }   // Stubs for controller page keys / button legend / string fetch (used by controller paging of the personal stash, not reached under touch)
int dm_swapskill_wset(void) { return -1; }
int dm_pages_cur(void) { return 0; } int dm_pages_count(void) { return 5; } void dm_pages_request_flip(int d) { (void)d; }   // stubs for the multi-page personal stash (dm_pages.c)
void dm_vault_ui_flip(int dir) { (void)dir; }
int dm_vault_ui_pager_hit(int x, int y) { (void)x; (void)y; return 0; }
void dm_vault_request_deposit(uint32_t id) { (void)id; }
uint32_t dm_vault_ui_held(void) { return 0; }
int dm_vault_ui_over(int x, int y) { (void)x; (void)y; return 0; }
int dm_vault_ui_tip_gate(int x, int y) { (void)x; (void)y; return 0; }
int dm_pouch_tip_gate(int x, int y) { (void)x; (void)y; return 0; }
int dm_vault_ui_blocks(int x, int y) { (void)x; (void)y; return 0; }
int dm_vault_ui_tap(int x, int y) { (void)x; (void)y; return 0; }
int dm_vault_ui_drag(int phase, int x, int y) { (void)phase; (void)x; (void)y; return 0; }
uint32_t dm_swapskill_itemsig(void) { return 0; }   // stub for the current weapon set of the swap-set skill (dm_actions.c): cannot be read
_Atomic int g_dm_frz_want, g_dm_frozen; void dm_freeze_frame(int want) { (void)want; }   // stub for the panel freeze (diag.c)
void dm_elysium_arm(int on) { (void)on; }   // stub for the Elysium checkbox (dm_elysium.c)
void dm_custom_on_uimsg(const char *cat, const char *act, const char *arg) { (void)cat; (void)act; (void)arg; }   // stub for the "Custom" settings (dm_custom.c)
void dm_belt_put(unsigned id) { (void)id; }
void dm_ui_rect(int *x, int *y, int *w, int *h) { *x = *y = *w = *h = 0; }
int dm_screen_real(int *w, int *h) { (void)w; (void)h; return 0; }
int dm_uiscreen_ingame(void) { return 0; }
void dm_uiscreen_set_ingame(int on) { (void)on; }   // stub for the UI rectangle (dm_uiscreen.c): true full screen not enabled
void dm_inv_sort(int page) { (void)page; }
int dm_diag_difficulty(void) { return -1; }
uint64_t dm_fs_commit_count(void) { return 0; }
void dm_held_equip(int bodyloc) { (void)bodyloc; }
int dm_rift_merc_unlocked(void) { return 1; }
int dm_rift_merc_slot_empty(int loc) { (void)loc; return 0; }
void dm_rift_merc_locked_hint(void) {}
void dm_stash_take(int count) { (void)count; }
void dm_shop_buy(void) {}
int dm_cursor_item(void *out) { (void)out; return 0; }
void dm_shop_sell_cursor(void) {}
module_t g_mod[MAX_MOD]; int g_nmod;
static void (*ui_cb)(const char *, const char *, const char *);
static uint32_t test_tick;
uint32_t dm_cur_tick(void) { return test_tick; }
static int test_loadscreen_down;
int dm_loadscreen_down(void) { return test_loadscreen_down; }   // the real check is in diag.c; the unit test sets it by hand following the loading screen messages
int dm_loadscreen_up(void) { return 0; }      // in the unit test the loading screen does not block starting a run: the freeze is not triggered
void dm_hold_for_loadscreen(void) {}
void uimsg_subscribe(void (*f)(const char *, const char *, const char *)) { ui_cb = f; }
static int checks, fails;
#define CHECK(c, s) do { checks++; if (!(c)) { fails++; printf("FAIL %s\n", s); } else printf("PASS %s\n", s); } while (0)

int main(void) {
    const char *path = "build/touch_host.script";
    FILE *f = fopen(path, "w"); if (!f) return 2;
    fputs("0 down 0 90,1220\n0.1 move 0 150,1220\n2.1 up 0\n", f); fclose(f);
    setenv("DM_TOUCH_SCRIPT", path, 1); unsetenv("DM_TOUCH_TEST_DROP");
    uint64_t b = 0; int32_t lx = 0, ly = 0, rx = 0, ry = 0;
    test_tick = 100;
    dm_touch_host_step(0, &b, &lx, &ly, &rx, &ry);
    ui_cb("FrontEndNavigation", "ToGame", "");
    ui_cb("PanelManager", "UnloadPanel", "LoadScreenPanel"); test_loadscreen_down = 1;
    dm_touch_host_step(0, &b, &lx, &ly, &rx, &ry);
    CHECK(lx == 0 && ly == 0, "down only sets the stick origin");
    for (test_tick = 101; test_tick <= 162; test_tick++) {
        b = 0; lx = ly = rx = ry = 0;
        dm_touch_host_step(0, &b, &lx, &ly, &rx, &ry);
    }
    CHECK(lx > 0 && ly == 0, "move writes the host left stick");
    test_tick = 162;
    b = 0; lx = ly = rx = ry = 0; dm_touch_host_step(0, &b, &lx, &ly, &rx, &ry);
    CHECK(lx > 0 && ly == 0, "repeated sampling in the same tick does not advance script time");
    test_tick = 212;
    b = 0; lx = ly = rx = ry = 0; dm_touch_host_step(0, &b, &lx, &ly, &rx, &ry);
    CHECK(lx == 0 && ly == 0, "up clears the host left stick");
    // Cleanup of the mode switch transaction (the "leave" registered in dm_mode_items.h): key presses on the player's behalf queued by touch are voided on a switch; ones the host sends by itself, such as the single "Show Items" press on entering a run, are not among them
    { uint64_t dm_ui_auto_buttons(void); void dm_ui_key_pulse(uint64_t, int), dm_ui_auto_mode_leave(void), dm_ui_cache_mode_leave(void);
      dm_ui_key_pulse(0x40, 1000); CHECK(dm_ui_auto_buttons() == 0x40, "touch button key pulse in flight: the key is among the keys pressed on the player's behalf");
      dm_ui_auto_mode_leave(); CHECK(dm_ui_auto_buttons() == 0, "key pulses in flight are voided by the switch cleanup");
      dm_ui_cache_mode_leave(); CHECK(1, "UI cache cleanup does not crash without a UI root"); }
    printf("== touch host %d checks, %d failed ==\n", checks, fails);
    return fails != 0;
}
void dm_shop_get(dm_shop_info *out) { memset(out, 0, sizeof *out); }   // vendor readout (dm_actions.c): all 0
void dm_item_use(unsigned id) { (void)id; }
int dm_ui_hover_now(int x, int y) { (void)x; (void)y; return 0; }
void dm_item_equip(unsigned id) { (void)id; }
void dm_item_unequip(unsigned id) { (void)id; }
int dm_held_size(int *w, int *h) { (void)w; (void)h; return 0; }
int dm_item_targeting(void) { return 0; }
int dm_vendor_repair_mode(void) { return 0; }
void dm_item_repair(uint32_t id) { (void)id; }
void dm_belt_fill(uint64_t w) { (void)w; }
void dm_item_identify(unsigned id) { (void)id; }
void dm_item_target_cancel(void) {}
void dm_item_compare(int on) { (void)on; }
void dm_held_stow(void) {}
int dm_held_stow_result(void) { return -1; }
int dm_held_pending(void) { return 0; }
void uimsg_emit(const char *cat, const char *act, const char *arg) { (void)cat; (void)act; (void)arg; }
void dm_item_identify_free(unsigned id) { (void)id; }   // stub for free identify (dm_actions.c)
int dm_runeword_long_press(const void *ci) { (void)ci; return 0; }   // stub for the runeword helper (dm_runeword.c)
int dm_runeword_list_open(void) { return 0; }
void dm_runeword_button(const char *name) { (void)name; }
void dm_runeword_list_close(void) {}
