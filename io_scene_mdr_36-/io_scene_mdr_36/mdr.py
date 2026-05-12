# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# Script copyright (C) Stanislav Bobovych
# Ported to Blender 3.x with help from API Claude

import numpy as np
import struct
from pprint import pprint


def print4x4matrix(matrix):
    print("[")
    for row in matrix:
        print("[{0: .2f}, {1: .2f}, {2: .2f}, {3: .2f}]".format(row[0], row[1], row[2], row[3]))
    print("]")


def read_matrix(f):
    print("# Start reading matrix", "0x%x" % f.tell())
    mat = np.identity(4)
    for column in range(0, 4):
        for row in range(0, 3):
            value, = struct.unpack("f", f.read(4))
            mat[row][column] = value
    print("# This is a transform matrix:")
    print(mat)
    return mat


def write_matrix(mat, f):
    for column in range(0, 4):
        f.write(struct.pack("fff", *mat[column][:3]))


def read_material(f):
    print("# Start reading material", "0x%x" % f.tell())
    ambient_color = struct.unpack("fff", f.read(4 * 3))
    print("# Ambient color", ambient_color)
    diffuse_color = struct.unpack("fff", f.read(4 * 3))
    print("# Diffuse color", diffuse_color)
    specular_color = struct.unpack("fff", f.read(4 * 3))
    print("# Specular color", specular_color)
    shininess, = struct.unpack("f", f.read(4))
    print("# Shininess", shininess)
    alpha_constant, = struct.unpack("f", f.read(4))
    print("# Alpha constant", alpha_constant)
    material_id, = struct.unpack("<I", f.read(4))
    print("# Material id", material_id)
    print("# End material", "0x%x" % f.tell())

    material = {
        "material_id": material_id,
        "ambient_color": ambient_color,
        "diffuse_color": diffuse_color,
        "specular_color": specular_color,
        "shininess": shininess,
        "alpha_constant": alpha_constant,
    }
    return material


