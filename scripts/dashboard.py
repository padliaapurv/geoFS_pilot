# Live dashboard: runs the same JSBSim + Navigator/Autopilot + FlightGear
# visualization as run_sim_flightgear.py's "external" mode (identical sim
# loop, reused via import -- this script adds a UI on top, it doesn't
# reimplement the sim), but in a background thread so a Tkinter window can
# show FlightGear's view alongside live-updating telemetry plots.
#
# FlightGear window embedding (via win32 SetParent) is attempted best-effort
# since reparenting an external OpenGL window across process boundaries is
# inherently fragile on Windows -- if it fails, or pywin32 isn't installed,
# FlightGear simply keeps running in its own separate window and the
# dashboard's main panel shows a placeholder instead. Either way, all seven
# telemetry plots are always live.

import argparse
import logging
import os
import sys
import threading
import time
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import yaml
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk

import run_sim_flightgear as fg

from src.aircraft.jsbsim_aircraft import JSBSimAircraft
from src.atmosphere.factory import build_wind_field
from src.guidance.navigator import Navigator
from src.guidance.offset_navigator import OffsetNavigator
from src.guidance.autopilot import Autopilot
from src.aircraft.geometry import euler_from_dcm
from src.sim.logger import setup_logging, RollingTelemetryLogger, TelemetryRow

logger = logging.getLogger(__name__)

TELEMETRY_WINDOW_S = 600.0   # 10 minutes, per config -- see RollingTelemetryLogger
PLOT_WINDOW_S = 120.0        # time-series plots show this much recent history; the
                             # rolling buffer/CSV underneath still holds the full 10 min
PLOT_INTERVAL_MS = 400


