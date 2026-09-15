# Top-level Aircraft API: the only object guidance/sim code talks to.
# Owns aero + propulsion + actuators + mass properties, exposes step() to
# advance one integration step given a control command and ambient wind.

import logging
import numpy as np
from src.atmosphere.isa import isa_atmosphere
from src.aircraft.aerodynamics import AeroModel
from src.aircraft.propulsion import EngineModel
from src.aircraft.control_surfaces import ActuatorModel
from src.aircraft.dynamics import build_inertia_properties, rk4_step
from src.aircraft.trim import solve_trim, build_trimmed_state
from src.aircraft.state import AircraftState, ControlSurfaceCommand

logger = logging.getLogger(__name__)

GRAVITY_M_S2 = 9.80665


class Aircraft:
    def __init__(self, config: dict):
        self.config = config
        self.mass_kg = config["mass"]["mass_kg"]
        self.inertia = build_inertia_properties(self.mass_kg, config["mass"]["inertia_kg_m2"])
        geometry_cfg = config["geometry"]
        self.aero_model = AeroModel(
            config["aerodynamics"],
            wing_area_m2=geometry_cfg["wing_area_m2"],
            wing_span_m=geometry_cfg["wing_span_m"],
            mean_aero_chord_m=geometry_cfg["mean_aero_chord_m"],
        )
        self.engine_model = EngineModel(config["propulsion"])
        self.actuator_model = ActuatorModel(config["control_surfaces"])
        self.state: AircraftState = None

    def trim_at(self, altitude_m: float, target_cl: float, position_ned_m: np.ndarray, heading_rad: float) -> None:
        trim_result = solve_trim(self.aero_model, self.engine_model, self.mass_kg, GRAVITY_M_S2, altitude_m, target_cl)
        self.state = build_trimmed_state(trim_result, position_ned_m, heading_rad)
        logger.info(
            "Trimmed at altitude=%.0fm CL=%.3f: V=%.2f m/s, alpha=%.3f rad, "
            "elevator_trim=%.4f rad, throttle=%.3f, CD=%.5f",
            altitude_m, target_cl, trim_result.airspeed_m_s, trim_result.alpha_rad,
            trim_result.elevator_trim_rad, trim_result.throttle_fraction, trim_result.cd,
        )

    @property
    def airspeed_m_s(self) -> float:
        return float(np.linalg.norm(self.state.velocity_body_m_s))

    @property
    def alpha_rad(self) -> float:
        u, _, w = self.state.velocity_body_m_s
        return float(np.arctan2(w, u))

    @property
    def beta_rad(self) -> float:
        u, v, w = self.state.velocity_body_m_s
        return float(np.arctan2(v, np.hypot(u, w)))

    def get_cl_cd(self, wind_field) -> tuple:
        # Telemetry/plotting convenience: CL/CD don't depend on dynamic
        # pressure (see aerodynamics.compute), so an approximate sea-level
        # qbar is fine here even though step() uses the exact altitude qbar.
        state = self.state
        wind_ned = wind_field.wind_ned(*state.position_ned_m, state.t_s)
        wind_body = state.attitude_dcm.T @ wind_ned
        airflow_body = state.velocity_body_m_s - wind_body
        airspeed = float(np.linalg.norm(airflow_body))
        u, v, w = airflow_body
        alpha = float(np.arctan2(w, u)) if airspeed > 1e-3 else 0.0
        beta = float(np.arctan2(v, np.hypot(u, w))) if airspeed > 1e-3 else 0.0
        dynamic_pressure = 0.5 * 1.225 * airspeed ** 2
        aero = self.aero_model.compute(
            alpha_rad=alpha, beta_rad=beta,
            p_rad_s=state.angular_rate_body_rad_s[0], q_rad_s=state.angular_rate_body_rad_s[1], r_rad_s=state.angular_rate_body_rad_s[2],
            controls=state.controls, airspeed_m_s=airspeed, dynamic_pressure_pa=dynamic_pressure,
        )
        return aero.cl, aero.cd

    def step(self, command: ControlSurfaceCommand, wind_field, dt: float) -> AircraftState:
        self.state.controls = self.actuator_model.step(self.state.controls, command, dt)

        def forces_moments_fn(position_ned_m, velocity_body_m_s, attitude_dcm, angular_rate_body_rad_s, t_s):
            altitude_m = -position_ned_m[2]
            atmosphere = isa_atmosphere(altitude_m)
            wind_ned = wind_field.wind_ned(position_ned_m[0], position_ned_m[1], position_ned_m[2], t_s)
            wind_body = attitude_dcm.T @ wind_ned
            airflow_body = velocity_body_m_s - wind_body
            airspeed = np.linalg.norm(airflow_body)
            u, v, w = airflow_body
            alpha = np.arctan2(w, u) if airspeed > 1e-3 else 0.0
            beta = np.arctan2(v, np.hypot(u, w)) if airspeed > 1e-3 else 0.0
            dynamic_pressure = 0.5 * atmosphere.density_kg_m3 * airspeed ** 2

            aero = self.aero_model.compute(
                alpha_rad=alpha, beta_rad=beta,
                p_rad_s=angular_rate_body_rad_s[0], q_rad_s=angular_rate_body_rad_s[1], r_rad_s=angular_rate_body_rad_s[2],
                controls=self.state.controls, airspeed_m_s=airspeed, dynamic_pressure_pa=dynamic_pressure,
            )

            mach = airspeed / atmosphere.speed_of_sound_m_s
            density_ratio_sigma = atmosphere.density_kg_m3 / 1.225
            thrust_body = self.engine_model.compute_thrust_body_n(
                self.state.controls.throttle_fraction, density_ratio_sigma, mach
            )

            gravity_ned = np.array([0.0, 0.0, self.mass_kg * GRAVITY_M_S2])
            gravity_body = attitude_dcm.T @ gravity_ned

            total_force = aero.force_body_n + thrust_body + gravity_body
            total_moment = aero.moment_body_n_m
            return total_force, total_moment

        self.state = rk4_step(self.state, self.inertia, dt, forces_moments_fn)
        return self.state
