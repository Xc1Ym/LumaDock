// hle_audio.c unit test (silent sink): 3 buffers of 100 ms each -> released in order at about 100/200/300 ms, each release triggering the event.
// Expected values are computed directly from the sample rate and block length: 4800 frames / 48 kHz = 100 ms.
#include "../hle_audio.c"
#include <time.h>
uint64_t now_ns(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return (uint64_t)t.tv_sec * 1000000000ull + t.tv_nsec; }
static struct { const void *k; void *v; } om[8];
void *objmap_get(const void *k) { for (int i = 0; i < 8; i++) if (om[i].k == k) return om[i].v; return NULL; }
void objmap_put(const void *k, void *v) { for (int i = 0; i < 8; i++) if (!om[i].k) { om[i].k = k; om[i].v = v; return; } }
void *objmap_del(const void *k) { for (int i = 0; i < 8; i++) if (om[i].k == k) { om[i].k = 0; return om[i].v; } return NULL; }
static _Atomic int g_sig;
void hle_signal_system_event(void *g) { (void)g; atomic_fetch_add_explicit(&g_sig, 1, memory_order_seq_cst); }
void hle_bind_system_event(void *g, int autoclear) { (void)g; (void)autoclear; }   // the real implementation needs a guest thread + SDK kernel event; the unit test only counts triggers
module_t *module_of(const void *p) { (void)p; return NULL; }   // call sites in the log: no guest modules in the unit test
void dm_host_helper_qos(qos_class_t q) { (void)q; }   // hle_thread.c: the helper threads keep the default class in the unit test
int main(void) {
    char out[64], ev[64]; uint8_t prm[16]; gbuf b[3]; static int16_t pcm[3][4800 * 2];
    h_au_InitParam(prm);
    if (h_au_Open(out, ev, NULL, prm)) return 1;
    if (h_au_Ch(out) != 2 || h_au_Rate(out) != 48000 || h_au_State(out) != STATE_STOPPED) { puts("FAIL parameters"); return 1; }
    for (int i = 0; i < 3; i++) { h_au_SetBuf(&b[i], pcm[i], sizeof pcm[i], sizeof pcm[i]); if (!h_au_Append(out, &b[i])) return 1; }
    if (h_au_Released(out)) { puts("FAIL buffers released before start"); return 1; }
    uint64_t t0 = now_ns(); h_au_Start(out);
    int got = 0, fail = 0;
    while (got < 3 && now_ns() - t0 < 10000000000ull) {
        gbuf *r = h_au_Released(out);
        if (!r) { usleep(1000); continue; }
        int ok = r == &b[got];
        printf("release #%d: expected block %d in order → got block %ld %s\n", got, got, (long)(r - b), ok ? "✓" : "✗");
        fail |= !ok; got++;
    }
    h_au_Close(out);
    int sig1 = atomic_load_explicit(&g_sig, memory_order_acquire);
    printf("released %d/3, event signaled %d times (expected 3)\n", got, sig1);
    if (fail || got != 3 || sig1 != 3) return 1;

    // Scenario 2: the real audio output sink (PCM all 0, inaudible) plays 6 blocks of 100 ms each, pausing at 150 ms (app to background / incoming call) and resuming at 350 ms.
    // Expected: during the pause the silent sink takes over and consumes in real time, all 6 blocks are released in order with 6 events; total duration ~ 600 ms (real time, neither stalled by the pause nor sped up).
    setenv("DM_AUDIO", "1", 1);
    char out2[64]; gbuf b2[6]; static int16_t pcm2[6][4800 * 2]; g_sig = 0;
    if (h_au_Open(out2, ev, NULL, prm)) return 1;
    for (int i = 0; i < 6; i++) { h_au_SetBuf(&b2[i], pcm2[i], sizeof pcm2[i], sizeof pcm2[i]); h_au_Append(out2, &b2[i]); }
    t0 = now_ns(); h_au_Start(out2);
    int got2 = 0, order_ok = 1, susp = 0, resumed = 0;
    while (got2 < 6 && now_ns() - t0 < 10000000000ull) {
        uint64_t ms = (now_ns() - t0) / 1000000;
        if (!susp && ms >= 150) { dm_audio_suspend(1); susp = 1; }
        if (susp && !resumed && ms >= 350) { dm_audio_suspend(0); resumed = 1; }
        gbuf *r = h_au_Released(out2);
        if (!r) { usleep(1000); continue; }
        order_ok &= r == &b2[got2]; got2++;
    }
    double total = (now_ns() - t0) / 1e6;
    h_au_Close(out2);
    int sig2 = atomic_load_explicit(&g_sig, memory_order_acquire);
    int ok2 = got2 == 6 && order_ok && sig2 == 6 && total > 520;
    printf("suspend / resume: released %d/6 in order=%d events %d (expected 6), total duration lower bound 520 ms, got %.0f ms %s\n", got2, order_ok, sig2, total, ok2 ? "✓" : "✗");
    if (!ok2) return 1;

    // Scenario 3: the device stops calling back while the output plays (iOS does this when another audio session takes over, without telling the AudioUnit). 20 blocks of 100 ms; at 150 ms the AudioUnit is stopped behind the host's back.
    // Expected: the watchdog sees no callback for 200 ms, the silent sink takes over (all 20 blocks still released in order, about 2 s plus the 200-250 ms gap), and the AudioUnit is restarted 1 s later and calls back again
    char out3[64]; gbuf b3[20]; static int16_t pcm3[20][4800 * 2]; g_sig = 0;
    if (h_au_Open(out3, ev, NULL, prm)) return 1;
    for (int i = 0; i < 20; i++) h_au_SetBuf(&b3[i], pcm3[i], sizeof pcm3[i], sizeof pcm3[i]);
    int app3 = 0; for (; app3 < 20 && h_au_Append(out3, &b3[app3]); app3++) ;
    aout *a3 = ao(out3); t0 = now_ns(); h_au_Start(out3);
    int got3 = 0, order3 = 1, cut = 0; uint64_t cb_restart = 0;
    while (got3 < 20 && now_ns() - t0 < 10000000000ull) {
        uint64_t ms = (now_ns() - t0) / 1000000;
        if (!cut && ms >= 150) { AudioOutputUnitStop(a3->au); cut = 1; }
        pthread_mutex_lock(&g_aos_lock); if (cut && !cb_restart && a3->backend == BK_AU && ms > 400) cb_restart = atomic_load(&a3->cb_n); pthread_mutex_unlock(&g_aos_lock);
        gbuf *r = h_au_Released(out3);
        if (!r) { usleep(1000); continue; }
        order3 &= r == &b3[got3]; got3++;
        if (app3 < 20) h_au_Append(out3, &b3[app3++]);
    }
    double total3 = (now_ns() - t0) / 1e6; usleep(100000);
    pthread_mutex_lock(&g_aos_lock); int back = a3->backend == BK_AU && !a3->stalled; uint64_t cb_end = atomic_load(&a3->cb_n); pthread_mutex_unlock(&g_aos_lock);
    h_au_Close(out3);
    int ok3 = got3 == 20 && order3 && total3 > 1900 && total3 < 2600 && back && cb_restart && cb_end > cb_restart;
    printf("device stall: released %d/20 in order=%d in %.0f ms (expected 2000-2600), AudioUnit restarted and calling back again=%d %s\n", got3, order3, total3, back && cb_restart && cb_end > cb_restart, ok3 ? "✓" : "✗");
    return !ok3;
}
