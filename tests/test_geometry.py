import numpy as np
from src.aircraft.geometry import (
    skew, integrate_dcm, orthonormalize, euler_from_dcm,
    rotation_matrix_body_to_ned_from_heading, heading_vector_ned, signed_heading_error_rad,
)


def test_skew_cross_product_equivalence():
    v = np.array([1.0, 2.0, 3.0])
    u = np.array([4.0, -1.0, 2.0])
    assert np.allclose(skew(v) @ u, np.cross(v, u))


def test_integrate_dcm_stays_orthonormal():
    C = np.eye(3)
    omega = np.array([0.1, -0.2, 0.05])
    for _ in range(500):
        C = integrate_dcm(C, omega, 0.01)
    assert np.allclose(C @ C.T, np.eye(3), atol=1e-8)
    assert np.isclose(np.linalg.det(C), 1.0, atol=1e-8)


def test_integrate_dcm_matches_known_rotation():
    # Pure yaw rate for a known duration should match an exact heading DCM.
    omega = np.array([0.0, 0.0, np.pi / 2.0])  # rad/s about down-axis
    C = integrate_dcm(np.eye(3), omega, 1.0)  # 1s -> 90 deg yaw
    expected = rotation_matrix_body_to_ned_from_heading(np.pi / 2.0)
    assert np.allclose(C, expected, atol=1e-6)


def test_euler_roundtrip_small_angles():
    heading = rotation_matrix_body_to_ned_from_heading(np.radians(30.0))
    yaw, pitch, roll = euler_from_dcm(heading)
    assert np.isclose(np.degrees(yaw), 30.0, atol=1e-6)
    assert np.isclose(pitch, 0.0, atol=1e-9)
    assert np.isclose(roll, 0.0, atol=1e-9)


def test_heading_vector_and_signed_error():
    C = rotation_matrix_body_to_ned_from_heading(0.0)  # pointing north
    current = heading_vector_ned(C)
    desired = np.array([0.0, 1.0])  # east
    error = signed_heading_error_rad(current, desired)
    assert np.isclose(error, np.pi / 2.0, atol=1e-6)
