# Trim solver: finds the steady, wings-level, zero-sideslip, unaccelerated
# cruise condition at a given altitude and target CL. Main elevator is held
# at zero (reserved for maneuvering) and the elevator trim tab is solved
# jointly with angle of attack to satisfy lift and pitching-moment balance,
# then throttle is solved to balance thrust against drag.

from dataclasses import dataclass
import numpy as np
from src.atmosphere.isa import isa_atmosphere
from src.aircraft.geometry import rotation_matrix_body_to_ned_from_heading, rotation_matrix_about_axis
from src.aircraft.state import AircraftState, ControlSurfaceState


@dataclass
class TrimResult:
    airspeed_m_s: float
    alpha_rad: float
    elevator_trim_rad: float
    throttle_fraction: float
    cl: float
    cd: float


def solve_trim(aero_model, engine_model, mass_kg: float, gravity_m_s2: float, altitude_m: float, target_cl: float) -> TrimResult:
    atmosphere = isa_atmosphere(altitude_m)
    weight_n = mass_kg * gravity_m_s2

    airspeed_m_s = np.sqrt(2.0 * weight_n / (atmosphere.density_kg_m3 * aero_model.wing_area_m2 * target_cl))
    dynamic_pressure_pa = 0.5 * atmosphere.density_kg_m3 * airspeed_m_s ** 2

    lift_cfg = aero_model.cfg["lift"]
    pitch_cfg = aero_model.cfg["pitch_moment"]

    # Linear 2x2 system for [alpha, elevator_trim]:
    #   CL_alpha * alpha + CL_elevator_trim * trim = target_cl - CL0
    #   Cm_alpha * alpha + Cm_elevator_trim * trim = -Cm0
    coefficient_matrix = np.array([
        [lift_cfg["CL_alpha"], lift_cfg["CL_elevator_trim"]],
        [pitch_cfg["Cm_alpha"], pitch_cfg["Cm_elevator_trim"]],
    ])
    rhs = np.array([target_cl - lift_cfg["CL0"], -pitch_cfg["Cm0"]])
    alpha_rad, elevator_trim_rad = np.linalg.solve(coefficient_matrix, rhs)

    drag_cfg = aero_model.cfg["drag"]
    aspect_ratio = aero_model.wing_span_m ** 2 / aero_model.wing_area_m2
    induced_drag_k = 1.0 / (np.pi * drag_cfg["oswald_efficiency"] * aspect_ratio)
    cd = drag_cfg["CD0"] + induced_drag_k * target_cl ** 2
    drag_n = dynamic_pressure_pa * aero_model.wing_area_m2 * cd

    mach = airspeed_m_s / atmosphere.speed_of_sound_m_s
    density_ratio_sigma = atmosphere.density_kg_m3 / 1.225
    max_thrust_n = engine_model.compute_thrust_body_n(1.0, density_ratio_sigma, mach)[0]
    throttle_fraction = float(np.clip(drag_n / max_thrust_n, 0.0, 1.0))

    return TrimResult(
        airspeed_m_s=airspeed_m_s,
        alpha_rad=alpha_rad,
        elevator_trim_rad=elevator_trim_rad,
        throttle_fraction=throttle_fraction,
        cl=target_cl,
        cd=cd,
    )


def build_trimmed_state(
    trim_result: TrimResult,
    position_ned_m: np.ndarray,
    heading_rad: float,
) -> AircraftState:
    # Zero flight-path-angle cruise: pitch attitude equals angle of attack,
    # so the NED-frame velocity vector is purely horizontal.
    velocity_body = np.array([
        trim_result.airspeed_m_s * np.cos(trim_result.alpha_rad),
        0.0,
        trim_result.airspeed_m_s * np.sin(trim_result.alpha_rad),
    ])

    heading_dcm = rotation_matrix_body_to_ned_from_heading(heading_rad)
    # Pitch nose up by alpha about the (heading-rotated) body y-axis, so that
    # velocity_ned = attitude_dcm @ velocity_body comes out purely horizontal.
    body_y_ned = heading_dcm @ np.array([0.0, 1.0, 0.0])
    pitch_dcm = rotation_matrix_about_axis(body_y_ned, trim_result.alpha_rad)
    attitude_dcm = pitch_dcm @ heading_dcm

    controls = ControlSurfaceState(
        aileron_rad=0.0,
        elevator_rad=0.0,
        rudder_rad=0.0,
        elevator_trim_rad=trim_result.elevator_trim_rad,
        throttle_fraction=trim_result.throttle_fraction,
    )

    return AircraftState(
        t_s=0.0,
        position_ned_m=np.asarray(position_ned_m, dtype=float),
        velocity_body_m_s=velocity_body,
        attitude_dcm=attitude_dcm,
        angular_rate_body_rad_s=np.zeros(3),
        controls=controls,
    )
