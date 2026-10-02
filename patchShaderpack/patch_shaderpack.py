"""Makes a copy of an Iris shader pack that draws RP-Mordor's fire eye.

Under a shader pack the resource pack's terrain shaders don't run, so the eye
(fire_eye*.glsl in the pack's assets/minecraft/shaders/include) would show
only as its model's small faces. Nor can it be drawn on quads as the pack
does: shader packs cut off their fog and clouds behind anything translucent,
so its wide glow would end in a hard edge, and the eye would vanish past the
render distance.

So this copies a shader pack and draws the eye over its finished scene, after
fog and clouds and before bloom, at a block position given here - one eye, at
a known place, shown at any distance, Distant Horizons' included:

- the eye (ball, almond, pupil, flames) is the resource pack's fireColor(),
  hidden by whatever is nearer than its front
- its glow is fireGlowLight(), added as light over what is behind it
- both are scaled to the pack's exposure, so they look as they do without
  shaders, before the pack's bloom
- the eye block's own faces are dropped

Packs are recognised by their code, not their name, so edits of a supported
pack work as long as the code patched here is intact; anything else is
refused rather than guessed at. Supported: Bliss, MakeUp, Mellow, BSL,
Complementary (Reimagined, Unbound, and edits such as Spooklementary), Solas
and Sildur's Vibrant.

    python patch_shaderpack.py <shader pack zip or folder> <RP-Mordor folder or vanilla pack> [--eye X Y Z] [--out folder]

The eye is where the pack's fire_eye_config.glsl puts it (FIRE_EYE_BLOCK),
unless --eye gives another block, in the overworld. With Distant Horizons
it shows at any distance; without, only where its block's chunk can be
drawn - within the render distance, which is a sphere, and within the
server's view distance across (FIRE_HANDOVER). The output defaults to
.minecraft/shaderpacks/<the pack's name>-MCME. Rerun it after the eye's
includes or the shader pack change: it only ever replaces a pack it wrote.
"""

import argparse
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

SHADERPACKS = Path.home() / "AppData/Roaming/.minecraft/shaderpacks"
EYE_INCLUDES = ("far_terrain.glsl", "fire_eye_config.glsl", "fire_eye.glsl")
MARKER = "MCME-PATCH.txt"

# how bright the eye and its glow are, relative to the resource pack's look
BRIGHTNESS = 1.5
GLOW = 1.0


# ---------------------------------------------------------------- shaders

# lib/mcme/fire_eye_face.glsl: whether a vertex is one of the eye block's
# faces, found as fire_eye_main.glsl finds them, by the descriptor their UV
# points at
FACE_GLSL = """// MCME: whether a vertex is one of the fire eye block's faces (patch_shaderpack.py)
#ifndef MCME_DECLARED_gtexture
uniform sampler2D gtexture;
#endif

bool mcmeFireEyeFace(vec2 uv) {
    ivec2 at = ivec2(uv * vec2(textureSize(gtexture, 0)));
    ivec4 pointer = ivec4(texelFetch(gtexture, at, 0) * 255.0 + 0.5);
    if (pointer.a != 254) return false;
    ivec2 origin = at - ivec2(pointer.r * 16 + (pointer.g >> 4), (pointer.g & 15) * 256 + pointer.b);
    return all(greaterThanEqual(origin, ivec2(0)))
        && ivec4(texelFetch(gtexture, origin, 0) * 255.0 + 0.5) == ivec4(98, 76, 54, 255)
        && ivec4(texelFetch(gtexture, origin + ivec2(1, 0), 0) * 255.0 + 0.5) == ivec4(13, 57, 93, 255);
}
"""

