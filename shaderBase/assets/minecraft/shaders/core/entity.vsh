#version 330

// Vanilla's, and MCME-GUI's models: entities on the stage (player heads, and players built from them) are drawn on
// the screen's board (include/mcme_gui_stage.glsl, include/mcme_gui_skin.glsl).

#if defined(PER_FACE_LIGHTING) || !defined(NO_CARDINAL_LIGHTING)
#moj_import <minecraft:light.glsl>
#endif
#moj_import <minecraft:fog.glsl>
#moj_import <minecraft:dynamictransforms.glsl>
#moj_import <minecraft:projection.glsl>
#moj_import <minecraft:sample_lightmap.glsl>
#moj_import <minecraft:globals.glsl>
#moj_import <minecraft:mcme_gui_stage.glsl>

in vec3 Position;
in vec4 Color;
in vec2 UV0;
in ivec2 UV1;
in ivec2 UV2;
in vec3 Normal;

#ifndef NO_OVERLAY
uniform sampler2D Sampler1;
#endif

#ifndef EMISSIVE
uniform sampler2D Sampler2;
#endif

out float sphericalVertexDistance;
out float cylindricalVertexDistance;

#ifdef PER_FACE_LIGHTING
out vec4 vertexPerFaceColorBack;
out vec4 vertexPerFaceColorFront;
#else
out vec4 vertexColor;
#endif

#ifndef EMISSIVE
out vec4 lightMapColor;
#endif

#ifndef NO_OVERLAY
out vec4 overlayColor;
#endif

out vec2 texCoord0;
flat out int guiSkinPart;

void main() {
    gl_Position = ProjMat * ModelViewMat * vec4(Position, 1.0);

    sphericalVertexDistance = fog_spherical_distance(Position);
    cylindricalVertexDistance = fog_cylindrical_distance(Position);

#ifdef PER_FACE_LIGHTING
    vec2 light = minecraft_compute_light(Light0_Direction, Light1_Direction, Normal);
    vertexPerFaceColorBack = minecraft_mix_light_separate(-light, Color);
    vertexPerFaceColorFront = minecraft_mix_light_separate(light, Color);
#elif defined(NO_CARDINAL_LIGHTING)
    vertexColor = Color;
#else
    vertexColor = minecraft_mix_light(Light0_Direction, Light1_Direction, Normal, Color);
#endif

#ifndef EMISSIVE
    lightMapColor = sample_lightmap(Sampler2, UV2);
#endif

#ifndef NO_OVERLAY
    overlayColor = texelFetch(Sampler1, UV1, 0);
#endif

    texCoord0 = UV0;

#ifdef APPLY_TEXTURE_MATRIX
    texCoord0 = (TextureMat * vec4(UV0, 0.0, 1.0)).xy;
#endif

    // On the stage, drawn on the board (mcme_gui_stage.glsl). Mixed in rather than in an if: with these in a branch,
    // a 26.2 client (NVIDIA, with Sodium and Iris) drew every entity in the world wrong, though the branch never ran
    // for them.
    float stage = gui_stage_height(Position);
    float onStage = stage >= 0.0 ? 1.0 : 0.0;
    guiSkinPart = stage >= 0.0 ? gui_stage_skin_part(UV2) : -1;
    gl_Position = mix(gl_Position, gui_stage_place(Position, max(stage, 0.0)), onStage);
    sphericalVertexDistance *= 1.0 - onStage;
    cylindricalVertexDistance *= 1.0 - onStage;
#ifdef PER_FACE_LIGHTING
    vertexPerFaceColorBack = mix(vertexPerFaceColorBack, gui_stage_light(-Normal, Color), onStage);
    vertexPerFaceColorFront = mix(vertexPerFaceColorFront, gui_stage_light(Normal, Color), onStage);
#else
    vertexColor = mix(vertexColor, gui_stage_light(Normal, Color), onStage);
#endif
#ifndef EMISSIVE
    lightMapColor = mix(lightMapColor, vec4(1.0), onStage);
#endif
#ifndef NO_OVERLAY
    overlayColor = mix(overlayColor, vec4(0.0, 0.0, 0.0, 1.0), onStage);
#endif
}