class MDR:
    def __init__(self, filepath, base_name, dump_manifest=False, parse_only=False, verbose=False):
        self.filepath = filepath
        self.base_name = base_name
        self.parse_only = parse_only
        self.verbose = verbose
        self.objects = []
        self.num_models = 0

    def read(self, outdir):
        with open(self.filepath, "rb") as f:
            self.num_models, = struct.unpack("<I", f.read(4))
            print("# number of models", self.num_models)
            for i in range(0, self.num_models):
                mdr_obj = MDRObject()
                mdr_obj.read(self.base_name, self.num_models, f, i, outdir, not self.parse_only, self.verbose)
                self.objects.append(mdr_obj)

    def write(self, filepath):
        with open(filepath, "wb") as f:
            self.num_models = len(self.objects)
            f.write(struct.pack("<I", self.num_models))

            for o in self.objects:
                f.write(struct.pack('x'))
                f.write(struct.pack("<H", len(o.name)))
                f.write(struct.pack("%is" % len(o.name), o.name))
                f.write(struct.pack("b", 2))  # unk0
                if len(o.meta_data1) != 0:
                    for i in range(0, 11):
                        f.write(struct.pack("f", o.meta_data1[i]))
                    if len(o.meta_data2) != 0:
                        for i in range(0, 24):
                            f.write(struct.pack("f", o.meta_data2[i]))
                        f.write(struct.pack("fff", *o.meta_data_unk1))
                    else:
                        f.write(struct.pack('x' * 108))
                else:
                    f.write(struct.pack("f", 1.0))
                    f.write(struct.pack('x' * 148))
                f.write(struct.pack("ff", o.bbox_x_min, o.bbox_x_max))
                f.write(struct.pack("ff", o.bbox_y_min, o.bbox_y_max))
                f.write(struct.pack("ff", o.bbox_z_min, o.bbox_z_max))
                f.write(struct.pack("<I", 3 * len(o.index_array)))
                for idx in o.index_array:
                    f.write(struct.pack("<HHH", idx[0], idx[1], idx[2]))
                f.write(struct.pack("<I", 2 * len(o.uv_array)))
                for uv in o.uv_array:
                    f.write(struct.pack("<ff", uv[0], uv[1]))
                f.write(struct.pack('<I', len(o.uv_array) - 1))

                f.write(struct.pack('xx'))
                f.write(struct.pack("<H", len(o.parent_name)))
                if len(o.parent_name) > 0:
                    f.write(struct.pack("%is" % len(o.parent_name), o.parent_name))

                write_matrix(o.transform_matrix, f)
                write_matrix(o.inverse_transform_matrix, f)

                f.write(struct.pack("<I", len(o.anchor_points)))
                for anchor in o.anchor_points:
                    name, m = anchor
                    f.write(struct.pack("<H", len(name)))
                    f.write(struct.pack("%is" % len(name), name))
                    write_matrix(m, f)

                f.write(struct.pack(60 * 'x'))

                f.write(struct.pack("fff", 1.0, 1.0, 1.0))  # ambient color hardcoded white
                f.write(struct.pack("fff", *o.material["diffuse_color"]))
                f.write(struct.pack("fff", *o.material["specular_color"]))
                f.write(struct.pack("f", o.material["shininess"]))
                f.write(struct.pack("f", o.material["alpha_constant"]))
                f.write(struct.pack("I", o.material["material_id"]))

                f.write(struct.pack("<H", len(o.texture_name)))
                f.write(struct.pack("%is" % len(o.texture_name), o.texture_name))
                f.write(struct.pack("b", 2))  # unk3
                if len(o.meta_data3) != 0:
                    for i in range(0, 35):
                        f.write(struct.pack("f", o.meta_data3[i]))
                    f.write(struct.pack("fff", *o.meta_data_unk2))
                else:
                    f.write(struct.pack("f", 1.0))
                    f.write(struct.pack('x' * 148))
                f.write(struct.pack("ff", o.bbox_x_min, o.bbox_x_max))
                f.write(struct.pack("ff", o.bbox_y_min, o.bbox_y_max))
                f.write(struct.pack("ff", o.bbox_z_min, o.bbox_z_max))
                f.write(struct.pack("<I", 3 * len(o.vertex_array)))
                for vert in o.vertex_array:
                    f.write(struct.pack("<fff", vert[0], vert[1], vert[2]))
                f.write(struct.pack("<I", 3 * len(o.vertex_normal_array)))
                for norm in o.vertex_normal_array:
                    f.write(struct.pack("<hhh", norm[0], norm[1], norm[2]))
                f.write(struct.pack("<I", 0))  # no footer