# lib/mcme/fire_eye_draw.glsl: the eye and its glow over a finished scene.
# Its includer declares gbufferModelViewInverse, cameraPositionInt,
# cameraPositionFract, frameTimeCounter and far, and defines MCME_EYE_BLOCK,
# MCME_LINEAR (1 if the scene's colour is linear), MCME_BRIGHTNESS and
# MCME_GLOW.
DRAW_GLSL = """// MCME: the fire eye, drawn over a finished scene (patch_shaderpack.py)
#include "/lib/mcme/far_terrain.glsl"
#include "/lib/mcme/fire_eye_config.glsl"
#define FIRE_NO_GLOW
int fireLayer = 0;
vec3 fireCentre = vec3(0.0);
float fireTime = 0.0;
vec3 fireRay = vec3(0.0, 0.0, -1.0);
#define Pos fireRay
#include "/lib/mcme/fire_eye.glsl"
#undef Pos

vec3 mcmeFireColour(vec3 c) {
#if MCME_LINEAR
    return pow(c, vec3(2.2));
#else
    return c;
#endif
}

// How much of the eye shows through what lies between it and the camera that
// the scene doesn't record the distance of - clouds - where a recipe can tell
// (1: all of it). The scene already holds those clouds, so the eye only fades.
float mcmeFireVisibility = 1.0;

// The scene's colour with the eye and its glow over it. viewPos: a point the
// pixel shows, in view space (any point along its ray, for the sky);
// sceneDistance: how far off that is (huge for the sky); scale: from the
// resource pack's colours into the scene's, before its exposure.
vec3 mcmeDrawFireEye(vec3 color, vec3 viewPos, float sceneDistance, float scale) {
    // relative to the camera's eye
    fireCentre = vec3(MCME_EYE_BLOCK - cameraPositionInt) + 0.5 - cameraPositionFract - gbufferModelViewInverse[3].xyz;
    fireTime = frameTimeCounter;
    fireRay = normalize(mat3(gbufferModelViewInverse) * viewPos);
    float fireDistance = length(fireCentre);
#if defined DISTANT_HORIZONS || defined VOXY
    float range = 1.0;
#else
    // without a distant terrain mod nothing is drawn where the eye's block
    // can't be, so neither is the eye: it fades out over the last chunk of the
    // render distance - a sphere - and of the server's view distance across
    float range = (1.0 - smoothstep(far - 16.0, far, fireDistance))
                * (1.0 - smoothstep(FIRE_HANDOVER - 16.0, FIRE_HANDOVER, length(fireCentre.xz)));
    if (range <= 0.0) return color;
#endif
    // the eye, where the ray passes near enough to meet it, hidden by
    // whatever is nearer than its front
    vec3 from = -fireCentre / FIRE_RADIUS;
    float pass = length(from + fireRay * max(dot(-from, fireRay), 0.0));
    if (pass < max(FIRE_EYE_WIDTH, FIRE_CORONA) * 1.05) {
        vec4 eye = fireColor();
        float shown = smoothstep(fireDistance - FIRE_RADIUS * 1.2, fireDistance - FIRE_RADIUS * 0.7, sceneDistance);
        color = mix(color, mcmeFireColour(eye.rgb) * scale * MCME_BRIGHTNESS, eye.a * shown * mcmeFireVisibility * range);
    }
    // its glow, as light over what is behind it: none in front of the ball,
    // all of it FIRE_GLOW_DEPTH radii behind
    float glowShown = smoothstep(fireDistance - FIRE_RADIUS, fireDistance + FIRE_RADIUS * FIRE_GLOW_DEPTH, sceneDistance);
    return color + mcmeFireColour(fireGlowLight(fireRay, fireCentre)) * scale * MCME_BRIGHTNESS * MCME_GLOW
                 * glowShown * mcmeFireVisibility * range;
}
"""

# A pass of its own, for packs with a free composite pass between their
# finished scene and their bloom: reads the scene and writes it back with
# the eye over it. Every declaration is its own, so none clash with the pack.
PASS_VSH = """#version 330 compatibility
// MCME: the fire eye, drawn over the finished scene (patch_shaderpack.py)
out vec2 mcmeTexCoord;

void main() {
    gl_Position = ftransform();
    mcmeTexCoord = gl_MultiTexCoord0.xy;
}
"""

PASS_FSH = """#version 330 compatibility
// MCME: the fire eye, drawn over the finished scene, before bloom
// (patch_shaderpack.py)
{settings}
uniform sampler2D colortex{buffer};
uniform sampler2D depthtex0;
uniform mat4 gbufferProjectionInverse;
uniform mat4 gbufferModelViewInverse;
uniform ivec3 cameraPositionInt;
uniform vec3 cameraPositionFract;
uniform float frameTimeCounter;
uniform float far;

{lod}
{defines}
#include "/lib/mcme/fire_eye_draw.glsl"

in vec2 mcmeTexCoord;

/* RENDERTARGETS: {buffer} */
layout(location = 0) out vec4 mcmeColor;

void main() {{
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    vec4 scene = texelFetch(colortex{buffer}, pixel, 0);
    float depth = texelFetch(depthtex0, pixel, 0).r;
    vec4 viewPos = gbufferProjectionInverse * vec4(vec3(mcmeTexCoord, depth) * 2.0 - 1.0, 1.0);
    viewPos /= viewPos.w;
    float sceneDistance = mcmeLodDistance(mcmeTexCoord, pixel, depth < 1.0 ? length(viewPos.xyz) : 1.0e9);
    mcmeColor = vec4(mcmeDrawFireEye(scene.rgb, viewPos.xyz, sceneDistance, {scale}), scene.a);
}}
"""

# How far off a distant terrain mod's terrain is, where it is nearer than
# what else a pixel shows - for packs whose distances leave it out. Iris
# gives each mod's depth and projection under its own names.
LOD_UNIFORMS = (("sampler2D", "dhDepthTex0"), ("mat4", "dhProjectionInverse"),
                ("sampler2D", "vxDepthTexOpaque"), ("mat4", "vxProjInv"))
LOD_GLSL = """// MCME: the distant terrain mods' terrain (patch_shaderpack.py)
#if defined DISTANT_HORIZONS
""" + "".join(f"#ifndef MCME_DECLARED_{n}\nuniform {t} {n};\n#endif\n" for t, n in LOD_UNIFORMS[:2]) + """#elif defined VOXY
""" + "".join(f"#ifndef MCME_DECLARED_{n}\nuniform {t} {n};\n#endif\n" for t, n in LOD_UNIFORMS[2:]) + """#endif

float mcmeLodDistance(vec2 coord, ivec2 pixel, float sceneDistance) {
#if defined DISTANT_HORIZONS || defined VOXY
    #ifdef DISTANT_HORIZONS
        float lodDepth = texelFetch(dhDepthTex0, pixel, 0).r;
        mat4 lodProjectionInverse = dhProjectionInverse;
    #else
        float lodDepth = texelFetch(vxDepthTexOpaque, pixel, 0).r;
        mat4 lodProjectionInverse = vxProjInv;
    #endif
    if (lodDepth < 1.0) {
        vec4 lodPos = lodProjectionInverse * vec4(vec3(coord, lodDepth) * 2.0 - 1.0, 1.0);
        sceneDistance = min(sceneDistance, length(lodPos.xyz / lodPos.w));
    }
#endif
    return sceneDistance;
}
"""


