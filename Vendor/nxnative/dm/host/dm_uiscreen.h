// On screens narrower than 16:9 (iPad 4:3), lay out the game UI at 16:9 while 3D still fills the whole screen. Off by default: when not turned on nothing is written, and the conversions below are all identity. Implementation and basis in dm_uiscreen.c
#pragma once
enum { DM_UISCREEN_OFF, DM_UISCREEN_TOP, DM_UISCREEN_CENTER, DM_UISCREEN_BOTTOM };
void dm_uiscreen_enable(int mode);           // Called by the front end when "the window is narrower than 16:9": DM_UISCREEN_BOTTOM etc. = turn on, with the UI rectangle (width = frame width, height = width÷16×9) top-aligned / centered / bottom-aligned; DM_UISCREEN_OFF = turn off and write the game's values back. Callable from any thread, takes effect next frame
void dm_uiscreen_pump(void);                 // Called every frame on the game main thread: on finding that the game rewrote the "screen width / height" globals (boot, switching docked / handheld mode), record the real values and rewrite them to the values the UI uses - this one place only, regardless of occasion
int dm_screen_real(int *w, int *h);          // Real frame width and height (the one used by 3D rendering and hit boxes). Returns 0 = not read yet
void dm_ui_rect(int *x, int *y, int *w, int *h);   // Position of the UI rectangle in the real frame (pixels); when off = the whole frame. The graphics layer shifting the UI draw and the front end placing the game view both read it; it is the only source for the vertical position
float dm_ui_ny(float ny_real);               // Normalized y in the real frame → normalized y within the UI rectangle (horizontal unchanged)
float dm_ui_ny_back(float ny_ui);            // Reverse
int dm_ui_proj_dy(void);   // Number of vertical pixels subtracted from the result of the game's "world point → screen" (main+0x1237c60 / 0x90d110) (the UI rectangle's y; not subtracting = 0). Add it back when the host itself calls these two functions and needs real frame coordinates
int dm_uiscreen_ingame(void);                // 1 = in a run (true fullscreen); 0 = out of a run (front end pages and loading screen: 16:9 centered with margins). The single signal, readable from any thread
void dm_uiscreen_set_ingame(int on);          // May only be called from the per-frame UI site (dm_cursor.c)
void dm_uiscreen_set_panel(int on);           // A large panel open in a run (function pages / stash / vendor / cube..., = the touch front end's panel mode): the UI rectangle moves to the center; when closed it drops back to the placement the front end chose. Called by the touch front end in the UI message callback
int dm_uiscreen_panel(void);                 // The state above: a large panel open in a run = 1
#include <stdint.h>
uint64_t dm_game_res(int docked);            // The value the game's render resolution parameter slot should give right now (packed {u32 width, u32 height}): the front end's native value, changed to 16:9 of the screen width when true fullscreen is on and not in a run
void dm_uiscreen_res_reread(void);            // May only be called by hle_oe.c when the game takes the "performance mode changed" notification
