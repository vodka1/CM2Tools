# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
# ##### END GPL LICENSE BLOCK #####

# Script copyright (C) Stanislav Bobovych
# Ported to Blender 3.x with help from API Claude

"""
Export from Blender 3.x to Combat Mission MDR files.

Usage: File > Export > CMx2 MDR (.mdr)
"""

import bpy
import os
import math
from mathutils import Matrix, Vector
from .mdr import MDR, MDRObject


def _get_bounds(obj):
    """Return (x_min, x_max, y_min, y_max, z_min, z_max) in world space."""
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def _get_diffuse_texture_name(ob, operator):
    """Extract texture file base name from the active material (node-based)."""
    mat = ob.material_slots[0].material if ob.material_slots else None
    if mat is None or not mat.use_nodes:
        operator.report({'ERROR'}, "%s: material uses no nodes" % ob.name)
        return None

    for node in mat.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image is not None:
            # strip all extensions: "name.bmp" -> "name", "name.bmp.001" -> "name"
            name = node.image.name
            base = os.path.splitext(os.path.splitext(name)[0])[0]
            return base

    operator.report({'ERROR'}, "%s: no Image Texture node with an image found" % ob.name)
    return None


def save(operator, context, filepath, var_float=1.0, use_metadata=False, path_mode='AUTO'):
    selected = [ob for ob in context.selected_objects if ob.type == 'MESH']
    if not selected:
        operator.report({'ERROR'}, "Select at least one mesh object to export")
        return {'CANCELLED'}

    print("Exporting", filepath)
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    m = MDR(filepath, base_name, False, False, False)

    # Identify root (no parent) and children
    root_obj = next((ob for ob in selected if ob.parent is None), selected[0])
    child_objs = [ob for ob in selected if ob is not root_obj]
    ob_list = [root_obj] + child_objs

    for ob in ob_list:
        print(ob.name, ob.type)
        matrix_world = ob.matrix_basis

        mdr_obj = MDRObject()
        mdr_obj.name = ob.name.encode('ascii')
        mdr_obj.parent_name = ob.parent.name.encode('ascii') if ob.parent else b''
        mdr_obj.var_float = var_float

        # Anchor points from EMPTY children
        for c in ob.children:
            if c.type == 'EMPTY':
                anchor_matrix = c.matrix_world @ Matrix.Rotation(math.radians(-90), 4, "Y")
                mdr_obj.anchor_points.append(
                    (c.name.encode('ascii'), Matrix.transposed(anchor_matrix)))

        me = ob.data
        # Triangulate a temporary copy to be safe
        index_array = []
        for poly in me.polygons:
            if len(poly.vertices) >= 3:
                index_array.append((poly.vertices[0], poly.vertices[1], poly.vertices[2]))

        if not me.uv_layers:
            operator.report({'ERROR'}, "%s: missing UV map" % ob.name)
            return {'CANCELLED'}

        uv_layer = me.uv_layers.active
        uv_array = [None] * len(me.vertices)
        for poly in me.polygons:
            for li in poly.loop_indices:
                vi = me.loops[li].vertex_index
                uv_array[vi] = uv_layer.data[li].uv

        vertex_array = []
        vertex_normal_array = []
        for vert in me.vertices:
            x, y, z = matrix_world @ vert.co
            vertex_array.append((x, y, z))
            transformed_normal = matrix_world.inverted().transposed() @ vert.normal
            nx, ny, nz = transformed_normal.normalized()
            vertex_normal_array.append((
                int(nx * (2 ** 15 - 1)),
                int(ny * (2 ** 15 - 1)),
                int(nz * (2 ** 15 - 1)),
            ))

        x_min, x_max, y_min, y_max, z_min, z_max = _get_bounds(ob)
        mdr_obj.bbox_x_min = x_min
        mdr_obj.bbox_x_max = x_max
        mdr_obj.bbox_y_min = y_min
        mdr_obj.bbox_y_max = y_max
        mdr_obj.bbox_z_min = z_min
        mdr_obj.bbox_z_max = z_max

        texture_base = _get_diffuse_texture_name(ob, operator)
        if texture_base is None:
            return {'CANCELLED'}

        mat = ob.material_slots[0].material
        diff_color = tuple(mat.diffuse_color[:3]) if hasattr(mat, 'diffuse_color') else (0.8, 0.8, 0.8)
        spec_color = (0.5, 0.5, 0.5)
        shininess = 64.0
        alpha_const = 1.0
        # Try to pull values from Principled BSDF if present
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                base = node.inputs['Base Color'].default_value
                diff_color = (base[0], base[1], base[2])
                spec_val = node.inputs['Specular'].default_value
                spec_color = (spec_val, spec_val, spec_val)
                roughness = node.inputs['Roughness'].default_value
                shininess = (1.0 - roughness) * 128.0
                alpha_const = node.inputs['Alpha'].default_value
                break

        mat_id = 0
        for i, key in enumerate(bpy.data.materials.keys()):
            if mat == bpy.data.materials[key]:
                mat_id = i
                break

        mdr_obj.index_array = index_array
        mdr_obj.uv_array = uv_array
        mdr_obj.vertex_array = vertex_array
        mdr_obj.vertex_normal_array = vertex_normal_array
        mdr_obj.texture_name = texture_base.encode('ascii')
        mdr_obj.transform_matrix = matrix_world.transposed()
        mdr_obj.inverse_transform_matrix = matrix_world.inverted().transposed()
        mdr_obj.material = {
            "diffuse_color": diff_color,
            "specular_color": spec_color,
            "shininess": shininess,
            "alpha_constant": alpha_const,
            "material_id": mat_id,
        }

        mdr_obj.meta_data1 = []
        mdr_obj.meta_data2 = []
        mdr_obj.meta_data3 = []
        mdr_obj.foliage_meta = {}
        mdr_obj.meta_data_unk1 = (0.0, 0.0, 0.0)
        mdr_obj.meta_data_unk2 = (0.0, 0.0, 0.0)

        if use_metadata:
            for i in range(0, 11):
                try:
                    mdr_obj.meta_data1.append(ob["meta1_%i" % i])
                except KeyError:
                    pass
            for i in range(0, 24):
                try:
                    mdr_obj.meta_data2.append(ob["meta2_%i" % i])
                except KeyError:
                    pass
            for i in range(0, 35):
                try:
                    mdr_obj.meta_data3.append(ob["meta3_%i" % i])
                except KeyError:
                    pass
            try:
                mdr_obj.meta_data_unk1 = ob["meta_unk1"]
            except KeyError:
                pass
            try:
                mdr_obj.meta_data_unk2 = ob["meta_unk2"]
            except KeyError:
                pass

        print("Exporting %i faces, %i UVs, %i verts" % (
            len(mdr_obj.index_array), len(mdr_obj.uv_array), len(mdr_obj.vertex_array)))
        m.objects.append(mdr_obj)

    m.write(filepath)
    return {'FINISHED'}
