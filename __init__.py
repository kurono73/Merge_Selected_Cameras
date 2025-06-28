# Merge Selected Cameras


import bpy
import re
from math import isclose

def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    return [int(text) if text.isdigit() else text.lower() for text in _nsre.split(s)]

class MergeSelectedCamerasOperator(bpy.types.Operator):
    bl_idname = "camera.merge_selected_cameras"
    bl_label = "Merge Cameras"
    bl_options = {'REGISTER', 'UNDO'}

    delete_original_cameras: bpy.props.BoolProperty(
        name="Delete Original Cameras",
        description="Remove original cameras after merging",
        default=True,
    )
    process_only_selected_cameras: bpy.props.BoolProperty(
        name="Selected cameras only",
        description="Process only manually selected cameras; if unchecked, auto-detect cameras by name from the active camera",
        default=False,
    )
    camera_name_custom: bpy.props.StringProperty(
        name="Custom Camera Name",
        description="Custom name for the merged camera if not using input sequence name", # Description updated
        default="MergedCamera",
    )
    camera_name_use_derived: bpy.props.BoolProperty(
        name="Input sequence name", # Label changed in Scene Property definition
        description="If checked, the merged camera name will be derived from the input camera sequence's base name. Otherwise, the custom name below is used.", # Description updated
        default=False,
    )

    @classmethod
    def poll(cls, context):
        scene = context.scene
        if scene.process_only_selected_cameras:
            return any(obj.type == 'CAMERA' for obj in context.selected_objects)
        else:
            active_obj = context.view_layer.objects.active
            return active_obj is not None and active_obj.type == 'CAMERA'

    def execute(self, context):
        scene = context.scene
        base_name_match_for_auto_detect = None

        if self.process_only_selected_cameras:
            selected_objects = context.selected_objects
            camera_objects = [obj for obj in selected_objects if obj.type == 'CAMERA']
        else:
            active_camera_obj = context.view_layer.objects.active
            if not active_camera_obj or active_camera_obj.type != 'CAMERA':
                self.report({'WARNING'}, "No active camera found for auto-detection.")
                return {'CANCELLED'}
            base_name_match_for_auto_detect = re.match(r'(.*?)(\d+)(\.\w+)?$', active_camera_obj.name)
            if not base_name_match_for_auto_detect:
                self.report({'WARNING'}, "Active camera name does not match expected pattern.")
                return {'CANCELLED'}
            base_name_for_glob = base_name_match_for_auto_detect.group(1)
            if not base_name_for_glob and not base_name_match_for_auto_detect.group(2):
                 self.report({'INFO'}, f"Active camera name '{active_camera_obj.name}' suggests a simple numeric sequence.")
            camera_objects = [
                obj for obj in bpy.data.objects
                if obj.type == 'CAMERA' and re.match(fr'{re.escape(base_name_for_glob)}\d+(\.\w+)?$', obj.name)
            ]

        if not camera_objects:
            self.report({'WARNING'}, "No cameras found to merge based on current settings.")
            return {'CANCELLED'}

        sorted_camera_objects = sorted(camera_objects, key=lambda cam: natural_sort_key(cam.name))

        final_camera_name = ""
        if self.camera_name_use_derived: # Corresponds to "Input sequence name" checkbox
            derived_base_name_from_sequence = ""
            if self.process_only_selected_cameras:
                if sorted_camera_objects:
                    reference_name = sorted_camera_objects[0].name
                    match = re.match(r'(.*?)(\d+)(\.\w+)?$', reference_name)
                    if match:
                        derived_base_name_from_sequence = match.group(1)
            else:
                if base_name_match_for_auto_detect:
                    derived_base_name_from_sequence = base_name_match_for_auto_detect.group(1)
            cleaned_derived_name = derived_base_name_from_sequence.rstrip(' _.-')
            if not cleaned_derived_name.strip():
                final_camera_name = "MergedCamera"
                self.report({'WARNING'}, "Could not derive name from sequence, using default 'MergedCamera'.")
            else:
                final_camera_name = cleaned_derived_name
        else:
            if not self.camera_name_custom.strip():
                final_camera_name = "MergedCamera"
                self.report({'WARNING'}, "Custom camera name was blank, using default 'MergedCamera'.")
            else:
                final_camera_name = self.camera_name_custom

        bpy.ops.object.camera_add(location=(0, 0, 0))
        animated_camera = context.object
        animated_camera.name = final_camera_name

        first_camera = sorted_camera_objects[0]
        animated_camera.data.sensor_width = first_camera.data.sensor_width
        animated_camera.data.sensor_height = first_camera.data.sensor_height
        animated_camera.data.lens = first_camera.data.lens
        animated_camera.data.shift_x = first_camera.data.shift_x
        animated_camera.data.shift_y = first_camera.data.shift_y

        start_frame = scene.frame_start
        scene.frame_end = start_frame + len(sorted_camera_objects) - 1
        lens_values, shift_x_values, shift_y_values = [], [], []

        wm = context.window_manager
        total_cameras = len(sorted_camera_objects)
        if total_cameras > 0: wm.progress_begin(0, total_cameras)

        for offset, cam in enumerate(sorted_camera_objects):
            if total_cameras > 0: wm.progress_update(offset)
            frame = start_frame + offset
            scene.frame_set(frame)
            animated_camera.location = cam.location
            animated_camera.rotation_euler = cam.rotation_euler
            animated_camera.keyframe_insert(data_path="location", frame=frame)
            animated_camera.keyframe_insert(data_path="rotation_euler", frame=frame)
            animated_camera.data.lens = cam.data.lens
            animated_camera.data.shift_x = cam.data.shift_x
            animated_camera.data.shift_y = cam.data.shift_y
            animated_camera.data.keyframe_insert(data_path="lens", frame=frame)
            animated_camera.data.keyframe_insert(data_path="shift_x", frame=frame)
            animated_camera.data.keyframe_insert(data_path="shift_y", frame=frame)
            lens_values.append(cam.data.lens)
            shift_x_values.append(cam.data.shift_x)
            shift_y_values.append(cam.data.shift_y)

        if total_cameras > 0: wm.progress_end()

        def remove_constant_keyframes_from_obj(obj_data, data_path, values_list):
            if not obj_data.animation_data or not obj_data.animation_data.action: return
            if not values_list: return
            is_constant = True
            if len(values_list) > 1:
                first_val = values_list[0]
                for v in values_list[1:]:
                    if not isclose(v, first_val, abs_tol=1e-4): is_constant = False; break
            if is_constant:
                fcurve = obj_data.animation_data.action.fcurves.find(data_path)
                if fcurve: obj_data.animation_data.action.fcurves.remove(fcurve)

        if animated_camera.data:
            remove_constant_keyframes_from_obj(animated_camera.data, "lens", lens_values)
            remove_constant_keyframes_from_obj(animated_camera.data, "shift_x", shift_x_values)
            remove_constant_keyframes_from_obj(animated_camera.data, "shift_y", shift_y_values)

        if self.delete_original_cameras:
            deleted_cam_names = [cam.name for cam in sorted_camera_objects]
            bpy.data.batch_remove(sorted_camera_objects)
            self.report({'INFO'}, f"Original cameras deleted: {', '.join(deleted_cam_names)}")
        self.report({'INFO'}, f"Cameras merged into '{animated_camera.name}'.")
        return {'FINISHED'}