def draw_defines(eye, linear):
    x, y, z = eye
    return (f"#define MCME_EYE_BLOCK ivec3({x}, {y}, {z})\n"
            f"#define MCME_LINEAR {1 if linear else 0}\n"
            f"#define MCME_BRIGHTNESS {BRIGHTNESS}\n"
            f"#define MCME_GLOW {GLOW}\n")


# ---------------------------------------------------------------- editing

class Unsupported(Exception):
    pass


def read(path):
    return path.read_bytes().decode("utf-8")


def write(path, text):
    path.write_bytes(text.encode("utf-8"))


def find_one(text, anchor, what):
    matches = list(re.finditer(anchor, text))
    if len(matches) != 1:
        raise Unsupported(f"expected one {anchor!r} in {what}, found {len(matches)}")
    return matches[0]


def insert(text, anchor, what, addition, before=False):
    m = find_one(text, anchor, what)
    nl = "\r\n" if "\r\n" in text else "\n"
    i = m.start() if before else m.end()
    return text[:i] + addition.replace("\n", nl) + text[i:]


def end_of_block(text, open_brace):
    """The index just past the brace closing the one at open_brace, skipping
    comments."""
    depth, i = 0, open_brace
    while i < len(text):
        if text.startswith("//", i):
            i = text.find("\n", i)
            i = len(text) if i < 0 else i
        elif text.startswith("/*", i):
            i = text.find("*/", i) + 2
            if i < 2:
                break
        else:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
    raise Unsupported("unbalanced braces")


def expand(shaders, text, here, seen=None):
    """text with its #includes expanded (Iris style: /-rooted at shaders, or
    relative to here), every branch kept - for finding declarations."""
    seen = set() if seen is None else seen

    def include(m):
        name = m.group(1)
        path = (shaders / name.lstrip("/")) if name.startswith("/") else (here / name)
        path = path.resolve()
        if path in seen or not path.is_file():
            return ""
        seen.add(path)
        return expand(shaders, read(path), path.parent, seen)

    return re.sub(r'#include\s+"([^"]+)"', include, text)


