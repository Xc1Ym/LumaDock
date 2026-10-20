// Tapping a target in the game world = interacting with it (implementation and rationale in dm_world.c)
#pragma once
unsigned dm_world_tap(float nx, float ny);   // any thread: queue one tap (coordinates normalized to the rendered picture, [0,1]); the main thread resolves the target and sends the command at the controller-poll point, and sends nothing when there is no target. Returns the sequence number
int dm_world_tap_result(unsigned seq);       // -1 not executed yet; 0 no target; 1 item (pick up) 2 NPC (talk) 3 object (use) 4 exit 5 corpse (retrieve)
int dm_world_has_target(void);               // any thread: whether a target that the primary button would interact with exists (the game's own controller-version selection)
void dm_world_pump(void);                    // called every frame where the controller is fetched (main thread)
void dm_world_watch(int type, uint32_t cls);     // test probe: watch one kind of unit (type < 0 cancels); the main thread publishes the screen position of its body box center every frame
int dm_world_watch_pos(float *nx, float *ny);    // any thread: returns 1 and gives normalized coordinates when the watched unit is in the picture
// Minimap quest goals (dm_world.c): published by the main thread every frame, fetched by the front end from any thread. x / y = world cell; art >= 64 = frame art-64 of the Tal Rasha symbols, otherwise = nameplate number (tools/gen_map_goal_art.py)
typedef struct { int n, px, py; float sx, sy; int x[12], y[12]; unsigned char art[12]; } dm_map_goal_view;   // px / py player world cell; sx / sy position of the player's feet on screen (normalized)
int dm_map_goals(dm_map_goal_view *v);      // returns the number of goals (map marking switch off, no goal in this level, scan not finished = 0)
