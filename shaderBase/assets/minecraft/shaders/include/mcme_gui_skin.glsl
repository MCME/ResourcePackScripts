// MCME GUI: a player in a screen, built from their head (docs/gui.md: Players). For the entity shader's fragment
// stage; needs nothing.
//
// MCME-GUI's PlayerModel draws each part of a player (head, body, arms, legs) as an item display of the player's
// head on the stage, stretched to the part's size. A head is an 8 x 8 x 8 box with the skin's head on its faces, and
// a hat box 0.5 pixels bigger with the head's outer layer. Every box of a skin has the same layout around its
// corner on the skin, so where a pixel is on a face of the head is where it is on that face of the part: this reads
// the part's pixel instead. The display's sky light says which part (mcme_gui_stage.glsl's gui_stage_skin_part).
// The skin is 64 x 64: the game gives old 64 x 32 ones the new layout.

#ifndef MCME_GUI_SKIN_GLSL
#define MCME_GUI_SKIN_GLSL

const int GUI_SKIN_HEAD = 1;
const int GUI_SKIN_BODY = 2;
const int GUI_SKIN_RIGHT_ARM = 3;
const int GUI_SKIN_LEFT_ARM = 4;
const int GUI_SKIN_RIGHT_LEG = 5;
const int GUI_SKIN_LEFT_LEG = 6;
const int GUI_SKIN_RIGHT_ARM_SLIM = 7;
const int GUI_SKIN_LEFT_ARM_SLIM = 8;

// A part's box: where its inner layer starts on the skin (xy), where its outer layer starts (zw).
vec4 gui_skin_corners(int part) {
    if (part == GUI_SKIN_BODY) return vec4(16.0, 16.0, 16.0, 32.0);
    if (part == GUI_SKIN_RIGHT_ARM || part == GUI_SKIN_RIGHT_ARM_SLIM) return vec4(40.0, 16.0, 40.0, 32.0);
    if (part == GUI_SKIN_LEFT_ARM || part == GUI_SKIN_LEFT_ARM_SLIM) return vec4(32.0, 48.0, 48.0, 48.0);
    if (part == GUI_SKIN_RIGHT_LEG) return vec4(0.0, 16.0, 0.0, 32.0);
    if (part == GUI_SKIN_LEFT_LEG) return vec4(16.0, 48.0, 0.0, 48.0);
    return vec4(0.0, 0.0, 32.0, 0.0);
}

// A part's box size in pixels: width, height, depth.
vec3 gui_skin_size(int part) {
    if (part == GUI_SKIN_BODY) return vec3(8.0, 12.0, 4.0);
    if (part == GUI_SKIN_RIGHT_ARM_SLIM || part == GUI_SKIN_LEFT_ARM_SLIM) return vec3(3.0, 12.0, 4.0);
    if (part >= GUI_SKIN_RIGHT_ARM && part <= GUI_SKIN_LEFT_LEG) return vec3(4.0, 12.0, 4.0);
    return vec3(8.0);
}

// The skin coordinate to read for a point of the head's skin (uv, 0-1) when the head is drawn as a part.
vec2 gui_skin_uv(vec2 uv, int part) {
    if (part <= GUI_SKIN_HEAD) {
        return uv;
    }
    vec2 px = uv * 64.0;
    bool outer = px.x >= 32.0;
    vec2 local = px - vec2(outer ? 32.0 : 0.0, 0.0);
    // The head's face, and where in it (0-1): top and bottom are along the top row, then right, front, left, back.
    int face;
    vec2 f;
    if (local.y < 8.0) {
        face = local.x < 16.0 ? 0 : 1;
        f = (local - vec2(face == 0 ? 8.0 : 16.0, 0.0)) / 8.0;
    } else {
        int i = clamp(int(local.x / 8.0), 0, 3);
        face = 2 + i;
        f = (local - vec2(8.0 * float(i), 8.0)) / 8.0;
    }
    f = clamp(f, 0.0, 0.999);
    vec4 corners = gui_skin_corners(part);
    vec2 at = outer ? corners.zw : corners.xy;
    vec3 s = gui_skin_size(part);
    float w = s.x;
    float h = s.y;
    float d = s.z;
    vec2 origin;
    vec2 size;
    if (face == 0) { origin = at + vec2(d, 0.0);             size = vec2(w, d); }
    else if (face == 1) { origin = at + vec2(d + w, 0.0);     size = vec2(w, d); }
    else if (face == 2) { origin = at + vec2(0.0, d);         size = vec2(d, h); }
    else if (face == 3) { origin = at + vec2(d, d);           size = vec2(w, h); }
    else if (face == 4) { origin = at + vec2(d + w, d);       size = vec2(d, h); }
    else { origin = at + vec2(d + w + d, d);                  size = vec2(w, h); }
    return (origin + f * size) / 64.0;
}

#endif
