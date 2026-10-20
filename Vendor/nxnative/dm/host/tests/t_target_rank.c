// Automatic monster targeting unit test: lay out fake units / fake monster data in this process's memory, call the observation gate callback, and check the score adjustment (expected values computed by hand, not by calling the implementation under test).
// Layout: unit +0 type, +4 class number, +0x10 -> monster data (+0x1A TypeFlag: 0x02 super unique / 0x04 champion / 0x08 unique / 0x10 minion).
#include <stdio.h>
#include <string.h>
#include <stdint.h>
int gate_obs_present(int id) { (void)id; return 1; }
static void (*g_fn)(const uint64_t *);
void gate_obs_set(int id, void (*fn)(const uint64_t *)) { (void)id; g_fn = fn; }
void target_rank_install(void);
static int fails, cases;
static float run(const void *unit, float score) {
    uint64_t frame[100] = {0}; frame[1] = (uint64_t)(uintptr_t)unit; frame[2] = 1;
    memcpy(&frame[32], &score, 4); g_fn(frame);
    float out; memcpy(&out, &frame[32], 4); return out;
}
static void expect(const char *what, float got, float want) {
    cases++; if (got == want) printf("✓ %s (%g)\n", what, got); else { fails++; printf("✗ %s: got %g, expected %g\n", what, got, want); }
}
int main(void) {
    target_rank_install();
    uint8_t data[0x40] = {0};
    struct { uint32_t type, cls, id, mode; uint64_t data; } unit = {1, 5, 77, 0, (uint64_t)(uintptr_t)data};
    expect("normal zombie (class 5, TypeFlag 0): score unchanged", run(&unit, 0.5f), 0.5f);
    data[0x1a] = 0x10; expect("minion (0x10) counts as normal", run(&unit, 0.5f), 0.5f);
    data[0x1a] = 0x04; expect("champion (0x04) +1000", run(&unit, 0.5f), 1000.5f);
    data[0x1a] = 0x08; expect("unique (0x08) +1000", run(&unit, 0.25f), 1000.25f);
    data[0x1a] = 0x02; expect("super unique (0x02) +1000", run(&unit, 0.75f), 1000.75f);
    data[0x1a] = 0; unit.cls = 156; expect("Andariel (class 156, boss=1) +2000", run(&unit, 0.5f), 2000.5f);
    unit.cls = 745; expect("new 3.3 Boss Colossus (class 745) +2000", run(&unit, 0.125f), 2000.125f);
    unit.cls = 5; unit.type = 0; data[0x1a] = 0x08; expect("player unit (type 0) untouched", run(&unit, 0.5f), 0.5f);
    unit.type = 1; unit.data = 0; data[0x1a] = 0; expect("null monster data pointer: nothing to read, untouched", run(&unit, 0.5f), 0.5f);
    expect("null candidate unit untouched", run(NULL, 0.5f), 0.5f);
    // Across tiers: the worst elite score (0.01+1000) is still higher than the best normal score (0.99); the worst Boss score is higher than the best elite score
    unit.data = (uint64_t)(uintptr_t)data; data[0x1a] = 0x04; float elite = run(&unit, 0.01f);
    data[0x1a] = 0; unit.cls = 211; float boss = run(&unit, 0.01f);
    cases++; if (elite > 0.99f && boss > 1000.99f) printf("✓ priority across tiers: elite %g > normal 0.99, Boss %g > elite 1000.99\n", elite, boss); else { fails++; printf("✗ priority across tiers\n"); }
    printf("%s: %d/%d\n", fails ? "[RED] auto-targeting" : "auto-targeting all green", cases - fails, cases);
    return fails != 0;
}
