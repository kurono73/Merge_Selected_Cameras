# Blender Addon: Merge selected cameras

## Overview
This Blender addon converts individual cameras exported from photogrammetry software (such as RealityScan) into a single animated camera. It allows you to use photogrammetry software as a camera tracking tool within Blender.

---

## Features
- Merges sequential cameras into one continuous animated camera.
- Supports variable focal length and sensor shift animations.
- Can process multiple cuts or additional photogrammetry sequences captured at the same location.
- Automatically sets background images based on Blender Movie Clips.

---

## Location
 `3D View > Sidebar > Tracking Tab> Merge selected cameras`

---

## How to Use

### 0. Export from RealityScan
- Export the scene as **Alembic (.abc)** or **FBX (.fbx)** with **camera export enabled**.
- Texture and image export are optional.
- Ensure that the sequence is in order, as the addon assumes a sequential camera setup.

### 1. Merge Sequential Cameras
In Blender, navigate to the addon panel:

- Click **Merge Cameras** to automatically combine the selected camera’s sequence into one animated camera.
- Only one camera selection is required to execute.

#### Options:
- **Selected Cameras Only**  
    Merge only the selected cameras. Useful for manual control or when sequence recognition fails.  
    *Default: OFF*

- **Delete Original Cameras**  
    Automatically deletes source cameras after merging.  
    *Default: ON*

- **Camera Naming**  
    Choose whether to use a custom name or inherit the sequence name.

---

### 2. Background Image Setup
- Use **Set as Background** to assign a Movie Clip to the created camera.
- Features:
    - Render resolution is automatically adjusted to match the Movie Clip.
    - Camera start frame is synced with the Movie Clip’s start frame.
    - Sensor size and focal length are applied based on the Movie Clip’s metadata (zoom lenses use the start frame value).

---

## Technical Notes
- The animation starts from the **current timeline frame** when the process is executed.  
- The end frame is automatically determined based on the sequence length.
- Missing frames in the sequence are not skipped; the cameras will connect sequentially regardless.
- Fully supports:
    - Focal length animations
    - Sensor shift animations  
    (Keyframes are only inserted when these properties change.)

---

## Recommended Settings for RealityScan
- Select all images and use **Prior calibration** to fix the camera group.
- Specify focal length using the **35mm equivalent standard** (=sensor width: 36mm).
- Apply lens distortion correction in advance and set Prior Lens Distortion **Fixed**.
    - Brown model distortion coefficients can be used in Blender.
    - Distortion parameters are not easily transferable to Nuke or other VFX software.
- When exporting:
    - Use Alembic or FBX.
    - Enable **Camera Export**.
    - Undistorted images and texture export can be disabled if not needed.
- For faster processing:
    - The preview mesh is sufficient to use as a guide.
    - Mesh and texture processing can be accelerated by using only key frames (e.g., every 5 or 10 frames) for mesh and texture processing.
    - Disable Undistort images, Export images, etc. in export if you do not need them.



---