class SimWorker:
    # Owns the sim loop + shared telemetry buffer. Runs on its own thread so
    # Tkinter's mainloop (which must own the main thread) stays responsive.
    def __init__(self, config_path: str, duration_s: float):
        self.config_path = config_path
        self.duration_s = duration_s
        self.lock = threading.Lock()
        self.rolling = None  # RollingTelemetryLogger, created once dt_s is known
        self.fg_process = None
        self.embed_hwnd = None
        self.stop_requested = False
        self.done = False
        self.error = None

    def snapshot(self):
        with self.lock:
            if self.rolling is None:
                return []
            return list(self.rolling.buffer)

    def run(self) -> None:
        try:
            self._run()
        except Exception as exc:  # surfaced to the UI thread rather than silently dying
            logger.exception("Sim worker crashed")
            self.error = exc
        finally:
            self.done = True

    def _run(self) -> None:
        sim_config = fg.load_yaml(self.config_path)
        setup_logging(sim_config["logging"])
        trim_cfg = sim_config["trim"]
        aircraft_config = fg.load_yaml(sim_config["aircraft_config"])
        wake_config = fg.load_yaml(sim_config["wake_config"])

        aircraft = JSBSimAircraft(aircraft_config, flightgear_output=True)
        aircraft.trim_at(
            altitude_m=trim_cfg["cruise_altitude_m"], target_cl=trim_cfg["target_cl"],
            position_ned_m=np.array(trim_cfg["initial_position_ned_m"], dtype=float),
            heading_rad=np.radians(trim_cfg["initial_heading_deg"]),
            start_lat_deg=fg.START_LAT_DEG, start_lon_deg=fg.START_LON_DEG,
        )

        self.fg_process = fg.launch_flightgear(
            altitude_m=trim_cfg["cruise_altitude_m"], heading_deg=trim_cfg["initial_heading_deg"],
            airspeed_m_s=aircraft.airspeed_m_s,
        )
        logger.info("Waiting for FlightGear to start up...")
        time.sleep(20.0)
        props_sock = fg.connect_props()
        fg.set_chase_view(props_sock)
        fg.push_gear_up(props_sock)

        wind_field = build_wind_field(wake_config)
        guidance_mode = sim_config.get("flightgear", {}).get("guidance_mode", "straight_offset")
        if guidance_mode == "waypoint":
            navigator = Navigator(sim_config["guidance"], cruise_altitude_m=trim_cfg["cruise_altitude_m"], cruise_airspeed_m_s=aircraft.airspeed_m_s)
        else:
            navigator = OffsetNavigator(sim_config["guidance"], initial_state=aircraft.state, cruise_altitude_m=trim_cfg["cruise_altitude_m"], cruise_airspeed_m_s=aircraft.airspeed_m_s)
        _, trim_pitch_attitude_rad, _ = euler_from_dcm(aircraft.state.attitude_dcm)
        autopilot = Autopilot(
            sim_config["guidance"], trim_elevator_trim_rad=aircraft.state.controls.elevator_trim_rad,
            trim_throttle_fraction=aircraft.state.controls.throttle_fraction, trim_pitch_attitude_rad=trim_pitch_attitude_rad,
        )

        dt = sim_config["integration"]["dt_s"]
        with self.lock:
            self.rolling = RollingTelemetryLogger(
                sim_config["logging"]["telemetry_csv"].replace(".csv", "_rolling.csv"),
                window_s=TELEMETRY_WINDOW_S, dt_s=dt,
            )

        steps = int(self.duration_s / dt) if self.duration_s > 0 else None
        surface_push_stride = max(1, round(0.2 / dt))
        logger.info("Dashboard sim loop starting (guidance_mode=%s)", guidance_mode)

        wall_clock_start = time.time()
        i = 0
        while not self.stop_requested and (steps is None or i < steps):
            state = aircraft.state
            guidance_command = navigator.compute(state)
            control_command = autopilot.compute_control(state, guidance_command, dt)
            aircraft.step(control_command, wind_field, dt)

            if props_sock is not None and i % surface_push_stride == 0:
                try:
                    fg.push_surface_properties(props_sock, control_command)
                except OSError:
                    props_sock = None

            row = self._build_row(aircraft, wind_field, guidance_command)
            with self.lock:
                self.rolling.log(row)

            target_wall_time = wall_clock_start + (i + 1) * dt
            sleep_s = target_wall_time - time.time()
            if sleep_s > 0:
                time.sleep(sleep_s)
            i += 1

        with self.lock:
            if self.rolling is not None:
                self.rolling.close()
        if props_sock is not None:
            props_sock.close()
        logger.info("Dashboard sim loop finished")

    def _build_row(self, aircraft, wind_field, guidance_command) -> TelemetryRow:
        state = aircraft.state
        yaw, pitch, roll = euler_from_dcm(state.attitude_dcm)
        wind_ned = wind_field.wind_ned(state.position_ned_m[0], state.position_ned_m[1], state.position_ned_m[2], state.t_s)
        wind_body = state.attitude_dcm.T @ wind_ned
        airflow_body = state.velocity_body_m_s - wind_body
        u, v, w = airflow_body
        airspeed = float(np.linalg.norm(airflow_body))
        alpha = float(np.arctan2(w, u)) if airspeed > 1e-3 else 0.0
        beta = float(np.arctan2(v, np.hypot(u, w))) if airspeed > 1e-3 else 0.0
        cl, cd = aircraft.get_cl_cd(wind_field)
        return TelemetryRow(
            t_s=state.t_s, north_m=state.position_ned_m[0], east_m=state.position_ned_m[1],
            altitude_m=state.altitude_m, airspeed_m_s=airspeed,
            alpha_deg=np.degrees(alpha), beta_deg=np.degrees(beta),
            roll_deg=np.degrees(roll), pitch_deg=np.degrees(pitch), heading_deg=np.degrees(yaw) % 360.0,
            p_deg_s=np.degrees(state.angular_rate_body_rad_s[0]), q_deg_s=np.degrees(state.angular_rate_body_rad_s[1]),
            r_deg_s=np.degrees(state.angular_rate_body_rad_s[2]), cl=cl, cd=cd,
            aileron_deg=np.degrees(state.controls.aileron_rad), elevator_deg=np.degrees(state.controls.elevator_rad),
            rudder_deg=np.degrees(state.controls.rudder_rad), elevator_trim_deg=np.degrees(state.controls.elevator_trim_rad),
            throttle_fraction=state.controls.throttle_fraction,
            wind_north_m_s=wind_ned[0], wind_east_m_s=wind_ned[1], wind_down_m_s=wind_ned[2],
            thrust_lbf=aircraft.total_thrust_lbf,
            target_north_m=guidance_command.target_north_m, target_east_m=guidance_command.target_east_m,
        )


