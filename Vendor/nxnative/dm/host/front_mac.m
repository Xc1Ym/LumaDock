// Mac front end: with DM_WINDOW=1 open a window (CAMetalLayer, for the graphics backend to present frames) + keyboard → dm_input; the guest runs on a large-stack thread instead and the main thread belongs to AppKit.
// Without DM_WINDOW: the guest runs directly on the current thread, behaving the same as with no front end (windowless tests use this).
// PC layout: WASD left stick, mouse right stick; E=A, Shift=B, Space=X, left mouse=Y,
// right mouse=ZL, Q=L, G=R, R=ZR, Ctrl=press left stick, C=press right stick,
// Tab=Plus, M=Minus, arrows=D-pad. Esc only toggles mouse capture; no legacy aliases.
#import <Cocoa/Cocoa.h>
#import <CoreGraphics/CoreGraphics.h>
#import <QuartzCore/CAMetalLayer.h>
#import <Metal/Metal.h>
#include "dm.h"
#include "dm_input.h"
#include "dm_uiscreen.h"
void mtl_set_ui_rect_fn(void (*fn)(double *y, double *h));
static void ui_rect_frac(double *fy, double *fh) { int x, y, w, h, rw = 0, rh = 0; dm_ui_rect(&x, &y, &w, &h); if (dm_screen_real(&rw, &rh) && rh > 0) { *fy = (double)y / rh; *fh = (double)h / rh; } }   // Same as front_ios.m: vertical position and height of the UI rectangle (as fractions of the frame height)
__attribute__((constructor)) static void ui_shift_reg(void) { mtl_set_ui_rect_fn(ui_rect_frac); }   // Must also take effect when running without a window (screenshots / gate checks), so it is not placed where the layer is created
#include "front.h"
#include "hle.h"
#include <signal.h>
#include "mouse_mac.h"
#include "input_config_mac.h"

static CAMetalLayer *g_layer;
static uint64_t g_btn, g_mouse_btn;
static int g_w, g_a, g_s, g_d;
static int32_t g_key_rx, g_key_ry, g_mouse_axes[4];
static int g_mouse_targets[24];
static unsigned g_mouse_physical;
static dm_mouse_mac g_mouse = {.sensitivity = 1};
static double g_mouse_clock, g_mouse_since;
static __weak NSWindow *g_window;

void *front_metal_layer(void) { return (__bridge void *)g_layer; }
// The original game's 16:9 constants, behavior unchanged; DM_GAME_RES=<width>x<height> (docked mode; handheld scaled by 720/900) is only for side-by-side comparison with iOS widescreen
uint64_t front_game_res(int docked) {
    unsigned w, h; const char *e = getenv("DM_GAME_RES");
    if (e && sscanf(e, "%ux%u", &w, &h) == 2) return docked ? (uint64_t)h << 32 | w : (uint64_t)(h * 4 / 5) << 32 | (w * 4 / 5 + 3) / 4 * 4;
    return docked ? 900ull << 32 | 1600 : 720ull << 32 | 1280;
}

static void push(void) {
    int32_t lx = (g_d - g_a) * 32767, ly = (g_w - g_s) * 32767;
    if(abs(g_mouse_axes[0])>abs(lx)) lx=g_mouse_axes[0]; if(abs(g_mouse_axes[1])>abs(ly)) ly=g_mouse_axes[1];
    int32_t rx=abs(g_mouse_axes[2])>abs(g_key_rx) ? g_mouse_axes[2] : g_key_rx, ry=abs(g_mouse_axes[3])>abs(g_key_ry) ? g_mouse_axes[3] : g_key_ry;
    dm_input_set(g_btn | g_mouse_btn, lx, ly, abs(rx)>abs(g_mouse.rx) ? rx : g_mouse.rx, abs(ry)>abs(g_mouse.ry) ? ry : g_mouse.ry);
}

static void mouse_capture(int on) {
    NSWindow *win = g_window;
    if (input_touch && on) return;
    if (on == g_mouse.captured) return;
    if (on) {
        if (!win.isKeyWindow || !NSApp.active || NSApp.modalWindow) return;
        NSPoint center = [win convertPointToScreen:NSMakePoint(NSMidX(win.contentView.bounds), NSMidY(win.contentView.bounds))];
        CGError error = CGWarpMouseCursorPosition(CGPointMake(center.x, CGDisplayBounds(CGMainDisplayID()).size.height - center.y));
        if (!error) error = CGAssociateMouseAndMouseCursorPosition(false);
        if (error) { LOG("[RED] cannot capture the mouse: CoreGraphics error %d", error); return; }
        [NSCursor hide];
    } else {
        CGAssociateMouseAndMouseCursorPosition(true);
        [NSCursor unhide];
    }
    dm_mouse_mac_capture(&g_mouse, on);
    g_mouse_btn = 0; g_mouse_physical=0; memset(g_mouse_targets,0,sizeof g_mouse_targets);memset(g_mouse_axes,0,sizeof g_mouse_axes);
    g_mouse_clock = g_mouse_since = NSProcessInfo.processInfo.systemUptime;
    win.title = on ? @DM_GAME_NAME " — Esc: release mouse" : @DM_GAME_NAME " — Esc: mouse look";
    LOG("mouse look %s", on ? "captured" : "released");
    push();
}

