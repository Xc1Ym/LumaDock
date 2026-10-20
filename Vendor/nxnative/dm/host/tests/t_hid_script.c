// HID script unit test: a fake clock advances frame by frame, with real DM_KEYS parsing and the real GetNpad path; no sleeping, no skipping steps by duration.
// Begin is action start/repeat trigger and End marks action end: two Begins need only one End of the same action.
#ifndef HLE_HID_SOURCE
#define HLE_HID_SOURCE "../hle_hid.c"
#endif
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>
#include HLE_HID_SOURCE
module_t g_mod[MAX_MOD]; int g_nmod;
static uint64_t clock_ns = 1000000000ull;
static uint64_t guest_frame;
static uint64_t server_tick;
static int server_available;
uint64_t now_ns(void) { return clock_ns; }
uint64_t guest_ns(void) { return clock_ns; }
uint64_t dm_guest_frame(void) { return guest_frame; }
uint64_t dm_server_tick(void) { return server_available ? server_tick : UINT64_MAX; }
int touch_fill(void *out, uint64_t max) { (void)out; (void)max; return 0; }
static int test_loadscreen_up, hold_requests;
int dm_loadscreen_up(void) { return test_loadscreen_up; }                 // the real check is in diag.c; the unit test sets it by hand
void dm_hold_for_loadscreen(void) { hold_requests++; }                     // the real implementation freezes the guest clock; the unit test only counts requests
int dm_opmode(void) { return 1; }
void dm_touch_set(const dm_touch *t, int n) { (void)t; (void)n; }
static void (*ui_cb)(const char *, const char *, const char *);
void uimsg_subscribe(void (*f)(const char *, const char *, const char *)) { ui_cb = f; }
static int checks, fails;
#define CHECK(c, s) do { checks++; int ok = !!(c); fails += !ok; printf("%s %s\n", ok ? "✓" : "✗", s); } while (0)
static void setup(const char *script) {
    memset(g_steps, 0, sizeof g_steps); memset(g_keys, 0, sizeof g_keys);
    g_nsteps = g_nkeys = g_kcur = g_ktries = g_kbeg = g_kend = 0; g_kstate = KS_PRE; g_krel = 1;
    clock_ns = 1000000000ull; guest_frame = 0; server_tick = 0; server_available = 1; setenv("DM_KEYS", script, 1); keys_parse();
}
static void setup_pregame(const char *script) {
    memset(g_steps, 0, sizeof g_steps); memset(g_keys, 0, sizeof g_keys);
    g_nsteps = g_nkeys = g_kcur = g_ktries = g_kbeg = g_kend = 0; g_kstate = KS_PRE; g_krel = 1;
    clock_ns = 1000000000ull; guest_frame = 0; server_tick = 0; server_available = 0; setenv("DM_KEYS", script, 1); keys_parse();
}
static void ui(const char *act) { ui_cb("InputMessage", act, ""); }
static NpadState read_state(void) { NpadState s; fill(&s, 0, STYLE_FULLKEY); return s; }
static int neutral(NpadState s) { return !s.buttons && !s.lx && !s.ly; }
static void release(void) { guest_frame += ACTION_HOLD_TICKS; server_tick += ACTION_HOLD_TICKS; read_state(); }
static void frames(uint64_t n) { guest_frame += n; server_tick += n; read_state(); }
int main(int argc, char **argv) {
    unsetenv("DM_KEYS"); hid_keys_init();
    setup("LSL@+0.05,LSU@+0.05");
    NpadState s = read_state(); CHECK(s.lx == -32767 && s.ly == 0 && s.buttons == 0, "first step LSL goes into the real controller layout, not into the button bits");
    ui("ControllerActionBegin"); ui("ControllerActionBegin"); release();
    CHECK(neutral(read_state()), "with two Begins and no End yet, the next step is still held back");
    ui("ControllerActionEnd"); s = read_state();
    CHECK(s.ly == 32767 && s.lx == 0, "after two repeated Begins / one End, the next step LSU goes ahead");

    setup("A@+0.05,B@+0.05"); CHECK(read_state().buttons == DM_BTN_A, "plain A pressed");
    ui("ControllerActionBegin"); release();
    CHECK(neutral(read_state()), "a single Begin without End holds back the next key");
    ui("ControllerActionEnd"); CHECK(read_state().buttons == DM_BTN_B, "B is sent only after End, no key swallowed");

    setup("A@+0.6"); CHECK(read_state().buttons == DM_BTN_A, "hold duration test: A pressed first");
    clock_ns += 60000000000ull; guest_frame += 15 - 1; server_tick += 15 - 1;   // +0.6 seconds = 0.6*25 = 15 ticks
    CHECK(read_state().buttons == DM_BTN_A, "wall clock jumps but the guest frame is not due: A still held");
    guest_frame++; server_tick++; CHECK(neutral(read_state()), "A released only once the server tick is due");

    setup("LSL@+0.05,LSU@+0.05"); read_state(); release();
    CHECK(read_state().ly == 32767, "no Begin in the run: idle on release, no wait for an End that never comes");

    setup("A@+0.05,B@+0.05"); read_state(); ui("ControllerActionBegin"); ui("ControllerActionEnd"); ui("ControllerActionBegin"); release();
    CHECK(neutral(read_state()), "a new Begin after End: busy again, the old End does not release the new action");
    ui("ControllerActionEnd"); CHECK(read_state().buttons == DM_BTN_B, "goes ahead after the new action's own End");

    setup("A@+0.05,B@+0.05"); read_state(); ui("ControllerActionEnd"); ui("ControllerActionEnd"); ui("ControllerActionBegin"); release();
    CHECK(neutral(read_state()), "surplus Ends that came first do not cancel a later Begin");
    ui("ControllerActionEnd"); CHECK(read_state().buttons == DM_BTN_B, "continues once the later Begin has ended");

    setup("A@>OpenPanel:Done,B@+0.05"); read_state(); ui("ControllerActionBegin"); ui("ControllerActionBegin");
    ui_cb("PanelManager", "OpenPanel", "Done");
    CHECK(neutral(read_state()), "a confirm while held releases, but with the action not ended it still waits for idle");
    ui("ControllerActionEnd"); CHECK(read_state().buttons == DM_BTN_B, "repeated Begins after the confirm need only one End, then B goes");

    setup("A@+0.05,B@%0.2+0.05"); read_state(); ui("ControllerActionBegin"); ui("ControllerActionBegin"); release(); ui("ControllerActionEnd");
    CHECK(neutral(read_state()), "End does not skip the script's own delay");
    frames(4); CHECK(neutral(read_state()), "server delay at 4 of 5 ticks: next key held back");
    frames(1); CHECK(read_state().buttons == DM_BTN_B, "next key only once the server delay reaches 5 ticks and the action has ended");
    release(); CHECK(neutral(read_state()), "no extra key press after the last step is released");

    setup("A@>Never"); read_state(); release();
    frames(OK_WAIT_TICKS - ACTION_HOLD_TICKS - 1); CHECK(g_ktries == 1 && neutral(read_state()), "no re-press before the confirm wait reaches 150 server ticks");
    frames(1); CHECK(g_ktries == 2 && read_state().buttons == DM_BTN_A, "re-press only after a confirm wait of 150 server ticks");

    setup_pregame("A@%0.2"); read_state(); frames(11); CHECK(neutral(read_state()), "main menu presented-frame delay at 11/12 frames: no early press");
    frames(1); CHECK(read_state().buttons == DM_BTN_A, "main menu presented-frame delay: press only after 12 frames");

    pid_t short_hold = fork();
    if (!short_hold) { setup("A@+0.01"); _exit(read_state().buttons == 0 ? 0 : 99); }
    int short_status; waitpid(short_hold, &short_status, 0);
    CHECK(WIFEXITED(short_status) && WEXITSTATUS(short_status) == 0, "counterexample: held less than 1 server tick, the real reading counts as not sampled");

    pid_t child = fork();
    if (!child) { setup("A@>Never"); read_state(); release(); clock_ns += 60000000000ull; read_state(); _exit(99); }
    int status; waitpid(child, &status, 0);
    CHECK(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT, "guest frames stopped but 60 s of wall clock: only the fallback prints a [RED] line");

    setup("A@Start>OpenPanel:Done,B@>OpenPanel:Next");
    ui_cb("PanelManager", "OpenPanel", "Done"); ui_cb("PanelManager", "OpenPanel", "Start");
    CHECK(read_state().buttons == DM_BTN_A && g_kcur == 0, "an old confirm from before the press does not complete the current step");
    ui("ControllerActionBegin"); ui("ControllerActionBegin"); ui_cb("PanelManager", "OpenPanel", "Done");
    ui_cb("PanelManager", "OpenPanel", "Next");
    CHECK(neutral(read_state()), "an old confirm before the next step is pressed cannot skip a step, still waits for the previous action's End");
    ui("ControllerActionEnd");
    CHECK(read_state().buttons == DM_BTN_B && g_kcur == 1, "after the previous End the next step really presses B, the old Next confirm does not count as completion");
    ui_cb("PanelManager", "OpenPanel", "Next");
    CHECK(neutral(read_state()) && g_kcur == 2, "only a fresh confirm after the next step is pressed completes it and releases");
    if (argc > 1) {
        FILE *f = fopen(argv[1], "r"); if (!f) { perror("trace"); return 2; }
        setup("LSL@+8,LSU@+8"); read_state(); char line[2048]; int entered = 0, nb = 0, ne = 0;
        while (fgets(line, sizeof line, f)) {
            if (strstr(line, "hid script step 3 pressed")) entered = 1;
            if (!entered) continue;
            double t;
            if (sscanf(line, "[dm] UIMSG [%lfs]", &t) != 1) continue;
            int beg = strstr(line, "InputMessage ControllerActionBegin") != NULL;
            int end = strstr(line, "InputMessage ControllerActionEnd") != NULL;
            if (!beg && !end) continue;
            clock_ns = 1000000000ull + (uint64_t)((t - 16.13) * 1e9); read_state();
            ui(beg ? "ControllerActionBegin" : "ControllerActionEnd"); nb += beg; ne += end;
            if (end) break;
        }
        fclose(f); s = read_state();
        CHECK(nb == 73 && ne == 1 && s.ly == 32767, "iOS original step 3 trace, 73 Begin / 1 End replayed, then enters LSU (fake clock advanced by message times)");
    }
    // During a tick freeze (DM_TICK_HOLD) the tick number does not advance: the precondition was seen under the in-game tick clock, then the host reports "no tick", and %1 must be finished by presented frames instead, 60 frames (host_savecmp waited 451 s dead)
    setup("A@OpenPanel:PauseLayout%1>PausePanelMessage:ExitGame"); server_tick = 401; guest_frame = 1000;
    ui_cb("PanelManager", "OpenPanel", "PauseLayout"); CHECK(neutral(read_state()), "pre seen before the freeze, delay not elapsed: no press");
    server_available = 0; read_state();
    guest_frame += 59; CHECK(neutral(read_state()), "counted in frames after the freeze: 59 frames, under 1 second, no press");
    guest_frame += 1; CHECK(read_state().buttons == DM_BTN_A, "counted in frames after the freeze: A pressed at 60 frames (1 second), no endless wait on the stopped tick number");
    // An in-game key press that comes due while the loading screen is still up: do not press, request a tick freeze; press only after it is down (screenshot gate NPC page: the A at tick 84 was swallowed by the loading screen)
    setup("A@DM:Tick:84#>OpenPanel:NpcDialogPanel"); server_tick = 84; test_loadscreen_up = 1; hold_requests = 0;
    ui_cb("DM", "Tick", "84#"); CHECK(neutral(read_state()) && hold_requests == 1, "loading screen up: no A even though the pre has arrived, and a tick freeze is requested");
    frames(30); CHECK(neutral(read_state()) && hold_requests >= 2, "loading screen still up: still no press");
    test_loadscreen_up = 0; hold_requests = 0; CHECK(read_state().buttons == DM_BTN_A && hold_requests == 0, "loading screen down: A pressed, no more freeze requests");
    setup("A@DM:Tick:84#>OpenPanel:NpcDialogPanel"); server_tick = 84; test_loadscreen_up = 0; hold_requests = 0;
    ui_cb("DM", "Tick", "84#"); CHECK(read_state().buttons == DM_BTN_A && hold_requests == 0, "loading screen already down: press when due, no freeze request (timing unchanged)");
    printf("== HID script %d checks, %d failed ==\n", checks, fails); return fails != 0;
}
