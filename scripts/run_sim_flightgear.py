# Launches FlightGear in "external FDM" mode and streams our JSBSim-backed
# 777-200 guidance simulation to it in real time, so the guided turn onto
# the waypoint can be watched in FlightGear's 3D view.
#
# FlightGear renders whatever aircraft/scenery it has; our simulation still
# owns all the actual physics/guidance (JSBSim + our Navigator/Autopilot) --
# FlightGear is purely a puppeted visualization client here, driven by
# JSBSim's own built-in FLIGHTGEAR output type (native FDM UDP protocol),
# never our own struct-encoding code.

import argparse
import logging
import os
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
import numpy as np

from src.aircraft.jsbsim_aircraft import JSBSimAircraft
from src.atmosphere.factory import build_wind_field
from src.guidance.navigator import Navigator
from src.guidance.autopilot import Autopilot
from src.aircraft.geometry import euler_from_dcm
from src.sim.logger import setup_logging

logger = logging.getLogger(__name__)

FGFS_EXE = r"C:\Program Files\FlightGear 2020.3\bin\fgfs.exe"
FG_ROOT = r"C:\Program Files\FlightGear 2020.3\data"
NATIVE_FDM_PORT = 5550
NATIVE_FDM_RATE_HZ = 30
TELNET_PORT = 5501

# Freeware 777 model from the official FGAddon aircraft hangar (requires
# only FlightGear >=2020.3.12, unlike some newer community 777 models that
# need 2024.x+ and silently fail to load here), installed outside
# FG_ROOT/data/Aircraft (which isn't writable without admin) and added to
# FlightGear's aircraft search path via --fg-aircraft instead. Visual only,
# same as the previous c172p stand-in -- our own JSBSim/Navigator/Autopilot
# code still owns all the actual physics/guidance.
FG_AIRCRAFT_DIR = r"C:\Users\padli\FlightGear_Aircraft"
FG_AIRCRAFT_ID = "777-200"

# Chase View -- see $FG_ROOT/data/defaults.xml's default <view> ordering
# (0=Cockpit, 1=Helicopter, 2=Chase); set after startup over the telnet
# props interface since properties passed on the command line get reset
# once the view manager finishes initializing.
CHASE_VIEW_NUMBER = 2

# Bay Area coordinates purely for a nicer FlightGear starting view; our own
# dynamics/guidance run entirely in the flat-NED frame regardless.
START_LAT_DEG = 37.6189
START_LON_DEG = -122.3750


def load_yaml(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def launch_flightgear(altitude_m: float, heading_deg: float, airspeed_m_s: float) -> subprocess.Popen:
    args = [
        FGFS_EXE,
        f"--fg-root={FG_ROOT}",
        f"--fg-aircraft={FG_AIRCRAFT_DIR}",
        f"--aircraft={FG_AIRCRAFT_ID}",  # visual model only; JSBSim/our sim owns the actual flight dynamics
        "--fdm=external",
        f"--native-fdm=socket,in,{NATIVE_FDM_RATE_HZ},,{NATIVE_FDM_PORT},udp",
        f"--telnet={TELNET_PORT}",
        f"--lat={START_LAT_DEG}",
        f"--lon={START_LON_DEG}",
        f"--altitude={altitude_m * 3.280839895:.0f}",
        f"--heading={heading_deg:.0f}",
        f"--vc={airspeed_m_s * 1.9438445:.0f}",
        "--disable-ai-traffic",
        "--disable-real-weather-fetch",
        "--disable-terrasync",
        "--disable-random-objects",
        "--timeofday=noon",
    ]
    logger.info("Launching FlightGear: %s", " ".join(args))
    return subprocess.Popen(args)


def set_chase_view(timeout_s: float = 90.0) -> None:
    # Command-line --prop: values for view state get clobbered once
    # FlightGear's view manager finishes its own init, so this has to be
    # set after startup, over the props/telnet interface instead. The
    # telnet server itself only comes up once FlightGear finishes loading
    # the aircraft model/textures -- slow and hard to bound for a heavy
    # payware-grade model like the 777, so retry rather than fixed-wait.
    deadline = time.time() + timeout_s
    last_exc = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("localhost", TELNET_PORT), timeout=5.0) as sock:
                sock.sendall(f"set /sim/current-view/view-number {CHASE_VIEW_NUMBER}\r\n".encode("ascii"))
                sock.recv(4096)
            logger.info("Switched FlightGear to chase view (view-number=%d)", CHASE_VIEW_NUMBER)
            return
        except OSError as exc:
            last_exc = exc
            time.sleep(2.0)
    logger.warning("Could not set chase view over telnet after %.0fs: %s", timeout_s, last_exc)


