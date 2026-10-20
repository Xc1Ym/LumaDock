#pragma once
#include <stdint.h>

void dm_cursor_set(int x, int y);
// The front end registers a 'pending write to the original game's cursor' (screen point coordinates), and the host applies it when the game reads the controller (hle_hid fill):
// it reaches the game in the same sample as the keys. If the front-end main thread writes the cursor global directly at an arbitrary time, the game writes it back from its own controller cursor state before processing A, and A lands at the old cursor
void dm_cursor_set_screen(float x, float y, float screen_w, float screen_h);
void dm_cursor_clear(void);
// Stick closed loop (interim approach, used until the original game's mouse mode switch is found): on a real device the original game's per-frame mouse move path does not run, and a directly written cursor gets overwritten by the controller cursor logic.
// Instead: on every controller read, read the original game's cursor (main+0x2d128f8/fc), and if it is > DM_CURSOR_NEAR (9) pixels from the target push the left stick toward the target (force reduced by distance within 60 pixels);
// an A pressed before it is in position is queued and held back together with the target position at that time, and released only when the cursor reaches that position (one each for the start / end of a drag-and-drop); if not in position after 1.5 seconds in the queue, report a failure and drop it.
// Called where the host reads the controller (hle_hid fill), reaching the game in the same sample as the keys
void dm_cursor_apply(uint64_t *buttons, int32_t *lx, int32_t *ly);
int dm_cursor_pending(void);   // How many A presses are still held back and not delivered to the game (the cursor is not in position yet); the front end must wait for it to return to zero before ending the pulse
// Native click (UI mouse message injection, see dm_cursor.c): the front end hands over the touch points, and the host sends them frame by frame to the UI root widget where the game reads the controller
void dm_ui_send_queue(const char *spec);   // 'category:action[:argument]'; sent to the UI root widget on the next controller read (used by the MSG step of key scripts)
int dm_ui_fe_drag_ok(void);                      // Whether a vertical drag in the front end can count as a scroll right now (not while the delete confirmation / mode page / naming page / a confirmation box is open)
void dm_ui_touch(int phase, float nx, float ny);   // phase: 0 down, 1 move, 2 up, 3 cancelled (turned into a scroll); coordinates = normalized to the rendered picture [0,1]
void dm_ui_mouse_pump(void);
// Generic pointer events: HOVER starts a held hover (pins the cursor every frame), MOVE updates the position, END ends the hold; the rest are queued, one per frame. arg: SCROLL = wheel amount (120 per notch), KEY = VK key code
enum { DM_UP_HOVER = 0, DM_UP_MOVE = 1, DM_UP_END = 2, DM_UP_LDOWN = 3, DM_UP_LUP = 4, DM_UP_RDOWN = 5, DM_UP_RUP = 6, DM_UP_SCROLL = 7, DM_UP_KEYDOWN = 8, DM_UP_KEYUP = 9 };
unsigned dm_ui_item_query(float nx, float ny);   // Ask 'is this point an item area'; returns the question sequence number; the main thread answers on the next frame
int dm_ui_item_result(unsigned seq);             // 1 item area / 2 tab / 0 other widget inside a panel / 3 outside the panels / 6 pressing on a button covered by an upper panel (not clicked) / 7 goods on the vendor shelf / 8 stacked cell / 10 another item while the single-item slot is occupied (left alone) / -1 not answered yet
unsigned dm_ui_drop_query(float nx, float ny_lifted, float ny_finger);   // How to handle a drag-and-drop landing point: result 5 put at the position given by dm_ui_drop_point (item area; for an equipment slot the slot center) / 3 drop / 0 put back where it was (fetched with dm_ui_item_result as well)
int dm_ui_drop_at_now(float nx, float ny_lifted, float ny_finger);        // Synchronous version, callable only from the game main thread
int dm_ui_origin_point(float *nx, float *ny);   // Center of the original position of the most recently 'picked up' item (used to put it back where it was); 0 = none
int dm_ui_drop_last(void);                      // Class of the most recently answered drag-and-drop landing point (used on release if this one has not been answered yet; -1 = none)
int dm_ui_drop_point(float *nx, float *ny);   // Put-down position when the landing verdict is 5 (normalized)
int dm_ui_drop_bag(void);                       // When the landing verdict is 5, whether the landing point is a player inventory cell (shelf drag-to-buy / dragging out of a stacked cell only complete here)
int dm_fe_bliss(void);   // Whether "Elysium" on the character-creation mode page is checked (1 = checked; the last value is kept after the player leaves the mode page and is read at character creation). Readable from any thread
int dm_ui_shelf_grid(float g[4]);   // Vendor shelf grid (normalized: top-left x,y, width and height of one cell); 0 = not probed yet
int dm_ui_item_rect(unsigned seq, float r[4]);   // Screen rectangle of the goods being held down on the vendor shelf (normalized; used for the finger-following image when dragging goods); 0 = none / not ready yet, ask again next frame
int dm_ui_stack_left(void);                       // How many items are in the stack of the stacked cell pressed this time; -1 = not read yet
void dm_ui_world_tap(float ux, float uy, float wx, float wy);   // Tap on the world in the game state: a tap on the mercenary portrait = open the mercenary page, otherwise forwarded to dm_world_tap(wx, wy). u = normalized to the view, w = normalized to the rendered picture
void dm_ui_stack_take_at(float nx, float ny);     // A stack in the advanced stash dragged to the inventory and released: put the cursor back on that stack and take 1 item into the inventory
void dm_ui_stack_cube_at(float nx, float ny);     // A stack in the advanced stash dragged onto the Horadric Cube cell at the bottom of this page and released (landing class 11): put the cursor back on that stack and press the original game's X = 1 item into the Horadric Cube
void dm_ui_shop_buy_at(float nx, float ny);       // Goods on the vendor shelf dragged to the inventory and released: put the controller cursor back on those goods (it was moved away when the drag started) and buy them
void dm_ui_item_tap(void);                       // Single tap in an item area: when in the 'identify scroll / tome used, waiting for target selection' state = identify the item under the cursor; does nothing when not in that state
int dm_ui_targeting(void);                       // Whether that state is in effect right now (published by the host every frame, read from any thread)
int dm_ui_panel_resident(const char *name);   // In-run always-on layers (the HUD layers, mercenary portrait bar, save indicator, button legend...): being open does not count as 'a panel is open'
enum { DM_PS_BANK = 1, DM_PS_VENDOR = 2, DM_PS_DEAD = 4, DM_PS_TEXT = 8, DM_PS_IMBUE = 16, DM_PS_CUBE = 32, DM_PS_VAULT = 64 };   // VAULT = the stash is open on the sixth page "Chronicle" (dm_vault_ui.c)   // CUBE = the Horadric Cube page is open (HoradricCubeLayout)   // IMBUE = the single-item task slot panel is open (ImbueItemsPanel, shared by imbue / socketing / personalize / tomb pedestal)
int dm_ui_panel_state(void);
void dm_ui_lifecycle(int background);   /* Called when the front end enters / leaves the background: position guard self-check (dm_cursor.c mv_audit) */   // Panel state bits (published by reading the game's panel tree every frame; on change the synthetic UI message DM:PanelState is sent)
int dm_ui_panel_shown(const char *name);   // This panel is visible in the game's panel tree right now (called from the game main thread)
int dm_ui_tap_box(void);   // Whether the most recently single-tapped item is the Horadric Cube
uint32_t dm_ui_cur_stack_id(void);   // While the stash is open, if the cursor is pointing at an item in the inventory right now = its unit id, otherwise 0
int dm_ui_free_cursor(void);   // Whether the current page has a free cursor
void dm_ui_use_item(void);                       // Double-tap in an item area: a vendor's goods under the cursor -> buy; equippable -> the original game's 'hold the confirm button' path (auto-equip); everything else -> use on the spot (drink a potion / read a scroll / open the Horadric Cube)
void dm_ui_long_press(void);                     // Long-press in an item area = refill the belt: if the controller cursor points at a potion in the inventory that can go into the belt and the belt has room, put it into the belt; anything else is left alone
void dm_ui_tab_go(void);                         // The most recent hit was a tab and this time it is a tap: press ZL / ZR (L / R at the top) enough times to switch to it
int dm_ui_item_at_now(float nx, float ny);        // Synchronous version of the above; may only be called from the game main thread
void dm_ui_watch(const char *spec);            // Test probe: watch the UI widget 'name[@panel name]' (NULL cancels); the main thread publishes its center every frame
int dm_ui_watch_pos(float *nx, float *ny);    // Any thread: returns 1 if the watched widget is visible and gives its coordinates normalized to the game view
uint64_t dm_ui_taps_base(void);   // Test: presented frame at which DM_UI_TAPS_AT hit (0 = not hit yet)
void dm_ui_ptr(int kind, float nx, float ny, int arg);
int dm_ui_touch_active(void);
// Front-end path streamlining (see dm_cursor.c): UI message callback registration, execution where the controller is read, auto key mask
void dm_ui_on_uimsg(const char *cat, const char *act, const char *arg);
void dm_ui_frontend_pump(void);
uint64_t dm_ui_auto_buttons(void);
void dm_ui_key_pulse(uint64_t mask, int frames);   // Tap a controller key on the player's behalf (held for frames guest frames)
// Continuous UI gestures (called by the front end from any thread, executed every frame on the main thread): kind 1 = vertical drag -> scroll, 2 = horizontal drag -> slider; coordinates = normalized to the rendered picture [0,1]; tol_ny = how much vertical slack to allow when identifying a slider (finger thickness)
void dm_ui_drag_begin(int kind, float ox, float oy, float tol_ny);
void dm_ui_drag_move(float x, float y);
void dm_ui_drag_end(void);
void dm_ui_drag_lift(float ny);   // Before a drag starts, report how far the item image is lifted above the finger (as a fraction of screen height): dragging a chronicle cell back to the inventory decides the landing point by the item image position (dm_vault_ui.c)
// Rectangle of the top-right minimap (the game's AutoMap panel) in the rendered picture, normalized [0,1]: r = left, top, right, bottom. Returns 1 = has been read (the most recent one is given while the panel is closed); callable from any thread
int dm_ui_minimap_rect(float r[4]);
// Full-screen map ↔ minimap (switched at runtime, not written to disk): dm_ui_map_full(1) switches to full screen, (0) returns to the minimap level set by the player; dm_ui_map_is_full() = whether the game is currently on the full-screen map (callable from any thread, refreshed every frame on the main thread)
// Touch flow for skill binding (called by the front end from any thread, advanced every frame on the main thread): dm_ui_bind_begin(key) = choose a skill for this controller key (may carry ZL = second set) -- the host opens the skill tree,
// the player taps a skill (while the flow is in progress the front end turns the tap into 'cursor to the point + press Y') -> the original game's "Press button to rebind skill" box pops up -> the host presses the target key for the player -> the panel closes. dm_ui_bind_active() = flow in progress (0 none / 1 opening the skill tree / 2 waiting for the player to tap a skill / 3 wrapping up)
void dm_ui_bind_begin(uint64_t key_mask);
int dm_ui_bind_slot(void);   /* Binding target slot 1..8 (F1–F8), 0 when not in the binding state */
void dm_ui_safe_left(int units);    /* Left safe area, in layout units (2160 high); the mercenary / party member portrait bar in the top-left corner is moved inward by it */
void dm_ui_safe_right(int units);   /* Right safe area, in layout units (2160 high); the minimap and info bar in the top-right corner are moved inward by it */
uint32_t dm_ui_hit_id(void);   /* The most recently hit point-spending button: attribute '+' 1..4 (strength / dexterity / vitality / energy), skill icon = an identifier with the top bit set to 1; 0 if nothing was hit */
int dm_ui_bind_active(void); uint64_t dm_ui_auto_release(void);   /* Used where the controller is read: the keys to release from the player's input right now */ int dm_ui_bind_skill_hit(float *nx, float *ny);   /* The most recent hit (after snapping) landed on a point-spending button: 1 = a skill icon in the skill tree, 2 = a '+' on the attributes page; comes with normalized coordinates */
void dm_ui_bind_cancel(void);
void dm_ui_map_full(int on);
int dm_ui_map_is_full(void);
void dm_ui_text_entered(const char *text);   // Called when the system keyboard returns: text = final text written back to the game (UTF-8); pass NULL for cancel / empty string
// Latency readout (diagnostic, DM_LAT_LOG=1): at key moments print a line "LAT <millisecond timestamp> <event>", to measure the latency from finger down / release to the game taking effect
int dm_lat_on(void);
#define DM_LAT(fmt, ...) do { if (dm_lat_on()) LOG("LAT %llu " fmt, (unsigned long long)(now_ns() / 1000000), ##__VA_ARGS__); } while (0)
void dm_ui_hand_idle(int idle);                  // Reported by the touch front end every tick: no fingers, no keys or cursor requests being sent / queued = 1 (used by the held-item guard, dm_cursor.c hand_guard)
uint32_t dm_ui_hover_unid(void);               // id of our own unidentified item the cursor is pointing at right now (inventory / stash / cube / equipped; none = 0). Published by the host every frame, read from any thread
void dm_ui_identify_hovered(void);              // Touch layer double-tap on an unidentified item: on the next frame the host calls free identify on it (dm_item_identify_free)
int dm_ui_map_geom(float *cell);   // Map geometry: returns 0 not open / 1 minimap / 2 full screen, *cell = pixels per cell (real picture pixels, any thread)
