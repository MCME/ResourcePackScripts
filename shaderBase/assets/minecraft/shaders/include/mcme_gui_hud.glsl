// MCME GUI: hiding the HUD while a screen is open (docs/gui.md). For the GUI pass; needs projection.glsl and
// globals.glsl.
//
// The GUI pass can't see the head turn or the screen's displays, but it does see where the camera is. The plugin
// seats a player with a screen open where the camera's x and z are each in the middle of a sixteenth of a block,
// which nobody stands at by chance (a block's centre is at the start of one), so that is how the GUI pass knows.
// Then it drops the crosshair and the hotbar with everything around it (off hand, hearts, food, armour, air, the
// experience and locator bars, the experience level), and the screen shows through to the bottom.
//
// Nothing moves a vertex: a menu opened over the screen (Esc, chat) shares these shaders, and a quad with only some
// corners moved stretches across the screen. The hotbar area is cut out per pixel, from the GUI position each
// vertex passes on; the crosshair by its exact corners.

#ifndef MCME_GUI_HUD_GLSL
#define MCME_GUI_HUD_GLSL

// Must match MCME-GUI's Session (SEAT_GRID): the middle of a 1/16 step, the same whichever way the offset runs.
const float GUI_SEAT_GRID = 16.0;

bool gui_screen_open() {
    vec2 f = abs(fract(CameraOffset.xz * GUI_SEAT_GRID) - 0.5);
    return f.x < 0.002 && f.y < 0.002;
}

// The GUI's size in GUI pixels while a screen is open and this is the GUI's orthographic projection; else 0.
vec2 gui_hud_ui() {
    return ProjMat[3][3] == 1.0 && gui_screen_open() ? 2.0 / vec2(ProjMat[0][0], -ProjMat[1][1]) : vec2(0.0);
}

// The hotbar and what sits above it, in GUI pixels: hearts, food and armour reach 64 up, the off hand 122 out.
bool gui_in_hotbar_area(vec2 pos, vec2 ui) {
    return abs(pos.x - ui.x * 0.5) <= 122.0 && pos.y >= ui.y - 64.0;
}

// Text there is the experience level and the held item's name; not the chat line being typed (the bottom 14
// pixels) or the action bar (68 up).
bool gui_in_hud_text_area(vec2 pos, vec2 ui) {
    return abs(pos.x - ui.x * 0.5) <= 122.0 && pos.y >= ui.y - 56.0 && pos.y < ui.y - 14.0;
}

bool gui_near(float a, float b) {
    return abs(a - b) < 0.01;
}

// 1 at a corner of the crosshair (15 pixels square at ((w - 15) / 2, (h - 15) / 2), whole pixels) or of the attack
// indicator under it (16 across at w / 2 - 8, 9 to 13 below the middle); 0 elsewhere. Only a quad with all four
// corners there is 1 all over.
float gui_crosshair_corner(vec2 pos, vec2 ui) {
    vec2 size = floor(ui + 0.5);
    vec2 at = floor((size - 15.0) * 0.5);
    bool cross = (gui_near(pos.x, at.x) || gui_near(pos.x, at.x + 15.0))
              && (gui_near(pos.y, at.y) || gui_near(pos.y, at.y + 15.0));
    vec2 mid = floor(size * 0.5);
    bool indicator = pos.x >= mid.x - 8.01 && pos.x <= mid.x + 8.01
                  && (gui_near(pos.y, mid.y + 9.0) || gui_near(pos.y, mid.y + 13.0));
    return cross || indicator ? 1.0 : 0.0;
}

#endif
