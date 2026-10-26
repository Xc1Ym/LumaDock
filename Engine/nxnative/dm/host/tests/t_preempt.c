// Start/wake-to-run ordering through real thread SVCs. Suspend the child pthread
// to model a host dispatch delay: it is guest-runnable as soon as StartThread or
// a signal makes it ready, even though Mach still reports it stopped. Its payload
// must precede the lower-priority caller's return, including delays over 5 ms.
#include "../hle_thread.c"
#include <assert.h>
#include <unistd.h>

static thr_t worker;
static uint32_t event_read, event_write;
static _Atomic int payload;
static unsigned dispatch_us;
static _Atomic uint32_t mutex_word, condition_key;
static uint32_t main_handle;
static int wait_kind;
static _Atomic int worker_host_work;
static int worker_ready;

// FFT's SDK auto-clear event wakes one condition waiter. Its private worker
// queues cannot influence the kernel's priority/FIFO selection.
static thr_t fifo_workers[3];
static _Atomic int fifo_done;
static void *fifo_wait(void *arg) {
    thr_t *t = arg;
    pthread_setspecific(g_keythr, t);
    atomic_store(&mutex_word, t->handle);
    uint64_t r[32] = {(uint64_t)&mutex_word, (uint64_t)&condition_key, t->handle, (uint64_t)-1};
    svc_thread(0x1C, r);
    assert(r[0] == 0 && atomic_load(&mutex_word) == t->handle);
    r[0] = (uint64_t)&mutex_word; svc_thread(0x1B, r);
    atomic_fetch_add(&fifo_done, 1);
    thread_exit(t);
    return NULL;
}
static void condition_order(void) {
    pthread_t threads[3];
    atomic_store(&mutex_word, 0); atomic_store(&condition_key, 0); atomic_store(&fifo_done, 0);
    for (int i = 0; i < 3; i++) {
        thr_t *t = &fifo_workers[i]; memset(t, 0, sizeof *t);
        pthread_cond_init(&t->cv, NULL); pthread_cond_init(&t->pcv, NULL);
        t->started = 1; t->prio = i == 2 ? 45 : 46; t->core = 0; t->mask = 7;
        pthread_mutex_lock(&G);
        t->handle = h_new(O_THREAD, t); t->all = g_all; g_all = t;
        pthread_mutex_unlock(&G);
        assert(!pthread_create(&threads[i], NULL, fifo_wait, t));
        for (;;) {
            pthread_mutex_lock(&G); int waiting = t->wkind == 2; pthread_mutex_unlock(&G);
            if (waiting) break;
            usleep(100);
        }
    }
    int expected[] = {2, 0, 1}; // priority first, then registration order
    for (int i = 0; i < 3; i++) {
        atomic_store(&mutex_word, main_handle);
        uint64_t r[32] = {(uint64_t)&condition_key, 1}; svc_thread(0x1D, r);
        pthread_mutex_lock(&G);
        assert(fifo_workers[expected[i]].wkind == 1);
        assert(atomic_load(&mutex_word) == (main_handle | WAITERS_BIT));
        pthread_mutex_unlock(&G);
        r[0] = (uint64_t)&mutex_word; svc_thread(0x1B, r);
        while (atomic_load(&fifo_done) != i + 1) usleep(100);
    }
    assert(atomic_load(&condition_key) == 0);
    for (int i = 2; i >= 0; i--) {
        thr_t *t = &fifo_workers[i]; pthread_join(threads[i], NULL);
        pthread_mutex_lock(&G); assert(g_all == t); g_all = t->all;
        g_h[t->handle - 0x1000].type = O_FREE; g_h[t->handle - 0x1000].obj = NULL;
        pthread_mutex_unlock(&G);
        pthread_cond_destroy(&t->cv); pthread_cond_destroy(&t->pcv);
    }
    puts("PASS: condition waiters selected by priority, then FIFO; mutex reacquired before return");
}

