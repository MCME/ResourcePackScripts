// MCME GUI: 3D models in a screen (docs/gui.md: Models). For the item shader; needs dynamictransforms.glsl,
// projection.glsl and globals.glsl before it.
//
// A screen's board is drawn in place of the camera's view, so a model can't simply float in front of the player:
// turning the head would slide it across the screen. MCME-GUI puts each model's item display on the stage instead,
// far below the world at y GUI_STAGE_Y, straight under the camera, and this draws it on the board like the rest:
// - its x and -z from the camera are its board point, as a text display's are (they are exact: the seat puts the
//   camera there);
// - the display lies like the board (model up is north, model front is up), so its height is how near it is:
//   GUI_STAGE_LAYER_STEP blocks a layer, and within a layer, up to GUI_STAGE_DEPTH blocks either way from it.
// Nothing else is ever there: displays don't fall out of the world, and nothing in the world goes that deep. Displays
// aren't culled by the view (no culling box) or by chunks (none past the world's height), so the stage is drawn
// whichever way the camera looks.
//
// A model draws between its layer's panels and its text, lit like an item in an inventory, without fog or the
// world's light. Every pixel is opaque or not drawn (docs/gui.md: Draw order): its alpha is multiplied far past 1.
//
// Must match MCME-GUI's Board (STAGE_Y, STAGE_LAYER_STEP), Session (SEAT_GRID) and the numbers of mcme_gui.glsl,
// copied here so that this needs nothing of the text shader's.

#ifndef MCME_GUI_STAGE_GLSL
#define MCME_GUI_STAGE_GLSL

const float GUI_STAGE_Y = -2048.0;
const float GUI_STAGE_LAYER_STEP = 32.0;
const float GUI_STAGE_DEPTH = 12.0;
const float GUI_STAGE_SEAT_GRID = 16.0;
const vec2 GUI_STAGE_BOARD_HALF = vec2(12.0, 6.75);

// The camera sits in the middle of a 1/16 block step: a screen is open (mcme_gui_hud.glsl's gui_screen_open).
bool gui_stage_open() {
    vec2 f = abs(fract(CameraOffset.xz * GUI_STAGE_SEAT_GRID) - 0.5);
    return f.x < 0.002 && f.y < 0.002;
}

// The vertex's height above the stage, or a negative number when it isn't on the stage. Off the GUI's own
// projection (inventories, the hotbar: orthographic) nothing is.
float gui_stage_height(vec3 position) {
    if (ProjMat[3][3] == 1.0 || !gui_stage_open()) {
        return -1.0;
    }
    float y = position.y + float(CameraBlockPos.y) + CameraOffset.y - GUI_STAGE_Y;
    return y > -GUI_STAGE_DEPTH && y < GUI_STAGE_LAYER_STEP * 32.0 ? y + GUI_STAGE_DEPTH : -1.0;
}

// As mcme_gui.glsl's gui_view_half: the board area the screen shows.
vec2 gui_stage_view_half() {
    float aspect = ScreenSize.x / max(ScreenSize.y, 1.0);
    float boardAspect = GUI_STAGE_BOARD_HALF.x / GUI_STAGE_BOARD_HALF.y;
    return aspect >= boardAspect ? vec2(GUI_STAGE_BOARD_HALF.y * aspect, GUI_STAGE_BOARD_HALF.y)
                                 : vec2(GUI_STAGE_BOARD_HALF.x, GUI_STAGE_BOARD_HALF.x / aspect);
}

// As mcme_gui.glsl's gui_depth: slot 3 x layer + 1 is the layer's panels, + 3 its text.
float gui_stage_depth(float slot) {
    float d = 0.2 - 0.0014 * slot;
    return (ProjMat[2][2] * -d + ProjMat[3][2]) / d;
}

// The clip position of a stage vertex, height from gui_stage_height.
vec4 gui_stage_place(vec3 position, float height) {
    float layer = floor(height / GUI_STAGE_LAYER_STEP);
    float near = clamp((height - layer * GUI_STAGE_LAYER_STEP - GUI_STAGE_DEPTH) / GUI_STAGE_DEPTH, -1.0, 1.0);
    // Between the layer's panels (slot + 1) and its text (slot + 3), nearer higher.
    float slot = layer * 3.0 + 2.0 + near * 0.9;
    vec2 board = vec2(position.x, -position.z);
    return vec4(board / gui_stage_view_half(), gui_stage_depth(slot), 1.0);
}

// A model's brightness says what it is: block light 15 and sky light 15 a plain model, sky light 1-8 a part of a
// player drawn from their head (mcme_gui_skin.glsl's GUI_SKIN_*, for the entity shader). Returns 0 for a plain one.
int gui_stage_skin_part(ivec2 light) {
    int block = light.x >> 4;
    int sky = light.y >> 4;
    return block == 15 && sky >= 1 && sky <= 8 ? sky : 0;
}

// Lit as on a shelf, from the front, above and left, whatever the world's light. On the stage, a normal's x is the
// board's right, -z its up and y towards the viewer.
vec4 gui_stage_light(vec3 normal, vec4 color) {
    vec3 n = normalize(vec3(normal.x, -normal.z, normal.y));
    float key = max(0.0, dot(n, normalize(vec3(-0.35, 0.55, 0.75))));
    float fill = max(0.0, dot(n, normalize(vec3(0.6, -0.1, 0.8))));
    float light = min(1.0, 0.42 + 0.5 * key + 0.22 * fill);
    // Alpha far past 1: every pixel the cutout keeps is opaque.
    return vec4(color.rgb * light, 255.0);
}

#endif
