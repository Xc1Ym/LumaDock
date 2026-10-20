// Frame step in whole vsyncs (pure function, shared by Mac / iOS; unit test tests/t_fstep.c). The rewriter's frame-step stubs (patch_nso.py FRAME_STEP: Tears of the Kingdom 1.4.3,
// Breath of the Wild 1.9.0) step the game by the vsyncs (1/60 s) the host hands them each frame, and the host keeps each frame on screen for k vsyncs (hle_nvn.c present_itv).
// At a steady rate the step is the time on screen: even motion, and only steps the games' own interval logic uses (60 / 30 / 20 fps). Real time the game falls behind (a late
// frame, a hitch) is a debt paid back one extra vsync per frame, so over time game time = real time. k follows the frames' cost: three late frames in a row step up to the cost
// (30 fps when 60 does not hold: no 40 fps steps on 120 Hz screens); 30 frames in a row whose cost would fit k − 1 try it, and a trial that fails waits twice as long before
// the next (1 s → 8 s), so a device on the edge does not flap.
#pragma once
#include <math.h>
#include <stdint.h>

#define FSTEP_MAX 3           // the largest step: both games' own interval logic uses 1–3 (BotW clamps to [2, 3], TOTK picks 2 or 3), so their integer readers never see 4
#define FSTEP_LATE 0.1        // a frame is late when it or its GPU work took this many vsyncs (1.7 ms) more than k: 53 fps is not 60 (start-to-start jitter on time is well below)
#define FSTEP_FIT 0.85        // a frame would fit k − 1 when its cost is at most this share of it
#define FSTEP_RUN 30          // frames in a row that fit k − 1 before a trial, and frames a trial must hold
#define FSTEP_DEBT_MAX 15.0   // debt kept at most (0.25 s): the rest of a long stall (a load) is dropped, not replayed
#define FSTEP_HOLD0 60.0      // vsyncs since the last step up before a trial: 1 s, doubled after each failed trial up to 8 s
#define FSTEP_HOLD_MAX 480.0

typedef struct {
    int k, step;              // vsyncs each frame stays on screen; the step handed to the game for the next frame (k, or k + 1 while paying back)
    int kmin;                 // the last call's kmin (a lower one takes effect at once)
    double debt;              // real time the game is behind, in vsyncs
    int late_run, fit_run, trial;   // late frames in a row; frames in a row whose cost fits k − 1; frames left of a trial at k − 1 (0 = none)
    double hold, since;       // vsyncs a trial waits for after a step up; vsyncs since the last step up
    uint64_t late, paid, ups, downs, failed; double dropped;   // statistics for the log
} nvn_fstep;

// Once per frame. shown: real time since the previous frame's start, in vsyncs; cost: the frame's work, max(CPU, GPU), in vsyncs (a GPU that cannot keep up makes frames late too); kmin: 1 at a 60 fps cap, 2 at 30;
// kmax: the longest hold (FSTEP_MAX; 2 at a 30 fps cap, where the display link runs at 30 Hz and holds only even counts); fixed: a step the game has set itself (BotW's
// VFR override; 0 = none), which the host then holds as it is. Returns the step for the next frame; s->k is how long that frame stays on screen
static inline int nvn_fstep_next(nvn_fstep *s, double shown, double cost, int kmin, int kmax, int fixed) {
    if (kmin < 1) kmin = 1;
    if (kmax > FSTEP_MAX) kmax = FSTEP_MAX;
    if (kmax < kmin) kmax = kmin;
    if (!s->hold) s->hold = FSTEP_HOLD0;
    if (fixed > 0) {   // the game's own step: speed is right by construction, nothing to pay back
        s->k = s->step = fixed < FSTEP_MAX ? fixed : FSTEP_MAX;
        s->debt = 0; s->late_run = s->fit_run = s->trial = 0;
        s->kmin = FSTEP_MAX + 1;   // when it ends, k starts again from kmin
        return s->step;
    }
    if (!s->k) { s->k = s->step = s->kmin = kmin; return s->step; }   // first frame: nothing measured yet
    int held = s->k;   // the frame that just ended stayed on screen this long
    s->debt += shown - s->step;
    if (s->debt > FSTEP_DEBT_MAX) { s->dropped += s->debt - FSTEP_DEBT_MAX; s->debt = FSTEP_DEBT_MAX; }
    if (s->debt < -1) s->debt = -1;   // ahead (a frame shorter than its step): nothing slows the game down, so at most one vsync is remembered
    s->since += shown;
    if (kmin < s->kmin || s->k < kmin) s->k = kmin;   // the cap rose (a movie or the game's own step ended) or fell
    if (s->k > kmax) s->k = kmax;
    s->kmin = kmin;
    int late = shown > held + FSTEP_LATE || cost > held + FSTEP_LATE;
    if (late) { s->late++; s->late_run++; s->fit_run = 0; } else s->late_run = 0;
    if (s->late_run >= 3 && s->k < kmax) {   // step up to the cost, at least one vsync
        int want = (int)ceil(cost - 0.05);
        if (want < s->k + 1) want = s->k + 1;
        if (want > kmax) want = kmax;
        if (s->trial) { s->failed++; s->trial = 0; s->hold = s->hold * 2 < FSTEP_HOLD_MAX ? s->hold * 2 : FSTEP_HOLD_MAX; }
        s->k = want; s->ups++; s->late_run = s->fit_run = 0; s->since = 0;
    } else if (s->trial && !--s->trial) s->hold = FSTEP_HOLD0;   // the trial held
    if (!late) s->fit_run = s->k > kmin && cost <= FSTEP_FIT * (s->k - 1) ? s->fit_run + 1 : 0;
    if (s->fit_run >= FSTEP_RUN && s->since >= s->hold && !s->trial) { s->k--; s->downs++; s->trial = FSTEP_RUN; s->fit_run = 0; }
    s->step = s->k + (s->debt >= 1 && s->k < FSTEP_MAX);
    s->paid += s->step > s->k;
    return s->step;
}