class MDRObject:
    def __init__(self):
        self.base_name = ""
        self.name = ""
        self.parent_name = ""
        self.index_array = []
        self.uv_array = []
        self.vertex_array = []
        self.vertex_normal_array = []
        self.texture_name = ""
        self.material = {}
        self.anchor_points = []
        self.bbox_x_min = 0
        self.bbox_x_max = 0
        self.bbox_y_min = 0
        self.bbox_y_max = 0
        self.bbox_z_min = 0
        self.bbox_z_max = 0
        self.transform_matrix = None
        self.inverse_transform_matrix = None
        self.foliage_meta = {}

    def read(self, base_name, num_models, f, model_number, outdir, dump=True, verbose=False):
        self.base_name = base_name
        print("# Start model %i" % model_number, "at 0x%x" % f.tell(),
              "##############################################################")
        f.read(1)
        name_length, = struct.unpack("<H", f.read(2))
        self.name = f.read(name_length).decode("ascii")
        print("# submodel name:", self.name)

        self.meta_data1 = []
        self.meta_data2 = []
        self.meta_data3 = []
        self.meta_data_unk1 = None
        self.meta_data_unk2 = None

        unk0, = struct.unpack("b", f.read(1))
        if unk0 != 2:
            print("unk0 is %s, not 2, 0x%x %s, %s, %s" % (unk0, f.tell() - 1, base_name, self.name, model_number))

        for i in range(0, 11):
            unk, = struct.unpack("f", f.read(4))
            self.meta_data1.append(unk)

        for i in range(0, 6):
            for j in range(0, 4):
                unk, = struct.unpack("f", f.read(4))
                self.meta_data2.append(unk)

        unk = struct.unpack("fff", f.read(12))
        self.meta_data_unk1 = unk
        self.bbox_x_min, self.bbox_x_max, self.bbox_y_min, self.bbox_y_max, self.bbox_z_min, self.bbox_z_max = struct.unpack("ffffff", f.read(24))

        face_count, = struct.unpack("<I", f.read(4))
        for i in range(0, int(face_count / 3)):
            if not dump:
                f.read(6)
            else:
                v0, v1, v2 = struct.unpack("<HHH", f.read(6))
                self.index_array.append((v0, v1, v2))

        uv_in_section, = struct.unpack("<I", f.read(4))
        for i in range(0, int(uv_in_section / 2)):
            if not dump:
                f.read(8)
            else:
                u, v = struct.unpack("<ff", f.read(8))
                self.uv_array.append((u, v))

        uv_last_index, = struct.unpack("<I", f.read(4))
        count, = struct.unpack("<H", f.read(2))
        if count != 0:
            for i in range(0, count):
                length, = struct.unpack("<H", f.read(2))
                meta_name = f.read(length).decode("ascii")
                meta_count, = struct.unpack("<H", f.read(2))
                meta_data = struct.unpack('b' * meta_count, f.read(meta_count))
                self.foliage_meta[meta_name] = meta_data

        length, = struct.unpack("<H", f.read(2))
        self.parent_name = ""
        if length > 0:
            self.parent_name = f.read(length).decode("ascii")

        self.transform_matrix = read_matrix(f)
        self.inverse_transform_matrix = read_matrix(f)

        anchor_point_count, = struct.unpack("<I", f.read(4))
        for i in range(0, anchor_point_count):
            name_length, = struct.unpack("<H", f.read(2))
            anchor_name = f.read(name_length).decode("ascii")
            m = read_matrix(f)
            self.anchor_points.append((anchor_name, m))

        # unknown section (6 x 10 bytes)
        for i in range(0, 3):
            f.read(1)
            f.read(1)
            f.read(4)
            f.read(4)
        for i in range(0, 3):
            f.read(1)
            f.read(1)
            f.read(4)
            f.read(4)

        self.material = read_material(f)

        name_length, = struct.unpack("<H", f.read(2))
        texture_name = f.read(name_length).decode("ascii")
        print("# Texture name:", texture_name)
        if dump:
            self.texture_name = texture_name

        unk3, = struct.unpack("b", f.read(1))
        if unk3 != 2:
            print("unk3 is %s, not 2, 0x%x %s, %s, %s" % (unk3, f.tell() - 1, base_name, self.name, model_number))

        for i in range(0, 35):
            unk, = struct.unpack("f", f.read(4))
            self.meta_data3.append(unk)
        unk = struct.unpack("fff", f.read(12))
        self.meta_data_unk2 = unk
        self.bbox_x_min, self.bbox_x_max, self.bbox_y_min, self.bbox_y_max, self.bbox_z_min, self.bbox_z_max = struct.unpack("ffffff", f.read(24))

        vertex_floats, = struct.unpack("<I", f.read(4))
        for i in range(0, int(vertex_floats / 3)):
            if not dump:
                f.read(12)
            else:
                x, y, z = struct.unpack("fff", f.read(12))
                self.vertex_array.append((x, y, z))

        normal_count, = struct.unpack("<I", f.read(4))
        for i in range(0, int(normal_count / 3)):
            if not dump:
                f.read(6)
            else:
                nx, ny, nz = struct.unpack("<hhh", f.read(6))
                self.vertex_normal_array.append((nx, ny, nz))

        footer_counter, = struct.unpack("<I", f.read(4))
        if footer_counter != 0:
            print("# Parsing footer, count:", footer_counter)
            for i in range(0, footer_counter):
                print(struct.unpack("<fff", f.read(12)))
                length, = struct.unpack("<I", f.read(4))
                f.read(length * 4)

        print("# End model 0x%x ##############################################################" % f.tell())
