# 6-DOF rigid body equations of motion, RK4 integration. Attitude kinematics
# use the rotation-matrix exponential map (see geometry.integrate_dcm), never
# Euler-angle rates, so there is no gimbal-lock singularity.

from dataclasses import dataclass
import numpy as np
from src.aircraft.geometry import skew, integrate_dcm
from src.aircraft.state import AircraftState


@dataclass(frozen=True)
class InertiaProperties:
    mass_kg: float
    inertia_body_kg_m2: np.ndarray      # 3x3
    inertia_body_inv_kg_m2: np.ndarray  # 3x3, precomputed inverse


def build_inertia_properties(mass_kg: float, inertia_cfg: dict) -> InertiaProperties:
    ixx, iyy, izz, ixz = inertia_cfg["Ixx"], inertia_cfg["Iyy"], inertia_cfg["Izz"], inertia_cfg["Ixz"]
    inertia = np.array([
        [ixx, 0.0, -ixz],
        [0.0, iyy, 0.0],
        [-ixz, 0.0, izz],
    ])
    return InertiaProperties(mass_kg=mass_kg, inertia_body_kg_m2=inertia, inertia_body_inv_kg_m2=np.linalg.inv(inertia))


@dataclass
class StateDerivative:
    d_position_ned_m_s: np.ndarray
    d_velocity_body_m_s2: np.ndarray
    angular_rate_body_rad_s: np.ndarray  # carried through for the DCM integrator
    d_angular_rate_body_rad_s2: np.ndarray


def compute_derivatives(
    position_ned_m: np.ndarray,
    velocity_body_m_s: np.ndarray,
    attitude_dcm: np.ndarray,
    angular_rate_body_rad_s: np.ndarray,
    force_body_n: np.ndarray,
    moment_body_n_m: np.ndarray,
    inertia: InertiaProperties,
) -> StateDerivative:
    d_position_ned = attitude_dcm @ velocity_body_m_s
    d_velocity_body = force_body_n / inertia.mass_kg - np.cross(angular_rate_body_rad_s, velocity_body_m_s)
    angular_momentum = inertia.inertia_body_kg_m2 @ angular_rate_body_rad_s
    d_angular_rate = inertia.inertia_body_inv_kg_m2 @ (
        moment_body_n_m - np.cross(angular_rate_body_rad_s, angular_momentum)
    )
    return StateDerivative(
        d_position_ned_m_s=d_position_ned,
        d_velocity_body_m_s2=d_velocity_body,
        angular_rate_body_rad_s=angular_rate_body_rad_s,
        d_angular_rate_body_rad_s2=d_angular_rate,
    )


def rk4_step(
    state: AircraftState,
    inertia: InertiaProperties,
    dt: float,
    forces_moments_fn,
) -> AircraftState:
    # forces_moments_fn(position, velocity_body, attitude_dcm, angular_rate, t) -> (force_body, moment_body)
    def eval_derivative(position, velocity_body, attitude_dcm, angular_rate, t):
        force_body, moment_body = forces_moments_fn(position, velocity_body, attitude_dcm, angular_rate, t)
        return compute_derivatives(position, velocity_body, attitude_dcm, angular_rate, force_body, moment_body, inertia)

    p0, v0, c0, w0, t0 = (
        state.position_ned_m, state.velocity_body_m_s, state.attitude_dcm, state.angular_rate_body_rad_s, state.t_s
    )

    k1 = eval_derivative(p0, v0, c0, w0, t0)
    p1 = p0 + 0.5 * dt * k1.d_position_ned_m_s
    v1 = v0 + 0.5 * dt * k1.d_velocity_body_m_s2
    c1 = integrate_dcm(c0, w0, 0.5 * dt)
    w1 = w0 + 0.5 * dt * k1.d_angular_rate_body_rad_s2

    k2 = eval_derivative(p1, v1, c1, w1, t0 + 0.5 * dt)
    p2 = p0 + 0.5 * dt * k2.d_position_ned_m_s
    v2 = v0 + 0.5 * dt * k2.d_velocity_body_m_s2
    c2 = integrate_dcm(c0, w1, 0.5 * dt)
    w2 = w0 + 0.5 * dt * k2.d_angular_rate_body_rad_s2

    k3 = eval_derivative(p2, v2, c2, w2, t0 + 0.5 * dt)
    p3 = p0 + dt * k3.d_position_ned_m_s
    v3 = v0 + dt * k3.d_velocity_body_m_s2
    c3 = integrate_dcm(c0, w2, dt)
    w3 = w0 + dt * k3.d_angular_rate_body_rad_s2

    k4 = eval_derivative(p3, v3, c3, w3, t0 + dt)

    new_position = p0 + (dt / 6.0) * (
        k1.d_position_ned_m_s + 2 * k2.d_position_ned_m_s + 2 * k3.d_position_ned_m_s + k4.d_position_ned_m_s
    )
    new_velocity = v0 + (dt / 6.0) * (
        k1.d_velocity_body_m_s2 + 2 * k2.d_velocity_body_m_s2 + 2 * k3.d_velocity_body_m_s2 + k4.d_velocity_body_m_s2
    )
    new_angular_rate = w0 + (dt / 6.0) * (
        k1.d_angular_rate_body_rad_s2 + 2 * k2.d_angular_rate_body_rad_s2
        + 2 * k3.d_angular_rate_body_rad_s2 + k4.d_angular_rate_body_rad_s2
    )
    # Average angular rate over the step for the attitude exponential-map update.
    avg_omega = (w0 + 2 * w1 + 2 * w2 + w3) / 6.0
    new_attitude = integrate_dcm(c0, avg_omega, dt)

    new_state = state.copy()
    new_state.t_s = t0 + dt
    new_state.position_ned_m = new_position
    new_state.velocity_body_m_s = new_velocity
    new_state.attitude_dcm = new_attitude
    new_state.angular_rate_body_rad_s = new_angular_rate
    return new_state
