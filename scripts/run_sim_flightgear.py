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
from src.guidance.offset_navigator import OffsetNavigator
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

# Placement-only defaults for "native" mode (see config/simulation.yaml's
# flightgear.dynamics) -- FlightGear's own FDM takes over from here, so
# these don't need to match the "external" mode's trimmed values exactly.
NATIVE_MODE_VC_KT = 280.0


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


def launch_flightgear_native(altitude_m: float, heading_deg: float) -> subprocess.Popen:
    # No --fdm=external, no --native-fdm: FlightGear flies the installed
    # 777-200 with its own bundled FDM/autopilot, entirely independent of
    # our JSBSim/Navigator/Autopilot stack.
    args = [
        FGFS_EXE,
        f"--fg-root={FG_ROOT}",
        f"--fg-aircraft={FG_AIRCRAFT_DIR}",
        f"--aircraft={FG_AIRCRAFT_ID}",
        f"--telnet={TELNET_PORT}",
        f"--lat={START_LAT_DEG}",
        f"--lon={START_LON_DEG}",
        f"--altitude={altitude_m * 3.280839895:.0f}",
        f"--heading={heading_deg:.0f}",
        f"--vc={NATIVE_MODE_VC_KT:.0f}",
        "--disable-ai-traffic",
        "--disable-real-weather-fetch",
        "--disable-terrasync",
        "--disable-random-objects",
        "--timeofday=noon",
    ]
    logger.info("Launching FlightGear (native dynamics): %s", " ".join(args))
    return subprocess.Popen(args)


def connect_props(timeout_s: float = 90.0) -> socket.socket:
    # The telnet props server only comes up once FlightGear finishes loading
    # the aircraft model/textures -- slow and hard to bound for a heavy
    # payware-grade model like the 777, so retry rather than fixed-wait.
    # Kept open for the whole run (chase view + gear + surface pushes all
    # share this one connection) rather than reconnecting for each command.
    deadline = time.time() + timeout_s
    last_exc = None
    while time.time() < deadline:
        try:
            sock = socket.create_connection(("localhost", TELNET_PORT), timeout=5.0)
            sock.settimeout(5.0)
            return sock
        except OSError as exc:
            last_exc = exc
            time.sleep(2.0)
    raise TimeoutError(f"Could not connect to FlightGear telnet props server after {timeout_s:.0f}s: {last_exc}")


def _drain(sock: socket.socket) -> None:
    # Discards any bytes left over from a previous fire-and-forget command
    # (or a reply we didn't fully read) so the next command's reply can't
    # get desynced -- reading a stale leftover chunk instead of the actual
    # reply to the command just sent, or blocking on a recv() that will
    # never see the response it's actually waiting for.
    sock.setblocking(False)
    try:
        while sock.recv(65536):
            pass
    except OSError:
        pass
    finally:
        sock.setblocking(True)


def _read_until_prompt(sock: socket.socket) -> str:
    # FlightGear's telnet props server ends every response with a "/>"
    # prompt; a single recv() call isn't guaranteed to capture a whole
    # reply (it can arrive split across TCP packets), so loop until we've
    # actually seen the terminator instead of trusting one read.
    buf = b""
    while b"/>" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    return buf.decode("ascii", errors="replace")


def _send_props(sock: socket.socket, prop_values: dict, wait_for_reply: bool = True) -> None:
    _drain(sock)
    cmds = "".join(f"set {path} {value:.4f}\r\n" for path, value in prop_values.items())
    sock.sendall(cmds.encode("ascii"))
    if not wait_for_reply:
        # Fire-and-forget: waiting for FlightGear's telnet ack on every call
        # (blocking for however long that round-trip takes) stole enough
        # wall-clock time from the real-time pacing loop to make a 90s run
        # take over 3 minutes. The unread ack gets drained on the next call.
        return
    _read_until_prompt(sock)


def _get_prop(sock: socket.socket, path: str) -> str:
    _drain(sock)
    sock.sendall(f"get {path}\r\n".encode("ascii"))
    return _read_until_prompt(sock)