def try_embed_flightgear(tk_frame: tk.Frame, pid: int, timeout_s: float = 60.0):
    # Best-effort only: finds fgfs.exe's top-level window by PID and
    # reparents it into tk_frame via win32 SetParent. OpenGL windows
    # reparented this way don't always keep rendering correctly -- if
    # anything here fails or times out, the caller falls back to leaving
    # FlightGear in its own window.
    try:
        import win32gui
        import win32con
        import win32process
    except ImportError:
        logger.warning("pywin32 not available; FlightGear will run in its own separate window")
        return None

    def find_hwnd():
        found = []

        def callback(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            if found_pid == pid and win32gui.GetWindowText(hwnd):
                found.append(hwnd)

        win32gui.EnumWindows(callback, None)
        return found[0] if found else None

    deadline = time.time() + timeout_s
    hwnd = None
    while time.time() < deadline and hwnd is None:
        hwnd = find_hwnd()
        if hwnd is None:
            time.sleep(1.0)

    if hwnd is None:
        logger.warning("Could not find FlightGear's window to embed; it will stay in its own window")
        return None

    try:
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        style &= ~(win32con.WS_CAPTION | win32con.WS_THICKFRAME | win32con.WS_POPUP)
        style |= win32con.WS_CHILD
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
        win32gui.SetParent(hwnd, tk_frame.winfo_id())
        _resize_embedded(tk_frame, hwnd)
        logger.info("Embedded FlightGear window (hwnd=%s) into the dashboard", hwnd)
        return hwnd
    except Exception:
        logger.warning("Embedding FlightGear's window failed; it will stay in its own window", exc_info=True)
        return None


def _resize_embedded(tk_frame: tk.Frame, hwnd) -> None:
    import win32gui
    w, h = tk_frame.winfo_width(), tk_frame.winfo_height()
    if w > 1 and h > 1:
        win32gui.MoveWindow(hwnd, 0, 0, w, h, True)


def build_ui(worker: SimWorker):
    root = tk.Tk()
    root.title("geoFS_pilot -- live dashboard")
    root.geometry("1400x900")

    fg_frame = tk.Frame(root, bg="black")
    fg_frame.place(relx=0.0, rely=0.0, relwidth=0.55, relheight=0.65)
    placeholder = tk.Label(
        fg_frame, fg="white", bg="black", justify="center",
        text="FlightGear is starting...\n(if embedding isn't available it will\nopen in its own window instead)",
    )
    placeholder.place(relx=0.5, rely=0.5, anchor="center")

    # Two separate figures/canvases rather than one: the 3 "right column"
    # plots sit beside FlightGear in the top ~65% of the window, and the 4
    # "bottom row" plots span the full width underneath -- a single
    # GridSpec can't occupy both regions since FlightGear's panel isn't a
    # matplotlib axis at all (it's a plain Tk frame, possibly holding the
    # embedded FlightGear window).
    fig_top = plt.Figure(figsize=(4, 6))
    ax_alt = fig_top.add_subplot(3, 1, 1)
    ax_speed = fig_top.add_subplot(3, 1, 2)
    ax_bank = fig_top.add_subplot(3, 1, 3)
    fig_top.subplots_adjust(left=0.18, right=0.95, top=0.95, bottom=0.08, hspace=0.6)

    fig_bottom = plt.Figure(figsize=(14, 3))
    ax_xy = fig_bottom.add_subplot(1, 4, 1)
    ax_surfaces = fig_bottom.add_subplot(1, 4, 2)
    ax_thrust = fig_bottom.add_subplot(1, 4, 3)
    ax_heading = fig_bottom.add_subplot(1, 4, 4)
    fig_bottom.subplots_adjust(left=0.06, right=0.98, top=0.88, bottom=0.18, wspace=0.4)

    for ax, title in [
        (ax_alt, "Altitude (m)"), (ax_speed, "Airspeed (m/s)"), (ax_bank, "Bank (deg)"),
    ]:
        ax.set_title(title, fontsize=9)
        ax.tick_params(labelsize=7)
    for ax, title in [
        (ax_xy, "Position: target vs current"), (ax_surfaces, "Control surfaces (deg)"),
        (ax_thrust, "Thrust (lbf)"), (ax_heading, "Heading (deg)"),
    ]:
        ax.set_title(title, fontsize=9)
        ax.tick_params(labelsize=7)

    top_canvas = FigureCanvasTkAgg(fig_top, master=root)
    top_canvas.get_tk_widget().place(relx=0.55, rely=0.0, relwidth=0.45, relheight=0.65)
    bottom_canvas = FigureCanvasTkAgg(fig_bottom, master=root)
    bottom_canvas.get_tk_widget().place(relx=0.0, rely=0.65, relwidth=1.0, relheight=0.35)

    def on_configure(event):
        if worker.embed_hwnd is not None:
            _resize_embedded(fg_frame, worker.embed_hwnd)

    fg_frame.bind("<Configure>", on_configure)

    def update(_frame):
        rows = worker.snapshot()
        if not rows:
            return []
        t0 = rows[-1].t_s
        recent = [r for r in rows if t0 - r.t_s <= PLOT_WINDOW_S]
        t = [r.t_s for r in recent]

        ax_alt.clear(); ax_alt.set_title("Altitude (m)", fontsize=9); ax_alt.tick_params(labelsize=7)
        ax_alt.plot(t, [r.altitude_m for r in recent], color="tab:blue")

        ax_speed.clear(); ax_speed.set_title("Airspeed (m/s)", fontsize=9); ax_speed.tick_params(labelsize=7)
        ax_speed.plot(t, [r.airspeed_m_s for r in recent], color="tab:green")

        ax_bank.clear(); ax_bank.set_title("Bank (deg)", fontsize=9); ax_bank.tick_params(labelsize=7)
        ax_bank.plot(t, [r.roll_deg for r in recent], color="tab:red")
        ax_bank.set_xlabel("t (s)", fontsize=8)

        ax_xy.clear(); ax_xy.set_title("Position: target vs current", fontsize=9); ax_xy.tick_params(labelsize=7)
        ax_xy.plot([r.east_m for r in rows], [r.north_m for r in rows], color="tab:gray", linewidth=1, label="path")
        ax_xy.plot([r.east_m for r in recent], [r.north_m for r in recent], color="tab:blue", label="current")
        ax_xy.scatter([recent[-1].target_east_m], [recent[-1].target_north_m], color="tab:red", marker="x", label="target")
        ax_xy.set_xlabel("east (m)", fontsize=8); ax_xy.set_ylabel("north (m)", fontsize=8)
        ax_xy.legend(fontsize=6, loc="best")

        ax_surfaces.clear(); ax_surfaces.set_title("Control surfaces (deg)", fontsize=9); ax_surfaces.tick_params(labelsize=7)
        ax_surfaces.plot(t, [r.aileron_deg for r in recent], label="aileron")
        ax_surfaces.plot(t, [r.elevator_deg for r in recent], label="elevator")
        ax_surfaces.plot(t, [r.rudder_deg for r in recent], label="rudder")
        ax_surfaces.legend(fontsize=6, loc="best")
        ax_surfaces.set_xlabel("t (s)", fontsize=8)

        ax_thrust.clear(); ax_thrust.set_title("Thrust (lbf)", fontsize=9); ax_thrust.tick_params(labelsize=7)
        ax_thrust.plot(t, [r.thrust_lbf for r in recent], color="tab:orange")
        ax_thrust.set_xlabel("t (s)", fontsize=8)

        ax_heading.clear(); ax_heading.set_title("Heading (deg)", fontsize=9); ax_heading.tick_params(labelsize=7)
        ax_heading.plot(t, [r.heading_deg for r in recent], color="tab:purple")
        ax_heading.set_xlabel("t (s)", fontsize=8)

        top_canvas.draw_idle()
        bottom_canvas.draw_idle()
        return []

    anim = FuncAnimation(fig_top, update, interval=PLOT_INTERVAL_MS, cache_frame_data=False)

    def on_close():
        worker.stop_requested = True
        if worker.fg_process is not None:
            try:
                worker.fg_process.terminate()
            except Exception:
                pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    def try_embed_once():
        if worker.fg_process is not None:
            hwnd = try_embed_flightgear(fg_frame, worker.fg_process.pid, timeout_s=45.0)
            if hwnd is not None:
                worker.embed_hwnd = hwnd
                placeholder.place_forget()
        else:
            root.after(500, try_embed_once)

    root.after(1000, lambda: threading.Thread(target=try_embed_once, daemon=True).start())

    return root, anim


def main():
    parser = argparse.ArgumentParser(description="Live dashboard for the B777-200 guidance simulation + FlightGear")
    parser.add_argument("--config", default="config/simulation.yaml")
    parser.add_argument("--duration-s", type=float, default=0.0, help="0 = run until the window is closed")
    args = parser.parse_args()

    worker = SimWorker(args.config, args.duration_s)
    sim_thread = threading.Thread(target=worker.run, daemon=True)
    sim_thread.start()

    root, anim = build_ui(worker)
    root.mainloop()

    if worker.error is not None:
        raise worker.error


if __name__ == "__main__":
    main()
