// Unit test for reading "unit -> the level it is in" (dm_unit.h, takes seconds).
// Situation: during the loading screen of an act change the client player "has a path but no room". The old code read four levels in one go, and with a null room went on to read address 0x18 -> sig=11 addr=0x18.
// Fail -> pass: with the same set of inputs, the old code (old_level, copied verbatim from the pre-fix line) runs in a child process and must die of SIGSEGV; the new code returns 0 (unknown level).
#include "dm_unit.h"
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static int fails, checks;
#define CHECK(c, ...) do { checks++; if (!(c)) { fails++; printf("  ✗ "); printf(__VA_ARGS__); printf("\n"); } } while (0)

static uint64_t rd(uint64_t a) { return a ? *(volatile uint64_t *)(uintptr_t)a : 0; }
static int old_level(uint64_t u) { uint64_t r = rd(rd(rd(rd(u + 0x38) + 0x20) + 0x18) + 0x90); return r ? *(int32_t *)(uintptr_t)(r + 0x1f8) : 0; }   // exactly as it was before the fix
// Run the old code in a child process: returns which signal it died of (0 = returned normally)
static int old_dies(uint64_t u) {
    fflush(stdout); pid_t p = fork(); if (p == 0) { signal(SIGSEGV, SIG_DFL); signal(SIGBUS, SIG_DFL); volatile int v = old_level(u); (void)v; _exit(0); }
    int st = 0; waitpid(p, &st, 0); return WIFSIGNALED(st) ? WTERMSIG(st) : 0;
}

int main(void) {
    static uint8_t unit[0x200], path[0x100], room[0x100], ex[0x100], level[0x300];
    // A complete chain: level id 59
    *(uint64_t *)(unit + 0x38) = (uint64_t)(uintptr_t)path; *(uint64_t *)(path + 0x20) = (uint64_t)(uintptr_t)room;
    *(uint64_t *)(room + 0x18) = (uint64_t)(uintptr_t)ex; *(uint64_t *)(ex + 0x90) = (uint64_t)(uintptr_t)level; *(int32_t *)(level + 0x1f8) = 59;
    uint64_t u = (uint64_t)(uintptr_t)unit;
    CHECK(dm_unit_level(u) == 59, "complete chain should read 59, read %d", dm_unit_level(u));
    CHECK(dm_unit_level_ptr(u) == (uint64_t)(uintptr_t)level, "complete chain should return the level struct pointer");
    CHECK(old_level(u) == 59, "old code should also read 59 on the complete chain (control)");

    // (1) Has a path, room is null (the client player during an act-change loading)
    *(uint64_t *)(path + 0x20) = 0;
    int sg = old_dies(u); CHECK(sg == SIGSEGV || sg == SIGBUS, "old code should crash (red) on 'path present, room null', actual signal %d", sg);
    CHECK(dm_unit_level(u) == 0 && dm_unit_level_ptr(u) == 0, "new code should return 0 on 'path present, room null'");
    // (2) Path is null
    *(uint64_t *)(path + 0x20) = (uint64_t)(uintptr_t)room; *(uint64_t *)(unit + 0x38) = 0;
    sg = old_dies(u); CHECK(sg == SIGSEGV || sg == SIGBUS, "old code should crash (red) on 'path null', actual signal %d", sg);
    CHECK(dm_unit_level(u) == 0 && dm_unit_level_ptr(u) == 0, "new code should return 0 on 'path null'");
    // (3) Unit is null
    sg = old_dies(0); CHECK(sg == SIGSEGV || sg == SIGBUS, "old code should crash (red) on 'unit null', actual signal %d", sg);
    CHECK(dm_unit_level(0) == 0 && dm_unit_level_ptr(0) == 0, "new code should return 0 on 'unit null'");
    // (4) Room present, room +0x18 null; (5) +0x90 null (the last two steps of the chain)
    *(uint64_t *)(unit + 0x38) = (uint64_t)(uintptr_t)path; *(uint64_t *)(room + 0x18) = 0;
    CHECK(dm_unit_level(u) == 0, "room +0x18 null should return 0");
    *(uint64_t *)(room + 0x18) = (uint64_t)(uintptr_t)ex; *(uint64_t *)(ex + 0x90) = 0;
    CHECK(dm_unit_level(u) == 0, "null level pointer should return 0");
    *(uint64_t *)(ex + 0x90) = (uint64_t)(uintptr_t)level;
    CHECK(dm_unit_level(u) == 59, "should read 59 again after relinking");
    // Taking the room chain head when the level pointer is null: returns 0 (previously each place did rd(lv + 0x10) directly and read address 0x10)
    CHECK(dm_level_rooms(0) == 0, "room list head should be 0 for a null level pointer");
    *(uint64_t *)(level + 0x10) = (uint64_t)(uintptr_t)room; CHECK(dm_level_rooms((uint64_t)(uintptr_t)level) == (uint64_t)(uintptr_t)room, "non-null level should read the room at +0x10");
    printf("t_unit_level: %d checks, %d failed\n", checks, fails); return fails != 0;
}