def blank_comments(text):
    """text with its comments blanked out, everything else where it was."""
    return re.sub(r"//[^\n]*|/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)


def declaration_ends(text, name):
    """Where the lines holding text's own declarations of uniform name end."""
    ends = []
    for m in re.finditer(rf"\buniform\b[^;{{}}]*\b{name}\b[^;{{}}]*;", blank_comments(text)):
        nl = text.find("\n", m.end())
        ends.append(len(text) if nl < 0 else nl + 1)
    return ends


def declares(text, name):
    return bool(declaration_ends(text, name))


def includes(shaders, text, here):
    """The files text includes, directly or not, each once."""
    found = []

    def walk(text, here):
        for m in re.finditer(r'#include\s+"([^"]+)"', blank_comments(text)):
            name = m.group(1)
            path = Path(os.path.normpath((shaders / name.lstrip("/")) if name.startswith("/") else (here / name)))
            if path not in found and path.is_file():
                found.append(path)
                walk(read(path), path.parent)

    walk(text, here)
    return found


def current(edits, path):
    return edits[path] if path in edits else read(path)


def mark_declarations(shaders, path, text, at, names, edits):
    """path's text, with #define MCME_DECLARED_<name> after each of the
    shader pack's own declarations of the uniforms named that come before at
    - in text, or in what it includes, whose new text goes into edits - so
    what is added at at declares each only where the pack's declaration isn't
    compiled: shader packs declare many uniforms only under some settings.
    Unsupported if one is declared after at (None: the end)."""
    at = len(text) if at is None else at
    before, after = text[:at], text[at:]
    for name in names:
        if declares(after, name) or any(declares(current(edits, f), name) for f in includes(shaders, after, path.parent)):
            raise Unsupported(f"{path.name} declares {name} after where it is needed")

    def marked(text, name):
        nl = "\r\n" if "\r\n" in text else "\n"
        define = f"#define MCME_DECLARED_{name}{nl}"
        for end in reversed(declaration_ends(text, name)):
            if not text.startswith(define, end):
                text = text[:end] + define + text[end:]
        return text

    for name in names:
        for f in includes(shaders, before, path.parent):
            if declares(current(edits, f), name):
                edits[f] = marked(current(edits, f), name)
        before = marked(before, name)
    return before + after


def declare_uniforms(shaders, path, text, at, uniforms, edits):
    """path's text with the uniforms - (type, name) - declared at at, each
    only where the shader pack's own declaration of it isn't compiled (see
    mark_declarations)."""
    marked = mark_declarations(shaders, path, text, at, [n for _, n in uniforms], edits)
    at += len(marked) - len(text)
    nl = "\r\n" if "\r\n" in text else "\n"
    return marked[:at] + uniform_lines(uniforms).replace("\n", nl) + marked[at:]


def uniform_lines(uniforms):
    return "".join(f"#ifndef MCME_DECLARED_{n}\nuniform {t} {n};\n#endif\n" for t, n in uniforms)


def wrap_vertex_main(shaders, path, name, wrapper, edits, names=(), start_marker=None):
    """path's text, its vertex main() - the first after start_marker -
    renamed name, and wrapper after it: the new main(), calling it, with
    the uniforms it declares, named names, marked (mark_declarations)."""
    text = current(edits, path)
    start = text.index(start_marker) if start_marker else 0
    m = re.compile(r"void\s+main\s*\(\s*\)").search(text, start)
    if not m:
        raise Unsupported(f"no vertex main() in {path.name}")
    end = end_of_block(text, text.index("{", m.end()))
    nl = "\r\n" if "\r\n" in text else "\n"
    renamed = text[:m.start()] + f"void {name}()" + text[m.end():end]
    marked = mark_declarations(shaders, path, renamed + text[end:], len(renamed), names, edits)
    at = len(renamed) + len(marked) - len(renamed + text[end:])
    return marked[:at] + wrapper.replace("\n", nl) + marked[at:]


def drop_eye_faces(shaders, path, edits, start_marker=None):
    """path's text, its vertex main() wrapped so the eye block's faces
    collapse to a point."""
    return wrap_vertex_main(shaders, path, "mcmePackMain", (
        "\n\n// MCME: the fire eye block's faces are dropped - the eye is drawn over the scene\n"
        '#include "/lib/mcme/fire_eye_face.glsl"\n'
        "void main() {\n"
        "    mcmePackMain();\n"
        "    if (mcmeFireEyeFace((gl_TextureMatrix[0] * gl_MultiTexCoord0).xy)) gl_Position = vec4(0.0);\n"
        "}\n"), edits, names=("gtexture",), start_marker=start_marker)


def drop_far_particles(shaders, path, edits, start_marker=None, guard=None):
    """path's text, its vertex main() - particles' - wrapped so that, while a
    distant terrain mod draws the world, particles past the server's view
    distance collapse to a point: they come from chunks loaded but not drawn,
    and would show through the mod's terrain in front of them. Only in
    programs defining guard, if given."""
    test = (f"    #ifdef {guard}\n" if guard else "") + (
        "    if (length((gl_ModelViewMatrix * gl_Vertex).xyz) > SERVER_VIEW_DISTANCE) gl_Position = vec4(0.0);\n"
    ) + ("    #endif\n" if guard else "")
    return wrap_vertex_main(shaders, path, "mcmeParticleMain", (
        "\n\n// MCME: with a distant terrain mod, particles past the server's view distance\n"
        "// are dropped - they would show through its terrain (lib/mcme/far_terrain.glsl)\n"
        '#include "/lib/mcme/far_terrain.glsl"\n'
        "void main() {\n"
        "    mcmeParticleMain();\n"
        "#if defined DISTANT_HORIZONS || defined VOXY\n" + test + "#endif\n"
        "}\n"), edits, start_marker=start_marker)


def new_pass(shaders, number, buffer, scale, linear, eye, settings="", folder="world0"):
    """The files of an overworld compositeN, in folder, drawing the eye over
    colortex buffer, as {path: text}."""
    world = shaders / folder
    for ext in ("vsh", "fsh"):
        if (world / f"composite{number}.{ext}").exists():
            raise Unsupported(f"world0/composite{number}.{ext} is taken")
    return {world / f"composite{number}.vsh": PASS_VSH,
            world / f"composite{number}.fsh": PASS_FSH.format(
                settings=settings, buffer=buffer, lod=LOD_GLSL, defines=draw_defines(eye, linear), scale=scale)}


# ---------------------------------------------------------------- recipes
# Each checks everything it needs before changing anything, and returns the
# files it changes as {path: text}; Unsupported if the pack isn't its.

def bliss(shaders, eye):
    """Bliss (Chocapic13 edit), 2.1 and its development builds: faces dropped
    in dimensions/all_translucent.vsh; the eye drawn in composite3, after fog,
    clouds and the translucents, with Bliss's own view position and distance
    (Distant Horizons' included: swappedDepth) and its exposure."""
    dims = shaders / "dimensions"
    vsh, comp = dims / "all_translucent.vsh", dims / "composite3.fsh"
    if not (vsh.is_file() and comp.is_file() and (shaders / "world0/gbuffers_water.vsh").is_file()):
        raise Unsupported("not Bliss")
    text = read(comp)
    # its view position: viewPos in development builds, fragpos in 2.1
    view = next((v for v in ("viewPos", "fragpos") if re.search(rf"vec3 {v} = toScreenSpace_DH\(", text)), None)
    if view is None or not re.search(r"float swappedDepth = ", text) or not re.search(r"float linearDistance = ", text):
        raise Unsupported("Bliss's composite3 has changed")
    particles = dims / "all_particles.vsh"
    if not particles.is_file():
        raise Unsupported("Bliss's particles have moved")
    edits = {}
    clouds = bliss_clouds(shaders, eye, edits)
    text = insert(text, r"void main\(\) \{", comp.name, """// MCME: the fire eye, at its block (patch_shaderpack.py)
#ifdef OVERWORLD_SHADER
""" + draw_defines(eye, True) + '#include "/lib/mcme/fire_eye_draw.glsl"\n'
        + ("uniform sampler2D mcmeEyeCloudSampler;\n" if clouds else "") + """#endif

""", before=True)
    text = declare_uniforms(shaders, comp, text, text.index("// MCME: the fire eye, at its block"), (
        ("ivec3", "cameraPositionInt"), ("vec3", "cameraPositionFract"), ("float", "far"),
        ("mat4", "gbufferModelViewInverse"), ("float", "frameTimeCounter"), ("sampler2D", "colortex4")), edits)
    edits[vsh] = drop_eye_faces(shaders, vsh, edits)
    edits[particles] = drop_far_particles(shaders, particles, edits)
    text = insert(text, r"gl_FragData\[0\](\.r)? = (vec4\()?bloomyFogMult", comp.name, f"""
  // MCME: the fire eye, after fog and clouds, so it shows at any distance,
  // Distant Horizons' too, and nothing cuts its glow off{" - faded by the clouds between it and the camera, which composite2 measures" if clouds else ""}
  #ifdef OVERWORLD_SHADER
    {"mcmeFireVisibility = texelFetch(mcmeEyeCloudSampler, ivec2(0), 0).r;" if clouds else ""}
    color.rgb = mcmeDrawFireEye(color.rgb, {view}, swappedDepth >= 1.0 ? 1.0e9 : linearDistance,
                                1.0 / max(texelFetch(colortex4, ivec2(10, 37), 0).r, 1.0e-4));
  #endif

""", before=True)
    edits[comp] = text
    return edits


# How much light gets through Bliss's clouds between the camera and the eye,
# for composite3 to fade the eye by: Bliss's own clouds, from its own cloud
# function, on the line to the eye, marched only as far as the eye - so the
# eye fades only behind clouds Bliss draws in front of it. Once a frame, by
# one pixel, into a 1x1 image.
BLISS_CLOUDS_GLSL = """
// MCME: the clouds between the camera and the fire eye (patch_shaderpack.py)
#ifdef OVERWORLD_SHADER
layout(r16f) uniform image2D mcmeEyeCloud;
{defines}#endif

"""

BLISS_CLOUDS_MAIN = """
		// MCME: the clouds between the camera and the fire eye, once a frame:
		// Bliss's own, as far as the eye
		if (all(lessThan(gl_FragCoord.xy, vec2(1.0)))) {
			vec3 mcmeEye = vec3(MCME_EYE_BLOCK - cameraPositionInt) + 0.5 - cameraPositionFract;
			float mcmeCloudDistance = cloudPlaneDistance;
			vec4 mcmeClouds = GetVolumetricClouds((gbufferModelView * vec4(mcmeEye, 1.0)).xyz, vec2(0.5), WsunVec,
			                                      directLightColor, indirectLightColor, mcmeCloudDistance, phaseLevels, backScatterPhase);
			imageStore(mcmeEyeCloud, ivec2(0), vec4(mcmeClouds.a));
		}
"""


def bliss_clouds(shaders, eye, edits):
    """Adds to edits those measuring the clouds in front of the eye - none
    where Bliss's clouds aren't the ones this knows (2.1's). Whether it did."""
    comp2 = shaders / "dimensions/composite2.fsh"
    if not comp2.is_file():
        return False
    text = current(edits, comp2)
    full = expand(shaders, text, comp2.parent)
    anchor = (r"vec4 VolumetricClouds = GetVolumetricClouds\(viewPos0, BN, WsunVec, directLightColor, indirectLightColor, "
              r"cloudPlaneDistance, phaseLevels, backScatterPhase\);")
    if not re.search(anchor, text) or "vec4 GetVolumetricClouds(" not in full:
        return False
    x, y, z = eye
    text = "#extension GL_ARB_shader_image_load_store : enable\n" + text
    text = insert(text, r"void main\(\) \{", comp2.name, BLISS_CLOUDS_GLSL.format(
        defines=f"#define MCME_EYE_BLOCK ivec3({x}, {y}, {z})\n"), before=True)
    text = declare_uniforms(shaders, comp2, text, text.index("// MCME: the clouds between the camera and the fire eye (patch"), (
        ("ivec3", "cameraPositionInt"), ("vec3", "cameraPositionFract"), ("mat4", "gbufferModelView")), edits)
    text = insert(text, anchor, comp2.name, BLISS_CLOUDS_MAIN)
    props = shaders / "shaders.properties"
    nl = "\r\n" if "\r\n" in read(props) else "\n"
    edits[comp2] = text
    edits[props] = (current(edits, props).rstrip() + nl + nl + "# MCME: the clouds between the camera and the fire eye (patch_shaderpack.py)"
                    + nl + "image.mcmeEyeCloud = mcmeEyeCloudSampler RED R16F HALF_FLOAT false false 1 1" + nl)
    return True


def makeup(shaders, eye):
    """MakeUp (and edits): faces dropped in common/water_blocks_vertex.glsl;
    the eye drawn in composite (its first, after the forward-rendered scene
    and its fog) before it takes its bloom source, in its gamma-space colours
    and exposure. It has no free pass, so this goes into its own."""
    vertex, comp = shaders / "common/water_blocks_vertex.glsl", shaders / "common/composite_fragment.glsl"
    if not (vertex.is_file() and comp.is_file()):
        raise Unsupported("not MakeUp")
    edits = {}
    text = read(comp)
    # LOD_GLSL declares the distant terrain mods' uniforms
    text = mark_declarations(shaders, comp, text, find_one(text, r"// MAIN FUNCTION -+", comp.name).start(),
                             [n for _, n in LOD_UNIFORMS], edits)
    text = insert(text, r"// MAIN FUNCTION -+", comp.name, """// MCME: the fire eye, at its block (patch_shaderpack.py)
#if !defined THE_END && !defined NETHER
""" + LOD_GLSL + draw_defines(eye, False) + """#include "/lib/mcme/fire_eye_draw.glsl"
#endif

""", before=True)
    text = declare_uniforms(shaders, comp, text, text.index("// MCME: the fire eye, at its block"), (
        ("mat4", "gbufferProjectionInverse"), ("mat4", "gbufferModelViewInverse"), ("ivec3", "cameraPositionInt"),
        ("vec3", "cameraPositionFract"), ("float", "frameTimeCounter"), ("float", "far")), edits)
    text = insert(text, r"    #ifdef BLOOM\s*\n\s*// Bloom source", comp.name, """    // MCME: the fire eye, before the bloom source, so it blooms
    #if !defined THE_END && !defined NETHER
    {
        vec4 mcmeView = gbufferProjectionInverse * vec4(vec3(texcoord, d) * 2.0 - 1.0, 1.0);
        mcmeView /= mcmeView.w;
        float mcmeDistance = mcmeLodDistance(texcoord, ivec2(gl_FragCoord.xy), d < 1.0 ? length(mcmeView.xyz) : 1.0e9);
        blockColor.rgb = mcmeDrawFireEye(blockColor.rgb, mcmeView.xyz, mcmeDistance, 1.0 / exposure);
    }
    #endif

""", before=True)
    particles = shaders / "common/solid_blocks_vertex.glsl"
    if not particles.is_file() or "GBUFFER_TEXTURED" not in read(shaders / "world0/gbuffers_textured.vsh"):
        raise Unsupported("MakeUp's particles have moved")
    edits[comp] = text
    edits[vertex] = drop_eye_faces(shaders, vertex, edits)
    edits[particles] = drop_far_particles(shaders, particles, edits, guard="GBUFFER_TEXTURED")
    return edits


def mellow(shaders, eye):
    """Mellow: faces dropped in program/gbuffers_water.vsh; the eye drawn in a
    pass of its own, composite1 - its composites start at 2, with bloom -
    over colortex0, its linear scene, with its fixed EXPOSURE."""
    water, final = shaders / "program/gbuffers_water.vsh", shaders / "program/composite8.fsh"
    settings = shaders / "lib/settings.glsl"
    if not (water.is_file() and final.is_file() and settings.is_file()):
        raise Unsupported("not Mellow")
    if "Color.rgb *= EXPOSURE;" not in read(final) or "DRAWBUFFERS:0" not in read(shaders / "program/gbuffers_water.fsh"):
        raise Unsupported("Mellow's scene buffer or exposure have changed")
    edits = new_pass(shaders, 1, 0, "1.0 / EXPOSURE", True, eye, settings='#include "/lib/settings.glsl"')
    particles = shaders / "program/gbuffers_basic.vsh"
    if not particles.is_file():
        raise Unsupported("Mellow's particles have moved")
    edits[water] = drop_eye_faces(shaders, water, edits)
    edits[particles] = drop_far_particles(shaders, particles, edits)
    return edits


def complementary(shaders, eye):
    """Complementary - Reimagined, Unbound and edits such as Spooklementary:
    faces dropped in program/gbuffers_water.glsl's vertex shader; the eye
    drawn in a pass of its own, composite2 - after composite1's refraction,
    reflections, volumetric light and fog, before composite3's blur and the
    bloom - over colortex0, its linear scene."""
    water, comp1 = shaders / "program/gbuffers_water.glsl", shaders / "program/composite1.glsl"
    if not (water.is_file() and comp1.is_file() and (shaders / "program/composite3.glsl").is_file()):
        raise Unsupported("not Complementary")
    marker = "//////////Vertex Shader//////////"
    if marker not in read(water) or "/* DRAWBUFFERS:0 */" not in read(comp1):
        raise Unsupported("Complementary's water or composite1 have changed")
    edits = new_pass(shaders, 2, 0, "1.0", True, eye)
    particles = shaders / "program/gbuffers_textured.glsl"
    if not particles.is_file() or marker not in read(particles):
        raise Unsupported("Complementary's particles have moved")
    edits[water] = drop_eye_faces(shaders, water, edits, start_marker=marker)
    edits[particles] = drop_far_particles(shaders, particles, edits, start_marker=marker)
    return edits


def bsl(shaders, eye):
    """BSL (v10, and edits): faces dropped in program/gbuffers_water.glsl's
    vertex shader; the eye drawn at the end of program/composite.glsl - its
    one composite always on, after fog, the translucents and the distant
    terrain mods' terrain, before its light shafts and bloom - in its linear
    colours, by its fixed exposure (exp2(2 + EXPOSURE), in composite5)."""
    program = shaders / "program"
    water, comp, tonemap = program / "gbuffers_water.glsl", program / "composite.glsl", program / "composite5.glsl"
    particles = program / "gbuffers_textured.glsl"
    if not all(p.is_file() for p in (water, comp, tonemap, particles)):
        raise Unsupported("not BSL")
    marker = "//Vertex Shader//"
    text = read(comp)
    if (marker not in read(water) or marker not in read(particles) or "color *= exp2(2.0 + EXPOSURE);" not in read(tonemap)
            or not re.search(r"vec4 viewPos = gbufferProjectionInverse \* \(screenPos \* 2\.0 - 1\.0\);", text)
            or not re.search(r"color\.rgb \*= color\.rgb;", text)):
        raise Unsupported("BSL's composite, exposure or water have changed")
    edits = {}
    main = r"void main\(\) \{\s*\n\s*vec4 color = texture2D\(colortex0, texCoord\);\s*\n\s*float z0 = "
    text = insert(text, main, comp.name, """// MCME: the fire eye, at its block (patch_shaderpack.py)
#ifdef OVERWORLD
""" + draw_defines(eye, True) + """#include "/lib/mcme/fire_eye_draw.glsl"
#endif

""", before=True)
    text = declare_uniforms(shaders, comp, text, text.index("// MCME: the fire eye, at its block"), (
        ("ivec3", "cameraPositionInt"), ("vec3", "cameraPositionFract"), ("float", "far"),
        ("mat4", "gbufferModelViewInverse"), ("float", "frameTimeCounter")), edits)
    text = insert(text, r"[ \t]*/\*DRAWBUFFERS:01\*/", comp.name, """	// MCME: the fire eye, after fog, the translucents and the distant terrain
	// mods' terrain (viewPos is theirs where they are nearest), before the
	// light shafts and bloom
	#ifdef OVERWORLD
	{
		float mcmeDistance = z0 < 1.0 ? length(viewPos.xyz) : 1.0e9;
		#ifdef DISTANT_HORIZONS
		if (z0 >= 1.0 && dhZ0 < 1.0) mcmeDistance = length(viewPos.xyz);
		#endif
		#ifdef VOXY
		if (z0 >= 1.0 && vxZ0 < 1.0) mcmeDistance = length(viewPos.xyz);
		#endif
		color.rgb = mcmeDrawFireEye(color.rgb, viewPos.xyz, mcmeDistance, 1.0 / exp2(2.0 + EXPOSURE));
	}
	#endif

""", before=True)
    edits[comp] = text
    edits[water] = drop_eye_faces(shaders, water, edits, start_marker=marker)
    edits[particles] = drop_far_particles(shaders, particles, edits, start_marker=marker)
    return edits


def solas(shaders, eye):
    """Solas: faces dropped in programs/gbuffers_water.glsl's vertex shader;
    the eye drawn in a pass of its own, composite4 - after its water fog,
    volumetric fog and refraction (composite to composite3), before its bloom
    (composite13) - over colortex0, its linear scene. Its overworld programs
    are its root's, which its other dimensions fall back to, so the pass is
    switched off in those."""
    programs = shaders / "programs"
    water, particles = programs / "gbuffers_water.glsl", programs / "gbuffers_textured.glsl"
    tonemap, bloom = programs / "composite14.glsl", programs / "composite13.glsl"
    if not all(p.is_file() for p in (water, particles, tonemap, bloom, shaders / "composite3.fsh")):
        raise Unsupported("not Solas")
    marker = "#ifdef VSH"
    if (marker not in read(water) or marker not in read(particles) or "Uncharted2Tonemap(color * TONEMAP_BRIGHTNESS)" not in read(tonemap)
            or "computeBloom" not in read(bloom) or "DRAWBUFFERS:0" not in read(programs / "composite3.glsl")):
        raise Unsupported("Solas's passes have changed")
    edits = new_pass(shaders, 4, 0, "1.0", True, eye, folder=".")
    props = shaders / "shaders.properties"
    nl = "\r\n" if "\r\n" in read(props) else "\n"
    edits[props] = (read(props).rstrip() + nl + nl + "# MCME: the fire eye's pass, in the overworld only (patch_shaderpack.py)" + nl
                    + "program.world-1/composite4.enabled=false" + nl + "program.world1/composite4.enabled=false" + nl)
    edits[water] = drop_eye_faces(shaders, water, edits, start_marker=marker)
    edits[particles] = drop_far_particles(shaders, particles, edits, start_marker=marker)
    return edits


def sildurs(shaders, eye):
    """Sildur's Vibrant: faces dropped in gbuffers_water.vsh; the eye drawn
    at the end of composite1 - after its fog, before TAA - in the linear
    colours it works in there; final's tonemap is fixed (4.7). Its overworld
    programs are its root's. Its bloom is taken earlier, in composite, so the
    eye doesn't bloom. composite1 runs only with one of its effects on, so it
    is switched on always."""
    comp, final = shaders / "composite1.fsh", shaders / "final.fsh"
    water, particles = shaders / "gbuffers_water.vsh", shaders / "gbuffers_textured.vsh"
    props = shaders / "shaders.properties"
    if not all(p.is_file() for p in (comp, final, water, particles, props)):
        raise Unsupported("not Sildur's")
    text = read(comp)
    gate = re.search(r"(?m)^program\.composite1\.enabled=[^\r\n]*", read(props))
    if ("Uncharted2Tonemap(albedo.rgb*4.7)" not in read(final) or not gate
            or not re.search(r"vec3 fragpos0 = utilScreenSpace\(", text) or not re.search(r"float depth0 = ", text)):
        raise Unsupported("Sildur's composite1 or final have changed")
    edits = {}
    main = r"void main\(\) \{"
    text = mark_declarations(shaders, comp, text, find_one(text, main, comp.name).start(), [n for _, n in LOD_UNIFORMS], edits)
    text = insert(text, main, comp.name, """// MCME: the fire eye, at its block (patch_shaderpack.py)
""" + LOD_GLSL + draw_defines(eye, True) + """#include "/lib/mcme/fire_eye_draw.glsl"

""", before=True)
    text = declare_uniforms(shaders, comp, text, text.index("// MCME: the fire eye, at its block"), (
        ("ivec3", "cameraPositionInt"), ("vec3", "cameraPositionFract"), ("float", "far"),
        ("mat4", "gbufferModelViewInverse"), ("float", "frameTimeCounter")), edits)
    text = insert(text, r"[ \t]*albedo\.rgb = pow\(albedo\.rgb, vec3\(0\.454\)\);", comp.name, """	// MCME: the fire eye, after fog, before TAA
	{
		float mcmeDistance = mcmeLodDistance(texcoord.xy, ivec2(gl_FragCoord.xy), depth0 < 1.0 ? length(fragpos0) : 1.0e9);
		albedo.rgb = mcmeDrawFireEye(albedo.rgb, fragpos0, mcmeDistance, 1.0);
	}

""", before=True)
    edits[comp] = text
    p = read(props)
    nl = "\r\n" if "\r\n" in p else "\n"
    edits[props] = (p[:gate.start()] + "# MCME: always on, for the fire eye (patch_shaderpack.py)" + nl
                    + "program.composite1.enabled=true" + p[gate.end():])
    edits[water] = drop_eye_faces(shaders, water, edits)
    edits[particles] = drop_far_particles(shaders, particles, edits)
    return edits


RECIPES = (("Bliss", bliss), ("MakeUp", makeup), ("Mellow", mellow), ("BSL", bsl), ("Complementary", complementary),
           ("Solas", solas), ("Sildur's", sildurs))


# ---------------------------------------------------------------- main

def find_includes(pack):
    for folder in (pack / "assets/minecraft/shaders/include", pack / "vanilla/assets/minecraft/shaders/include"):
        if all((folder / name).is_file() for name in EYE_INCLUDES):
            return folder
    raise SystemExit(f"no fire eye includes ({', '.join(EYE_INCLUDES)}) in {pack}")


def copy_pack(source, out):
    """Copies a shader pack - a zip or a folder, holding shaders/ at its top
    or one folder down - to out."""
    with tempfile.TemporaryDirectory() as tmp:
        if source.is_file():
            with zipfile.ZipFile(source) as z:
                z.extractall(tmp)
            source = Path(tmp)
        roots = [source] + [d for d in source.iterdir() if d.is_dir()]
        root = next((r for r in roots if (r / "shaders/shaders.properties").is_file()), None)
        if root is None:
            raise SystemExit(f"no shaders/shaders.properties in {source}")
        shutil.copytree(root, out)


def main():
    parser = argparse.ArgumentParser(description="Makes a copy of an Iris shader pack that draws RP-Mordor's fire eye.")
    parser.add_argument("shaderpack", type=Path, help="the shader pack, as a zip or a folder")
    parser.add_argument("pack", type=Path, help="RP-Mordor (its repository, or a vanilla pack made from it)")
    parser.add_argument("--eye", type=int, nargs=3, metavar=("X", "Y", "Z"),
                        help="the eye block's position, in the overworld; defaults to the pack's FIRE_EYE_BLOCK")
    parser.add_argument("--out", type=Path, help="defaults to .minecraft/shaderpacks/<the pack's name>-MCME")
    args = parser.parse_args()
    out = args.out or SHADERPACKS / (args.shaderpack.stem + "-MCME")
    includes = find_includes(args.pack)
    if args.eye is None:
        m = re.search(r"#define FIRE_EYE_BLOCK ivec3\((-?\d+), *(-?\d+), *(-?\d+)\)", read(includes / "fire_eye_config.glsl"))
        if not m:
            raise SystemExit("the pack's fire_eye_config.glsl has no FIRE_EYE_BLOCK: give --eye")
        args.eye = tuple(int(v) for v in m.groups())

    if out.exists():
        if not (out / MARKER).is_file():
            raise SystemExit(f"{out} exists and wasn't written by this script")
        shutil.rmtree(out)
    copy_pack(args.shaderpack, out)
    shaders = Path(os.path.abspath(out / "shaders"))
    lib = shaders / "lib/mcme"
    lib.mkdir(parents=True)
    for name in EYE_INCLUDES:
        shutil.copy(includes / name, lib / name)
    write(lib / "fire_eye_face.glsl", FACE_GLSL)
    write(lib / "fire_eye_draw.glsl", DRAW_GLSL)

    refusals = []
    for name, recipe in RECIPES:
        try:
            for path, text in recipe(shaders, args.eye).items():
                write(path, text)
            break
        except Unsupported as e:
            refusals.append(f"{name}: {e}")
    else:
        shutil.rmtree(out)
        raise SystemExit("not a supported shader pack:\n  " + "\n  ".join(refusals))

    x, y, z = args.eye
    write(out / MARKER,
          f"{args.shaderpack.name} with RP-Mordor's fire eye at {x} {y} {z}, made by\n"
          f"patch_shaderpack.py ({name} recipe) from {includes}.\n"
          "The shader pack's own licence and credits still apply.\n")
    print(f"written {out} ({name})")


if __name__ == "__main__":
    main()