static void input_release(void) {
    mouse_capture(0);
    g_btn = g_mouse_btn = 0;
    g_w = g_a = g_s = g_d = g_key_rx = g_key_ry = 0;
    g_mouse_physical=0;memset(g_mouse_targets,0,sizeof g_mouse_targets);memset(g_mouse_axes,0,sizeof g_mouse_axes);
    memset(input_down,0,sizeof input_down); input_flags=0; input_touch_down=0; input_active=0; dm_pad_set(0,0,0,0,0);
    dm_mouse_mac_capture(&g_mouse, 0);
    dm_touch_set(NULL, 0);
    push();
}

static void mouse_tick(void) {
    if (!g_mouse.captured) return;
    if (!g_window.isKeyWindow || !NSApp.active || NSApp.modalWindow) { input_release(); return; }
    double now = NSProcessInfo.processInfo.systemUptime;
    double dt=now-g_mouse_clock;
    int held=!input_recenter && g_mouse.dx==0 && g_mouse.dy==0;
    int32_t rx=g_mouse.rx,ry=g_mouse.ry;
    dm_mouse_mac_tick(&g_mouse,dt);
    if (held && dt<=.1) {g_mouse.rx=rx;g_mouse.ry=ry;g_mouse.x=rx;g_mouse.y=ry;}
    g_mouse_clock = now;
    push();
}
static void keyboard_publish(void) {
    input_defaults(); int active[24]={0}; unsigned consumed=0;
    for(int i=0;i<24;i++) if(input_codes[i]>=0 && input_mods[i] && input_down[input_codes[i]] && (input_flags & input_mods[i]) == (unsigned)input_mods[i]) consumed |= input_mods[i];
    for(int i=0;i<24;i++) {
        int c=input_codes[i]; if(c<0) continue;
        unsigned modifier=c==56 ? 1 : c==59 ? 2 : c==58 ? 4 : 0;
        active[i]=modifier ? ((input_flags & modifier) && !(consumed & modifier)) : (input_down[c] && (input_flags & input_mods[i])==(unsigned)input_mods[i]);
        // An unmodified alias does not fire alongside a more specific chord on that key.
        if(!input_mods[i]) for(int j=0;j<24;j++) if(input_codes[j]==c && input_mods[j] && input_down[c] && (input_flags & input_mods[j])==(unsigned)input_mods[j]) active[i]=0;
    }
    g_btn=0; for(int i=0;i<16;i++) if(active[i]) g_btn|=1ull<<i;
    g_w=active[16];g_s=active[17];g_a=active[18];g_d=active[19];
    g_key_rx=(active[23]-active[22])*32767;g_key_ry=(active[20]-active[21])*32767;push();
}
static NSEvent *on_keyboard_event(NSEvent *e, NSWindow *win) {
    if (!win.isKeyWindow || !NSApp.active || NSApp.modalWindow) return e;
    if (e.window != win && !(e.type == NSEventTypeFlagsChanged && !e.window)) return e;
    if (e.modifierFlags & NSEventModifierFlagCommand) { input_release(); return e; }
    input_active=1;
    input_flags=(e.modifierFlags & NSEventModifierFlagShift ? 1 : 0)|(e.modifierFlags & NSEventModifierFlagControl ? 2 : 0)|(e.modifierFlags & NSEventModifierFlagOption ? 4 : 0);
    if(e.type == NSEventTypeFlagsChanged) {keyboard_publish();return nil;}
    if(e.keyCode == 53) {if(e.type==NSEventTypeKeyDown && !e.isARepeat) mouse_capture(!g_mouse.captured);return nil;}
    int c=canonical_key(e.keyCode);if(c<128) input_down[c]=e.type==NSEventTypeKeyDown;
    keyboard_publish();return nil;
}
static void pointer_touch(NSEvent *e,NSWindow *win,int down) {
    NSPoint p=[win.contentView convertPoint:e.locationInWindow fromView:nil]; NSRect b=win.contentView.bounds;
    if(!down || !NSPointInRect(p,b)) {dm_touch_set(NULL,0);return;}
    dm_touch t={.id=1,.x=fmax(0,fmin(1,p.x/NSWidth(b))),.y=fmax(0,fmin(1,1-p.y/NSHeight(b)))};
    dm_touch_set(&t,1);
}
static NSEvent *on_mouse_button(NSEvent *e, NSWindow *win) {
    BOOL down=e.type==NSEventTypeLeftMouseDown || e.type==NSEventTypeRightMouseDown || e.type==NSEventTypeOtherMouseDown;
    int button=(e.type==NSEventTypeRightMouseDown || e.type==NSEventTypeRightMouseUp) ? 1 : (e.type==NSEventTypeLeftMouseDown || e.type==NSEventTypeLeftMouseUp) ? 0 : (int)e.buttonNumber; input_defaults();uint64_t bits=0;
    for(int i=0;i<24;i++) if(input_mouse[i]==button) bits|=1ull<<i;
    if(button<0 || button>4) return e;
    unsigned physical=1u<<button;
    if(NSApp.modalWindow || (e.window!=win && (down || !(g_mouse_physical & physical)))) return e;
    if(!down && !(g_mouse_physical & physical)) return e;
    if(down && !NSApp.active) return e;
    if(down && !g_mouse.captured) {NSPoint p=[win.contentView convertPoint:e.locationInWindow fromView:nil];if(!NSPointInRect(p,win.contentView.bounds)) return e;}
    if(input_touch && button==0) {g_mouse_physical=down ? g_mouse_physical|physical : g_mouse_physical&~physical;input_touch_down=down;pointer_touch(e,win,down);return nil;}
    if(!bits) return e;
    g_mouse_physical=down ? g_mouse_physical|physical : g_mouse_physical&~physical;
    for(int i=0;i<24;i++) if(input_mouse[i]==button) g_mouse_targets[i]=down;
    g_mouse_btn=0;for(int i=0;i<16;i++) if(g_mouse_targets[i]) g_mouse_btn|=1ull<<i;
    g_mouse_axes[0]=(g_mouse_targets[19]-g_mouse_targets[18])*32767;g_mouse_axes[1]=(g_mouse_targets[16]-g_mouse_targets[17])*32767;
    g_mouse_axes[2]=(g_mouse_targets[23]-g_mouse_targets[22])*32767;g_mouse_axes[3]=(g_mouse_targets[20]-g_mouse_targets[21])*32767;
    push();return nil;
}
static NSEvent *on_mouse_motion(NSEvent *e, NSWindow *win) {
    if(input_touch && input_touch_down && e.window==win) {pointer_touch(e,win,1);return nil;}
    if(!g_mouse.captured || e.window!=win || e.timestamp<g_mouse_since) return e;
    dm_mouse_mac_move(&g_mouse,e.deltaX*input_sx,e.deltaY*input_sy);return nil;
}

