# Merge Selected Cameras

import bpy
import re
from math import isclose

def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    """Provides a key for natural sorting of strings (e.g., 'item1', 'item2', 'item10')."""
    return [int(text) if text.isdigit() else text.lower() for text in _nsre.split(s)]

class MergeCamerasSettings(bpy.types.PropertyGroup):
    """Stores all the settings for the Merge Cameras addon."""
    delete_original_cameras: bpy.props.BoolProperty(
        name="Delete Original Cameras",
        description="Remove original cameras after merging",
        default=True,
    )
    process_only_selected_cameras: bpy.props.BoolProperty(
        name="Selected cameras only",
        description="If checked, process only manually selected cameras. If unchecked, auto-detect cameras by name from the active camera",
        default=False,
    )
    camera_name_custom: bpy.props.StringProperty(
        name="Custom Camera Name",
        description="Custom name for the merged camera if not using input sequence name",
        default="MergedCamera",
    )
    camera_name_use_derived: bpy.props.BoolProperty(
        name="Input sequence name",
        description="If checked, the merged camera name will be derived from the input camera sequence's base name. Otherwise, the custom name below is used.",
        default=False,
    )
    movieclip_selected: bpy.props.PointerProperty(
        name="",
        type=bpy.types.MovieClip,
        description="Select a Movie Clip to use as the camera background",
    )

