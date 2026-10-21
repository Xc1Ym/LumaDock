// Exercise the production AppKit front end in a temporary window, without game files.
#include "front_mac.m"
#include <assert.h>

static uint64_t received_buttons;
static int32_t received_lx, received_ly, received_rx, received_ry;
static uint64_t pad_received;
void dm_input_set(uint64_t b, int32_t lx, int32_t ly, int32_t rx, int32_t ry) {
    received_buttons = b; received_lx = lx; received_ly = ly; received_rx = rx; received_ry = ry;
}
void dm_pad_set(uint64_t b,int32_t lx,int32_t ly,int32_t rx,int32_t ry) {pad_received=b;(void)lx;(void)ly;(void)rx;(void)ry;}
void dm_touch_set(const dm_touch *t, int n) { (void)t; (void)n; }
void dm_focus_set(int value) { (void)value; }
void dm_audio_suspend(int value) { (void)value; }
void dm_gfx_suspend(int value) { (void)value; }
void dm_ui_rect(int *x, int *y, int *w, int *h) { *x = *y = 0; *w = 1280; *h = 720; }
int dm_screen_real(int *w, int *h) { *w = 1280; *h = 720; return 1; }
void mtl_set_ui_rect_fn(void (*fn)(double *, double *)) { (void)fn; }

@interface TestMotion : NSObject
@property NSWindow *window;
@property double timestamp, deltaX, deltaY;
@end
@implementation TestMotion
@end

static NSEvent *button(NSWindow *window, NSEventType type) {
    return [NSEvent mouseEventWithType:type location:NSMakePoint(200, 200) modifierFlags:0
                             timestamp:NSProcessInfo.processInfo.systemUptime
                          windowNumber:window.windowNumber context:nil eventNumber:1 clickCount:1 pressure:1];
}
static NSEvent *key(NSWindow *window, unsigned short code, NSEventType type) {
    return [NSEvent keyEventWithType:type location:NSZeroPoint modifierFlags:0
                           timestamp:NSProcessInfo.processInfo.systemUptime windowNumber:window.windowNumber
                             context:nil characters:@"j" charactersIgnoringModifiers:@"j" isARepeat:NO keyCode:code];
}
static NSEvent *flags(NSWindow *window, NSEventModifierFlags modifiers) {
    return [NSEvent keyEventWithType:NSEventTypeFlagsChanged location:NSZeroPoint modifierFlags:modifiers
                           timestamp:NSProcessInfo.processInfo.systemUptime windowNumber:window ? window.windowNumber : 0
                             context:nil characters:@"" charactersIgnoringModifiers:@"" isARepeat:NO keyCode:56];
}
static void neutral(void) {
    assert(!received_buttons && !received_lx && !received_ly && !received_rx && !received_ry);
}

