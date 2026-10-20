#include "../mouse_mac.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

int main(void) {
    dm_mouse_mac m = {.sensitivity = 1};
    dm_mouse_mac_move(&m, 20, -20); dm_mouse_mac_tick(&m, 0.01);
    assert(!m.rx && !m.ry);   // Ordinary desktop movement cannot steer.
    dm_mouse_mac_capture(&m, 1);
    dm_mouse_mac_move(&m, 6, -6); dm_mouse_mac_tick(&m, 0.01);
    assert(m.rx > 0 && m.ry > 0);   // Right/up motion -> right/up stick.
    for (int i = 0; i < 50; i++) { dm_mouse_mac_move(&m, 100, -100); dm_mouse_mac_tick(&m, 0.01); }
    assert(hypot(m.rx, m.ry) <= 32768);
    for (int i = 0; i < 6; i++) dm_mouse_mac_tick(&m, 0.01);
    assert(!m.rx && !m.ry);   // Stop moving -> neutral, no stuck camera.
    dm_mouse_mac_move(&m, 9, 9); dm_mouse_mac_capture(&m, 0);
    assert(!m.rx && !m.ry && !m.dx && !m.dy);
    dm_mouse_mac_capture(&m, 1); dm_mouse_mac_tick(&m, 0.01);
    assert(!m.rx && !m.ry);   // Recapture must not replay old movement.
    dm_mouse_mac a = {.captured = 1, .sensitivity = 1}, b = a;
    for (int i = 0; i < 40; i++) { dm_mouse_mac_move(&a, 2, 1); dm_mouse_mac_tick(&a, 0.005); }
    for (int i = 0; i < 20; i++) { dm_mouse_mac_move(&b, 4, 2); dm_mouse_mac_tick(&b, 0.01); }
    assert(abs(a.rx - b.rx) <= 2 && abs(a.ry - b.ry) <= 2);   // Same velocity at different event rates.
    dm_mouse_mac_move(&a, NAN, 2); dm_mouse_mac_tick(&a, NAN);
    assert(isfinite(a.x) && isfinite(a.y));
    dm_mouse_mac_move(&a, 500, 500); dm_mouse_mac_tick(&a, 0.5);
    assert(!a.rx && !a.ry && !a.dx && !a.dy);   // A UI stall cannot leave the camera spinning.
    puts("t_mouse_mac: PASS");
}