class MergeSelectedCamerasOperator(bpy.types.Operator):
    """
    Merges multiple cameras into a single animated camera.
    It can process either selected cameras or auto-detect a sequence from the active camera's name.
    Keyframes are created for location, rotation, and optionally for lens and shift properties.
    """
    bl_idname = "camera.merge_selected_cameras"
    bl_label = "Merge Cameras"
    bl_options = {'REGISTER', 'UNDO'}

    def _determine_final_camera_name(self, settings, sorted_cameras, auto_detect_match):
        """
        Determines the name for the merged camera based on operator properties.

        Args:
            settings (MergeCamerasSettings): The addon settings.
            sorted_cameras (list): The list of camera objects to be merged.
            auto_detect_match (re.Match or None): The regex match object from auto-detection.

        Returns:
            str: The final name for the new camera.
        """
        if settings.camera_name_use_derived:
            base_name = ""
            if settings.process_only_selected_cameras:
                if sorted_cameras:
                    match = re.match(r'(.*?)(\d+)(\.\w+)?$', sorted_cameras[0].name)
                    if match:
                        base_name = match.group(1)
            elif auto_detect_match:
                base_name = auto_detect_match.group(1)

            # Use regex to remove trailing separators for a cleaner name
            cleaned_name = re.sub(r'[ _.-]+$', '', base_name)
            if not cleaned_name.strip():
                self.report({'WARNING'}, "Could not derive a base name. Using default 'MergedCamera'.")
                return "MergedCamera"
            return cleaned_name
        else:
            if not settings.camera_name_custom.strip():
                self.report({'WARNING'}, "Custom name is blank. Using default 'MergedCamera'.")
                return "MergedCamera"
            return settings.camera_name_custom

    @classmethod
    def poll(cls, context):
        """Checks if the operator can run."""
        settings = context.scene.merge_camera_settings
        if settings.process_only_selected_cameras:
            return any(obj.type == 'CAMERA' for obj in context.selected_objects)
        else:
            active_obj = context.view_layer.objects.active
            return active_obj is not None and active_obj.type == 'CAMERA'

    def execute(self, context):
        """Executes the camera merging process."""
        scene = context.scene
        settings = scene.merge_camera_settings
        base_name_match_for_auto_detect = None

        if settings.process_only_selected_cameras:
            selected_objects = context.selected_objects
            camera_objects = [obj for obj in selected_objects if obj.type == 'CAMERA']
        else:
            active_camera_obj = context.view_layer.objects.active
            if not active_camera_obj or active_camera_obj.type != 'CAMERA':
                self.report({'WARNING'}, "No active camera found for auto-detection.")
                return {'CANCELLED'}
            base_name_match_for_auto_detect = re.match(r'(.*?)(\d+)(\.\w+)?$', active_camera_obj.name)
            if not base_name_match_for_auto_detect:
                self.report({'WARNING'}, "Active camera name does not match expected pattern for auto-detection (e.g., 'cam1').")
                return {'CANCELLED'}
            base_name_for_glob = base_name_match_for_auto_detect.group(1)
            # Iterate over the current scene's objects instead of all objects
            camera_objects = [
                obj for obj in context.scene.objects
                if obj.type == 'CAMERA' and re.match(fr'{re.escape(base_name_for_glob)}\d+(\.\w+)?$', obj.name)
            ]

        if not camera_objects:
            self.report({'WARNING'}, "No cameras found to merge based on current settings.")
            return {'CANCELLED'}

        sorted_camera_objects = sorted(camera_objects, key=lambda cam: natural_sort_key(cam.name))

        final_camera_name = self._determine_final_camera_name(settings, sorted_camera_objects, base_name_match_for_auto_detect)

        bpy.ops.object.camera_add(location=(0, 0, 0))
        animated_camera = context.object
        animated_camera.name = final_camera_name
        # Add a custom property to easily identify the merged camera later
        animated_camera["is_merged_camera"] = True

        first_camera = sorted_camera_objects[0]
        animated_camera.data.sensor_width = first_camera.data.sensor_width
        animated_camera.data.sensor_height = first_camera.data.sensor_height

        start_frame = scene.frame_start
        scene.frame_end = start_frame + len(sorted_camera_objects) - 1

        frames, lens_values, shift_x_values, shift_y_values = [], [], [], []

        wm = context.window_manager
        total_cameras = len(sorted_camera_objects)
        if total_cameras > 0:
            wm.progress_begin(0, total_cameras)

        for offset, cam in enumerate(sorted_camera_objects):
            if total_cameras > 0:
                wm.progress_update(offset)
            frame = start_frame + offset

            animated_camera.location = cam.location
            animated_camera.rotation_euler = cam.rotation_euler
            animated_camera.keyframe_insert(data_path="location", frame=frame)
            animated_camera.keyframe_insert(data_path="rotation_euler", frame=frame)

            frames.append(frame)
            lens_values.append(cam.data.lens)
            shift_x_values.append(cam.data.shift_x)
            shift_y_values.append(cam.data.shift_y)

        if total_cameras > 0:
            wm.progress_end()

        def clear_camera_data_keyframes(camera):
            if camera and camera.data and camera.data.animation_data:
                camera.data.animation_data_clear()

        def rebuild_keyframes_if_needed(camera, frames_list, lens_vals, shift_x_vals, shift_y_vals):
            if not all([camera, camera.data, frames_list, lens_vals, shift_x_vals, shift_y_vals]):
                return

            clear_camera_data_keyframes(camera)

            if len(lens_vals) > 1 and not all(isclose(v, lens_vals[0], abs_tol=1e-4) for v in lens_vals):
                for frame, value in zip(frames_list, lens_vals):
                    camera.data.lens = value
                    camera.data.keyframe_insert(data_path="lens", frame=frame)
            else:
                camera.data.lens = lens_vals[0] if lens_vals else 50.0

            if len(shift_x_vals) > 1 and not all(isclose(v, shift_x_vals[0], abs_tol=1e-4) for v in shift_x_vals):
                for frame, value in zip(frames_list, shift_x_vals):
                    camera.data.shift_x = value
                    camera.data.keyframe_insert(data_path="shift_x", frame=frame)
            else:
                camera.data.shift_x = shift_x_vals[0] if shift_x_vals else 0.0

            if len(shift_y_vals) > 1 and not all(isclose(v, shift_y_vals[0], abs_tol=1e-4) for v in shift_y_vals):
                for frame, value in zip(frames_list, shift_y_vals):
                    camera.data.shift_y = value
                    camera.data.keyframe_insert(data_path="shift_y", frame=frame)
            else:
                camera.data.shift_y = shift_y_vals[0] if shift_y_vals else 0.0

        rebuild_keyframes_if_needed(animated_camera, frames, lens_values, shift_x_values, shift_y_values)

        if settings.delete_original_cameras:
            bpy.data.batch_remove(sorted_camera_objects)

        self.report({'INFO'}, f"Cameras merged into '{animated_camera.name}'.")
        return {'FINISHED'}

