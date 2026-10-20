#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum { DM_TC_MAX_TOUCH = 16, DM_TC_COUNT = 12 };
enum {
    DM_TC_NONE = -1, DM_TC_JOYSTICK = -2, DM_TC_SWAP = -3, DM_TC_DIFF = -4,   /* DIFF: a finger captured by the difficulty cell / selector bar; sends no key */
    DM_TC_EDGE = -5,   /* A finger that started in the strip along the bottom edge of the screen that belongs to the system: not treated as the stick, and its release is not treated as a ground tap */
    DM_TC_MAIN = 0,
    DM_TC_SKILL1, DM_TC_SKILL2, DM_TC_SKILL3, DM_TC_SKILL4,
    DM_TC_PORTAL, DM_TC_BELT1, DM_TC_BELT2, DM_TC_BELT3, DM_TC_BELT4,
    DM_TC_MENU, DM_TC_MAP
};
typedef struct { float x, y, r; uint64_t button; } dm_tc_target;
typedef struct {
    float width, height;
    dm_tc_target target[DM_TC_COUNT];
    float joy_x, joy_y, joy_radius;
    dm_tc_target swap;   /* Skill set switch key: a local toggle; does not send a key directly */
    dm_tc_target diff;   /* Bottom UI v4 cell 0 difficulty: tap to open / collapse the 1–8 selector bar; sends no key */
    dm_tc_target pick[8];   /* The selector bar's 8 cells (cell i = player-count level i+1), above the seven cells */
} dm_tc_layout;
typedef struct {
    int active, target;
    float x, y;
    float aim_origin_x, aim_origin_y;
    uint64_t aim_move_sequence;
    int aim_cancelled;
    int key_down; double key_down_s;   /* Skill button: whether the key has gone down and when (after press, first wait the decision time, see update) */
    double start_time_s;
    int pointer_dragged, pointer_long;
    /*Continuous UI gesture (mouse click mode, started neither in the item area nor outside the panel; when displacement crosses the threshold the type is fixed by the initial direction and does not change afterwards): 1 = vertical drag (scroll), 2 = horizontal drag (slider).
              The gesture layer only fixes the type; on seeing it the front end forwards the start point and current point to the host (dm_ui_drag_*), and the scroll / slider is done by the host according to the game's own hit testing */
    int ui_drag;
    int shop_drag;   /* Drag starting from goods on the vendor shelf (not picked up): on release, buy / do not buy by the drop point */
    int locked_drag; /* Drag starting from another item while the single-item quest slot is occupied: do not pick up, and send no key on release */
} dm_tc_finger;
typedef struct {
    dm_tc_layout layout;
    dm_tc_finger finger[DM_TC_MAX_TOUCH];
    int joy_slot;
    float joy_origin_x, joy_origin_y;
    uint32_t enabled_targets;
    uint64_t buttons;
    int32_t lx, ly, rx, ry;
    int aim_slot, navigation_mode, map_cancel_active;
    uint64_t aim_move_sequence;
    int portal_pending, portal_phase; // 0idle / 1modifier-pending / 2armed
    uint64_t gesture_epoch, portal_binding_identity, portal_scene_epoch;
    /* Short-press pulse for release-to-cast: the key and the right-axis direction are published together, and the front end calls dm_tc_pulse_end to release it when due */
    uint64_t pulse_button, pulse_epoch;
    int32_t pulse_rx, pulse_ry;
    uint64_t defer_button; double defer_at_s;   /* The too-short tap in the second set: make it up once ZL has led long enough */
    /* Skill set: 0 = first set; 1 = second set (on the original Switch game, holding ZL uses the alt slots). It is a mode and is not cleared on cancel/size change */
    int skill_set;
    /*Second skill set (ZL modifier): ZL is held only while a finger is on the main button / a skill button or a skill pulse is being sent, and goes down DM_TC_ZL_LEAD_S before the skill button.
              When a release-to-cast press is too short, that pulse is delayed until ZL has led long enough (dm_tc_tick starts it when due). */
    int pointer_slot;
    double last_time_s;
    int pointer_pickup_done;
    int pointer_pulse_active, pointer_pulse_pending;
    float pointer_pending_x, pointer_pending_y;
    int pointer_valid;
    float pointer_x, pointer_y;
    /*Item gestures: pointer_item = the current pointer finger landed in the item area (set by the front end before release from the host's hit result). A single tap in the item area only moves the cursor (shows the tooltip),
              double tap = hold A (game hint: hold = open / use / equip; with the stash open, hold Y = move to the other side); a single tap outside the item area is as before = move the cursor + press A.
              pulse_hold_s > 0 = this pulse must be held this long, and the front end waits it out in full in addition to "the game has consumed it" before releasing */
    int pointer_item;
    /*Taps outside the item area go through mouse clicks (pause menu buttons and the close / repair buttons inserted back into the layout only respond to the mouse): mouse_click_mode is turned on by the front end;
              each such tap increments mouse_click_seq, and on seeing a change the front end sends one UI mouse click at (mouse_click_x, mouse_click_y) and no longer presses A */
    /*Whether the drag-and-drop release spot (the drop point where the item is lifted above the finger) is the item area: set by the front end before release. If not = dragged outside the panel = discard (pointer returns to the original spot and presses Y once in place).
              holding = the cursor is still holding an item (the last drop did not succeed): then tapping the item area = put down (A), tapping elsewhere does nothing */
    int pointer_release_item, holding; float release_x, release_y;
    /*A tap in game state (no panel open) = tap the game world: the finger did not land on any widget target (including landing in the stick area without dragging), less than 0.35 seconds from press to lift, displacement within the tap threshold
              → world_tap_seq is incremented, and on seeing a change the front end calls the host's dm_world_tap (tap an item name to pick up / tap an NPC to talk / tap a chest; tapping empty ground sends nothing). */
    unsigned world_tap_seq; float world_tap_x, world_tap_y;
    int close_left; double close_next_s;   /* After a tap outside the panel, how many more B presses remain and the earliest time of the next one (press until the panel is closed) */
    /*Vendor page: this press landed on goods on the shelf (set by the front end on host hit result 7). A drag starting from goods = intent to buy: do not send "pick up", and the cursor stays on that item (the host buys the item the cursor has selected);
              on release shop_drop_seq is incremented and the front end decides by the drop point -- landing in an inventory-type item area = buy; dragged back to the shelf / outside the panel / elsewhere = do not buy */
    int pointer_shop; unsigned shop_drop_seq;
    int pointer_lock;   /* Pressing on another item while the single-item quest slot holds something (host hit result 10): move the cursor and show the tooltip as in the item area, but do not pick it up; double tap / long press / single tap do not move it, and the item in the slot is not placed here either */
    /* Stacked cell of the advanced stash (set by the front end on host hit result 8): everything else follows the item area, only double tap differs -- stack_take_seq is incremented and the front end calls the host's dm_stash_take(1) to take 1 into the inventory */
    int pointer_stack; unsigned stack_take_seq;
    unsigned ident_seq;   /* Number of double taps on an unidentified item in the item area (only when unidentified does double tap = free identify, and this rule is checked first on every page): on seeing a change the front end calls the host's dm_ui_identify_hovered */
    unsigned use_seq;   /* Number of double taps in the item area (when no stash is open): on seeing a change the front end calls the host's dm_ui_use_item -- performs the native use / buy / equip on the item under the cursor without waiting for the "hold A" threshold */
    unsigned item_tap_seq;   /* Number of single taps in the item area (on seeing a change the front end calls the host's dm_ui_item_tap: in identify state, single-tapping an item = identify it) */
    unsigned long_press_seq;   /* Number of times the item area was held still for the full long-press duration (on seeing a change the front end calls the host's dm_ui_long_press: inventory potion → belt) */
    unsigned tab_tap_seq;   /* Number of taps that landed on a tab (on seeing a change the front end calls the host's dm_ui_tab_go) */
    int mouse_click_mode; unsigned mouse_click_seq; float mouse_click_x, mouse_click_y;
    /* Temporary front-end rewrite of "taps inside a panel outside the item area": non-zero = send no mouse click; instead the controller cursor walks to the touch point and presses this key on arrival (tapping a skill in the skill binding flow = cursor onto it and press Y). Tabs / outside the panel behave as before */
    uint64_t tap_button; float tap_x, tap_y; int tap_move; unsigned tap_move_seq;   /* tap_move: this tap only moves the cursor to tap_x / tap_y and sends no click (skill icon / attribute "+": select first, then confirm) */
    double pulse_hold_s;
    double last_tap_s; float last_tap_x, last_tap_y;
    double stash_x_check_s; float stash_x_x, stash_x_y; unsigned stash_x_id;   /* With the stash open, double-tapping an inventory item sent X first: if at this time the item is still under the cursor (the game did not accept that X), fall back to hold Y */
    uint64_t pointer_pending_button; double pointer_pending_hold;
    /* Difficulty: diff_open = selector bar expanded; diff_request = the player-count level just selected (1–8), cleared after the front end hands it to the host's dm_hud_request_players */
    int diff_open, diff_request;
    /*Belt expansion (the rows of the original game's keyboard-and-mouse "show belt"; the controller version has no entry for it): when the worn belt has more than 1 row, swiping up on a belt cell = expand, swiping down / tapping elsewhere = collapse,
              and after expansion tapping a potion in the upper rows = drink. belt_rows / belt_open are written by the front end from host readings before each touch; belt_request is cleared after the front end takes it:
              1 expand, 2 collapse, 0x100 | row << 4 | column = drink that cell (row 1–3 = which row above the bottom row) */
    int belt_rows, belt_open, belt_request;
    /* one tap on the belt = the player drinks, at the moment of release, several taps drink several; no double-tap detection, no mercenary feeding gesture on the belt */
    int belt_gap_cell; double belt_gap_at;   /* to drink a potion while a skill of the second skill set is held: first release ZL and the skill key and leave a gap of DM_TC_ZL_LEAD_S, and only at belt_gap_at press the belt key (belt_gap_cell = the cell that is waiting, 0 = none) */
    double joy_lost_s; float joy_lost_x, joy_lost_y;   /* time and position at which the joystick finger was cancelled by the system (0 = none): a finger landing again nearby right afterwards continues as the joystick */
    int joy_block;   /* speech text box open on its own (the front end does not enter panel state): a finger on the base starts no stick and is still just one click (closes the speech box). Written by the front end from the panel stack */
    double belt_pulse_s;   /* Time until which the most recent "player drinks" belt pulse is still being sent: during it the held second-set skill gives way together with ZL, and after the release ZL again leads by DM_TC_ZL_LEAD_S before the skill key comes back */
    int belt_q;   /* another pulse is being sent / another resend is pending: queue and fire when free (they never overwrite each other). Value = cell */
} dm_tc_state;

