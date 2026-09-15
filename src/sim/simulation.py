# Simulation orchestrator: wires Aircraft + WindField + Navigator + Autopilot
# together and runs the time-stepped loop. This is the only module that
# depends on all four of them; each of those stays independently swappable.

import logging
import numpy as np
from src.aircraft.aircraft import Aircraft
from src.aircraft.geometry import euler_from_dcm
from src.guidance.navigator import Navigator
from src.guidance.autopilot import Autopilot
from src.sim.logger import TelemetryLogger, TelemetryRow

logger = logging.getLogger(__name__)


class Simulation:
    def __init__(self, aircraft: Aircraft, wind_field, navigator: Navigator, autopilot: Autopilot, telemetry: TelemetryLogger = None):
        self.aircraft = aircraft
        self.wind_field = wind_field
        self.navigator = navigator
        self.autopilot = autopilot
        self.telemetry = telemetry

    def run(self, dt_s: float, max_duration_s: float) -> list:
        history = []
        steps = int(max_duration_s / dt_s)
        arrived_logged = False

        for _ in range(steps):
            state = self.aircraft.state
            guidance_command = self.navigator.compute(state)
            control_command = self.autopilot.compute_control(state, guidance_command, dt_s)
            self.aircraft.step(control_command, self.wind_field, dt_s)

            if guidance_command.arrived and not arrived_logged:
                logger.info("Arrived at target (t=%.1fs, position=%.1f/%.1f m)", state.t_s, state.position_ned_m[0], state.position_ned_m[1])
                arrived_logged = True

            row = self._build_telemetry_row(self.aircraft.state)
            history.append(row)
            if self.telemetry is not None:
                self.telemetry.log(row)

        if self.telemetry is not None:
            self.telemetry.close()

        return history

    def _build_telemetry_row(self, state) -> TelemetryRow:
        yaw, pitch, roll = euler_from_dcm(state.attitude_dcm)
        wind_ned = self.wind_field.wind_ned(state.position_ned_m[0], state.position_ned_m[1], state.position_ned_m[2], state.t_s)
        wind_body = state.attitude_dcm.T @ wind_ned
        airflow_body = state.velocity_body_m_s - wind_body
        u, v, w = airflow_body
        airspeed = float(np.linalg.norm(airflow_body))
        alpha = float(np.arctan2(w, u)) if airspeed > 1e-3 else 0.0
        beta = float(np.arctan2(v, np.hypot(u, w))) if airspeed > 1e-3 else 0.0

        # CL/CD depend only on alpha/controls/rates, not on dynamic pressure,
        # so an approximate sea-level dynamic pressure is fine for telemetry.
        dynamic_pressure = 0.5 * 1.225 * airspeed ** 2
        aero = self.aircraft.aero_model.compute(
            alpha_rad=alpha, beta_rad=beta,
            p_rad_s=state.angular_rate_body_rad_s[0], q_rad_s=state.angular_rate_body_rad_s[1], r_rad_s=state.angular_rate_body_rad_s[2],
            controls=state.controls, airspeed_m_s=airspeed, dynamic_pressure_pa=dynamic_pressure,
        )

        return TelemetryRow(
            t_s=state.t_s,
            north_m=state.position_ned_m[0],
            east_m=state.position_ned_m[1],
            altitude_m=state.altitude_m,
            airspeed_m_s=airspeed,
            alpha_deg=np.degrees(alpha),
            beta_deg=np.degrees(beta),
            roll_deg=np.degrees(roll),
            pitch_deg=np.degrees(pitch),
            heading_deg=np.degrees(yaw) % 360.0,
            p_deg_s=np.degrees(state.angular_rate_body_rad_s[0]),
            q_deg_s=np.degrees(state.angular_rate_body_rad_s[1]),
            r_deg_s=np.degrees(state.angular_rate_body_rad_s[2]),
            cl=aero.cl,
            cd=aero.cd,
            aileron_deg=np.degrees(state.controls.aileron_rad),
            elevator_deg=np.degrees(state.controls.elevator_rad),
            rudder_deg=np.degrees(state.controls.rudder_rad),
            elevator_trim_deg=np.degrees(state.controls.elevator_trim_rad),
            throttle_fraction=state.controls.throttle_fraction,
            wind_north_m_s=wind_ned[0],
            wind_east_m_s=wind_ned[1],
            wind_down_m_s=wind_ned[2],
        )
