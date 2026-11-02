# MCME-GUI in the shader base

MCME-GUI is a Paper plugin that draws full-screen GUIs (menus, lists, maps) on a vanilla client. It needs no mod. The plugin seats the player and spawns text displays that only that player can see, and the base's text shader turns them into a flat 2D screen. Every pack gets this part of the base, because a server GUI has to work whichever MCME pack a player has on.

| File | What it does |
|---|---|
| `minecraft/shaders/core/text.vsh` | Places the GUI's pieces, and the action bar's icons (unchanged) |
| `minecraft/shaders/core/text.fsh`<br>`mc26_3/.../core/text.fsh` | Draws them. 26.3's copy is hand-written for its transparency passes; text.vsh is translated as usual. |
| `minecraft/shaders/include/mcme_gui.glsl` | What each display is, and where it goes |
| `minecraft/shaders/include/mcme_gui_frag.glsl` | How panels, the cursor and the backdrop look |
| `minecraft/shaders/core/position_tex_color.vsh`, `.fsh`<br>`minecraft/shaders/include/mcme_gui_hud.glsl` | Hide the HUD while a screen is open (see below) |
| `mcme_gui/font/ui.json`, `mcme_gui/textures/font/ui.png` | The white glyph panels are drawn on, and space glyphs for aligning text and placing HUD overlays |
| `minecraft/shaders/core/item.vsh`, `core/entity.vsh`, `core/entity.fsh`<br>`mc26_3/.../core/` the same<br>`minecraft/shaders/include/mcme_gui_stage.glsl`, `mcme_gui_skin.glsl` | Draw MCME-GUI's 3D models and players on the board (see Models, Players). 26.3's copies are hand-written: its passes differ. |
| `minecraft/shaders/include/mcme_gui_addons*.glsl` | Where add-ons plug in (none yet) |
| `mcme_gui/items/invisible.json`, `mcme_gui/sounds.json` | The invisible item that fills the hotbar while a screen is open (it hides the arm, and holding right mouse with it is how dragging works), and the silent sound it is used with |

All other text, such as signs, name tags and chat, goes through vanilla's path unchanged.

## How it works

- **The board.** The screen is a board 24 x 13.5 units, with y up and its origin under the player's eyes. The shader replaces the camera's view with the board fitted to the screen. A 16:9 screen shows exactly the board; other shapes show more backdrop on the long side. Positions are camera-relative, so a display's board point is simply its x and −z.
- **The cursor** comes from the head turn, read out of the model-view matrix: 0.14 units per degree. The plugin works out the same point from the player's yaw and pitch, so hover and clicks match what the player sees.
- **Depth** comes from the layer, through the game's own projection, just past the near plane. Higher layers draw over lower ones. Within a layer, text draws over panels.
- **Corners** come from texture coordinates: the 240 px ui glyph gets a font page to itself, at 0,0. Vertex indices don't work, because text shares its vertex buffer.

## What a display's colour means

The **alpha byte** of a glyph's colour is the text display's text opacity, and it says what the display is:

| Alpha | What | Red, green, blue |
|---|---|---|
| 160–191 | Text on layer alpha − 160, drawn where it is | Its colour |
| 192–223 | A panel on layer alpha − 192: the ui glyph, scaled to the panel's size plus 0.1 units on every side for its shadow | Style, state, value |
| 224 | An image tile: a 240 px glyph on its own font page, with the image in its top-left corner, scaled like a panel | Red: the layer (bits 0–4) and pixel-art sampling (bit 5) |
| 240–252 | Add-ons (below) | Theirs |
| 253 | Red 1: the backdrop, covering the screen.<br>Red 2: the cursor, placed by the head turn | Cursor: blue 1 while over something clickable |

## Hiding the HUD

The HUD (crosshair, hotbar, hearts) draws in the GUI pass, after the world, so it would cover the screen. The GUI pass doesn't know the head turn, so it can't draw the cursor. It also doesn't know which displays are around. It does see the camera's position (`CameraOffset` in `Globals`, the part past the block).

So the plugin seats a player with a screen open where the camera's x and z are each in the middle of a 1/16-block step. That's less than 1/32 block from where they stood, and nobody stands there by chance: a block's centre is at the start of a step. When the camera is there, the GUI pass hides:

- in `position_tex_color`, which draws every HUD sprite: the crosshair with its attack indicator, and the hotbar with the off hand, hearts, food, armour, air and the experience and locator bars;
- in the text shader's GUI pass: the experience level and the held item's name. Not the chat line being typed or the action bar.

A vertex says whether it lies on one of the HUD's rows (hotbar, bars, hearts, food, armour, air, XP level, held item name, action bar), within the hotbar's reach of the middle. Only quads with all four corners there go, so menus keep theirs. Cutting out the whole area per pixel also cut dialog buttons. The crosshair is found by its exact corners: 15 px square at `((w − 15) / 2, (h − 15) / 2)`, the attack indicator under it.

No vertex is moved. Menus opened over a screen (Esc, chat) draw with the same shaders. A first version moved the HUD's vertices off screen, and any menu quad with only some corners in the area stretched across the screen.

The screen shows to the bottom with the cursor over it. Pressing F1 hides the same HUD anyway.

**Panel styles** (red):

| Id | Style | Id | Style |
|---|---|---|---|
| 0 | Surface | 6 | Progress bar (blue = fill, of 255) |
| 1 | Button | 7 | Scroll bar handle |
| 2 | List row (blue bit 0 shades it a little) | 8 | Divider line |
| 3 | Tab | 9 | Header band |
| 4 | Tooltip | 10 | Frame (outline only) |
| 5 | Toggle (a button with a switch) | 11 | Swatch (blue = RRRGGGBB) |

