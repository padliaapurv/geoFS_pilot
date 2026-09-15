# JSBSim-backed Aircraft: same public API as aircraft.Aircraft (trim_at,
# step, state, alpha_rad/beta_rad/airspeed_m_s), so Navigator/Autopilot/
# Simulation/viz code needs zero changes to run against a real validated
# nonlinear FDM instead of our own hand-rolled RK4 model. This is the
# "swap it for a better implementation" seam the architecture was built for.
#
# Attitude is read directly from JSBSim's FGPropagate::GetTl2b() (local-to-
# body direction cosine matrix), which JSBSim maintains internally via
# quaternion integration -- we never touch Euler angles, not even at the
# boundary. Position is JSBSim's own local flat-earth "distance from start,
# NEU" frame, matching our NED convention with z negated.

import logging
import os
import numpy as np
import jsbsim

from src.aircraft.state import AircraftState, ControlSurfaceState, ControlSurfaceCommand
from src.atmosphere.isa import isa_atmosphere

logger = logging.getLogger(__name__)

FT_TO_M = 0.3048
M_TO_FT = 1.0 / FT_TO_M
GRAVITY_M_S2 = 9.80665

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JSBSIM_AIRCRAFT_PATH = os.path.join(REPO_ROOT, "jsbsim_models", "aircraft")
JSBSIM_ENGINE_PATH = os.path.join(REPO_ROOT, "jsbsim_models", "engine")


