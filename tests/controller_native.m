// Exercise the actual nxnative Mac front end with Apple's writable snapshots.
#include "front_mac.m"
#include <assert.h>
#include <time.h>

int g_swkbd_min_chars;
static uint64_t received[DM_PLAYERS];
static int32_t axes[DM_PLAYERS][4];
void dm_input_set(uint64_t b, int32_t x, int32_t y, int32_t z, int32_t w) {(void)b;(void)x;(void)y;(void)z;(void)w;}
void dm_pad_set_player(int p,uint64_t b,int32_t x,int32_t y,int32_t z,int32_t w) {received[p]=b;axes[p][0]=x;axes[p][1]=y;axes[p][2]=z;axes[p][3]=w;}
void dm_pad_set(uint64_t b,int32_t x,int32_t y,int32_t z,int32_t w) {dm_pad_set_player(0,b,x,y,z,w);}
void dm_pad_players(uint32_t mask) {(void)mask;}
uint32_t dm_player_npad(int p) {return (uint32_t)p;}
void dm_touch_set(const dm_touch *t,int n) {(void)t;(void)n;}
void dm_focus_set(int s) {(void)s;}
void dm_audio_suspend(int s) {(void)s;}
void dm_gfx_suspend(int s) {(void)s;}
void dm_haptics_apple_init(void) {}
void dm_haptics_apple_controller(int p,GCController *c) {(void)p;(void)c;}
void dm_haptics_apple_shutdown(void) {}
// The front end now publishes GameController and passive HID motion to the
// service layer. Keep those sinks in the harness, like the pad/haptics sinks
// above; the host's own tests cover sensor fusion and HID packet decoding.
void dm_motion_set(int p,const float acc[3],const float rot[3]) {(void)p;(void)acc;(void)rot;}
void dm_motion_set_hid(int p,const float acc[3],const float rot[3],uint64_t ns) {(void)p;(void)acc;(void)rot;(void)ns;}
static unsigned motion_clears[DM_PLAYERS], hid_motion_clears[DM_PLAYERS];
void dm_motion_clear(int p) {assert(p>=0&&p<DM_PLAYERS);motion_clears[p]++;}
void dm_motion_clear_hid(int p) {assert(p>=0&&p<DM_PLAYERS);hid_motion_clears[p]++;}
uint64_t now_ns(void) {
    struct timespec t;assert(clock_gettime(CLOCK_MONOTONIC_RAW,&t)==0);
    return (uint64_t)t.tv_sec*1000000000ull+(uint64_t)t.tv_nsec;
}

// Snapshot controllers have no product identity. Override identity only; keep
// Apple's real GCExtendedGamepad elements and the production pad_read path.
@interface NamedController : GCController
@property NSString *testName;
@property NSString *testCategory;
@property GCExtendedGamepad *testPad;
@end
@implementation NamedController
- (NSString *)vendorName {return self.testName;}
- (NSString *)productCategory {return self.testCategory;}
- (GCExtendedGamepad *)extendedGamepad {return self.testPad;}
@end

@interface IdentityPad : GCExtendedGamepad
@property GCController *identity;
@property GCExtendedGamepad *backing;
@end
@implementation IdentityPad
- (GCController *)controller {return self.identity;}
- (GCControllerButtonInput *)buttonA {return self.backing.buttonA;}
- (GCControllerButtonInput *)buttonB {return self.backing.buttonB;}
- (GCControllerButtonInput *)buttonX {return self.backing.buttonX;}
- (GCControllerButtonInput *)buttonY {return self.backing.buttonY;}
- (GCControllerButtonInput *)buttonMenu {return self.backing.buttonMenu;}
- (GCControllerButtonInput *)buttonOptions {return self.backing.buttonOptions;}
- (GCControllerButtonInput *)leftShoulder {return self.backing.leftShoulder;}
- (GCControllerButtonInput *)rightShoulder {return self.backing.rightShoulder;}
- (GCControllerButtonInput *)leftTrigger {return self.backing.leftTrigger;}
- (GCControllerButtonInput *)rightTrigger {return self.backing.rightTrigger;}
- (GCControllerButtonInput *)leftThumbstickButton {return self.backing.leftThumbstickButton;}
- (GCControllerButtonInput *)rightThumbstickButton {return self.backing.rightThumbstickButton;}
- (GCControllerDirectionPad *)dpad {return self.backing.dpad;}
- (GCControllerDirectionPad *)leftThumbstick {return self.backing.leftThumbstick;}
- (GCControllerDirectionPad *)rightThumbstick {return self.backing.rightThumbstick;}
@end

int main(void) {
    @autoreleasepool {
        GCController *snapshot=[GCController controllerWithExtendedGamepad];
        NamedController *c=[NamedController new];
        IdentityPad *pad=[IdentityPad new];pad.identity=c;pad.backing=snapshot.extendedGamepad;c.testPad=pad;
        int p=pad_slot_take(&g_slots,(__bridge const void *)c,"snapshot");assert(p==0);g_held[p]=c;
        GCControllerButtonInput *buttons[]={pad.buttonA,pad.buttonB,pad.buttonX,pad.buttonY};
        for (NSString *name in @[@"Nintendo Switch Pro Controller",@"Joy-Con (L/R)",@"Pro Controller",@"Xbox Wireless Controller",@"DualSense Wireless Controller",@"DualShock 4",@"Generic USB Controller"]) {
            c.testName=name;c.testCategory=@"HID";
            BOOL nintendo=[name containsString:@"Nintendo"]||[name containsString:@"Joy-Con"]||[name isEqualToString:@"Pro Controller"];
            assert(luma_nintendo_layout(c)==nintendo);
            uint64_t xbox[]={DM_BTN_A,DM_BTN_B,DM_BTN_X,DM_BTN_Y};
            uint64_t switch_pad[]={DM_BTN_B,DM_BTN_A,DM_BTN_Y,DM_BTN_X};
            for(int i=0;i<4;i++) {
                [buttons[i] setValue:1];pad_read(pad);assert(received[p]==(nintendo?switch_pad[i]:xbox[i]));
                [buttons[i] setValue:0];pad_read(pad);assert(received[p]==0);
            }
        }
        [pad.buttonA setValue:1];[pad.buttonB setValue:1];[pad.leftTrigger setValue:1];[pad.rightShoulder setValue:1];
        [pad.leftThumbstick setValueForXAxis:.75 yAxis:-.5];pad_read(pad);
        assert(received[p]==(DM_BTN_A|DM_BTN_B|DM_BTN_ZL|DM_BTN_R));assert(axes[p][0]>0&&axes[p][1]<0);
#if __has_include("motion_pro_mac.h")
        // Simulate an assigned passive motion source without opening HID devices.
        g_pro_player=p;
#endif
        input_release();assert(received[p]==0&&axes[p][0]==0);pad_read(pad);assert(received[p]==0);
#if __has_include("motion_pro_mac.h")
        assert(hid_motion_clears[p]>0);
#endif
        g_input_on=1;pad_read(pad);assert(received[p]&DM_BTN_A);
        pads_changed(c);assert(received[p]==0&&axes[p][0]==0);assert(g_held[p]==nil);
#if __has_include("motion_apple.h")
        assert(motion_clears[p]>0);
#endif
        puts("PASS: native GameController face buttons, combos, axes, focus and disconnect cleanup");
    }
    return 0;
}