**States** (green, as bits): 1 hover, 2 selected, 4 disabled, 8 pressed.

A panel's size isn't sent: the fragment shader reads it from how fast the corner and the board point change across the quad, so a panel can be any size. Edges are smoothed over one screen pixel at any resolution.

The plugin's `Board`, `PanelStyle` and `Element` classes hold the same numbers. Change both sides together.

In each layer, panels draw under images, and images under text.

## Add-ons

A feature with its own pieces, such as a map, gets text opacities 240–252:

- **Plugin side:** its widgets draw `Canvas.custom`, which is the ui glyph in its code, placed like a panel.
- **Shader side:** its code joins the base as its own include, imported in `mcme_gui_addons.glsl` and called from:
  - `gui_addon_place`, which can move the vertex and returns its depth slot;
  - `gui_addon_colour` in `mcme_gui_addons_frag.glsl`, which returns the pixel's colour and coverage.

  Both are given the display's colour and opacity.

## Models

MCME-GUI's `Model` widget shows an item's 3D model in a screen. A model can't float in front of the player: turning the head moves only the cursor, so it would slide across the screen, and the board covers the world anyway. So the plugin puts each model's item display on the **stage**, at y −2048 (`GUI_STAGE_Y`), straight under the camera, and the item shader draws it on the board:

- **Which vertices:** with a screen open (the camera on the seat grid, as for the HUD), a vertex whose height in the world is within the stage's band. Nothing else is there: it is below any world, and displays don't fall out of it.
- **Where:** the display lies like the board (model up is north, front is up), so its x and −z from the camera are its board point, exact as a text display's. Its height is its layer, 32 blocks a layer, and up to 12 blocks either way how near it is.
- **Depth:** between its layer's panels and its text, nearer higher, through `gui_depth`'s formula.
- **Look:** lit like an inventory item from its normal, without fog or the world's light. Alpha is multiplied far past 1, so every pixel the cutout keeps is opaque (see Draw order) without a change to item.fsh.
- **Always drawn:** displays without a culling box aren't culled by the view, and the client skips its chunk check for entities past the world's height.

Item models go through `core/item`; special models (player heads, chests, shields) through `core/entity`, which places them the same way. `entity.vsh` mixes the stage's changes in rather than branching on them, and `text.vsh` its GUI pieces' places: with them in an `if`, a 26.2 client (NVIDIA, with Sodium and Iris) drew every entity, and sign text, wrong, though the branch never ran for them. Keep it that way when changing them.

## Players

MCME-GUI's `PlayerModel` builds a player from their head: each part (head, body, arms, legs) is an item display of the player's head on the stage, stretched to the part's size.

- **Which part:** the display's brightness, block light 15 and sky light 1–8 (`gui_stage_skin_part`): head, body, right arm, left arm, right leg, left leg, then slim right and left arms. Sky light 15 is a plain model.
- **Its skin:** every box of a skin has the same layout around its corner, so a pixel's place on a face of the head is its place on that face of the part. `entity.fsh` reads the part's pixel instead (`gui_skin_uv` in `mcme_gui_skin.glsl`), from the interpolated texture coordinate, so it doesn't depend on vertex order.
- **On the stage** every pixel is opaque or not drawn: below half alpha is dropped.

## HUD overlays

MCME-GUI's `Hud` sends text and icons as the subtitle, under an empty title held for an hour. The GUI pass moves every glyph coloured 251, G, B (`mcme_gui_hud.glsl`):

- **G's low 4 bits** are the anchor, from top-left to bottom-right.
- **G's high 4 bits** are the colour, one of Minecraft's 16.
- **B − 128** is the element's y offset in GUI pixels.
- **The x offset** is space glyphs. Each element ends with negative space as wide as itself, so the subtitle line has no width. A glyph's place in its element is then where the subtitle puts it, scaled back from 2.

They hide while a screen is open. The ui font has space glyphs of ±2^i pixels for this: U+E010 to U+E019 forward, U+E020 to U+E029 back.

## Draw order

Nothing the GUI draws is see-through. Every pixel is opaque or not drawn at all, so the depth test stacks the pieces by layer, and the order the client draws them in doesn't matter. Shapes have crisp edges, drawn where they cover at least half a pixel. Only shadows are soft, dithered with a 4×4 pattern that reads as a gradient at normal resolutions. Dithering the smoothed edges too made thin lines fuzzy. Looks that are meant to be see-through are blended in the shader with the colour underneath, which it knows:

- the header band with the backdrop (`gui_backdrop`);
- the shaded list rows with the surface they lie on (`GUI_SURFACE_FILL`, a flat colour for this reason).

This is because see-through pixels went wrong. A see-through pixel drawn before what lies under it hides that thing from the depth test, so the world shows through it. That happened at the tooltip's edge, the header and the cursor's outline. Vanilla 26.2 draws text displays in a pass for plain text and sorts each texture's quads back to front by their distance from the camera. In theory that is controllable: the plugin can set each panel's real distance, and a display with a background colour goes into a later pass. Two fixes built on that changed nothing on a client with Sodium, Iris and Distant Horizons, which is what most MCME players run. So the GUI no longer relies on any draw order, on any client.

## Testing

`checkShaders.py` compiles the text shader in each variant the game uses: the world pass, the GUI pass (`IS_GUI`, which runs the action bar and hides HUD text), see-through, grayscale and, for 26.3, the three transparency passes.
