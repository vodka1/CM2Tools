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

bl_info = {
    "name": "Combat Mission MDR format",
    "author": "Stanislav Bobovych (port to 3.x by Claude/Anthropic)",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "File > Import-Export",
    "description": "Import-Export MDR (Combat Mission CMx2 model format)",
    "warning": "",
    "wiki_url": "https://github.com/sbobovyc/CM2Tools/wiki",
    "support": 'COMMUNITY',
    "category": "Import-Export",
}

if "bpy" in locals():
    import importlib
    if "import_mdr" in locals():
        importlib.reload(import_mdr)
    if "export_mdr" in locals():
        importlib.reload(export_mdr)

import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper, path_reference_mode


class ImportMDR(bpy.types.Operator, ImportHelper):
    """Load a Combat Mission MDR File"""
    bl_idname = "import_scene.mdr"
    bl_label = "Import MDR"
    bl_options = {'PRESET', 'UNDO'}

    filename_ext = ".mdr"
    filter_glob: StringProperty(default="*.mdr", options={'HIDDEN'})

    use_shadeless: BoolProperty(
        name="Shadeless materials",
        description="Make all materials shadeless (Emission shader)",
        default=False,
    )
    use_smooth_shading: BoolProperty(
        name="Use smooth shading",
        description="Make all faces use smooth shading",
        default=True,
    )
    use_transform: BoolProperty(
        name="Apply transform",
        description="Apply the MDR transform matrix to the object",
        default=False,
    )
    use_recursive_search: BoolProperty(
        name="Recursive image search",
        description="Recursively scan parent folders for textures",
        default=True,
    )
    use_metadata: BoolProperty(
        name="Import metadata",
        description="Import MDR metadata into object custom properties",
        default=False,
    )

    def execute(self, context):
        from . import import_mdr
        keywords = self.as_keywords(ignore=("filter_glob",))
        if bpy.data.is_saved and context.preferences.filepaths.use_relative_paths:
            import os
            keywords["relpath"] = os.path.dirname(bpy.data.filepath)
        return import_mdr.load(context, **keywords)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "use_shadeless")
        layout.prop(self, "use_smooth_shading")
        layout.prop(self, "use_transform")
        layout.prop(self, "use_recursive_search")
        layout.prop(self, "use_metadata")


class ExportMDR(bpy.types.Operator, ExportHelper):
    """Save selected objects as a Combat Mission MDR File"""
    bl_idname = "export_scene.mdr"
    bl_label = "Export MDR"
    bl_options = {'PRESET'}

    filename_ext = ".mdr"
    filter_glob: StringProperty(default="*.mdr", options={'HIDDEN'})

    var_float: FloatProperty(
        name="Variable float",
        description="Variable float for testing",
        min=0.0, max=1000.0,
        default=1.0,
    )
    use_metadata: BoolProperty(
        name="Export metadata",
        description="Export metadata from object custom properties",
        default=False,
    )
    path_mode = path_reference_mode
    check_extension = True

    def execute(self, context):
        from . import export_mdr
        keywords = self.as_keywords(ignore=("check_existing", "filter_glob"))
        return export_mdr.save(self, context, **keywords)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "var_float")
        layout.prop(self, "use_metadata")


def menu_func_import(self, context):
    self.layout.operator(ImportMDR.bl_idname, text="CMx2 MDR (.mdr)")


def menu_func_export(self, context):
    self.layout.operator(ExportMDR.bl_idname, text="CMx2 MDR (.mdr)")


def register():
    bpy.utils.register_class(ImportMDR)
    bpy.utils.register_class(ExportMDR)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(ImportMDR)
    bpy.utils.unregister_class(ExportMDR)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()
