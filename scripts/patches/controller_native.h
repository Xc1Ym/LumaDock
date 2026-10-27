// LumaNX automatic controller semantics. No keyboard events or user bindings.
#pragma once
#import <GameController/GameController.h>

static inline BOOL luma_nintendo_layout(GCController *controller) {
    // GameController's A/B/X/Y are positions, even on Nintendo controllers.
    // Apple exposes Nintendo as HID, so use the product identity, not HID alone.
    NSString *identity = [NSString stringWithFormat:@"%@ %@", controller.productCategory ?: @"", controller.vendorName ?: @""];
    for (NSString *token in @[@"Nintendo", @"Switch", @"Joy-Con", @"Pro Controller"]) {
        if ([identity rangeOfString:token options:NSCaseInsensitiveSearch].location != NSNotFound) return YES;
    }
    return NO;  // Xbox/MFi: printed letters; PS: cross/circle/square/triangle.
}

static inline uint64_t luma_face_buttons(GCExtendedGamepad *pad) {
    BOOL nintendo = luma_nintendo_layout(pad.controller);
    uint64_t bits = 0;
    if (pad.buttonA.isPressed) bits |= 1ull << (nintendo ? 1 : 0);
    if (pad.buttonB.isPressed) bits |= 1ull << (nintendo ? 0 : 1);
    if (pad.buttonX.isPressed) bits |= 1ull << (nintendo ? 3 : 2);
    if (pad.buttonY.isPressed) bits |= 1ull << (nintendo ? 2 : 3);
    return bits;  // Switch ABI: A=0, B=1, X=2, Y=3, shared by Mac and iOS.
}