/* Driven by the original game's UI messages; panels are not guessed from input keys. AutoMap is a combat overlay and does not switch to navigation. */
typedef struct { int game; uint64_t panels; } dm_tc_scene;
int dm_tc_navigation(dm_tc_scene *scene, const char *cat, const char *act, const char *arg);
int dm_tc_scene_dialog_only(const dm_tc_scene *scene);   /* Only the NPC dialog menu is open */
int dm_tc_scene_dead(void);   /* Death popup open (navigation state, but no controller round buttons) */

/* Coordinates use UIKit points; the layout itself does not draw the orbs and does not claim the game has bound town portal/belt. */
/* Left/right safe-area insets (points); set before init / resize, and the layout afterwards uses them to move the right-side skill key group and the left stick into the safe area. Default 0. */
void dm_tc_set_safe_insets(float left, float right);
void dm_tc_set_edge_bottom(float bottom);   /* Height (points) of the strip along the bottom edge of the screen that belongs to the system; 0 = none. Constrains only where the movement stick may start */
void dm_tc_layout_make(dm_tc_layout *layout, float width, float height);
int dm_tc_hit(const dm_tc_layout *layout, float x, float y);
#define DM_TC_POINTER_LIFT_PT 40.0f   // Number of points the item is lifted above the finger while dragging on function pages (× widget scale)
void dm_tc_set_tall_scale(int on);   // Switch for scaling up by height/440 when picture height > 440 points; default off (the Mac host touch test cases pass pixel counts and must not be scaled up); the iOS front end turns it on when creating the view
float dm_tc_scale_for_size(float width, float height);   // Widget scale: phone min(1, width/667, height/375); when picture height > 440 points (iPad), scale up proportionally by height/440
void dm_tc_init(dm_tc_state *state, float width, float height);
/* A size change cancels all touch points, and the caller then pushes the zeroed state. */
void dm_tc_resize(dm_tc_state *state, float width, float height);
/* Widget switches do not change the layout; existing touch points are cancelled when the valid bits are toggled. */
void dm_tc_enable_targets(dm_tc_state *state, uint32_t mask);
/*Widgets available in navigation mode (a panel / dialog / front-end page is open): the five virtual controller round buttons on the right (confirm / back / action / bind / next page = A B X Y R).
      The "close" at the bottom bar's cross position is no longer offered: only one close entry for panels remains (the close button at the top-right corner of the frame; while the round buttons are present there is also "back").
      pad = 0: the five round buttons are not offered either (used once in-run fingers tapping the UI directly is hooked up; switch DM_TOUCH_NAV_PAD=0, default 1). Both front ends share this one place and do not each write their own. */