class SetBackgroundOperator(bpy.types.Operator):
    bl_idname = "camera.set_background"
    bl_label = "Set as Background"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene.movieclip_selected is not None

    def execute(self, context):
        scene = context.scene
        clip = scene.movieclip_selected
        active_camera = context.view_layer.objects.active
        if not active_camera or active_camera.type != 'CAMERA':
            found_camera = None
            custom_name_val = scene.merged_camera_name_custom
            derive_name_val = scene.merged_camera_name_use_derived
            potential_active_name = custom_name_val if not derive_name_val and custom_name_val.strip() else "MergedCamera"

            if potential_active_name in bpy.data.objects and bpy.data.objects[potential_active_name].type == 'CAMERA':
                found_camera = bpy.data.objects[potential_active_name]
            elif "MergedCamera" in bpy.data.objects and bpy.data.objects["MergedCamera"].type == 'CAMERA':
                found_camera = bpy.data.objects["MergedCamera"]
            else:
                for obj in bpy.data.objects:
                    if obj.type == 'CAMERA':
                        found_camera = obj; break
            
            if found_camera:
                active_camera = found_camera
                context.view_layer.objects.active = active_camera
                self.report({'INFO'}, f"No active camera; using '{active_camera.name}' for background.")
            else:
                self.report({'WARNING'}, "No camera found in the scene to set background for.")
                return {'CANCELLED'}

        if not active_camera.data:
            self.report({'WARNING'}, f"'{active_camera.name}' is not a valid camera.")
            return {'CANCELLED'}

        original_frame = scene.frame_current
        scene.frame_set(scene.frame_start)
        active_camera.data.show_background_images = True
        for bg_img_idx in range(len(active_camera.data.background_images) -1, -1, -1):
            active_camera.data.background_images.remove(active_camera.data.background_images[bg_img_idx])
        bg = active_camera.data.background_images.new()
        bg.source = 'MOVIE_CLIP'; bg.clip = clip; bg.alpha = 1.0
        clip.frame_start = scene.frame_start
        if clip.tracking and clip.tracking.camera:
            clip.tracking.camera.sensor_width = active_camera.data.sensor_width
            clip.tracking.camera.focal_length = active_camera.data.lens
        else:
             self.report({'WARNING'}, f"MovieClip '{clip.name}' has no tracking data.")
        scene.render.resolution_x = clip.size[0]; scene.render.resolution_y = clip.size[1]
        scene.render.pixel_aspect_x = 1.0; scene.render.pixel_aspect_y = 1.0
        scene.frame_set(original_frame)
        self.report({'INFO'}, f"Background set for '{active_camera.name}'.")
        return {'FINISHED'}

