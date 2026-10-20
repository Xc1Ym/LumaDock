// Unit test of the rift completion door landing points (dm_doorspot.h, takes seconds). The expected values are all computed by hand from the maps, without running the implementation under test.
// Situation: narrow maps of the Cave / Pit kind, the player standing against a wall, and the old rule's ideal point (10 cells with the back to the guardian, offset 5 cells left / right) lands inside a wall.
// Fail → pass: on the same map, the old rule's landing point is a blocked cell (old_spot_blocked); the new rule's landing point must be a reachable cell.
#include "dm_doorspot.h"
#include <stdio.h>

static int fails, checks;
#define CHECK(c, ...) do { checks++; if (!(c)) { fails++; printf("  ✗ "); printf(__VA_ARGS__); printf("\n"); } } while (0)

static struct ds_grid g;
static void fill(int v) { memset(g.blk, v, sizeof g.blk); }
static void rect(int x0, int y0, int x1, int y1, int v) { for (int y = y0; y <= y1; y++) for (int x = x0; x <= x1; x++) if (x >= -DS_R && x <= DS_R && y >= -DS_R && y <= DS_R) g.blk[(y + DS_R) * DS_W + x + DS_R] = (uint8_t)v; }
static int blk(int x, int y) { return ds_blk(&g, x + DS_R, y + DS_R); }
static int dist(int x, int y) { return ds_dist(&g, x + DS_R, y + DS_R); }

int main(void) {
    int x, y, t;
    // ① Open ground: the ideal point itself qualifies → taken as is (wilderness maps do not degrade)
    fill(0); ds_flood(&g);
    t = ds_pick(&g, 12, -3, 0, 0, 0, 6, &x, &y); CHECK(t == 0 && x == 12 && y == -3, "open ground should take the ideal point 12,-3 tier 0, got %d,%d tier %d", x, y, t);
    t = ds_pick(&g, 2, 12, 1, 12, -3, 6, &x, &y); CHECK(t == 0 && x == 2 && y == 12, "open ground, second door should take the ideal point 2,12, got %d,%d tier %d", x, y, t);
    CHECK(dist(12, -3) == 15, "open ground, 12,-3 is 15 steps away, computed %d", dist(12, -3));

    // ② Horizontal corridor (y −4..4 walkable, the rest is wall), the player in the middle, the ideal point inside the wall straight below
    fill(1); rect(-DS_R, -4, DS_R, 4, 0); ds_flood(&g);
    CHECK(blk(5, 10) && blk(-5, 10), "control: the old rule's two landing points ±5,10 are inside the wall");
    // Cross footprint → the reachable y is −3..3; the 2 cells around all reachable → y −1..1. The nearest to (5,10) is (5,1)
    t = ds_pick(&g, 5, 10, 0, 0, 0, 6, &x, &y); CHECK(t == 0 && x == 5 && y == 1, "in a corridor should take 5,1 tier 0, got %d,%d tier %d", x, y, t);
    CHECK(dist(x, y) >= 0 && !blk(x, y), "landing point must be reachable and not blocked");
    int x2, y2; t = ds_pick(&g, -5, 10, 1, x, y, 6, &x2, &y2); CHECK(t == 0 && x2 == -5 && y2 == 1, "in a corridor, second door should take -5,1, got %d,%d tier %d", x2, y2, t);

    // ③ There is a patch of open ground beyond the wall but it is not connected to the player: it must not be chosen
    fill(1); rect(-DS_R, -4, DS_R, 4, 0); rect(-DS_R, 8, DS_R, 16, 0); ds_flood(&g);
    CHECK(!blk(5, 10) && dist(5, 10) < 0, "control: 5,10 is not blocked but cannot be reached from the player");
    t = ds_pick(&g, 5, 10, 0, 0, 0, 6, &x, &y); CHECK(dist(x, y) >= 0 && y <= 1, "open ground behind a wall must not be chosen, should stay on the player's side, got %d,%d", x, y);

    // ④ Narrow passage (3 cells wide: y −1..1): neither 5 × 5 nor 3 × 3 fits → tier 2, take the reachable cell nearest to the player (with the cross footprint only the row y = 0 is reachable, 1 cell from the player)
    fill(1); rect(-DS_R, -1, DS_R, 1, 0); ds_flood(&g);
    t = ds_pick(&g, 5, 10, 0, 0, 0, 6, &x, &y); CHECK(t == 2 && y == 0 && abs(x) == 1, "in a narrow passage should fall back to the nearest reachable cell at the feet (±1,0) tier 2, got %d,%d tier %d", x, y, t);
    t = ds_pick(&g, -5, 10, 1, x, y, 6, &x2, &y2); CHECK(t == 2 && y2 == 0 && abs(x2 - x) >= 2 && dist(x2, y2) >= 0, "in a narrow passage, second door at least 2 cells from the first and reachable, got %d,%d tier %d", x2, y2, t);

    // ⑤ The player is boxed into a single cell: land at the feet
    fill(1); rect(0, 0, 0, 0, 0); ds_flood(&g);
    t = ds_pick(&g, 5, 10, 0, 0, 0, 6, &x, &y); CHECK(t == 3 && x == 0 && y == 0 && g.reach == 1, "when walled in, lands at the feet, tier 3, got %d,%d tier %d (%d cells reachable)", x, y, t, g.reach);

    // ⑥ Cells reached only by a long detour are not chosen: the ideal point is behind a long wall, and going around takes more than 36 steps
    fill(0); rect(-20, 6, 20, 7, 1); ds_flood(&g);
    CHECK(dist(0, 12) > DS_FAR, "control: 0,12 behind the wall takes %d steps (> %d)", dist(0, 12), DS_FAR);
    t = ds_pick(&g, 0, 12, 0, 0, 0, 6, &x, &y); CHECK(t == 0 && abs(x) == 3 && y == 2, "in front of a long wall should take ±3,2 on this side of the wall (y = 2 is the row nearest the wall with all cells within 2 reachable; at least 3 cells from the player, so x = ±3), got %d,%d tier %d", x, y, t);

    printf("t_doorspot: %d checks, %d failed\n", checks, fails); return fails != 0;
}
