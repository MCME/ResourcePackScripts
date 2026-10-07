"""The shader checks: what each one catches before a player's driver does."""

import json
import zipfile
from pathlib import Path

import pytest
import shader_check

DH_FRAG = "terrain/gl/frag.frag"
DH_ORIGINAL = """#version 330 core
in vec4 vertexColor;
out vec4 fragColor;
uniform float uClipDistance = 0.0;
layout (std140) uniform fragUniformBlock
{
    float uNoiseIntensity;
};
void main() { fragColor = vertexColor; }
"""


def _write(path: Path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _shader(pack: Path, namespace: str, path: str, text: str):
    _write(pack / "assets" / namespace / "shaders" / path, text)


def _dh_jar(tmp_path, files: dict) -> Path:
    jar = tmp_path / "dh.jar"
    with zipfile.ZipFile(jar, "w") as z:
        z.writestr("fabric.mod.json", json.dumps({"id": "distanthorizons", "version": "3.3.3"}))
        for path, text in files.items():
            z.writestr(f"assets/distanthorizons/shaders/{path}", text)
    return jar


@pytest.fixture
def pack(tmp_path):
    pack = tmp_path / "pack"
    (pack / "assets").mkdir(parents=True)
    return pack


def test_rules_pass_a_plain_shader(pack):
    _shader(pack, "minecraft", "core/terrain.fsh", "#version 330\nvoid main() {}\n")
    assert shader_check.check_rules(pack) == []


def test_rules_refuse_a_version_above_macos(pack):
    _shader(pack, "minecraft", "core/terrain.fsh", "#version 430\nvoid main() {}\n")
    assert "macOS stops at 410" in shader_check.check_rules(pack)[0]


def test_rules_refuse_an_include_above_macos(pack):
    _shader(pack, "minecraft", "include/water.glsl", "#version 450\n")
    assert len(shader_check.check_rules(pack)) == 1


def test_rules_refuse_es(pack):
    _shader(pack, "minecraft", "core/terrain.fsh", "#version 300 es\nvoid main() {}\n")
    assert "ES" in shader_check.check_rules(pack)[0]


def test_rules_refuse_an_extension(pack):
    _shader(pack, "minecraft", "core/terrain.fsh", "#version 330\n#extension GL_ARB_gpu_shader5 : require\n")
    assert "GL_ARB_gpu_shader5" in shader_check.check_rules(pack)[0]


def test_rules_allow_dhs_own_extension(pack):
    _shader(pack, "distanthorizons", "terrain/blaze/frag.fsh",
            "#version 330\n#extension GL_ARB_separate_shader_objects : require\n")
    assert shader_check.check_rules(pack) == []


def test_rules_refuse_a_stage_without_version(pack):
    _shader(pack, "minecraft", "core/terrain.fsh", "void main() {}\n")
    assert "no #version" in shader_check.check_rules(pack)[0]


def test_rules_ignore_comments(pack):
    _shader(pack, "minecraft", "core/terrain.fsh", "#version 330\n// #version 460\n/* #extension GL_X : require */\n")
    assert shader_check.check_rules(pack) == []


def test_dh_override_matching_its_original_passes(pack, tmp_path):
    _shader(pack, "distanthorizons", DH_FRAG, DH_ORIGINAL.replace("fragColor = vertexColor", "fragColor = vec4(1.0)"))
    jars = {"distanthorizons": _dh_jar(tmp_path, {DH_FRAG: DH_ORIGINAL})}
    assert shader_check.check_dh_overrides(pack, shader_check.Sources(pack, jars)) == []


def test_dh_override_may_add_its_own_inputs(pack, tmp_path):
    _shader(pack, "distanthorizons", DH_FRAG, DH_ORIGINAL.replace("out vec4", "in vec3 vLavaWorld;\nout vec4"))
    jars = {"distanthorizons": _dh_jar(tmp_path, {DH_FRAG: DH_ORIGINAL})}
    assert shader_check.check_dh_overrides(pack, shader_check.Sources(pack, jars)) == []


def test_dh_override_lacking_what_dh_added_fails(pack, tmp_path):
    _shader(pack, "distanthorizons", DH_FRAG, DH_ORIGINAL)
    newer = DH_ORIGINAL.replace("in vec4 vertexColor;", "in vec4 vertexColor;\nflat in uint vMaterial;")
    jars = {"distanthorizons": _dh_jar(tmp_path, {DH_FRAG: newer})}
    problems = shader_check.check_dh_overrides(pack, shader_check.Sources(pack, jars))
    assert len(problems) == 1 and "in uint vMaterial" in problems[0]


def test_dh_override_lacking_a_block_member_fails(pack, tmp_path):
    _shader(pack, "distanthorizons", DH_FRAG, DH_ORIGINAL)
    newer = DH_ORIGINAL.replace("float uNoiseIntensity;", "float uNoiseIntensity;\n    int uNoiseSteps;")
    jars = {"distanthorizons": _dh_jar(tmp_path, {DH_FRAG: newer})}
    problems = shader_check.check_dh_overrides(pack, shader_check.Sources(pack, jars))
    assert len(problems) == 1 and "fragUniformBlock.uNoiseSteps" in problems[0]


def test_dh_override_with_a_changed_type_fails(pack, tmp_path):
    _shader(pack, "distanthorizons", DH_FRAG, DH_ORIGINAL)
    newer = DH_ORIGINAL.replace("in vec4 vertexColor", "in vec3 vertexColor")
    jars = {"distanthorizons": _dh_jar(tmp_path, {DH_FRAG: newer})}
    assert "is vec3" in shader_check.check_dh_overrides(pack, shader_check.Sources(pack, jars))[0]


def test_dh_override_dh_no_longer_has_fails(pack, tmp_path):
    _shader(pack, "distanthorizons", DH_FRAG, DH_ORIGINAL)
    jars = {"distanthorizons": _dh_jar(tmp_path, {})}
    assert "never used" in shader_check.check_dh_overrides(pack, shader_check.Sources(pack, jars))[0]


def test_dh_overrides_unchecked_without_dh(pack):
    _shader(pack, "distanthorizons", DH_FRAG, DH_ORIGINAL)
    assert shader_check.check_dh_overrides(pack, shader_check.Sources(pack, {})) == []


def test_expand_fills_imports_and_defines(pack):
    _shader(pack, "minecraft", "core/terrain.fsh", "#version 330\n#moj_import <minecraft:a.glsl>\nvoid main() {}\n")
    _shader(pack, "minecraft", "include/a.glsl", "#version 150\n#moj_import <sodium:b.glsl>\nfloat a;\n")
    _shader(pack, "sodium", "include/b.glsl", "float b;\n")
    text = shader_check.Sources(pack, {}).expand("minecraft", "core/terrain.fsh", ["ALPHA_CUTOUT 0.5"])
    lines = text.splitlines()
    assert lines[0] == "#version 330" and lines[1] == "#define ALPHA_CUTOUT 0.5"
    assert "float a;" in text and "float b;" in text and "#version 150" not in text


def test_expand_names_a_missing_import(pack):
    _shader(pack, "minecraft", "core/terrain.fsh", "#version 330\n#moj_import <minecraft:gone.glsl>\n")
    with pytest.raises(FileNotFoundError, match="minecraft:include/gone.glsl"):
        shader_check.Sources(pack, {}).expand("minecraft", "core/terrain.fsh")


def test_programs_pair_stages(pack, tmp_path):
    _shader(pack, "minecraft", "core/terrain.vsh", "#version 330\n")
    _shader(pack, "minecraft", "core/terrain.fsh", "#version 330\n")
    _shader(pack, "minecraft", "core/lightmap.fsh", "#version 330\n")
    _shader(pack, "minecraft", "core/screenquad.vsh", "#version 330\n")
    _shader(pack, "distanthorizons", "fade/gl/vanilla_fade.frag", "#version 330\n")
    jars = {"distanthorizons": _dh_jar(tmp_path, {"shared/gl/quad_apply.vert": "#version 330\n",
                                                  "fade/gl/vanilla_fade.frag": "#version 330\n"})}
    found = shader_check.programs(pack, shader_check.Sources(pack, jars))
    assert ("minecraft", "core/terrain.vsh", "core/terrain.fsh") in found
    assert ("minecraft", "core/screenquad.vsh", "core/lightmap.fsh") in found
    assert ("distanthorizons", "shared/gl/quad_apply.vert", "fade/gl/vanilla_fade.frag") in found


GLSLANG = shader_check.find_glslang()


@pytest.mark.skipif(GLSLANG is None, reason="glslang isn't installed")
def test_compile_catches_a_broken_shader(pack):
    _shader(pack, "minecraft", "core/terrain.vsh", "#version 330\nvoid main() { gl_Position = vec4(0.0); }\n")
    _shader(pack, "minecraft", "core/terrain.fsh", "#version 330\nout vec4 c;\nvoid main() { c = vec3(1.0); }\n")
    report = shader_check.compile_pack(pack, shader_check.Sources(pack, {}), GLSLANG)
    assert report.problems and all("core/terrain.fsh" in p for p in report.problems)


@pytest.mark.skipif(GLSLANG is None, reason="glslang isn't installed")
def test_compile_passes_a_good_shader(pack):
    _shader(pack, "minecraft", "core/terrain.vsh", "#version 330\nvoid main() { gl_Position = vec4(0.0); }\n")
    _shader(pack, "minecraft", "core/terrain.fsh", "#version 330\nout vec4 c;\nvoid main() { c = vec4(1.0); }\n")
    report = shader_check.compile_pack(pack, shader_check.Sources(pack, {}), GLSLANG)
    assert report.problems == [] and len(report.notes) == 2  # without and with ALPHA_CUTOUT