typedef struct { void (*fn)(void); } guest_arg;
static void *guest_tramp(void *p) {
    static char alt[65536];                       // The signal alternate stack is per thread; crash printing must also work on the guest thread
    stack_t ss = {.ss_sp = alt, .ss_size = sizeof alt}; sigaltstack(&ss, 0);
    ((guest_arg *)p)->fn(); LOG("guest thread finished"); exit(0);
}

void front_run(void (*guest)(void)) {
    if (!getenv("DM_WINDOW")) { guest(); return; }
    @autoreleasepool {
        [NSApplication sharedApplication];
        input_load();
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
        NSRect r = NSMakeRect(0, 0, 1280, 720);
        NSWindow *win = [[NSWindow alloc] initWithContentRect:r
                                                    styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable
                                                      backing:NSBackingStoreBuffered defer:NO];
        g_window = win;
        win.title = @DM_GAME_NAME " — Esc: mouse look";
        win.acceptsMouseMovedEvents = YES;
        const char *sensitivity = getenv("DM_MOUSE_SENS");
        if (sensitivity) {
            double value = strtod(sensitivity, NULL);
            if (isfinite(value) && value >= 0.1 && value <= 10) g_mouse.sensitivity = value;
        }
        NSView *v = win.contentView;
        v.wantsLayer = YES;
        g_layer = [CAMetalLayer layer];
        g_layer.device = MTLCreateSystemDefaultDevice();
        g_layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
        g_layer.contentsScale = win.backingScaleFactor;
        v.layer = g_layer;
        [win center];
        [win makeKeyAndOrderFront:nil];
        [NSApp activateIgnoringOtherApps:YES];
        [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskKeyDown | NSEventMaskKeyUp | NSEventMaskFlagsChanged handler:^NSEvent *(NSEvent *e) {
            return on_keyboard_event(e, win);
        }];
        [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskLeftMouseDown | NSEventMaskLeftMouseUp | NSEventMaskRightMouseDown | NSEventMaskRightMouseUp | NSEventMaskOtherMouseDown | NSEventMaskOtherMouseUp handler:^NSEvent *(NSEvent *e) {
            return on_mouse_button(e, win);
        }];
        [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskMouseMoved | NSEventMaskLeftMouseDragged | NSEventMaskRightMouseDragged | NSEventMaskOtherMouseDragged handler:^NSEvent *(NSEvent *e) {
            return on_mouse_motion(e, win);
        }];
        NSTimer *mouse_timer = [NSTimer timerWithTimeInterval:1.0 / 120 repeats:YES block:^(NSTimer *timer) { (void)timer; mouse_tick(); }];
        [[NSRunLoop mainRunLoop] addTimer:mouse_timer forMode:NSRunLoopCommonModes];
        [[NSNotificationCenter defaultCenter] addObserverForName:NSWindowWillCloseNotification object:win queue:nil
                                                      usingBlock:^(NSNotification *n) { (void)n; input_release(); exit(0); }];
        // Lifecycle (hle.h / dm.h): focus lost → 2, focus regained → 1; minimized → 3 + audio paused + GPU suspended, restored → resume (followed by focus regained → 1)
        NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
        [nc addObserverForName:GCControllerDidConnectNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) {(void)n;refresh_gamepad();}];
        [nc addObserverForName:GCControllerDidDisconnectNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) {(void)n;refresh_gamepad();}];
        refresh_gamepad();
        [nc addObserverForName:NSWindowDidResignKeyNotification object:win queue:nil usingBlock:^(NSNotification *n) { (void)n; input_release(); if (!win.miniaturized) dm_focus_set(2); }];
        [nc addObserverForName:NSApplicationDidResignActiveNotification object:NSApp queue:nil usingBlock:^(NSNotification *n) { (void)n; input_release(); }];
        [nc addObserverForName:NSApplicationWillTerminateNotification object:NSApp queue:nil usingBlock:^(NSNotification *n) { (void)n; input_release(); }];
        [nc addObserverForName:NSWindowDidBecomeKeyNotification object:win queue:nil usingBlock:^(NSNotification *n) { (void)n; input_active=1; refresh_gamepad(); dm_focus_set(1); }];
        [nc addObserverForName:NSWindowDidMiniaturizeNotification object:win queue:nil usingBlock:^(NSNotification *n) { (void)n; input_release(); dm_focus_set(3); dm_audio_suspend(1); dm_gfx_suspend(1); }];
        [nc addObserverForName:NSWindowDidDeminiaturizeNotification object:win queue:nil usingBlock:^(NSNotification *n) { (void)n; dm_gfx_suspend(0); dm_audio_suspend(0); dm_focus_set(2); }];
        // Guest thread: 64 MiB stack (the Switch main thread stack is specified by npdm; the host gives plenty)
        static guest_arg ga; ga.fn = guest;
        pthread_attr_t a; pthread_attr_init(&a); pthread_attr_setstacksize(&a, 64u << 20);
        pthread_t th; if (pthread_create(&th, &a, guest_tramp, &ga)) die("pthread_create guest");
        [NSApp run];
    }
}