static void check_controls(void) {
    NSWindow *window = g_window;
    if (!NSApp.active || !window.isKeyWindow) {
        fprintf(stderr, "FAIL: test window did not become active\n"); exit(2);
    }
    const unsigned short codes[] = {14, 49, 12, 5, 15, 8, 48, 46, 123, 126, 124, 125};
    const uint64_t buttons[] = {DM_BTN_A, DM_BTN_X, DM_BTN_L, DM_BTN_R, DM_BTN_ZR, DM_BTN_RS,
                               DM_BTN_PLUS, DM_BTN_MINUS, DM_BTN_LEFT, DM_BTN_UP, DM_BTN_RIGHT, DM_BTN_DOWN};
    uint64_t assigned = DM_BTN_B | DM_BTN_LS | DM_BTN_Y | DM_BTN_ZL;
    for (unsigned i = 0; i < sizeof codes / sizeof *codes; i++) {
        assert(!(assigned & buttons[i])); assigned |= buttons[i];
        on_keyboard_event(key(window, codes[i], NSEventTypeKeyDown), window);
        assert(received_buttons == buttons[i]);
        on_keyboard_event(key(window, codes[i], NSEventTypeKeyUp), window); neutral();
    }
    assert(assigned == 0xffff);   // Exactly one binding for every Switch button.
    const unsigned short removed[] = {38, 40, 32, 34, 3, 6, 36, 51, 76};   // J/K/U/I/F/Z/Return/Backspace/keypad Enter.
    for (unsigned i = 0; i < sizeof removed / sizeof *removed; i++) {
        on_keyboard_event(key(window, removed[i], NSEventTypeKeyDown), window); neutral();
        on_keyboard_event(key(window, removed[i], NSEventTypeKeyUp), window); neutral();
    }
    assert(!g_mouse.captured);   // M was Minus, never a mouse toggle.
    on_keyboard_event(flags(window, NSEventModifierFlagShift), window);
    assert(received_buttons == DM_BTN_B);
    on_keyboard_event(flags(window, NSEventModifierFlagShift | NSEventModifierFlagControl), window);
    assert(received_buttons == (DM_BTN_B | DM_BTN_LS));
    on_keyboard_event(flags(window, NSEventModifierFlagControl), window);
    assert(received_buttons == DM_BTN_LS);
    on_keyboard_event(flags(window, 0), window); neutral();
    // Some modifier events have no window; accept them only for the active game window.
    on_keyboard_event(flags(nil, NSEventModifierFlagShift), window);
    assert(received_buttons == DM_BTN_B);
    on_keyboard_event(flags(nil, 0), window); neutral();
    on_mouse_button(button(window, NSEventTypeLeftMouseDown), window);
    assert(received_buttons == DM_BTN_Y);
    on_keyboard_event(key(window, 14, NSEventTypeKeyDown), window);
    assert(received_buttons == (DM_BTN_Y | DM_BTN_A));
    on_mouse_button(button(window, NSEventTypeLeftMouseUp), window);
    assert(received_buttons == DM_BTN_A);   // Releasing attack must preserve a held interaction key.
    on_keyboard_event(key(window, 14, NSEventTypeKeyUp), window); neutral();
    NSEvent *title_down = [NSEvent mouseEventWithType:NSEventTypeLeftMouseDown
        location:NSMakePoint(20, NSHeight(window.contentView.bounds) + 10) modifierFlags:0
        timestamp:NSProcessInfo.processInfo.systemUptime windowNumber:window.windowNumber
        context:nil eventNumber:2 clickCount:1 pressure:1];
    assert(on_mouse_button(title_down, window) == title_down); neutral();
    NSEvent *unused_up = button(window, NSEventTypeLeftMouseUp);
    assert(on_mouse_button(unused_up, window) == unused_up); neutral();
    on_mouse_button(button(window, NSEventTypeRightMouseDown), window);
    assert(received_buttons == DM_BTN_ZL);
    on_keyboard_event(key(window, 14, NSEventTypeKeyDown), window);
    assert(received_buttons == (DM_BTN_ZL | DM_BTN_A));   // Shield parry combo.
    on_keyboard_event(key(window, 14, NSEventTypeKeyUp), window);
    on_keyboard_event(key(window, 49, NSEventTypeKeyDown), window);
    on_keyboard_event(key(window, 0, NSEventTypeKeyDown), window);
    assert(received_buttons == (DM_BTN_ZL | DM_BTN_X) && received_lx == -32767);   // Side-hop combo.
    on_keyboard_event(key(window, 49, NSEventTypeKeyUp), window);
    on_keyboard_event(key(window, 0, NSEventTypeKeyUp), window);
    on_mouse_button(button(window, NSEventTypeLeftMouseDown), window);
    assert(received_buttons == (DM_BTN_Y | DM_BTN_ZL));
    input_release(); neutral();
    on_keyboard_event(key(window, 53, NSEventTypeKeyDown), window);
    on_keyboard_event(key(window, 53, NSEventTypeKeyUp), window);
    if (!g_mouse.captured) { fprintf(stderr, "FAIL: native mouse capture failed\n"); exit(3); }
    neutral();   // Escape never sends a guest button.
    TestMotion *motion = [TestMotion new];
    motion.window = window; motion.timestamp = NSProcessInfo.processInfo.systemUptime;
    motion.deltaX = 8; motion.deltaY = -4;
    on_mouse_motion((NSEvent *)motion, window);
    g_mouse_clock = NSProcessInfo.processInfo.systemUptime - 0.01;
    mouse_tick();
    assert(received_rx > 0 && received_ry > 0);
    on_keyboard_event(key(window, 13, NSEventTypeKeyDown), window);
    assert(received_ly == 32767 && received_rx > 0);   // Movement cannot erase the camera axis.
    on_keyboard_event(flags(window, NSEventModifierFlagShift), window);
    assert(received_buttons == DM_BTN_B && received_ly == 32767 && received_rx > 0);
    for (int i = 0; i < 7; i++) {
        g_mouse_clock = NSProcessInfo.processInfo.systemUptime - 0.01; mouse_tick();
    }
    assert(!received_rx && !received_ry);
    [[NSNotificationCenter defaultCenter] postNotificationName:NSWindowDidResignKeyNotification object:window];
    assert(!g_mouse.captured); neutral();
    mouse_capture(1); assert(g_mouse.captured);
    on_mouse_button(button(window, NSEventTypeLeftMouseDown), window);
    [[NSNotificationCenter defaultCenter] postNotificationName:NSWindowDidMiniaturizeNotification object:window];
    assert(!g_mouse.captured); neutral();
    mouse_capture(1); assert(g_mouse.captured);
    on_keyboard_event(key(window, 53, NSEventTypeKeyDown), window);
    on_keyboard_event(key(window, 53, NSEventTypeKeyUp), window);
    assert(!g_mouse.captured); neutral();
    // A new DM_INPUT_CONFIG changes mappings without recompiling the guest.
    NSMutableDictionary *config=[@{@"schema":@1,@"keyboard":@{@"A":@{@"code":@6,@"modifiers":@0},@"B":@{@"code":@56,@"modifiers":@0},@"LS":@{@"code":@59,@"modifiers":@0}},@"mouse":@{@"Y":@0,@"ZL":@1},@"gamepad":@{},@"axes":@{},@"mouseOptions":@{@"mode":@"camera",@"sensitivityX":@2,@"sensitivityY":@0.5,@"invertX":@YES,@"invertY":@NO,@"recenter":@NO},@"deadzone":@0.2} mutableCopy];
    NSString *path=[NSTemporaryDirectory() stringByAppendingPathComponent:[NSUUID.UUID.UUIDString stringByAppendingString:@"-input.json"]];
    [[NSJSONSerialization dataWithJSONObject:config options:0 error:NULL] writeToFile:path atomically:YES];setenv("DM_INPUT_CONFIG",path.UTF8String,1);input_load();input_release();
    on_keyboard_event(key(window,14,NSEventTypeKeyDown),window);neutral();on_keyboard_event(key(window,14,NSEventTypeKeyUp),window);
    on_keyboard_event(key(window,6,NSEventTypeKeyDown),window);assert(received_buttons==DM_BTN_A);on_keyboard_event(key(window,6,NSEventTypeKeyUp),window);neutral();
    config[@"keyboard"]=@{@"A":@{@"code":@14,@"modifiers":@3},@"B":@{@"code":@56,@"modifiers":@0},@"LS":@{@"code":@59,@"modifiers":@0}};
    [[NSJSONSerialization dataWithJSONObject:config options:0 error:NULL] writeToFile:path atomically:YES];input_load();
    on_keyboard_event(flags(window,NSEventModifierFlagShift|NSEventModifierFlagControl),window);assert(received_buttons==(DM_BTN_B|DM_BTN_LS));
    NSEvent *chord=[NSEvent keyEventWithType:NSEventTypeKeyDown location:NSZeroPoint modifierFlags:NSEventModifierFlagShift|NSEventModifierFlagControl timestamp:0 windowNumber:window.windowNumber context:nil characters:@"e" charactersIgnoringModifiers:@"e" isARepeat:NO keyCode:14];
    on_keyboard_event(chord,window);assert(received_buttons==DM_BTN_A);
    on_keyboard_event(key(window,14,NSEventTypeKeyUp),window);on_keyboard_event(flags(window,0),window);neutral();
    mouse_capture(1);motion.timestamp=NSProcessInfo.processInfo.systemUptime;motion.deltaX=8;motion.deltaY=-4;on_mouse_motion((NSEvent *)motion,window);g_mouse_clock=NSProcessInfo.processInfo.systemUptime-.01;mouse_tick();assert(received_rx<0 && received_ry>0);
    int32_t held_rx=received_rx;for(int i=0;i<7;i++){g_mouse_clock=NSProcessInfo.processInfo.systemUptime-.01;mouse_tick();}assert(received_rx==held_rx);
    input_release();neutral();pad_received=DM_BTN_A;read_gamepad(nil);assert(pad_received==0);
    [[NSFileManager defaultManager] removeItemAtPath:path error:NULL];unsetenv("DM_INPUT_CONFIG");
    puts("PASS: runtime configuration reload, chord priority, independent sensitivities/inversion, optional hold, controller neutral state.");
    puts("PASS: unique PC bindings, removed aliases, modifier press/release, attack/block mouse, shield-parry and side-hop combinations, Esc capture toggle, camera idle neutral, focus/minimize cleanup and title-bar controls.");
    fflush(stdout);
    exit(0);
}

static void dummy_guest(void) { for (;;) sleep(1); }
int main(void) {
    setenv("DM_WINDOW", "1", 1);
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{ check_controls(); });
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 5 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{ input_release(); fprintf(stderr, "FAIL: UI test timed out\n"); exit(4); });
    front_run(dummy_guest);
    return 5;
}