class JSBSimAircraft:
    def __init__(self, config: dict, model_name: str = "777-200"):
        self.config = config
        surf = config["control_surfaces"]
        self._limits_rad = {
            "aileron_rad": surf["aileron"]["limit_rad"],
            "elevator_rad": surf["elevator"]["limit_rad"],
            "rudder_rad": surf["rudder"]["limit_rad"],
            "elevator_trim_rad": surf["elevator_trim"]["limit_rad"],
        }

        self.fdm = jsbsim.FGFDMExec(root_dir=REPO_ROOT)
        self.fdm.set_aircraft_path(JSBSIM_AIRCRAFT_PATH)
        self.fdm.set_engine_path(JSBSIM_ENGINE_PATH)
        if not self.fdm.load_model(model_name):
            raise RuntimeError(f"JSBSim failed to load aircraft model '{model_name}'")
        # Engines default to off (set-running=0); run_ic() alone does not
        # start them (do_trim happens to spin them up for its own search,
        # but leaves them off afterward) -- without this, the aircraft
        # flies as an unpowered glider with the throttle doing nothing.
        self.fdm.get_propulsion().init_running(-1)

        self._origin_ned_m = np.zeros(3)
        self.state: AircraftState = None

    def trim_at(self, altitude_m: float, target_cl: float, position_ned_m: np.ndarray, heading_rad: float) -> None:
        atmosphere = isa_atmosphere(altitude_m)
        mass_kg = self.config["mass"]["mass_kg"]
        wing_area_m2 = self.config["geometry"]["wing_area_m2"]
        airspeed_m_s = np.sqrt(2.0 * mass_kg * GRAVITY_M_S2 / (atmosphere.density_kg_m3 * wing_area_m2 * target_cl))

        self._origin_ned_m = np.asarray(position_ned_m, dtype=float).copy()

        self.fdm["ic/h-sl-ft"] = altitude_m * M_TO_FT
        self.fdm["ic/vt-fps"] = airspeed_m_s * M_TO_FT
        self.fdm["ic/gamma-deg"] = 0.0
        self.fdm["ic/phi-deg"] = 0.0
        self.fdm["ic/psi-true-deg"] = np.degrees(heading_rad)
        self.fdm["ic/beta-deg"] = 0.0
        self.fdm.run_ic()
        self.fdm.get_propulsion().init_running(-1)  # run_ic() resets engines to off

        try:
            self.fdm.do_trim(1)  # tFull: solves alpha, elevator/pitch-trim, throttle, ailerons, rudder
        except jsbsim.TrimFailureError as exc:
            logger.warning("JSBSim trim did not fully converge: %s", exc)
        self.fdm.get_propulsion().init_running(-1)  # ensure engines are still running post-trim

        self.fdm["fcs/throttle-cmd-norm[1]"] = self.fdm["fcs/throttle-cmd-norm"]
        self.state = self._read_state()

        logger.info(
            "JSBSim trimmed at altitude=%.0fm CL_target=%.3f: V=%.2f m/s, alpha=%.3f deg, "
            "pitch_trim=%.4f rad, throttle=%.3f",
            altitude_m, target_cl, airspeed_m_s, self.fdm["aero/alpha-deg"],
            self.fdm["fcs/pitch-trim-pos-rad"], self.fdm["fcs/throttle-pos-norm"],
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

    def get_cl_cd(self, wind_field=None) -> tuple:
        qbar_psf = self.fdm["aero/qbar-psf"]
        sw_sqft = self.fdm["metrics/Sw-sqft"]
        cl = float(np.sqrt(max(self.fdm["aero/cl-squared"], 0.0)))
        cd = float(self.fdm["aero/force/Drag_basic"] / max(qbar_psf * sw_sqft, 1e-6))
        return cl, cd

    def step(self, command: ControlSurfaceCommand, wind_field, dt: float) -> AircraftState:
        position = self.state.position_ned_m
        t_s = self.state.t_s
        wind_ned = wind_field.wind_ned(position[0], position[1], position[2], t_s)
        self.fdm["atmosphere/wind-north-fps"] = wind_ned[0] * M_TO_FT
        self.fdm["atmosphere/wind-east-fps"] = wind_ned[1] * M_TO_FT
        self.fdm["atmosphere/wind-down-fps"] = wind_ned[2] * M_TO_FT

        self.fdm["fcs/aileron-cmd-norm"] = self._normalize(command.aileron_rad, "aileron_rad")
        self.fdm["fcs/elevator-cmd-norm"] = self._normalize(command.elevator_rad, "elevator_rad")
        self.fdm["fcs/rudder-cmd-norm"] = self._normalize(command.rudder_rad, "rudder_rad")
        self.fdm["fcs/pitch-trim-cmd-norm"] = self._normalize(command.elevator_trim_rad, "elevator_trim_rad")
        throttle = float(np.clip(command.throttle_fraction, 0.0, 1.0))
        self.fdm["fcs/throttle-cmd-norm"] = throttle
        self.fdm["fcs/throttle-cmd-norm[1]"] = throttle

        self.fdm.set_dt(dt)
        self.fdm.run()

        self.state = self._read_state()
        return self.state

    def _normalize(self, value_rad: float, key: str) -> float:
        return float(np.clip(value_rad / self._limits_rad[key], -1.0, 1.0))

    def _read_state(self) -> AircraftState:
        fdm = self.fdm
        # "from-start-neu" is horizontal displacement relative to the IC
        # position, but neu-u is absolute altitude above the start datum
        # (equal to h-sl-ft at t=0) -- not relative -- so only north/east
        # get the origin offset; down comes straight from the absolute
        # altitude with no further offset, or it would double-count.
        north_m = fdm["position/from-start-neu-n-ft"] * FT_TO_M + self._origin_ned_m[0]
        east_m = fdm["position/from-start-neu-e-ft"] * FT_TO_M + self._origin_ned_m[1]
        down_m = -fdm["position/from-start-neu-u-ft"] * FT_TO_M

        velocity_body = np.array([fdm["velocities/u-fps"], fdm["velocities/v-fps"], fdm["velocities/w-fps"]]) * FT_TO_M
        angular_rate = np.array([fdm["velocities/p-rad_sec"], fdm["velocities/q-rad_sec"], fdm["velocities/r-rad_sec"]])

        # Local(NED)-to-body DCM, straight from JSBSim's quaternion-based
        # propagation state -- transpose gives body-to-NED, our convention.
        t_l2b = np.array(fdm.get_propagate().get_Tl2b()).reshape(3, 3)
        attitude_dcm = t_l2b.T

        controls = ControlSurfaceState(
            aileron_rad=fdm["fcs/aileron-pos-rad"],
            elevator_rad=fdm["fcs/elevator-pos-rad"],
            rudder_rad=fdm["fcs/rudder-pos-rad"],
            elevator_trim_rad=fdm["fcs/pitch-trim-pos-rad"],
            throttle_fraction=fdm["fcs/throttle-pos-norm"],
        )

        return AircraftState(
            t_s=fdm.get_sim_time(),
            position_ned_m=np.array([north_m, east_m, down_m]),
            velocity_body_m_s=velocity_body,
            attitude_dcm=attitude_dcm,
            angular_rate_body_rad_s=angular_rate,
            controls=controls,
        )
