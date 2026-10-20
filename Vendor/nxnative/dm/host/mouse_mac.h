// Relative mouse movement -> right-stick velocity. Used only by the Mac front end.
#pragma once
#include <math.h>
#include <stdint.h>

typedef struct {
    int captured;
    double dx, dy, x, y, idle, sensitivity;
    int32_t rx, ry;
} dm_mouse_mac;

static inline void dm_mouse_mac_capture(dm_mouse_mac *m, int on) {
    double sensitivity = m->sensitivity;
    *m = (dm_mouse_mac){.captured = on, .sensitivity = sensitivity};
}

static inline void dm_mouse_mac_move(dm_mouse_mac *m, double dx, double dy) {
    if (!m->captured || !isfinite(dx) || !isfinite(dy)) return;
    m->dx += dx; m->dy += dy;
}

static inline void dm_mouse_mac_tick(dm_mouse_mac *m, double dt) {
    if (!m->captured || !isfinite(dt) || dt <= 0) return;
    // A delayed UI callback must not turn accumulated movement into a long spin.
    if (dt > 0.1) { dm_mouse_mac_capture(m, 1); return; }
    double gain = 32767.0 * m->sensitivity / (600.0 * dt);
    double x = m->dx * gain, y = -m->dy * gain;
    if (m->dx || m->dy) m->idle = 0; else m->idle += dt;
    m->dx = m->dy = 0;
    double length = hypot(x, y);
    if (length > 32767) { x *= 32767 / length; y *= 32767 / length; }
    double alpha = 1 - exp(-dt / 0.012);
    m->x += (x - m->x) * alpha; m->y += (y - m->y) * alpha;
    if (m->idle >= 0.05) m->x = m->y = 0;
    m->rx = (int32_t)lround(m->x); m->ry = (int32_t)lround(m->y);
}
