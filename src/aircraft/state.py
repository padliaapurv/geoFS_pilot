# Aircraft state container. Attitude is a DCM, never Euler angles.

from dataclasses import dataclass, field
import numpy as np


@dataclass
class ControlSurfaceState:
    # Current (actuated, lagged) surface positions.
    aileron_rad: float = 0.0
    elevator_rad: float = 0.0
    rudder_rad: float = 0.0
    elevator_trim_rad: float = 0.0
    throttle_fraction: float = 0.0


@dataclass
class ControlSurfaceCommand:
    # Commanded (unlagged) surface positions, as issued by the autopilot.
    aileron_rad: float = 0.0
    elevator_rad: float = 0.0
    rudder_rad: float = 0.0
    elevator_trim_rad: float = 0.0
    throttle_fraction: float = 0.0


@dataclass
class AircraftState:
    t_s: float
    position_ned_m: np.ndarray          # [north, east, down]
    velocity_body_m_s: np.ndarray       # [u, v, w] in body frame
    attitude_dcm: np.ndarray            # 3x3, body -> NED
    angular_rate_body_rad_s: np.ndarray # [p, q, r]
    controls: ControlSurfaceState = field(default_factory=ControlSurfaceState)

    def copy(self) -> "AircraftState":
        return AircraftState(
            t_s=self.t_s,
            position_ned_m=self.position_ned_m.copy(),
            velocity_body_m_s=self.velocity_body_m_s.copy(),
            attitude_dcm=self.attitude_dcm.copy(),
            angular_rate_body_rad_s=self.angular_rate_body_rad_s.copy(),
            controls=ControlSurfaceState(**vars(self.controls)),
        )

    @property
    def altitude_m(self) -> float:
        return -self.position_ned_m[2]
