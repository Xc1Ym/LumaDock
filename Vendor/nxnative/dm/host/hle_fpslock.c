// Engine frame limits kept in game memory (FPSLocker's evaluate_write entries): some engines cap their own frame rate with a float the host can raise. The target is the profile's
// fps_target (DM_FPS_TARGET overrides; 0 = leave the game's own limit), the same key that drives Tears of the Kingdom's frame step (loader.c install_fps_state). Called on every present
// (hle_nvn.c); the game sets the value after boot and may set it again, so it is written whenever it differs. Fixed addresses: each row runs only on the main build it was found in (AGENTS.md)
#include "hle.h"
#include <mach/mach.h>

static const struct { const char *build, *what; uint64_t ptr_off; uint32_t field; } k_locks[] = {
    // Monster Hunter Rise 16.0.2: RE Engine's frame limit, a float at [main+0x1295b3f0]+0x434 (the pointer is a global in main's bss). The frame loop (main+0x6b106c8) sleeps until
    // [+0x430] / [+0x434] sixtieths of a second have passed ([+0x430] = 60) and steps the game by the time that really passed (+0x41c), so a higher limit runs the game faster in frames
    // at the same speed. The game sets 30 after boot; it also asks for present interval 2, which the profile's present_interval display ignores.
    // From masagrator's FPSLocker config for this build (FPSLocker-Warehouse, patches/0100B04011742000/C9A3DD7702075ECD.yaml)
    { "c9a3dd7702075ecd90101f4555389582", "RE Engine frame limit", 0x1295b3f0, 0x434 },
};

static int rd(uint64_t a, void *out, size_t n) { vm_size_t got = 0; return a >= 0x1000 && vm_read_overwrite(mach_task_self(), (vm_address_t)a, n, (vm_address_t)out, &got) == KERN_SUCCESS && got == n; }

void dm_fps_lock_tick(void) {
    static int row = -2, nlog; static float target; static uint8_t *base; static const char *src;
    if (row == -1) return;
    if (row == -2) {
        row = -1;
        for (int i = 0; i < g_nmod; i++) if (!strcmp(g_mod[i].name, "main"))
            for (int k = 0; k < (int)(sizeof k_locks / sizeof k_locks[0]); k++) if (!strcmp(g_mod[i].build_id, k_locks[k].build)) { row = k; base = g_mod[i].base; }
        if (row < 0) return;
        const char *e = getenv("DM_FPS_TARGET"); int t = e ? atoi(e) : DM_GAME_FPS_TARGET; src = e ? "DM_FPS_TARGET" : "game profile fps_target";
        if (t != 0 && t != 30 && t != 60) { LOG("[RED] DM_FPS_TARGET=%s: must be 0, 30 or 60; leaving the game's frame limit", e); t = 0; }
        if (!t) { LOG("main: %s left as the game sets it (%s)", k_locks[row].what, src); row = -1; return; }
        target = (float)t;
    }
    uint64_t obj; float cur;
    if (!rd((uint64_t)(uintptr_t)(base + k_locks[row].ptr_off), &obj, sizeof obj) || !obj || !rd(obj + k_locks[row].field, &cur, sizeof cur)) return;   // not created yet
    if (cur == target || !(cur >= 10 && cur <= 120)) return;   // already set, or not set yet (6000 at boot)
    float *p = (float *)(uintptr_t)(obj + k_locks[row].field);
    dm_guest_write_prepare(p, sizeof *p); *p = target;
    if (nlog < 8) { nlog++; LOG("main: %s %g → %g (%s)", k_locks[row].what, cur, target, src); }
}
