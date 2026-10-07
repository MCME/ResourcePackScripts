# Boat prototype

A custom boat shape for every player, without a mod. The oak boat is drawn
as a longboat: same entity, same texture file, vertices moved by the entity
shader.

```
python prototypes/boat/make_boat.py [pack folder] [--jar <26.2 client jar>]
```

This writes a resource pack (by default `MCME-boat-prototype` in
`.minecraft/resourcepacks`) with `core/entity.vsh`, `include/mcme_boat.glsl`
and a marked `textures/entity/boat/oak.png`. Load it above the other packs.

## How it works

- **The marker.** The boat texture carries two texels in its unused top-left
  corner. The vertex shader checks them, so every other entity is left alone.
- **Which vertex is which.** A boat vertex is known by its texture coordinate
  and its corner (`gl_VertexID & 3`): `vanilla_boat.py` rebuilds the vanilla
  boat's faces exactly as Minecraft 26.2 does (`BoatModel`, `ModelPart$Cube`,
  `ModelPart$Polygon`, `AbstractBoatRenderer`).
- **Where the boat is.** A face pointing sideways gives the boat's yaw from its
  normal, and the corner's place on the vanilla boat gives the boat's origin.
  Its four corners are then drawn where the new model puts them.

## Limits

- **14 faces.** Faces pointing up or down can't tell the yaw, and six sideways
  faces share a texture corner with another face, so nothing tells them
  apart. Those are hidden; the other 14 carry the new model.
- **The paddles stay vanilla.** They swing on their own axes.
- **Rocking when hit** isn't followed: the boat is taken to turn about y only.
- **The water patch** that hides water inside the boat keeps the vanilla size.
- **Shader packs** draw the vanilla boat.
- **Oak only** for now. Chest boats and the bamboo raft have their own models.

## Status

Prototype on the `feat/toolbox` branch, with the shader base's other
toolbox items (fog block, spray, rock, ice). Not tested in game yet: if the
boat shows scrambled or missing, the assumption that the game sends each
face's four vertices in order, as for terrain, doesn't hold for entities.