static void *work(void *arg) {
    (void)arg;
    pthread_setspecific(g_keythr, &worker);
    worker.mport = pthread_mach_thread_np(pthread_self());
    if (wait_kind == 0) {
        pthread_mutex_lock(&G);
        worker_ready = 1;
        while (!worker.started) pthread_cond_wait(&worker.cv, &G);
        pthread_mutex_unlock(&G);
    }
    uint32_t handle = event_read; uint64_t r[32] = {0};
    if (wait_kind == 4) {
        r[1] = (uint64_t)&handle; r[2] = 1; r[3] = (uint64_t)-1;
        svc_thread(0x18, r);
    } else if (wait_kind == 2) {
        atomic_store(&mutex_word, worker.handle);
        r[0] = (uint64_t)&mutex_word; r[1] = (uint64_t)&condition_key;
        r[2] = worker.handle; r[3] = (uint64_t)-1;
        svc_thread(0x1C, r);
    } else if (wait_kind == 1) {
        r[0] = main_handle; r[1] = (uint64_t)&mutex_word; r[2] = worker.handle;
        svc_thread(0x1A, r);
    }
    assert(r[0] == 0);
    atomic_store(&payload, 1);
    usleep(1000);   // dispatching the work is insufficient: its teardown must finish too
    atomic_store(&payload, 2);
    thread_exit(&worker);
    return NULL;
}
static void *dispatch(void *arg) {
    (void)arg;
    usleep(dispatch_us);
    assert(thread_resume(worker.mport) == KERN_SUCCESS);
    return NULL;
}
static int delayed_wake(unsigned delay, int kind, int exclusion) {
    uint64_t r[32] = {0};
    svc_thread(0x45, r); assert(r[0] == 0);
    event_write = r[1]; event_read = r[2];
    memset(&worker, 0, sizeof worker);
    pthread_cond_init(&worker.cv, NULL); pthread_cond_init(&worker.pcv, NULL);
    worker.started = kind != 0; worker.prio = 30; worker.core = 0; worker.mask = 1;
    if (exclusion == 1) worker.prio = 44;   // equal priority
    if (exclusion == 2) worker.core = 1, worker.mask = 2;   // another guest core
    if (exclusion == 3) worker.mask = 7;   // can run on another guest core
    if (exclusion == 4) worker.host_owned = 1;   // host helper, no guest core
    if (exclusion == 5) worker.pause_req = 1;   // guest suspension
    if (exclusion == 6) { worker_host_work = 1; worker.host_work = &worker_host_work; }   // host GPU work
    pthread_mutex_lock(&G);
    worker.handle = h_new(O_THREAD, &worker); worker.all = g_all; g_all = &worker;
    pthread_mutex_unlock(&G);
    atomic_store(&payload, 0);
    atomic_store(&mutex_word, main_handle | WAITERS_BIT); atomic_store(&condition_key, 0);
    wait_kind = kind;
    worker_ready = 0;
    pthread_t w, d; assert(!pthread_create(&w, NULL, work, NULL));
    for (;;) {
        pthread_mutex_lock(&G); int waiting = kind == 0 ? worker_ready : worker.wkind == kind; pthread_mutex_unlock(&G);
        if (waiting) break;
        usleep(100);
    }
    assert(thread_suspend(worker.mport) == KERN_SUCCESS);
    dispatch_us = delay; assert(!pthread_create(&d, NULL, dispatch, NULL));
    if (kind == 0) { r[0] = worker.handle; svc_thread(0x09, r); }
    else if (kind == 4) { r[0] = event_write; svc_thread(0x11, r); }
    else if (kind == 2) { r[0] = (uint64_t)&condition_key; r[1] = 1; svc_thread(0x1D, r); }
    else { r[0] = (uint64_t)&mutex_word; svc_thread(0x1B, r); }
    assert(r[0] == 0);
    pthread_mutex_lock(&G); int ordered = atomic_load(&payload) == 2 && worker.exited; pthread_mutex_unlock(&G);
    pthread_join(d, NULL); pthread_join(w, NULL);
    pthread_mutex_lock(&G); g_all = worker.all;
    unsigned slot = worker.handle - 0x1000; g_h[slot].type = O_FREE; g_h[slot].obj = NULL;
    pthread_mutex_unlock(&G);
    pthread_cond_destroy(&worker.cv); pthread_cond_destroy(&worker.pcv);
    r[0] = event_read; svc_thread(0x16, r);
    r[0] = event_write; svc_thread(0x16, r);
    int ok = exclusion ? !ordered : ordered;
    printf("%s: wait kind %d, dispatch delay %u us, exclusion %d, payload before signaller returns %d\n", ok ? "PASS" : "FAIL", kind, delay, exclusion, ordered);
    return ok;
}
int main(int argc, char **argv) {
    (void)argv;
    alarm(10);
    setenv("DM_PREEMPT", argc > 1 ? "1" : "0", 1);
    main_handle = svc_thread_main_init();
    condition_order();
    int ok = 1;
    for (int kind = 0; kind <= 4; kind++) if (kind != 3) {
        ok &= delayed_wake(1000, kind, 0);
        ok &= delayed_wake(20000, kind, 0);
    }
    for (int exclusion = 1; exclusion <= 6; exclusion++) {
        ok &= delayed_wake(20000, 0, exclusion);
        ok &= delayed_wake(20000, 4, exclusion);
    }
    return ok ? 0 : 1;
}