def main():
    parser = argparse.ArgumentParser(description="Run the B777-200 guidance simulation live in FlightGear")
    parser.add_argument("--config", default="config/simulation.yaml")
    parser.add_argument("--duration-s", type=float, default=180.0, help="Real-time duration to run/stream")
    parser.add_argument("--no-launch", action="store_true", help="Don't launch FlightGear; assume it's already running and listening")
    args = parser.parse_args()

    sim_config = load_yaml(args.config)
    aircraft_config = load_yaml(sim_config["aircraft_config"])
    wake_config = load_yaml(sim_config["wake_config"])
    setup_logging(sim_config["logging"])

    trim_cfg = sim_config["trim"]
    aircraft = JSBSimAircraft(aircraft_config, flightgear_output=True)
    aircraft.trim_at(
        altitude_m=trim_cfg["cruise_altitude_m"],
        target_cl=trim_cfg["target_cl"],
        position_ned_m=np.array(trim_cfg["initial_position_ned_m"], dtype=float),
        heading_rad=np.radians(trim_cfg["initial_heading_deg"]),
        start_lat_deg=START_LAT_DEG,
        start_lon_deg=START_LON_DEG,
    )

    fg_process = None
    if not args.no_launch:
        fg_process = launch_flightgear(
            altitude_m=trim_cfg["cruise_altitude_m"],
            heading_deg=trim_cfg["initial_heading_deg"],
            airspeed_m_s=aircraft.airspeed_m_s,
        )
        logger.info("Waiting for FlightGear to start up...")
        time.sleep(20.0)
        set_chase_view()
    else:
        logger.info("Assuming FlightGear is already running and listening on port %d", NATIVE_FDM_PORT)

    wind_field = build_wind_field(wake_config)
    navigator = Navigator(
        sim_config["guidance"], cruise_altitude_m=trim_cfg["cruise_altitude_m"], cruise_airspeed_m_s=aircraft.airspeed_m_s,
    )
    _, trim_pitch_attitude_rad, _ = euler_from_dcm(aircraft.state.attitude_dcm)
    autopilot = Autopilot(
        sim_config["guidance"],
        trim_elevator_trim_rad=aircraft.state.controls.elevator_trim_rad,
        trim_throttle_fraction=aircraft.state.controls.throttle_fraction,
        trim_pitch_attitude_rad=trim_pitch_attitude_rad,
    )

    dt = sim_config["integration"]["dt_s"]
    steps = int(args.duration_s / dt)
    logger.info("Streaming %.0fs of simulation to FlightGear on UDP port %d ...", args.duration_s, NATIVE_FDM_PORT)

    wall_clock_start = time.time()
    for i in range(steps):
        state = aircraft.state
        guidance_command = navigator.compute(state)
        control_command = autopilot.compute_control(state, guidance_command, dt)
        aircraft.step(control_command, wind_field, dt)

        # Real-time pacing: sleep off however much wall-clock time is left
        # in this step, so FlightGear receives roughly one update per dt.
        target_wall_time = wall_clock_start + (i + 1) * dt
        sleep_s = target_wall_time - time.time()
        if sleep_s > 0:
            time.sleep(sleep_s)

    logger.info("Done streaming. FlightGear window stays open; close it manually when finished.")
    if fg_process is not None:
        logger.info("(FlightGear PID: %d)", fg_process.pid)


if __name__ == "__main__":
    main()
