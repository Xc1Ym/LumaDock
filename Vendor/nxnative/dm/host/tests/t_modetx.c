// Unit test of the controller / touch switch transaction (takes seconds): the state machine and input gate of dm_modetx.h, without touching the game. Expected values are all computed by hand from the rules:
// rebuild complete = SETTLE consecutive frames without movement after the hint panel reopen count has moved; if that has not happened within TIMEOUT frames, proceed as a timeout; keys that were held during the freeze are passed to the game only after they have been released once following the unfreeze.
#include <stdio.h>
#include "../dm_modetx.h"
static int fails, checks;
#define CHECK(c, ...) do { checks++; if (!(c)) { fails++; printf("  ✗ "); printf(__VA_ARGS__); printf("\n"); } } while (0)
int main(void) {
    { dm_modetx t = {0}; uint64_t f = 100;   // One normal switch: touch (0) → controller (1)
      CHECK(dm_modetx_step(&t, f, -1, 0, 7) == DM_TXA_NONE, "no request: must not move");
      CHECK(dm_modetx_step(&t, f, 0, 0, 7) == DM_TXA_NONE, "requested mode is the current one: must not move");
      CHECK(dm_modetx_step(&t, f, 1, 0, 7) == DM_TXA_BEGIN && t.st == DM_TX_REBUILD1, "request for the other mode should begin");
      for (int i = 1; i <= 10; i++) CHECK(dm_modetx_step(&t, f + i, 1, 0, 7) == DM_TXA_NONE, "must not proceed before the hint panel reopens (frame %d)", i);
      CHECK(dm_modetx_step(&t, f + 11, 1, 0, 8) == DM_TXA_NONE, "the frame of the reopen does not count as done");
      CHECK(dm_modetx_step(&t, f + 13, 1, 0, 9) == DM_TXA_NONE, "reopened again: restart the settle count");
      CHECK(dm_modetx_step(&t, f + 16, 1, 0, 9) == DM_TXA_NONE, "3 settled frames are not enough");
      CHECK(dm_modetx_step(&t, f + 17, 1, 0, 9) == DM_TXA_REPORT_BACK && t.st == DM_TX_REBUILD2, "4 settled frames → report back the original run mode");
      CHECK(dm_modetx_step(&t, f + 30, 0, 1, 9) == DM_TXA_NONE, "a reverse request during the transaction does not interrupt it");
      CHECK(dm_modetx_step(&t, f + 31, 0, 1, 10) == DM_TXA_NONE, "second rebuild just started");
      CHECK(dm_modetx_step(&t, f + 35, 0, 1, 10) == DM_TXA_DONE && t.st == DM_TX_IDLE && !t.timeouts, "second rebuild settled → done, no timeout");
      CHECK(dm_modetx_step(&t, f + 36, 0, 1, 10) == DM_TXA_BEGIN, "the frame after completion handles the queued reverse request"); }
    { dm_modetx t = {0};   // Timeout: the hint panel never reopens
      CHECK(dm_modetx_step(&t, 0, 1, 0, 0) == DM_TXA_BEGIN, "begin");
      CHECK(dm_modetx_step(&t, DM_MODETX_TIMEOUT - 1, 1, 0, 0) == DM_TXA_NONE, "1 frame short: no timeout");
      CHECK(dm_modetx_step(&t, DM_MODETX_TIMEOUT, 1, 0, 0) == DM_TXA_REPORT_BACK && t.timeouts == 1, "at the deadline proceed as a timeout and count it");
      CHECK(dm_modetx_step(&t, 2 * DM_MODETX_TIMEOUT - 1, 1, 0, 0) == DM_TXA_NONE, "second stage restarts the timer");
      CHECK(dm_modetx_step(&t, 2 * DM_MODETX_TIMEOUT, 1, 0, 0) == DM_TXA_DONE && t.timeouts == 2 && t.st == DM_TX_IDLE, "second stage times out too → done, 2 counted"); }
    { dm_modegate g = {0}; uint64_t b;   // Input gate: A=0x1 triggers the switch and stays held, B=0x2 is also pressed along the way, and after releasing B it is pressed again
      b = 0x1; CHECK(dm_modegate_apply(&g, 1, &b) == 1 && b == 0, "frozen: keys cleared, sticks cleared too");
      b = 0x3; CHECK(dm_modegate_apply(&g, 1, &b) == 1 && b == 0, "keys newly pressed while frozen are not passed either");
      b = 0x3; CHECK(dm_modegate_apply(&g, 0, &b) == 0 && b == 0, "A and B still held after the unfreeze are not passed");
      b = 0x5; CHECK(dm_modegate_apply(&g, 0, &b) == 0 && b == 0x4, "B released, A still held: newly pressed X=0x4 is passed as usual, A still not");
      b = 0x0; CHECK(dm_modegate_apply(&g, 0, &b) == 0 && b == 0, "all released");
      b = 0x3; CHECK(dm_modegate_apply(&g, 0, &b) == 0 && b == 0x3, "pressed again after a release: passed as usual"); }
    printf("t_modetx: %d checks, %d failed\n", checks, fails); return fails != 0;
}
