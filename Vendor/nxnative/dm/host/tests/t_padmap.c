// Physical controller face button mapping (dm_padmap.h): each type x four face buttons -> game keys. Expected values are hand-written from
// the rule: whatever letter is printed is that game key; Nintendo glyphs are right A, bottom B, top X, left Y, Xbox glyphs are bottom A,
// right B, left X, top Y; everything else is laid out as Xbox.
#include <stdio.h>
#include "../dm_padmap.h"
static int checks, fails;
#define CHECK(c, ...) do { checks++; if (c) printf("  ✓ "); else { fails++; printf("  ✗ "); } printf(__VA_ARGS__); printf("\n"); } while (0)
int main(void) {
    struct { const char *cat, *ven; int kind; } id[] = {
        { "Switch Pro Controller", "Pro Controller", DM_PADKIND_NINTENDO }, { "Nintendo Switch Joy-Con (L/R)", "Joy-Con (L/R)", DM_PADKIND_NINTENDO },
        { "Nintendo Switch Joy-Con (L)", "Joy-Con (L)", DM_PADKIND_NINTENDO }, { "MFi", "NINTENDO compatible pad", DM_PADKIND_NINTENDO },
        { "Xbox One", "Xbox Wireless Controller", DM_PADKIND_XBOX }, { "DualSense", "DualSense Wireless Controller", DM_PADKIND_XBOX },
        { "DualShock 4", "DUALSHOCK 4 Wireless Controller", DM_PADKIND_XBOX }, { "MFi", "SteelSeries Nimbus", DM_PADKIND_XBOX }, { NULL, NULL, DM_PADKIND_XBOX }, { "", "", DM_PADKIND_XBOX } };
    for (unsigned i = 0; i < sizeof id / sizeof *id; i++) CHECK(dm_padmap_kind(id[i].cat, id[i].ven) == id[i].kind, "category '%s' vendor name '%s' → %s layout", id[i].cat ? id[i].cat : "(empty)", id[i].ven ? id[i].ven : "(empty)", id[i].kind ? "Nintendo" : "Xbox");
    // bottom right left top
    CHECK(dm_padmap_face(DM_PADKIND_NINTENDO, 1, 0, 0, 0) == DM_BTN_B, "Nintendo: bottom = B"); CHECK(dm_padmap_face(DM_PADKIND_NINTENDO, 0, 1, 0, 0) == DM_BTN_A, "Nintendo: right = A");
    CHECK(dm_padmap_face(DM_PADKIND_NINTENDO, 0, 0, 1, 0) == DM_BTN_Y, "Nintendo: left = Y"); CHECK(dm_padmap_face(DM_PADKIND_NINTENDO, 0, 0, 0, 1) == DM_BTN_X, "Nintendo: top = X");
    CHECK(dm_padmap_face(DM_PADKIND_XBOX, 1, 0, 0, 0) == DM_BTN_A, "Xbox: bottom = A"); CHECK(dm_padmap_face(DM_PADKIND_XBOX, 0, 1, 0, 0) == DM_BTN_B, "Xbox: right = B");
    CHECK(dm_padmap_face(DM_PADKIND_XBOX, 0, 0, 1, 0) == DM_BTN_X, "Xbox: left = X"); CHECK(dm_padmap_face(DM_PADKIND_XBOX, 0, 0, 0, 1) == DM_BTN_Y, "Xbox: top = Y");
    CHECK(dm_padmap_face(DM_PADKIND_XBOX, 1, 1, 0, 0) == (DM_BTN_A | DM_BTN_B), "two pressed at once: each counted on its own"); CHECK(dm_padmap_face(DM_PADKIND_NINTENDO, 0, 0, 0, 0) == 0, "none pressed = 0");
    printf("== %d checks, %d failed ==\n", checks, fails);
    return fails != 0;
}
