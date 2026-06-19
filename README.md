# MergeVRCFuryPlugin

Blender addon for merging VRCFury-style split avatars where source bones/vertex groups are prefixed (for example `Mane.Chest`) and destination bones are unprefixed (`Chest`).

## What it does

- Uses the active armature as destination and the other selected armature as source
- Renames source-driven vertex groups with VRCFury-style prefix stripping
- Merges duplicate vertex groups when names collide after rename
- Copies missing source bones into the destination armature while preserving hierarchy
- Rebinds source meshes to the destination armature

## Usage

1. Install this addon from the repository root as a Blender addon.
2. In Object Mode, select exactly two armatures.
3. Make the destination armature active.
4. Run **Sidebar → Merge VRCFury → Merge VRCFury Armatures**.
