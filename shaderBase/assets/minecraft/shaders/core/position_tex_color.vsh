#version 330

// Vanilla 26.2's position_tex_color.vsh (GUI sprites, the crosshair and a few world things), plus what its .fsh
// needs to hide the HUD while an MCME-GUI screen is open (include/mcme_gui_hud.glsl). Vanilla's copy repeats its
// uniform blocks because it is used before resource packs load; this one is only used once they have.

#moj_import <minecraft:dynamictransforms.glsl>
#moj_import <minecraft:projection.glsl>
#moj_import <minecraft:globals.glsl>
#moj_import <minecraft:mcme_gui_hud.glsl>

in vec3 Position;
in vec2 UV0;
in vec4 Color;

out vec2 texCoord0;
out vec4 vertexColor;
flat out vec2 hudUi;
out vec2 hudPos;
out float hudCrosshair;

void main() {
    gl_Position = ProjMat * ModelViewMat * vec4(Position, 1.0);

    texCoord0 = UV0;
    vertexColor = Color;
    hudUi = gui_hud_ui();
    hudPos = Position.xy;
    hudCrosshair = hudUi.x > 0.0 ? gui_crosshair_corner(Position.xy, hudUi) : 0.0;
}