def set_chase_view(sock: socket.socket) -> None:
    # Command-line --prop: values for view state get clobbered once
    # FlightGear's view manager finishes its own init, so this has to be
    # set after startup, over the props/telnet interface instead.
    _send_props(sock, {"/sim/current-view/view-number": CHASE_VIEW_NUMBER})
    logger.info("Switched FlightGear to chase view (view-number=%d)", CHASE_VIEW_NUMBER)


# The installed 777 (FGAddon) drives its aileron/elevator/rudder animation
# through a full property-rule fly-by-wire network (Systems/777-fbw.xml,
# 777-fcs.xml) that RECOMPUTES fcs/*/final-deg from scratch every frame --
# an earlier version of this code wrote final-deg directly, which just got
# overwritten again on the next frame (that's why it never visibly moved).
# The real root inputs, traced through that filter network, are the same
# generic axes any joystick/yoke drives: controls/flight/aileron/elevator
# /rudder/elevator-trim (normalized -1..1).
#
# Those are further gated on realistic hydraulic pump availability
# (Nasal/Hydraulics.nas), which traces back to engine/electrical state that
# --fdm=external never provides (no internal FDM means no engine-driven
# pumps ever "start"), so we fake the two inputs that chain bottoms out on:
# both engines reporting as running (feeds the pump system's power-source
# count) and the center hydraulic system's electric pump switch (a real
# cockpit switch, off by default). Landing gear needed no such workaround
# in the end -- see JSBSimAircraft.trim_at's "gear/gear-pos-norm" fix,
# which corrects it at the source (our own simulated aircraft's reported
# gear state), rather than fighting FlightGear's display of it here.
POWER_UP_PROPS = {
    "engines/engine/run": 1.0,
    "engines/engine[1]/run": 1.0,
    "controls/hydraulics/system[1]/C2ELEC-switch": 1.0,
}


def power_up_aircraft_systems(sock: socket.socket, timeout_s: float = 30.0) -> None:
    # Something in this aircraft's own startup sequence resets these switches
    # back to their cold-and-dark default a few seconds after the model
    # loads (observed: setting them right after chase-view got silently
    # reverted; setting them well after that startup window is stable) --
    # so verify the write actually stuck rather than trusting a fixed wait,
    # and keep re-asserting until it does.
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        _send_props(sock, POWER_UP_PROPS)
        time.sleep(1.0)
        readback = _get_prop(sock, "controls/hydraulics/system[1]/C2ELEC-switch")
        if "true" in readback:
            logger.info("Powered up engine/hydraulics state so gear and control surfaces can move")
            return
    logger.warning("Could not get the aircraft's hydraulics switch to stick after %.0fs; gear/surfaces may stay static", timeout_s)


def push_surface_properties(sock: socket.socket, control_command, limits_rad: dict) -> None:
    def normalized(value_rad: float, key: str) -> float:
        return float(np.clip(value_rad / limits_rad[key], -1.0, 1.0))

    _send_props(sock, {
        "controls/flight/aileron": normalized(control_command.aileron_rad, "aileron_rad"),
        "controls/flight/elevator": normalized(control_command.elevator_rad, "elevator_rad"),
        "controls/flight/rudder": normalized(control_command.rudder_rad, "rudder_rad"),
        "controls/flight/elevator-trim": normalized(control_command.elevator_trim_rad, "elevator_trim_rad"),
    }, wait_for_reply=False)


def run_native(trim_cfg: dict, args) -> None:
    # flightgear.dynamics == "native": FlightGear flies itself, using the
    # installed 777-200's own FDM/autopilot. No JSBSim, no Navigator/
    # Autopilot, no UDP streaming -- this whole mode is just "launch
    # FlightGear and let it run," kept separate from the "external" path
    # above so that path stays untouched.
    fg_process = None
    if not args.no_launch:
        fg_process = launch_flightgear_native(
            altitude_m=trim_cfg["cruise_altitude_m"], heading_deg=trim_cfg["initial_heading_deg"],
        )
        logger.info("Waiting for FlightGear to start up...")
        time.sleep(20.0)
        props_sock = connect_props()
        set_chase_view(props_sock)
        props_sock.close()
    else:
        logger.info("Assuming FlightGear is already running (native dynamics)")

    logger.info("FlightGear is flying itself for %.0fs (native dynamics) ...", args.duration_s)
    time.sleep(args.duration_s)

    logger.info("Done. FlightGear window stays open; close it manually when finished.")
    if fg_process is not None:
        logger.info("(FlightGear PID: %d)", fg_process.pid)


