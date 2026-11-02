# MCME-GUI in the shader base

MCME-GUI is a Paper plugin that draws full-screen GUIs (menus, lists, maps) on a vanilla client. It needs no mod. The plugin seats the player and spawns text displays that only that player can see, and the base's text shader turns them into a flat 2D screen. Every pack gets this part of the base, because a server GUI has to work whichever MCME pack a player has on.

| File | What it does |
|---|---|
| `minecraft/shaders/core/text.vsh` | Places the GUI's pieces, and the action bar's icons (unchanged) |
| `minecraft/shaders/core/text.fsh`<br>`mc26_3/.../core/text.fsh` | Draws them. 26.3's copy is hand-written for its transparency passes; text.vsh is translated as usual. |
| `minecraft/shaders/include/mcme_gui.glsl` | What each display is, and where it goes |
| `minecraft/shaders/include/mcme_gui_frag.glsl` | How panels, the cursor and the backdrop look |
| `minecraft/shaders/core/position_tex_color.vsh`, `.fsh`<br>`minecraft/shaders/include/mcme_gui_hud.glsl` | Hide the HUD while a screen is open (see below) |
| `mcme_gui/font/ui.json`, `mcme_gui/textures/font/ui.png` | The white glyph panels are drawn on, and space glyphs for aligning text |
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
| 253 | Red 1: the backdrop, covering the screen.<br>Red 2: the cursor, placed by the head turn | Cursor: blue 1 while over something clickable |

## Hiding the HUD

The HUD (crosshair, hotbar, hearts) draws in the GUI pass, after the world, so it would cover the screen. The GUI pass doesn't know the head turn, so it can't draw the cursor. It also doesn't know which displays are around. It does see the camera's position (`CameraOffset` in `Globals`, the part past the block).

So the plugin seats a player with a screen open where the camera's x and z are each in the middle of a 1/16-block step. That's less than 1/32 block from where they stood, and nobody stands there by chance: a block's centre is at the start of a step. When the camera is there, the GUI pass hides:

- in `position_tex_color`, which draws every HUD sprite: the crosshair with its attack indicator, and the hotbar with the off hand, hearts, food, armour, air and the experience and locator bars;
- in the text shader's GUI pass: the experience level and the held item's name. Not the chat line being typed or the action bar.

The hotbar area is cut out per pixel: each vertex passes its GUI position to the fragment shader, which skips the pixels inside the area. The crosshair is found by its exact corners: 15 px square at `((w − 15) / 2, (h − 15) / 2)`, the attack indicator under it.

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

## Draw order

Nothing the GUI draws is see-through. Every pixel is opaque or not drawn at all, so the depth test stacks the pieces by layer, and the order the client draws them in doesn't matter. Shapes have crisp edges, drawn where they cover at least half a pixel. Only shadows are soft, dithered with a 4×4 pattern that reads as a gradient at normal resolutions. Dithering the smoothed edges too made thin lines fuzzy. Looks that are meant to be see-through are blended in the shader with the colour underneath, which it knows:

- the header band with the backdrop (`gui_backdrop`);
- the shaded list rows with the surface they lie on (`GUI_SURFACE_FILL`, a flat colour for this reason).

This is because see-through pixels went wrong. A see-through pixel drawn before what lies under it hides that thing from the depth test, so the world shows through it. That happened at the tooltip's edge, the header and the cursor's outline. Vanilla 26.2 draws text displays in a pass for plain text and sorts each texture's quads back to front by their distance from the camera. In theory that is controllable: the plugin can set each panel's real distance, and a display with a background colour goes into a later pass. Two fixes built on that changed nothing on a client with Sodium, Iris and Distant Horizons, which is what most MCME players run. So the GUI no longer relies on any draw order, on any client.

## Testing

`checkShaders.py` compiles the text shader in each variant the game uses: the world pass, the GUI pass (`IS_GUI`, which runs the action bar and hides HUD text), see-through, grayscale and, for 26.3, the three transparency passes.
