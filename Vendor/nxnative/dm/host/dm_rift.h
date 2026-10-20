// Rift tower climb (dm_rift.c)
#pragma once
#include <stdint.h>
typedef struct { int tier; float progress; int secs_left, done, guardian, inc; } dm_rift_hud_t;
void dm_rift_tick(uint64_t G, uint64_t player, uint8_t *main_base);   // Server tick (diag.c)
void dm_rift_c2s(uint64_t G, const uint8_t *pkt, uint32_t len);      // Client command (door tap)
void dm_rift_client_pump(uint8_t *main_base);                         // At the controller sampling point (dm_world.c): recognize kills and newly spawned monsters
int dm_rift_hud(dm_rift_hud_t *out);                                  // Front end every frame: returns 1 while a rift is in progress / just completed
int dm_rift_active(void);
void dm_rift_gamble_vals(int best, uint32_t *uniq, uint32_t *set);   // Gambling bonus: highest cleared level -> Hell unique / set values (in units of 1/100000); best < 1 = 0 (no bonus)
typedef struct { int menu, best, unlock, def; unsigned ms; int clvl, tier, done, secs_left; float progress; int inc; } dm_rift_menu_t;   // menu 1 = level selection page, 2 = continue / quit; inc = 0 with done set = Guardian defeated after time ran out (not passed)
int dm_rift_cleared_any(void);              // has this character cleared any Greater Rift level (only clears within the time limit count: highest cleared level ≥ 1): the unlock condition for the hard skill point cap (dm_actions.c)
int dm_rift_merc_unlocked(void);            // Whether the new mercenary equipment slots are unlocked (highest rift level cleared ≥ 10)
void dm_rift_merc_locked_hint(void);        // Hint when not unlocked: "Clear Greater Rift Level 10 to unlock"
int dm_rift_tier_level(int tier, int clvl);   // this level's monster level (below level 9, 0 = unchanged)
int dm_rift_tier_hp_x10(int tier, int clvl);  // total life multiplier of this level's monsters ×10 (relative to a native Hell /players 1 monster)
int dm_rift_menu(dm_rift_menu_t *out);      // Front end every frame: the page to show (0 = none)
void dm_rift_menu_close(void);              // Close (the X at the top right)
void dm_rift_menu_start(int tier);          // Level selection page "Enter Rift"
void dm_rift_menu_continue(void);           // "Continue"
void dm_rift_menu_abandon(void);
int dm_rift_menu_pending(void); int dm_rift_menu_seq(void); int dm_rift_swept(uint32_t id);            // "Quit" (after abandoning, the server opens the level selection page again)
void dm_rift_menu_peek(dm_rift_menu_t *out);   // Fetch the page readout even when there is no page to open (chronicle "Rift" page)
void dm_rift_ui_pump(void);                     // dm_rift_ui.c: every frame on the game main thread (dm_actions.c)
void dm_rift_ui_on_uimsg(const char *cat, const char *act, const char *arg);   // UI messages (diag.c)
typedef struct { int best, clears, deaths, tier, unlock; unsigned ms; int fast[101]; } dm_rift_stats_t;
int dm_rift_stats(dm_rift_stats_t *out);    // Kill board "Rift" page readout (sidecar file); returns 0 if there is none
