# Wind/wake field API. Every implementation exposes the same contract:
# wind_ned(x, y, z, t) -> np.ndarray([Vn, Ve, Vd]) in m/s, NED frame.
# This is the boundary the aircraft dynamics depend on, so any external or
# higher-fidelity wake model (CFD lookup, another simulator) can be dropped
# in by implementing WindField without touching aircraft/guidance code.

from abc import ABC, abstractmethod
import numpy as np


class WindField(ABC):
    @abstractmethod
    def wind_ned(self, x: float, y: float, z: float, t: float) -> np.ndarray:
        # x = north (m), y = east (m), z = down (m, negative = above ground), t = time (s)
        raise NotImplementedError


class ZeroWind(WindField):
    # Default: still air everywhere, always.
    def wind_ned(self, x: float, y: float, z: float, t: float) -> np.ndarray:
        return np.zeros(3)


class LambOseenVortexPairWake(WindField):
    # Trailing wake vortex pair behind a lead aircraft flying a straight,
    # constant-velocity track. Standard Lamb-Oseen tangential velocity
    # profile for each of the two counter-rotating vortices, with an
    # empirical circulation decay to model wake age/dissipation. Intended
    # as the "induce a wake and minimum-seek away from it" scenario.
    def __init__(
        self,
        lead_start_position_ned_m: np.ndarray,
        lead_velocity_ned_m_s: np.ndarray,
        lead_wing_span_m: float,
        lead_mass_kg: float,
        core_radius0_m: float,
        core_growth_m2_s: float,
        circulation_decay_s: float,
        gravity_m_s2: float = 9.80665,
        air_density_kg_m3: float = 0.38,  # approx density at FL350, used for Gamma0
    ):
        self.lead_start_position_ned_m = np.asarray(lead_start_position_ned_m, dtype=float)
        self.lead_velocity_ned_m_s = np.asarray(lead_velocity_ned_m_s, dtype=float)
        self.lead_speed_m_s = np.linalg.norm(self.lead_velocity_ned_m_s)
        self.vortex_separation_m = np.pi / 4.0 * lead_wing_span_m
        # Initial circulation from lifting-line theory: Gamma0 = 4*W / (rho * V * pi * b0)
        weight_n = lead_mass_kg * gravity_m_s2
        self.circulation0_m2_s = 4.0 * weight_n / (
            air_density_kg_m3 * max(self.lead_speed_m_s, 1e-3) * np.pi * self.vortex_separation_m
        )
        self.core_radius0_m = core_radius0_m
        self.core_growth_m2_s = core_growth_m2_s
        self.circulation_decay_s = circulation_decay_s

    def _lead_position_at(self, t: float) -> np.ndarray:
        return self.lead_start_position_ned_m + self.lead_velocity_ned_m_s * t

    def wind_ned(self, x: float, y: float, z: float, t: float) -> np.ndarray:
        lead_pos = self._lead_position_at(t)
        # Work in the plane perpendicular to the lead aircraft's track.
        track_dir = self.lead_velocity_ned_m_s / max(self.lead_speed_m_s, 1e-6)
        relative = np.array([x, y, z]) - lead_pos
        along_track = np.dot(relative, track_dir)
        # along_track > 0 means the point is ahead of the lead aircraft's
        # current position (no wake laid there yet); the wake trails behind,
        # so age is positive when along_track is negative.
        age_s = -along_track / max(self.lead_speed_m_s, 1e-6)
        if age_s < 0.0:
            return np.zeros(3)

        circulation = self.circulation0_m2_s * np.exp(-age_s / self.circulation_decay_s)
        core_radius = np.sqrt(self.core_radius0_m ** 2 + self.core_growth_m2_s * age_s)

        cross_track = relative - along_track * track_dir
        east_unit = np.array([-track_dir[1], track_dir[0], 0.0])
        down_unit = np.array([0.0, 0.0, 1.0])
        lateral_offset = np.dot(cross_track, east_unit)
        vertical_offset = np.dot(cross_track, down_unit)

        induced = np.zeros(3)
        for sign in (+1.0, -1.0):
            vortex_center_lateral = sign * self.vortex_separation_m / 2.0
            dl = lateral_offset - vortex_center_lateral
            dv = vertical_offset
            r = np.hypot(dl, dv)
            if r < 1e-6:
                continue
            v_theta = _lamb_oseen_tangential_velocity(sign * circulation, r, core_radius)
            radial_unit_lateral = dl / r
            radial_unit_vertical = dv / r
            induced_lateral = -v_theta * radial_unit_vertical
            induced_vertical = v_theta * radial_unit_lateral
            induced += induced_lateral * east_unit + induced_vertical * down_unit

        return induced


def _lamb_oseen_tangential_velocity(circulation: float, radius: float, core_radius: float) -> float:
    # Lamb-Oseen vortex: v_theta(r) = Gamma / (2*pi*r) * (1 - exp(-r^2 / rc^2))
    return circulation / (2.0 * np.pi * radius) * (1.0 - np.exp(-(radius ** 2) / (core_radius ** 2)))
