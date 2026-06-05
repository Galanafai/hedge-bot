"""
geometry.py – camera math helpers for the pick-and-stack solution.

Convention (proven by diagnostic round-trip, max residual ≈ 46 mm):
  - depth[row_stored, col, 0] is the camera-frame perpendicular Z > 0.
  - Images are stored BOTTOM-UP (MuJoCo/OpenGL): row 0 = bottom.
    Before applying K, flip: row_eff = (IMAGE_H - 1) - row_stored.
  - R_ext is the 4x4 cam-to-world from get_camera_extrinsic_matrix,
    which applies the diag(1,-1,-1) OpenGL axis correction so the
    corrected camera frame is: +x right, +y up, +z forward (OpenCV).
  - Backproject: x_cc = (col - cx)/fx * Z, y_cc = (row_eff-cy)/fy * Z
                 p_world = R_ext @ [x_cc, y_cc, Z, 1]
  - Project:  p_cc = R_ext_inv @ [p_world; 1]
              u = fx*p_cc[0]/p_cc[2] + cx
              v_stored = (H-1) - (fy*p_cc[1]/p_cc[2] + cy)

No ground-truth reads. No imports from motion_planning.diagnostics.
"""
from __future__ import annotations

import numpy as np

IMAGE_H = 256
IMAGE_W = 256


def get_camera_matrices(sim) -> tuple[np.ndarray, np.ndarray]:
    """Return (K, R_ext) for the frontview camera.

    K     : 3×3 intrinsic matrix
    R_ext : 4×4 cam-to-world (corrected OpenCV frame)
    """
    from robosuite.utils.camera_utils import get_camera_extrinsic_matrix
    K     = sim.get_camera_intrinsics()                        # (3,3)
    R_ext = get_camera_extrinsic_matrix(sim.env.sim, "frontview")  # (4,4)
    return K, R_ext


def backproject_pixel_to_world(
    u: float,
    v_stored: float,
    Z: float,
    K: np.ndarray,
    R_ext: np.ndarray,
) -> np.ndarray:
    """Backproject pixel (col=u, row=v_stored) + depth Z → world (3,).

    Args:
        u        : column (0-indexed)
        v_stored : row as stored in the numpy array (0 = image bottom in world)
        Z        : camera-frame perpendicular depth from get_real_depth_map
        K        : 3×3 intrinsic
        R_ext    : 4×4 cam-to-world (from get_camera_extrinsic_matrix)
    """
    v_optical = float((IMAGE_H - 1) - v_stored)
    x_cc = (u - K[0, 2]) / K[0, 0] * Z
    y_cc = (v_optical - K[1, 2]) / K[1, 1] * Z
    return (R_ext @ np.array([x_cc, y_cc, Z, 1.0]))[:3]


def project_world_to_pixel(
    p_world: np.ndarray,
    K: np.ndarray,
    R_ext: np.ndarray,
) -> tuple[tuple[float, float], float]:
    """Project world point → ((u, v_stored), Z_perp).

    Returns NaN u/v if the point is behind the camera.
    """
    R_inv  = np.linalg.inv(R_ext)
    p_cc4  = R_inv @ np.append(p_world, 1.0)
    p_cc   = p_cc4[:3]
    Z_perp = float(p_cc[2])
    if Z_perp <= 0:
        return (float("nan"), float("nan")), Z_perp
    u         = float(K[0, 0] * p_cc[0] / Z_perp + K[0, 2])
    v_optical = float(K[1, 1] * p_cc[1] / Z_perp + K[1, 2])
    v_stored  = float((IMAGE_H - 1) - v_optical)
    return (u, v_stored), Z_perp


def backproject_depth_image(
    depth: np.ndarray,
    K: np.ndarray,
    R_ext: np.ndarray,
) -> np.ndarray:
    """Vectorised backprojection of the full depth image.

    Args:
        depth : (H, W, 1) or (H, W) float32 in metres
        K     : (3, 3)
        R_ext : (4, 4)

    Returns:
        world_pts : (H, W, 3) float32 – world coordinate for every pixel
    """
    d = depth[..., 0] if depth.ndim == 3 else depth   # (H, W)
    H, W = d.shape
    rows = np.arange(H, dtype=np.float32)
    cols = np.arange(W, dtype=np.float32)
    cc, rr = np.meshgrid(cols, rows)                   # (H, W) each
    # undo bottom-up storage
    rr_eff = float(H - 1) - rr
    Z = d
    x_cc = (cc - K[0, 2]) / K[0, 0] * Z
    y_cc = (rr_eff - K[1, 2]) / K[1, 1] * Z
    ones = np.ones_like(Z)
    # shape (4, H*W)
    cam_pts = np.stack([x_cc.ravel(), y_cc.ravel(), Z.ravel(), ones.ravel()], axis=0)
    world_pts = (R_ext @ cam_pts)[:3].T.reshape(H, W, 3)
    return world_pts.astype(np.float32)


def top_down_quat(yaw: float = 0.0) -> np.ndarray:
    """Return quaternion for a top-down grasp (gripper z pointing down) with given yaw.

    Yaw is rotation about the world Z axis (0 = fingers along world-X axis).
    Returns (x, y, z, w) quaternion (robosuite convention).
    """
    # Base orientation: gripper pointing down = rotate 180° about world X
    # Then apply yaw about world Z.
    # Rotation: first Rx(pi) then Rz(yaw)
    # Rx(pi): (x,y,z,w) = (1,0,0,0) in axis-angle * sin/cos
    half_pi = np.pi / 2.0
    # q_rx_pi = (sin(pi/2), 0, 0, cos(pi/2)) = (1, 0, 0, 0)
    # but in robosuite (xyzw) the 180° rotation about x is:
    qx = np.array([1.0, 0.0, 0.0, 0.0])  # (x,y,z,w) = (sin90, 0,0, cos90) NO
    # Let's be explicit: q for angle theta about axis n: (n*sin(theta/2), cos(theta/2))
    # 180° about X: (sin90, 0, 0, cos90) = (1, 0, 0, 0)  in (x,y,z,w)
    qx = np.array([1.0, 0.0, 0.0, 0.0])
    # yaw about Z: (0, 0, sin(yaw/2), cos(yaw/2))
    qz = np.array([0.0, 0.0, np.sin(yaw / 2.0), np.cos(yaw / 2.0)])
    # Compose: q_total = qz * qx (apply Rx first, then Rz)
    return _quat_mul(qz, qx)


def _quat_mul(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    """Multiply two quaternions (xyzw convention)."""
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return np.array([
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
        w1*w2 - x1*x2 - y1*y2 - z1*z2,
    ])


def closing_axis_from_yaw(yaw: float) -> tuple[np.ndarray, np.ndarray]:
    """Return (closing_axis, finger_axis) in world XY for the given grasp yaw.

    closing_axis: unit vector along which fingers approach each other
    finger_axis:  unit vector along which each finger extends (perpendicular)
    """
    ca = np.array([np.cos(yaw), np.sin(yaw), 0.0])
    fa = np.array([-np.sin(yaw), np.cos(yaw), 0.0])
    return ca, fa
