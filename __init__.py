bl_info = {
    "name": "Merge VRCFury Armatures",
    "author": "SoobaTomcat",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Merge VRCFury",
    "description": "Merge source armature meshes and missing bones into a destination armature",
    "category": "Object",
}

import bpy
from mathutils import Vector

MIN_BONE_LENGTH = 0.01
MIN_BONE_LENGTH_TOLERANCE = 1e-6
BONE_CONNECTION_TOLERANCE = 1e-4
DEFAULT_BONE_DIRECTION = Vector((0.0, 1.0, 0.0))


def _normalized_bone_name(name: str) -> str:
    if "." not in name:
        return name
    prefix, _, suffix = name.partition(".")
    if not suffix or suffix.isdigit() or not prefix:
        return name
    return suffix


def _source_meshes(source_armature):
    meshes = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        for modifier in obj.modifiers:
            if modifier.type == "ARMATURE" and modifier.object == source_armature:
                meshes.append(obj)
                break
    return meshes


def _find_group_weight(vertex, group_index):
    for group in vertex.groups:
        if group.group == group_index:
            return group.weight
    return 0.0


def _merge_vertex_group(obj, source_group, destination_group):
    source_index = source_group.index
    for vertex in obj.data.vertices:
        weight = _find_group_weight(vertex, source_index)
        if weight > 0.0:
            destination_group.add([vertex.index], weight, "ADD")
    obj.vertex_groups.remove(source_group)


def _rename_vertex_groups(meshes, bone_name_map):
    for mesh in meshes:
        for group in list(mesh.vertex_groups):
            target_name = bone_name_map.get(group.name, _normalized_bone_name(group.name))
            if target_name == group.name:
                continue
            existing_group = mesh.vertex_groups.get(target_name)
            if existing_group is None:
                group.name = target_name
            else:
                _merge_vertex_group(mesh, group, existing_group)


def _bone_depth(bone):
    depth = 0
    current = bone.parent
    while current is not None:
        depth += 1
        current = current.parent
    return depth


def _ensure_missing_bones(source_armature, destination_armature, bone_name_map):
    source_bones = sorted(source_armature.data.bones, key=_bone_depth)
    destination_bones = destination_armature.data.bones

    previous_active = bpy.context.view_layer.objects.active
    previous_selected = list(bpy.context.selected_objects)

    bpy.ops.object.select_all(action="DESELECT")
    destination_armature.select_set(True)
    bpy.context.view_layer.objects.active = destination_armature
    bpy.ops.object.mode_set(mode="EDIT")

    edit_bones = destination_armature.data.edit_bones
    destination_inverse_world = destination_armature.matrix_world.inverted()

    for source_bone in source_bones:
        normalized_name = bone_name_map[source_bone.name]
        if normalized_name in edit_bones:
            continue

        edit_bone = edit_bones.new(normalized_name)

        source_head_world = source_armature.matrix_world @ source_bone.head_local
        source_tail_world = source_armature.matrix_world @ source_bone.tail_local
        head = destination_inverse_world @ source_head_world
        tail = destination_inverse_world @ source_tail_world

        bone_direction = tail - head
        if bone_direction.length < MIN_BONE_LENGTH_TOLERANCE:
            bone_direction = DEFAULT_BONE_DIRECTION
        tail = head + bone_direction.normalized() * max(bone_direction.length, MIN_BONE_LENGTH)

        edit_bone.head = head
        edit_bone.tail = tail

        source_matrix_world = source_armature.matrix_world @ source_bone.matrix_local
        source_z_axis = (source_matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
        destination_z_axis = (destination_inverse_world.to_3x3() @ source_z_axis).normalized()
        edit_bone.align_roll(destination_z_axis)

        if source_bone.parent is not None:
            parent_name = bone_name_map[source_bone.parent.name]
            parent_edit_bone = edit_bones.get(parent_name)
            if parent_edit_bone is not None:
                edit_bone.parent = parent_edit_bone
                if source_bone.use_connect and (edit_bone.head - parent_edit_bone.tail).length < BONE_CONNECTION_TOLERANCE:
                    edit_bone.use_connect = True

    bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in previous_selected:
        if obj.name in bpy.data.objects:
            obj.select_set(True)
    if previous_active and previous_active.name in bpy.data.objects:
        bpy.context.view_layer.objects.active = previous_active


def _reparent_meshes(meshes, destination_armature, source_armature):
    for mesh in meshes:
        mesh.parent = destination_armature
        mesh.parent_type = "OBJECT"
        mesh.matrix_parent_inverse = destination_armature.matrix_world.inverted() @ mesh.matrix_world

        for modifier in mesh.modifiers:
            if modifier.type == "ARMATURE" and modifier.object == source_armature:
                modifier.object = destination_armature


class OBJECT_OT_merge_vrcfury_armatures(bpy.types.Operator):
    bl_idname = "object.merge_vrcfury_armatures"
    bl_label = "Merge VRCFury Armatures"
    bl_description = "Merge source armature bones/weights into destination armature"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selected_armatures = [obj for obj in context.selected_objects if obj.type == "ARMATURE"]
        if len(selected_armatures) != 2:
            self.report({"ERROR"}, "Select exactly two armatures (active = destination)")
            return {"CANCELLED"}

        destination_armature = context.view_layer.objects.active
        if destination_armature is None or destination_armature.type != "ARMATURE":
            self.report({"ERROR"}, "Active object must be the destination armature")
            return {"CANCELLED"}

        source_armature = selected_armatures[0] if selected_armatures[1] == destination_armature else selected_armatures[1]
        if source_armature == destination_armature:
            self.report({"ERROR"}, "Source and destination armatures must be different")
            return {"CANCELLED"}

        source_meshes = _source_meshes(source_armature)
        if not source_meshes:
            self.report({"WARNING"}, "No meshes were found using the source armature")

        bone_name_map = {bone.name: _normalized_bone_name(bone.name) for bone in source_armature.data.bones}

        _ensure_missing_bones(source_armature, destination_armature, bone_name_map)
        _rename_vertex_groups(source_meshes, bone_name_map)
        _reparent_meshes(source_meshes, destination_armature, source_armature)

        self.report(
            {"INFO"},
            f"Merged {len(source_meshes)} mesh(es) from '{source_armature.name}' into '{destination_armature.name}'",
        )
        return {"FINISHED"}


class VIEW3D_PT_merge_vrcfury_armatures(bpy.types.Panel):
    bl_label = "Merge VRCFury"
    bl_idname = "VIEW3D_PT_merge_vrcfury_armatures"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Merge VRCFury"

    def draw(self, _context):
        self.layout.operator(OBJECT_OT_merge_vrcfury_armatures.bl_idname)


classes = (
    OBJECT_OT_merge_vrcfury_armatures,
    VIEW3D_PT_merge_vrcfury_armatures,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
