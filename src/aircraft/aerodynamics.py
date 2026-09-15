# Linear stability-derivative aerodynamic model. Pure function of the flow
# angles, body rates, and control surface deflections -> forces/moments in
# the body frame. No knowledge of trim, guidance, or integration.

from dataclasses import dataclass
import numpy as np
from src.aircraft.state import ControlSurfaceState


@dataclass
class AeroForcesMoments:
    force_body_n: np.ndarray
    moment_body_n_m: np.ndarray
    cl: float
    cd: float


class AeroModel:
    def __init__(self, config: dict, wing_area_m2: float, wing_span_m: float, mean_aero_chord_m: float):
        self.cfg = config
        self.wing_area_m2 = wing_area_m2
        self.wing_span_m = wing_span_m
        self.mean_aero_chord_m = mean_aero_chord_m

    def compute(
        self,
        alpha_rad: float,
        beta_rad: float,
        p_rad_s: float,
        q_rad_s: float,
        r_rad_s: float,
        controls: ControlSurfaceState,
        airspeed_m_s: float,
        dynamic_pressure_pa: float,
    ) -> AeroForcesMoments:
        v = max(airspeed_m_s, 1.0)  # guard divide-by-zero at rest
        b2v = self.wing_span_m / (2.0 * v)
        c2v = self.mean_aero_chord_m / (2.0 * v)

        lift_cfg = self.cfg["lift"]
        cl = (
            lift_cfg["CL0"]
            + lift_cfg["CL_alpha"] * alpha_rad
            + lift_cfg["CL_elevator"] * controls.elevator_rad
            + lift_cfg["CL_elevator_trim"] * controls.elevator_trim_rad
            + lift_cfg["CL_q"] * q_rad_s * c2v
        )

        drag_cfg = self.cfg["drag"]
        aspect_ratio = self.wing_span_m ** 2 / self.wing_area_m2
        induced_drag_k = 1.0 / (np.pi * drag_cfg["oswald_efficiency"] * aspect_ratio)
        cd = drag_cfg["CD0"] + induced_drag_k * cl ** 2

        side_cfg = self.cfg["side_force"]
        cy = side_cfg["CY_beta"] * beta_rad + side_cfg["CY_rudder"] * controls.rudder_rad

        pitch_cfg = self.cfg["pitch_moment"]
        cm = (
            pitch_cfg["Cm0"]
            + pitch_cfg["Cm_alpha"] * alpha_rad
            + pitch_cfg["Cm_elevator"] * controls.elevator_rad
            + pitch_cfg["Cm_elevator_trim"] * controls.elevator_trim_rad
            + pitch_cfg["Cm_q"] * q_rad_s * c2v
        )

        roll_cfg = self.cfg["roll_moment"]
        cl_moment = (
            roll_cfg["Cl_beta"] * beta_rad
            + roll_cfg["Cl_p"] * p_rad_s * b2v
            + roll_cfg["Cl_r"] * r_rad_s * b2v
            + roll_cfg["Cl_aileron"] * controls.aileron_rad
            + roll_cfg["Cl_rudder"] * controls.rudder_rad
        )

        yaw_cfg = self.cfg["yaw_moment"]
        cn_moment = (
            yaw_cfg["Cn_beta"] * beta_rad
            + yaw_cfg["Cn_p"] * p_rad_s * b2v
            + yaw_cfg["Cn_r"] * r_rad_s * b2v
            + yaw_cfg["Cn_aileron"] * controls.aileron_rad
            + yaw_cfg["Cn_rudder"] * controls.rudder_rad
        )

        qs = dynamic_pressure_pa * self.wing_area_m2
        # Wind axes -> body axes via alpha, beta (small-angle-free exact form).
        ca, sa = np.cos(alpha_rad), np.sin(alpha_rad)
        cb, sb = np.cos(beta_rad), np.sin(beta_rad)

        drag_force = -qs * cd
        side_force = qs * cy
        lift_force = -qs * cl

        # Stability axes (drag along -relative-wind, lift perpendicular) rotated
        # into body axes using alpha and beta.
        fx = ca * cb * drag_force - ca * sb * side_force - sa * lift_force
        fy = sb * drag_force + cb * side_force
        fz = sa * cb * drag_force - sa * sb * side_force + ca * lift_force

        force_body = np.array([fx, fy, fz])
        moment_body = np.array([
            qs * self.wing_span_m * cl_moment,
            qs * self.mean_aero_chord_m * cm,
            qs * self.wing_span_m * cn_moment,
        ])

        return AeroForcesMoments(force_body_n=force_body, moment_body_n_m=moment_body, cl=cl, cd=cd)