// Software keyboard input box (front.h): the main thread shows an NSAlert + text field and the guest thread waits synchronously for the result. Not shown in windowless mode (returns -1, the caller treats it as cancel)
int front_text_input(const char *title, const char *sub, const char *guide, const char *initial, int max_chars, char *out, int out_cap) {
    if (!g_layer) return -1;
    __block int r = 0;
    __block NSString *text = nil;
    dispatch_sync(dispatch_get_main_queue(), ^{
        input_release();
        NSAlert *a = [NSAlert new];
        a.messageText = title && *title ? @(title) : @"Input";
        NSString *info = [NSString stringWithFormat:@"%s%s%s", sub ? sub : "", sub && *sub && guide && *guide ? "\n" : "", guide ? guide : ""];
        a.informativeText = info;
        [a addButtonWithTitle:@"OK"]; [a addButtonWithTitle:@"Cancel"];
        NSTextField *f = [[NSTextField alloc] initWithFrame:NSMakeRect(0, 0, 300, 24)];
        f.stringValue = initial ? @(initial) : @"";
        if (guide && *guide) f.placeholderString = @(guide);
        a.accessoryView = f; a.window.initialFirstResponder = f;
        r = [a runModal] == NSAlertFirstButtonReturn;
        text = f.stringValue;
    });
    if (!r) return 0;
    (void)max_chars;                              // Truncation is done uniformly in hle_swkbd.c in UTF-16 units
    snprintf(out, out_cap, "%s", text.UTF8String);
    return 1;
}