def main():
    parser = argparse.ArgumentParser(description="Run the B777-200 guidance simulation live in FlightGear")
    parser.add_argument("--config", default="config/simulation.yaml")
    parser.add_argument("--duration-s", type=float, default=180.0, help="Real-time duration to run/stream")
    parser.add_argument("--no-launch", action="store_true", help="Don't launch FlightGear; assume it's already running and listening")
    args = parser.parse_args()

    sim_config = load_yaml(args.config)
    setup_logging(sim_config["logging"])
    trim_cfg = sim_config["trim"]

    dynamics_mode = sim_config.get("flightgear", {}).get("dynamics", "external")
    if dynamics_mode == "native":
        run_native(trim_cfg, args)
        return
    elif dynamics_mode != "external":
        raise ValueError(f"Unknown flightgear.dynamics mode: {dynamics_mode!r} (expected 'external' or 'native')")

    aircraft_config = load_yaml(sim_config["aircraft_config"])
    wake_config = load_yaml(sim_config["wake_config"])

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
    props_sock = None
    if not args.no_launch:
        fg_process = launch_flightgear(
            altitude_m=trim_cfg["cruise_altitude_m"],
            heading_deg=trim_cfg["initial_heading_deg"],
            airspeed_m_s=aircraft.airspeed_m_s,
        )
        logger.info("Waiting for FlightGear to start up...")
        time.sleep(20.0)
        props_sock = connect_props()
        set_chase_view(props_sock)
        power_up_aircraft_systems(props_sock)
    else:
        logger.info("Assuming FlightGear is already running and listening on port %d", NATIVE_FDM_PORT)

    wind_field = build_wind_field(wake_config)
    guidance_mode = sim_config.get("flightgear", {}).get("guidance_mode", "straight_offset")
    if guidance_mode == "waypoint":
        navigator = Navigator(
            sim_config["guidance"], cruise_altitude_m=trim_cfg["cruise_altitude_m"], cruise_airspeed_m_s=aircraft.airspeed_m_s,
        )
    elif guidance_mode == "straight_offset":
        navigator = OffsetNavigator(
            sim_config["guidance"], initial_state=aircraft.state,
            cruise_altitude_m=trim_cfg["cruise_altitude_m"], cruise_airspeed_m_s=aircraft.airspeed_m_s,
        )
    else:
        raise ValueError(f"Unknown flightgear.guidance_mode: {guidance_mode!r} (expected 'waypoint' or 'straight_offset')")
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

    # Pushing surface properties every step would mean a telnet round-trip
    # at 20Hz; the surfaces don't need that -- do it at ~5Hz instead.
    surface_push_stride = max(1, round(0.2 / dt))

    wall_clock_start = time.time()
    for i in range(steps):
        state = aircraft.state
        guidance_command = navigator.compute(state)
        control_command = autopilot.compute_control(state, guidance_command, dt)
        aircraft.step(control_command, wind_field, dt)

        if props_sock is not None and i % surface_push_stride == 0:
            try:
                push_surface_properties(props_sock, control_command, aircraft.limits_rad)
            except OSError as exc:
                logger.warning("Lost FlightGear telnet props connection: %s", exc)
                props_sock = None

        # Real-time pacing: sleep off however much wall-clock time is left
        # in this step, so FlightGear receives roughly one update per dt.
        target_wall_time = wall_clock_start + (i + 1) * dt
        sleep_s = target_wall_time - time.time()
        if sleep_s > 0:
            time.sleep(sleep_s)

    logger.info("Done streaming. FlightGear window stays open; close it manually when finished.")
    if fg_process is not None:
        logger.info("(FlightGear PID: %d)", fg_process.pid)
    if props_sock is not None:
        props_sock.close()


if __name__ == "__main__":
    main()
