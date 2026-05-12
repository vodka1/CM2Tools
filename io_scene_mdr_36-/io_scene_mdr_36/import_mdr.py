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
Import Combat Mission MDR files to Blender 3.x

Usage: File > Import > CMx2 MDR (.mdr)
"""

import bpy
import os
import math
import numpy as np
from bpy_extras.image_utils import load_image
from mathutils import Matrix
from .mdr import MDR


def _make_principled_material(name, texture_name, filepath, mdr_mat, use_shadeless,
                               use_recursive_search, relpath):
    """Create a Principled BSDF material with the MDR texture."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = 'HASHED'   # alpha transparency
    mat.shadow_method = 'HASHED'

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # Output
    out = nodes.new('ShaderNodeOutputMaterial')
    out.location = (400, 0)

    if use_shadeless:
        # Emission shader = unlit/shadeless
        emit = nodes.new('ShaderNodeEmission')
        emit.location = (200, 0)
        shader_socket = emit.outputs['Emission']
        color_input = emit.inputs['Color']
    else:
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location = (200, 0)
        shader_socket = bsdf.outputs['BSDF']
        color_input = bsdf.inputs['Base Color']

        # Material colours from MDR
        if "diffuse_color" in mdr_mat:
            r, g, b = mdr_mat["diffuse_color"]
            bsdf.inputs['Base Color'].default_value = (r, g, b, 1.0)
        if "specular_color" in mdr_mat:
            r, g, b = mdr_mat["specular_color"]
            # Principled uses a single specular value; use luminance
            bsdf.inputs['Specular'].default_value = (r + g + b) / 3.0
        if "shininess" in mdr_mat:
            # shininess 0..128 -> roughness 1..0
            roughness = 1.0 - (mdr_mat["shininess"] / 128.0)
            bsdf.inputs['Roughness'].default_value = max(0.0, min(1.0, roughness))
        if "alpha_constant" in mdr_mat:
            bsdf.inputs['Alpha'].default_value = mdr_mat["alpha_constant"]

    links.new(shader_socket, out.inputs['Surface'])

    # Texture
    tex_node = nodes.new('ShaderNodeTexImage')
    tex_node.location = (-200, 0)

    image = None
    bmp_name = texture_name + ".bmp"
    # reuse already-loaded image if present
    for im in bpy.data.images:
        if im.name == bmp_name:
            image = im
            break
    if image is None:
        image = load_image(bmp_name, os.path.dirname(filepath))
    if image is None and use_recursive_search:
        parent_dir = os.path.dirname(os.path.dirname(filepath))
        image = load_image(bmp_name, parent_dir, recursive=True, relpath=relpath)

    if image is not None:
        tex_node.image = image
        links.new(tex_node.outputs['Color'], color_input)
        if not use_shadeless:
            links.new(tex_node.outputs['Alpha'], bsdf.inputs['Alpha'])
    else:
        print("Could not load texture:", bmp_name)
        mat.blend_method = 'OPAQUE'

    return mat


def load(context, use_shadeless, use_smooth_shading, use_transform,
         use_recursive_search, use_metadata, filepath, relpath=None):
    print(filepath)
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    m = MDR(filepath, base_name, False, False, False)
    m.read("")

    collection = context.collection
    new_objects = []
    new_materials = {}

    for mdr_ob in m.objects:
        print("Importing:", mdr_ob.name)

        me = bpy.data.meshes.new(mdr_ob.name)
        verts = mdr_ob.vertex_array
        faces = mdr_ob.index_array

        me.from_pydata(verts, [], faces)
        me.validate()
        me.update()

        # UV map
        uv_layer = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            if use_smooth_shading:
                poly.use_smooth = True
            for li in poly.loop_indices:
                vi = me.loops[li].vertex_index
                if vi < len(mdr_ob.uv_array) and mdr_ob.uv_array[vi] is not None:
                    uv_layer.data[li].uv = mdr_ob.uv_array[vi]

        # Material
        mat_key = "%s_%i" % (mdr_ob.texture_name,
                              mdr_ob.material.get("material_id", 0))
        if mat_key in new_materials:
            mat = new_materials[mat_key]
        else:
            mat = _make_principled_material(
                mat_key, mdr_ob.texture_name, filepath,
                mdr_ob.material, use_shadeless,
                use_recursive_search, relpath)
            new_materials[mat_key] = mat
        me.materials.append(mat)

        ob = bpy.data.objects.new(mdr_ob.name, me)
        collection.objects.link(ob)
        new_objects.append(ob)

    # Parent / transform / anchors pass
    for ob, mdr_ob in zip(new_objects, m.objects):
        # Parenting
        if ob != new_objects[0] and mdr_ob.parent_name:
            demangled = mdr_ob.parent_name.split('.')[0]
            parent = next(
                (x for x in new_objects if x.name.split('.')[0] == demangled),
                None)
            if parent:
                ob.parent = parent
                ob.matrix_parent_inverse = parent.matrix_world.inverted()

        # Transform
        if use_transform:
            transform_matrix = Matrix(mdr_ob.transform_matrix)
            inverse_transform_matrix = Matrix(mdr_ob.inverse_transform_matrix)
            diff = np.sum(
                np.abs(np.array(transform_matrix.inverted()) -
                       np.array(inverse_transform_matrix)))
            if diff < 0.01:
                ob.data.transform(inverse_transform_matrix)
                for v in ob.data.vertices:
                    n = v.normal
                    v.normal = (inverse_transform_matrix.inverted().transposed() @ n).normalized()
                ob.matrix_world = transform_matrix
            else:
                print("Transform mismatch for", ob.name)

        # Anchor points
        for anchor in mdr_ob.anchor_points:
            name, matrix = anchor
            anchor_matrix = Matrix(matrix)
            anchor_ob = bpy.data.objects.new(name, None)
            collection.objects.link(anchor_ob)
            anchor_ob.empty_display_size = 0.1
            anchor_ob.empty_display_type = 'SINGLE_ARROW'
            anchor_ob.matrix_world = anchor_matrix
            anchor_ob.matrix_local @= Matrix.Rotation(math.radians(90), 4, "Y")
            anchor_ob.parent = ob
            anchor_ob.matrix_parent_inverse = ob.matrix_world.inverted()

        # Metadata
        if use_metadata:
            for i, v in enumerate(mdr_ob.meta_data1):
                ob["meta1_%i" % i] = v
            for i, v in enumerate(mdr_ob.meta_data2):
                ob["meta2_%i" % i] = v
            for i, v in enumerate(mdr_ob.meta_data3):
                ob["meta3_%i" % i] = v
            ob["meta_unk1"] = mdr_ob.meta_data_unk1
            ob["meta_unk2"] = mdr_ob.meta_data_unk2
            for key, val in mdr_ob.foliage_meta.items():
                ob["foliage_meta_%s" % key] = val

    return {'FINISHED'}
