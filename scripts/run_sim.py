# Entry point: load config, trim the aircraft, run guidance to a waypoint,
# save plots and telemetry.

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
import numpy as np

from src.aircraft.aircraft import Aircraft
from src.atmosphere.factory import build_wind_field
from src.guidance.navigator import Navigator
from src.guidance.autopilot import Autopilot
from src.sim.simulation import Simulation
from src.sim.logger import setup_logging, TelemetryLogger
from src.viz.plots import plot_all
from src.viz.wake_field import plot_wake_cross_section

logger = logging.getLogger(__name__)


def load_yaml(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Run the B777-200 cruise/guidance simulation")
    parser.add_argument("--config", default="config/simulation.yaml")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()

    sim_config = load_yaml(args.config)
    aircraft_config = load_yaml(sim_config["aircraft_config"])
    wake_config = load_yaml(sim_config["wake_config"])

    setup_logging(sim_config["logging"])
    logger.info("Loaded configs: aircraft=%s wake_type=%s", aircraft_config["name"], wake_config.get("type"))

    aircraft = Aircraft(aircraft_config)
    trim_cfg = sim_config["trim"]
    aircraft.trim_at(
        altitude_m=trim_cfg["cruise_altitude_m"],
        target_cl=trim_cfg["target_cl"],
        position_ned_m=np.array(trim_cfg["initial_position_ned_m"], dtype=float),
        heading_rad=np.radians(trim_cfg["initial_heading_deg"]),
    )

    wind_field = build_wind_field(wake_config)

    navigator = Navigator(
        sim_config["guidance"],
        cruise_altitude_m=trim_cfg["cruise_altitude_m"],
        cruise_airspeed_m_s=aircraft.airspeed_m_s,
    )
    autopilot = Autopilot(
        sim_config["guidance"],
        trim_elevator_trim_rad=aircraft.state.controls.elevator_trim_rad,
        trim_throttle_fraction=aircraft.state.controls.throttle_fraction,
    )

    telemetry = TelemetryLogger(
        sim_config["logging"]["telemetry_csv"], stride=sim_config["logging"]["telemetry_stride"]
    )
    simulation = Simulation(aircraft, wind_field, navigator, autopilot, telemetry)

    logger.info(
        "Starting simulation: target=%s, dt=%.3fs, max_duration=%.0fs",
        sim_config["guidance"]["target_xy_m"], sim_config["integration"]["dt_s"], sim_config["integration"]["max_duration_s"],
    )
    history = simulation.run(sim_config["integration"]["dt_s"], sim_config["integration"]["max_duration_s"])
    logger.info("Simulation complete: %d steps logged", len(history))

    plot_all(history, sim_config["guidance"]["target_xy_m"], args.output_dir)
    logger.info("Plots written to %s", args.output_dir)

    if wake_config.get("type") != "zero":
        cruise_z_m = -trim_cfg["cruise_altitude_m"]
        plot_wake_cross_section(
            wind_field, x_m=0.0, t_s=60.0, y_range_m=(-100, 100), z_range_m=(cruise_z_m - 50, cruise_z_m + 50),
            output_path=os.path.join(args.output_dir, "wake_cross_section.png"),
        )
        logger.info("Wake cross-section plot written")


if __name__ == "__main__":
    main()