static inline uint32_t dm_tc_nav_mask(int pad) { return pad ? ((1u<<DM_TC_MAIN)|(1u<<DM_TC_SKILL1)|(1u<<DM_TC_SKILL2)|(1u<<DM_TC_SKILL3)|(1u<<DM_TC_SKILL4)) : 0; }
/* A mode change releases all gestures; navigation mode only presses keys and does not enable skill dragging or the map cancel area. */
void dm_tc_set_navigation_mode(dm_tc_state *state, int navigation_mode);
void dm_tc_set_joy_block(dm_tc_state *state, int block);   /* speech text box / dialogue menu open on its own: a finger on the base starts no stick and is just one click */
/* Cancel only the core touch point owned by the town-portal widget; the physical touch point is kept by the front end. */
void dm_tc_set_portal_button(dm_tc_state *state, uint64_t mask);
void dm_tc_set_portal_binding(dm_tc_state *state, uint64_t mask, uint64_t binding_identity, uint64_t scene_epoch);
/* Feedback confirmation applies only to a pending gesture that is still held and whose identity/scene/request match; returns whether it was armed for the first time. */
int dm_tc_portal_ack(dm_tc_state *state, uint64_t gesture_epoch, uint64_t binding_identity, uint64_t scene_epoch);
void dm_tc_cancel_portal(dm_tc_state *state);
void dm_tc_begin(dm_tc_state *state, int slot, float x, float y);
void dm_tc_move(dm_tc_state *state, int slot, float x, float y);
void dm_tc_end(dm_tc_state *state, int slot);
void dm_tc_begin_at(dm_tc_state *state, int slot, float x, float y, double now_s);
void dm_tc_move_at(dm_tc_state *state, int slot, float x, float y, double now_s);
void dm_tc_end_at(dm_tc_state *state, int slot, double now_s);
void dm_tc_tick(dm_tc_state *state, double now_s);
void dm_tc_cancel_all(dm_tc_state *state);
void dm_tc_cancel_finger(dm_tc_state *state, int slot);   /* The system cancels this finger: do not treat it as a release, only let go of what it was holding */
/* End the cast pulse corresponding to epoch; returns whether anything changed (the caller then pushes) */
int dm_tc_pulse_end(dm_tc_state *state, uint64_t pulse_epoch);
// After release there is still a queued pointer pulse (the "put-down" of a drag-and-drop arrived before the "pick-up" was released): the front end waits until the game has seen a release once, then calls resume to start it
int dm_tc_pulse_pending(const dm_tc_state *state);
void dm_tc_pointer_press(dm_tc_state *state, float x, float y, uint64_t button);   /* Cursor to (x, y), then press button once; the current pointer finger is marked "long press handled" and its release no longer counts as a tap */
void dm_tc_pointer_item(dm_tc_state *state, int kind);   /* Called as soon as the pointer finger's hit result is available (before release at the latest): 1 = item area, 2 = tab, 3 = outside the panel (tap = close the panel), anything else = elsewhere inside the panel (tap = mouse click) */
void dm_tc_pointer_release(dm_tc_state *state, int kind);   /* Called before a drag-and-drop release: the host's drop decision (1 place at the lifted point / 4 place at the finger point / 3 discard / 0 put back where it was) */
void dm_tc_pointer_release_at(dm_tc_state *state, float x, float y);   /* Called before a drag-and-drop release: place at this position (computed by the host; equipment slot = slot center) */
void dm_tc_set_holding(dm_tc_state *state, int holding);
void dm_tc_set_cur_stack(unsigned id);   /* id of the inventory item the cursor is pointing at right now while the stash is open (pointing at the stash side / pointing at nothing = 0) */
void dm_tc_set_hover_unid(unsigned id);   /* id of our unidentified item the cursor is pointing at right now (host dm_ui_hover_unid): an item-area double tap checks it first -- non-zero = identify (ident_seq incremented), skipping each page's original double tap */
void dm_tc_set_tap_box(int on);   /* Whether the most recently single-tapped item is the cube (with the stash open, double-tapping the cube = open) */
void dm_tc_set_panel_state(int bits);   /* State bits the host obtains by reading the game panel tree (1 stash open / 2 vendor page / 4 death popup); the front end calls this when the UI message DM:PanelState arrives */
void dm_tc_set_iso_fix(int on);   /* Switch for the movement stick's diagonal pre-correction (default on; used to measure before and after the change) */
int dm_tc_belt_outside(const dm_tc_state *state, float x, float y);
#define DM_TC_AIM_SETTLE_S 0.08    /* After a skill button is pressed, wait this long to decide tap versus drag (dragging past the dead zone puts the key down early) */
#define DM_TC_BELT_SWIPE_PT 24      /* On release over a belt cell, vertical displacement beyond this many points = expand / collapse; less = tap (drink) */
#define DM_TC_KEY_MIN_S 0.035       /* A skill button is held at least this long (about 2 frames); a shorter one is made up as a pulse on release to guarantee the game reads it */
#define DM_TC_JOY_RESUME_S 0.35   /* after the joystick finger is cancelled by the system, a finger landing again near the same spot within this long continues as the joystick (landing near the base is not required) */
#define DM_TC_JOY_GRAB_K 1.5f   /* the joystick starts only when a finger lands within this many radii of the joystick base center (the base is fixed and does not follow the touch-down point) */
#define DM_TC_ZL_LEAD_S 0.17   /* Time the modifier key leads the main key (about 10 frames; pressed in the same frame, the game only recognizes the main key) */
#define DM_TC_DOUBLE_TAP_S 0.40   /* Upper limit of the interval between two single taps */
#define DM_TC_HOLD_USE_S 0.60     /* Hold duration of the "hold" action: measured on the Mac host, 0.25 s only picks up, 0.45 s opens the cube */
int dm_tc_pulse_resume(dm_tc_state *state);

#ifdef __cplusplus
}
#endif
