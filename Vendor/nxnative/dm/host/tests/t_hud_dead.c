// Unit test for hiding the bottom bar on death: mode -> dead, bottom bar show/hide decision (dm_hud.h). Expected values are hand-written from the game code: main+0x6e5c48 player mode 0 / 0x11 means dead
#include <stdio.h>
#include "dm_hud.h"
static int fails, cases;
static void expect(const char *what, int got, int want) {
    cases++; if (got == want) printf("✓ %s\n", what); else { fails++; printf("✗ %s: got %d, expected %d\n", what, got, want); }
}
int main(void) {
    char buf[64];
    for (unsigned m = 0; m <= 19; m++) {   // D2 player modes 0..19 (DEATH ... KNOCKBACK)
        snprintf(buf, sizeof buf, "mode %u %s", m, (m == 0 || m == 17) ? "→ dead" : "→ alive");
        expect(buf, dm_hud_player_mode_dead(m), m == 0 || m == 17);
    }
    expect("mode 0xffffffff (out of range) → alive", dm_hud_player_mode_dead(0xffffffffu), 0);
    dm_hud_info h = {0}; h.valid = 1;
    for (unsigned m = 0; m <= 19; m++) {
        h.dead = dm_hud_player_mode_dead(m);
        snprintf(buf, sizeof buf, "normal in-game state, mode %u → bottom bar %s", m, (m == 0 || m == 17) ? "hidden" : "shown");
        expect(buf, dm_hud_bar_visible(&h, 0, 0), !(m == 0 || m == 17));
    }
    h.dead = 0;
    expect("alive but in navigation state → hidden", dm_hud_bar_visible(&h, 1, 0), 0);
    expect("alive but covered by a panel → hidden", dm_hud_bar_visible(&h, 0, 1), 0);
    h.valid = 0; expect("player not read → hidden", dm_hud_bar_visible(&h, 0, 0), 0);
    printf("%s t_hud_dead %d/%d\n", fails ? "FAIL" : "OK", cases - fails, cases);
    return fails != 0;
}