class MergeCamerasPanel(bpy.types.Panel):
    bl_label = "Merge Selected Cameras"
    bl_idname = "CAMERA_PT_merge_selected_cameras"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tracking'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        main_merge_box = layout.box()
        main_merge_box.label(text="1. Merge Sequential Cameras") # Label changed

        source_options_box = main_merge_box.box()
        source_options_box.label(text="Options:")
        source_options_box.prop(scene, "process_only_selected_cameras")
        source_options_box.prop(scene, "delete_original_cameras")

        naming_options_box = main_merge_box.box()
        naming_options_box.label(text="Camera Naming:")
        naming_options_box.prop(scene, "merged_camera_name_use_derived") # Label comes from property's 'name'

        row = naming_options_box.row(align=True)
        row.active = not scene.merged_camera_name_use_derived
        row.prop(scene, "merged_camera_name_custom", text="Name")

        op_merge = main_merge_box.operator(MergeSelectedCamerasOperator.bl_idname, icon='OUTLINER_OB_CAMERA')
        
        op_merge.delete_original_cameras = scene.delete_original_cameras
        op_merge.process_only_selected_cameras = scene.process_only_selected_cameras
        op_merge.camera_name_custom = scene.merged_camera_name_custom
        op_merge.camera_name_use_derived = scene.merged_camera_name_use_derived

        layout.separator()

        box_bg = layout.box()
        box_bg.label(text="2. Background Image Setup")
        box_bg.prop(scene, "movieclip_selected", text="")
        box_bg.operator(SetBackgroundOperator.bl_idname)

def register():
    bpy.utils.register_class(MergeSelectedCamerasOperator)
    bpy.utils.register_class(SetBackgroundOperator)
    bpy.utils.register_class(MergeCamerasPanel)

    bpy.types.Scene.delete_original_cameras = bpy.props.BoolProperty(
        name="Delete Original Cameras",
        description="Remove original cameras after merging",
        default=True,
    )
    bpy.types.Scene.process_only_selected_cameras = bpy.props.BoolProperty(
        name="Selected cameras only", 
        description="If checked, process only manually selected cameras. If unchecked, auto-detect cameras by name from the active camera",
        default=False,
    )
    bpy.types.Scene.movieclip_selected = bpy.props.PointerProperty(
        name="", 
        type=bpy.types.MovieClip,
        description="Select a Movie Clip to use as the camera background",
    )
    bpy.types.Scene.merged_camera_name_custom = bpy.props.StringProperty(
        name="Custom Name",
        description="Custom name for the merged camera if not using input sequence name", # Description updated
        default="MergedCamera",
    )
    bpy.types.Scene.merged_camera_name_use_derived = bpy.props.BoolProperty(
        name="Input sequence name", # Label changed
        description="If checked, the merged camera name will be derived from the input camera sequence's base name. Otherwise, the custom name below is used.", # Description updated
        default=False,
    )

def unregister():
    bpy.utils.unregister_class(MergeSelectedCamerasOperator)
    bpy.utils.unregister_class(SetBackgroundOperator)
    bpy.utils.unregister_class(MergeCamerasPanel)

    del bpy.types.Scene.delete_original_cameras
    del bpy.types.Scene.process_only_selected_cameras
    del bpy.types.Scene.movieclip_selected
    del bpy.types.Scene.merged_camera_name_custom
    del bpy.types.Scene.merged_camera_name_use_derived

if __name__ == "__main__":
    register()