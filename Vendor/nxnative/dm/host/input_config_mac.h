// Versioned runtime input configuration. No game code or shader rebuild is required.
#pragma once
#import <GameController/GameController.h>
static const char *input_targets[] = {"A","B","X","Y","LS","RS","L","R","ZL","ZR","PLUS","MINUS","LEFT","UP","RIGHT","DOWN","LS_UP","LS_DOWN","LS_LEFT","LS_RIGHT","RS_UP","RS_DOWN","RS_LEFT","RS_RIGHT"};
static int input_codes[24], input_mods[24], input_mouse[24];
static NSString *input_pad[24];
static NSString *input_axes[4];
static int input_axis_inv[4], input_ready, input_touch, input_recenter = 1;
static double input_sx = 1, input_sy = 1, input_deadzone = .15;
static unsigned input_flags;
static unsigned char input_down[128];
static int input_active = 1, input_touch_down;
static int canonical_key(int code) { return code == 60 ? 56 : code == 62 ? 59 : code == 61 ? 58 : code; }
static void input_defaults(void) {
    if (input_ready) return; input_ready = 1;
    for (int i = 0; i < 24; i++) input_codes[i] = input_mouse[i] = -1;
    int code[] = {14,56,49,-1,59,8,12,5,-1,15,48,46,123,126,124,125,13,1,0,2,-1,-1,-1,-1};
    const char *pad[] = {"east","south","north","west","leftStick","rightStick","leftShoulder","rightShoulder","leftTrigger","rightTrigger","menu","options","dpadLeft","dpadUp","dpadRight","dpadDown"};
    for (int i = 0; i < 24; i++) {input_codes[i] = code[i]; if(i < 16) input_pad[i] = @(pad[i]);}
    input_mouse[3] = 0; input_mouse[8] = 1;
    input_axes[0] = @"leftX"; input_axes[1] = @"leftY"; input_axes[2] = @"rightX"; input_axes[3] = @"rightY";
}
static void input_load(void) {
    input_defaults(); const char *path = getenv("DM_INPUT_CONFIG"); if (!path) return;
    NSData *data = [NSData dataWithContentsOfFile:@(path)]; NSError *error = nil;
    NSDictionary *config = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:&error] : nil;
    if (![config isKindOfClass:NSDictionary.class] || [config[@"schema"] intValue] != 1) die("invalid DM_INPUT_CONFIG");
    NSMutableSet *keys = [NSMutableSet new], *mice = [NSMutableSet new], *pads = [NSMutableSet new];
    for (int i = 0; i < 24; i++) {
        NSString *target = @(input_targets[i]); NSDictionary *binding = config[@"keyboard"][target];
        input_codes[i] = -1; input_mods[i] = 0; input_mouse[i] = -1; input_pad[i] = nil;
        if (binding) {
            int code = canonical_key([binding[@"code"] intValue]), mods = [binding[@"modifiers"] intValue];
            NSString *physical = [NSString stringWithFormat:@"%d:%d",code,mods];
            if (code < 0 || code >= 128 || code == 53 || code == 54 || code == 55 || mods < 0 || mods > 7 || [keys containsObject:physical]) die("invalid or duplicate keyboard binding");
            [keys addObject:physical]; input_codes[i] = code; input_mods[i] = mods;
        }
        NSNumber *mouse = config[@"mouse"][target];
        if (mouse) { if ([mouse intValue] < 0 || [mouse intValue] > 4 || [mice containsObject:mouse]) die("invalid or duplicate mouse binding"); [mice addObject:mouse]; input_mouse[i] = [mouse intValue]; }
        NSString *pad = config[@"gamepad"][target];
        if (pad) { if (![pad isKindOfClass:NSString.class] || [pads containsObject:pad]) die("invalid or duplicate gamepad binding"); [pads addObject:pad]; input_pad[i] = pad; }
    }
    NSDictionary *m = config[@"mouseOptions"];
    input_touch = [m[@"mode"] isEqual:@"touch"]; input_recenter = m[@"recenter"] ? [m[@"recenter"] boolValue] : 1;
    input_sx = m[@"sensitivityX"] ? [m[@"sensitivityX"] doubleValue] : 1; input_sy = m[@"sensitivityY"] ? [m[@"sensitivityY"] doubleValue] : 1;
    if (!isfinite(input_sx) || !isfinite(input_sy) || input_sx < .1 || input_sx > 10 || input_sy < .1 || input_sy > 10) die("invalid mouse sensitivity");
    if ([m[@"invertX"] boolValue]) input_sx *= -1; if ([m[@"invertY"] boolValue]) input_sy *= -1;
    input_deadzone = config[@"deadzone"] ? [config[@"deadzone"] doubleValue] : .15;
    if (!isfinite(input_deadzone) || input_deadzone < 0 || input_deadzone >= .9) die("invalid controller deadzone");
    NSMutableSet *axes = [NSMutableSet new]; const char *names[] = {"LX","LY","RX","RY"};
    for (int i = 0; i < 4; i++) {
        NSDictionary *a = config[@"axes"][@(names[i])]; if (!a) continue;
        NSString *source = a[@"source"];
        if (![@[@"leftX",@"leftY",@"rightX",@"rightY"] containsObject:source] || [axes containsObject:source]) die("invalid controller axis binding");
        [axes addObject:source]; input_axes[i] = source; input_axis_inv[i] = [a[@"invert"] boolValue];
    }
    LOG("runtime input configuration loaded (schema 1)");
}
static float pad_button(GCExtendedGamepad *g, NSString *code) {
    if ([code isEqual:@"east"]) return g.buttonB.value;
    if ([code isEqual:@"south"]) return g.buttonA.value;
    if ([code isEqual:@"north"]) return g.buttonY.value;
    if ([code isEqual:@"west"]) return g.buttonX.value;
    if ([code isEqual:@"leftStick"]) return g.leftThumbstickButton.value;
    if ([code isEqual:@"rightStick"]) return g.rightThumbstickButton.value;
    if ([code isEqual:@"leftShoulder"]) return g.leftShoulder.value;
    if ([code isEqual:@"rightShoulder"]) return g.rightShoulder.value;
    if ([code isEqual:@"leftTrigger"]) return g.leftTrigger.value;
    if ([code isEqual:@"rightTrigger"]) return g.rightTrigger.value;
    if ([code isEqual:@"menu"]) return g.buttonMenu.value;
    if ([code isEqual:@"options"]) return g.buttonOptions.value;
    if ([code isEqual:@"dpadLeft"]) return g.dpad.left.value;
    if ([code isEqual:@"dpadUp"]) return g.dpad.up.value;
    if ([code isEqual:@"dpadRight"]) return g.dpad.right.value;
    if ([code isEqual:@"dpadDown"]) return g.dpad.down.value;
    return 0;
}
static int32_t pad_axis(GCExtendedGamepad *g, int i) {
    NSString *s = input_axes[i]; float v = [s isEqual:@"leftX"] ? g.leftThumbstick.xAxis.value : [s isEqual:@"leftY"] ? g.leftThumbstick.yAxis.value : [s isEqual:@"rightX"] ? g.rightThumbstick.xAxis.value : g.rightThumbstick.yAxis.value;
    if (!isfinite(v) || fabsf(v) <= input_deadzone) return 0;
    v = copysignf((fabsf(v)-input_deadzone)/(1-input_deadzone),v); return lroundf(fmaxf(-1,fminf(1,v)) * (input_axis_inv[i] ? -32767 : 32767));
}
static void read_gamepad(GCExtendedGamepad *g) {
    if (!input_active || !g) { dm_pad_set(0,0,0,0,0); return; }
    uint64_t buttons = 0; int pressed[24] = {0};
    for (int i=0;i<24;i++) {pressed[i]=pad_button(g,input_pad[i])>.5; if(i<16 && pressed[i]) buttons|=1ull<<i;}
    int32_t a[4]; for(int i=0;i<4;i++) a[i]=pad_axis(g,i);
    int32_t digital[] = {(pressed[19]-pressed[18])*32767,(pressed[16]-pressed[17])*32767,(pressed[23]-pressed[22])*32767,(pressed[20]-pressed[21])*32767};
    for(int i=0;i<4;i++) if(abs(digital[i])>abs(a[i])) a[i]=digital[i];
    dm_pad_set(buttons,a[0],a[1],a[2],a[3]);
}
static void refresh_gamepad(void) {
    dm_pad_set(0,0,0,0,0);
    for (GCController *c in GCController.controllers) {c.extendedGamepad.valueChangedHandler = nil;}
    for (GCController *c in GCController.controllers) {
        if (!c.extendedGamepad) continue; c.handlerQueue = dispatch_get_main_queue();
        c.extendedGamepad.valueChangedHandler = ^(GCExtendedGamepad *g, GCControllerElement *e) { (void)e; read_gamepad(g); };
        read_gamepad(c.extendedGamepad); break;
    }
}