class SetBackgroundOperator(bpy.types.Operator):
    """
    Sets a selected Movie Clip as the background for the active (or found) camera.
    It clears existing backgrounds, sets the new clip, and adjusts render resolution to match.
    """
    bl_idname = "camera.set_background"
    bl_label = "Set as Background"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Checks if a movie clip is selected in the panel."""
        return context.scene.merge_camera_settings.movieclip_selected is not None

    def execute(self, context):
        """Executes the background setting process."""
        scene = context.scene
        settings = scene.merge_camera_settings
        clip = settings.movieclip_selected
        active_camera = context.view_layer.objects.active

        if not active_camera or active_camera.type != 'CAMERA':
            found_camera = None
            # First, try to find the camera created by this addon using its custom property
            for obj in context.scene.objects:
                if obj.type == 'CAMERA' and obj.get("is_merged_camera"):
                    found_camera = obj
                    break
            
            # If not found, fall back to finding any camera in the scene
            if not found_camera:
                for obj in context.scene.objects:
                    if obj.type == 'CAMERA':
                        found_camera = obj
                        break

            if found_camera:
                active_camera = found_camera
                context.view_layer.objects.active = active_camera
                self.report({'INFO'}, f"No active camera; using '{active_camera.name}' for background.")
            else:
                self.report({'WARNING'}, "No camera found in the scene to set background for.")
                return {'CANCELLED'}

        if not active_camera.data:
            self.report({'WARNING'}, f"'{active_camera.name}' is not a valid camera object.")
            return {'CANCELLED'}

        original_frame = scene.frame_current
        scene.frame_set(scene.frame_start)

        active_camera.data.show_background_images = True
        for bg_img in list(active_camera.data.background_images):
            active_camera.data.background_images.remove(bg_img)
        bg = active_camera.data.background_images.new()
        bg.source = 'MOVIE_CLIP'
        bg.clip = clip
        bg.alpha = 1.0
        clip.frame_start = scene.frame_start

        if clip.tracking and clip.tracking.camera:
            clip.tracking.camera.sensor_width = active_camera.data.sensor_width
            clip.tracking.camera.focal_length = active_camera.data.lens
        else:
            self.report({'WARNING'}, f"MovieClip '{clip.name}' has no tracking data to sync.")

        scene.render.resolution_x = clip.size[0]
        scene.render.resolution_y = clip.size[1]
        scene.render.pixel_aspect_x = 1.0
        scene.render.pixel_aspect_y = 1.0
        scene.frame_set(original_frame)

        self.report({'INFO'}, f"Background set for '{active_camera.name}'.")
        return {'FINISHED'}

class MergeCamerasPanel(bpy.types.Panel):
    """The UI panel for the Merge Selected Cameras addon, located in the 3D View's 'Tracking' tab."""
    bl_label = "Merge Selected Cameras"
    bl_idname = "CAMERA_PT_merge_selected_cameras"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tracking'

    def draw(self, context):
        """Draws the UI panel."""
        layout = self.layout
        # Get settings from the PropertyGroup
        settings = context.scene.merge_camera_settings

        main_merge_box = layout.box()
        main_merge_box.label(text="1. Merge Sequential Cameras")

        source_options_box = main_merge_box.box()
        source_options_box.label(text="Options:")
        source_options_box.prop(settings, "process_only_selected_cameras")
        source_options_box.prop(settings, "delete_original_cameras")

        naming_options_box = main_merge_box.box()
        naming_options_box.label(text="Camera Naming:")
        naming_options_box.prop(settings, "camera_name_use_derived")
        row = naming_options_box.row(align=True)
        row.active = not settings.camera_name_use_derived
        row.prop(settings, "camera_name_custom", text="Name")

        # The operator automatically gets its properties from the context,
        # so we don't need to pass them manually anymore.
        # The operator will read the settings from the PropertyGroup itself.
        main_merge_box.operator(MergeSelectedCamerasOperator.bl_idname, icon='OUTLINER_OB_CAMERA')

        layout.separator()

        box_bg = layout.box()
        box_bg.label(text="2. Background Image Setup")
        box_bg.prop(settings, "movieclip_selected", text="")
        box_bg.operator(SetBackgroundOperator.bl_idname)

def register():
    """Registers all addon classes and properties."""
    bpy.utils.register_class(MergeCamerasSettings)
    bpy.utils.register_class(MergeSelectedCamerasOperator)
    bpy.utils.register_class(SetBackgroundOperator)
    bpy.utils.register_class(MergeCamerasPanel)
    
    # Add the PropertyGroup to the Scene type
    bpy.types.Scene.merge_camera_settings = bpy.props.PointerProperty(type=MergeCamerasSettings)

def unregister():
    """Unregisters all addon classes and properties."""
    # Important to unregister in reverse order
    del bpy.types.Scene.merge_camera_settings
    
    bpy.utils.unregister_class(MergeCamerasPanel)
    bpy.utils.unregister_class(SetBackgroundOperator)
    bpy.utils.unregister_class(MergeSelectedCamerasOperator)
    bpy.utils.unregister_class(MergeCamerasSettings)

if __name__ == "__main__":
    register()