# Prototypes (the toolbox)

Shader features being tried out, kept out of the packs and the shader base
until they're ready. None of them ships.

| Folder | What | State |
|---|---|---|
| [boat/](boat) | A custom boat shape for every player, by moving the vanilla boat's vertices in the entity shader | Builds a test pack; first test in game pending |
| [fog/](fog) | Fog block, waterfall spray, clouds and smoke | From RP-Mordor's `experimental/fog-clouds-smoke`; not hooked into the base yet |
| [rock/](rock) | Rock varying by world position on one blockstate, and webbed stone | From RP-Human's `feat/rock-prototype`; uses the base's hooks |

The ice module stays in the shader base itself (`shaderBase/modules/ice`),
switched off: no pack turns it on yet.
