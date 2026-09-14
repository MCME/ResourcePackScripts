# Test fixtures

## `sodium_pack/`

A minimal resource pack laid out the way `convert_model` expects, used by the
objmc golden tests. Kept deliberately small (29 files, ~140KB).

Models are copied verbatim from RP-Human so the geometry is genuine. RP-Human
itself is gitignored, so these have to be committed to be usable anywhere but
the machine that pack lives on. Pinning them also means a golden diff can only
come from objmc or from our code — never from the pack shifting underneath.

### What each fixture covers

| Fixture | Branch of `convert_model` it exercises |
|---|---|
| `block/pine_leaves_brown` | the ordinary case: `.objmeta` with `parent`, `mtl_override`, texture from `.mtl` |
| `block/maple_leaves` | a second model sharing `leaves_parent.obj` — different texture, same geometry |
| `block/spruce_thin_trunk_vertical` | **no `.objmeta` at all**; texture resolved from `.mtl`, no manual parent |
| `block/forestfloor` | `omnidirectional_parent: true` — rotation must *not* append the `_1_N` parent suffix |
| `block/spruce_leaves_omnidirectional` | rotated with a manual parent whose `_1_2` variant **exists** |
| `block/synthetic_options` | *synthetic* — `texture`, `output_texture`, `offset`, `visibility`, `options` |
| `block/synthetic_vanilla_texture` | *synthetic* — a `minecraft:`-namespace texture, so lookup goes to `RELATIVE_VANILLA_TEXTURES_PATH` |

Two cases are sequences rather than single files:

- **rotated parent missing** — convert `pine_leaves_brown` at `y=180`. Its parent
  `block/leaves_parent` has no `_1_3` variant, so this takes the fallback branch
  that warns and reuses the unrotated parent.
- **shared parent extraction** — convert the same `model_path` twice. The second
  call rewrites both outputs as children of a shared `*_parent` file.

### Why two fixtures are synthetic

All 1252 `.objmeta` files in RP-Human set only `parent` (1246 of them) and
`omnidirectional_parent` (6). The `texture`, `output_texture`, `offset`,
`options` and `visibility` keys are read by `convert_model` but appear nowhere
in the pack, as does any `minecraft:`-namespace texture. Copying real files
could not cover those branches, so the two `synthetic_*` fixtures set them
explicitly — built by editing a copied real model, so the geometry stays honest.

### A note on what actually changes

objmc encodes the model's geometry into the *texture*, not the model JSON. Two
fixtures sharing an `.obj` produce near-identical `elements` and differ only in
their baked PNG. That is why the goldens commit the JSON in full but record the
PNG as a hash plus its dimensions — the JSON diff shows our wiring, the hash and
size show objmc's encoding moving.
