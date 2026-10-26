// Periodic profiling closes at a frame boundary even when every frame is selected.
// Fake counter / event objects exercise production heap ownership without a GPU.
#include "../nvn/nvn_mtl.m"
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t g_mod[MAX_MOD]; int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }
static int checks, failed;
#define CHECK(c, label) do { checks++; if (!(c)) { failed++; fprintf(stderr, "FAIL: %s\n", label); } } while (0)

@interface ProfileHeap : NSObject
@property int invalidations, resolutions;
@end
@implementation ProfileHeap
- (void)invalidateCounterRange:(NSRange)range { (void)range; _invalidations++; }
- (NSData *)resolveCounterRange:(NSRange)range {
    _resolutions++; uint64_t values[GP_MAX];
    for (NSUInteger i = 0; i < range.length; i++) values[i] = 1000 + 100 * i;
    return [NSData dataWithBytes:values length:range.length * sizeof *values];
}
@end
@interface ProfileDevice : NSObject
@end
@implementation ProfileDevice
- (uint64_t)queryTimestampFrequency { return 1000000000; }
@end
@interface ProfileEvent : NSObject
@property(copy) MTLSharedEventNotificationBlock notification;
@property uint64_t value;
@property int registrations;
@end
@implementation ProfileEvent
- (void)notifyListener:(MTLSharedEventListener *)listener atValue:(uint64_t)value block:(MTLSharedEventNotificationBlock)block {
    (void)listener; CHECK(!_notification, "a pending report keeps exclusive ownership of the heap");
    _notification = block; _value = value; _registrations++;
}
- (void)complete {
    MTLSharedEventNotificationBlock block = _notification; _notification = nil;
    CHECK(block != nil, "the sampled frame registered a completion report");
    if (block) block((id)self, _value);
}
@end

int main(void) { @autoreleasepool {
    ProfileHeap *heap = [ProfileHeap new]; ProfileEvent *event = [ProfileEvent new];
    g_gp_heap = (id)heap; g_dev = (id)[ProfileDevice new]; g_ev = (id)event;
    setenv("DM_NVN_GPUPROF", "every:1", 1);
    atomic_store(&g_cur_frame, 0); gp_begin(nil, 'C', nil); CHECK(!g_gp_state, "frame zero is not profiled");
    for (uint64_t frame = 1; frame <= 3; frame++) {
        atomic_store(&g_cur_frame, frame); gp_begin(nil, 'C', nil); gp_end(nil);
        CHECK(g_gp_state == 1 && g_gp_frame == frame && g_gp_n == 1, "a fresh sample belongs only to its selected frame");
        gp_begin(nil, 'C', nil); gp_end(nil);
        CHECK(g_gp_n == 2, "all encoders in the frame share its sample");
        g_fence = frame * 10;
        atomic_store(&g_cur_frame, frame + 1); gp_begin(nil, 'C', nil);
        CHECK(g_gp_state == 2 && atomic_load(&g_gp_busy), "the next frame closes the prior sample even for every:1");
        CHECK(event.value == g_fence, "report waits for every committed segment of the sampled frame");
        CHECK(g_gp_n == 2 && heap.invalidations == frame, "no following frame overwrites pending timestamps");
        [event complete];
        CHECK(!atomic_load(&g_gp_busy) && heap.resolutions == frame, "completion resolves the sampled frame once and releases the heap");
    }
    // Sparse periodic selection also closes without waiting for a later unprofiled commit.
    g_gp_every = 5; g_gp_state = 0;
    atomic_store(&g_cur_frame, 5); gp_begin(nil, 'C', nil); gp_end(nil); g_fence = 50;
    atomic_store(&g_cur_frame, 6); gp_begin(nil, 'C', nil); [event complete];
    CHECK(event.registrations == 4 && heap.resolutions == 4, "sparse and consecutive selection both report per frame");
    printf("t_gpuprof: %d checks, %d failed\n", checks, failed); return failed != 0;
} }
