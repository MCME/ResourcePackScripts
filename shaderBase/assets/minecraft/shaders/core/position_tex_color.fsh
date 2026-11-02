#version 330

// Vanilla 26.2's position_tex_color.fsh plus hiding the HUD while an MCME-GUI screen is open
// (include/mcme_gui_hud.glsl): the crosshair, and every sprite pixel in the hotbar area.

#moj_import <minecraft:dynamictransforms.glsl>
#moj_import <minecraft:projection.glsl>
#moj_import <minecraft:globals.glsl>
#moj_import <minecraft:mcme_gui_hud.glsl>

uniform sampler2D Sampler0;

in vec2 texCoord0;
in vec4 vertexColor;
flat in vec2 hudUi;
in vec2 hudPos;
in float hudCrosshair;

out vec4 fragColor;

void main() {
    if (hudUi.x > 0.0 && (hudCrosshair > 0.999 || gui_in_hotbar_area(hudPos, hudUi))) {
        discard;
    }
    vec4 color = texture(Sampler0, texCoord0) * vertexColor;
    if (color.a == 0.0) {
        discard;
    }
    fragColor = color * ColorModulator;
}
