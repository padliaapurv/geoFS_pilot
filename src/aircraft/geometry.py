# Rotation-matrix (DCM) attitude utilities. Attitude is always represented
# and propagated as a 3x3 direction cosine matrix, never as Euler angles.
# Euler angles only ever appear in `euler_from_dcm`, which exists purely for
# human-readable logging/plotting and is never fed back into the dynamics.

import numpy as np


def skew(v: np.ndarray) -> np.ndarray:
    # Cross-product matrix such that skew(v) @ u == v x u.
    return np.array([
        [0.0, -v[2], v[1]],
        [v[2], 0.0, -v[0]],
        [-v[1], v[0], 0.0],
    ])


def rotation_matrix_body_to_ned_from_heading(heading_rad: float) -> np.ndarray:
    # Builds an initial wings-level, zero-pitch DCM pointed at `heading_rad`
    # (measured clockwise from north). Used only for setting initial
    # conditions before trim adjusts pitch.
    c, s = np.cos(heading_rad), np.sin(heading_rad)
    return np.array([
        [c, -s, 0.0],
        [s, c, 0.0],
        [0.0, 0.0, 1.0],
    ])


def rotation_matrix_about_axis(axis: np.ndarray, angle_rad: float) -> np.ndarray:
    # Rodrigues' rotation formula: exact matrix exponential of skew(axis*angle).
    axis_norm = np.linalg.norm(axis)
    if axis_norm < 1e-12:
        return np.eye(3)
    a = axis / axis_norm
    K = skew(a)
    return np.eye(3) + np.sin(angle_rad) * K + (1.0 - np.cos(angle_rad)) * (K @ K)


def integrate_dcm(C: np.ndarray, omega_body: np.ndarray, dt: float) -> np.ndarray:
    # Exact exponential-map update for a body rotating at constant angular
    # rate omega_body over dt: C_new = C @ expm(skew(omega_body) * dt).
    # This is the rotation-matrix analogue of Euler-angle integration and
    # stays exactly orthonormal (up to the axis/angle trig, not linearization).
    angle = np.linalg.norm(omega_body) * dt
    delta_rotation = rotation_matrix_about_axis(omega_body, angle)
    C_new = C @ delta_rotation
    return orthonormalize(C_new)


def orthonormalize(C: np.ndarray) -> np.ndarray:
    # Gram-Schmidt-free re-orthonormalization via SVD, guards against drift
    # from repeated floating point integration.
    U, _, Vt = np.linalg.svd(C)
    return U @ Vt


def euler_from_dcm(C: np.ndarray) -> tuple:
    # Standard ZYX (yaw, pitch, roll) extraction, used only as a derived
    # scalar measurement for logs/plots and for autopilot loop feedback
    # (e.g. bank-angle hold). Never used as a state variable or integrated;
    # all kinematic propagation stays on the DCM via integrate_dcm above.
    pitch = -np.arcsin(np.clip(C[2, 0], -1.0, 1.0))
    roll = np.arctan2(C[2, 1], C[2, 2])
    yaw = np.arctan2(C[1, 0], C[0, 0])
    return yaw, pitch, roll


def heading_vector_ned(C: np.ndarray) -> np.ndarray:
    # Horizontal (north, east) projection of the body x-axis expressed in
    # NED, i.e. the aircraft's ground track direction if there were no wind.
    body_x_ned = C @ np.array([1.0, 0.0, 0.0])
    horizontal = body_x_ned[:2]
    norm = np.linalg.norm(horizontal)
    if norm < 1e-9:
        return np.array([1.0, 0.0])
    return horizontal / norm


def signed_heading_error_rad(current_heading_vec: np.ndarray, desired_heading_vec: np.ndarray) -> float:
    # Signed angle from current to desired 2D heading vectors via atan2 of
    # the cross/dot product. This is a scalar controller error, not a state
    # variable, so it does not reintroduce Euler-angle kinematics.
    cross = current_heading_vec[0] * desired_heading_vec[1] - current_heading_vec[1] * desired_heading_vec[0]
    dot = np.dot(current_heading_vec, desired_heading_vec)
    return np.arctan2(cross, dot)
