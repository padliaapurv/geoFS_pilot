# Static matplotlib plots from a list of TelemetryRow. Purely a consumer of
# telemetry data, no dependency on aircraft/guidance internals.

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _times(history):
    return [row.t_s for row in history]


def plot_trajectory_topdown(history, target_xy_m, output_path):
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot([row.east_m for row in history], [row.north_m for row in history], label="track")
    ax.plot(history[0].east_m, history[0].north_m, "go", label="start")
    ax.plot(target_xy_m[1], target_xy_m[0], "r*", markersize=15, label="target")
    ax.set_xlabel("East (m)")
    ax.set_ylabel("North (m)")
    ax.set_title("Ground track")
    ax.axis("equal")
    ax.grid(True)
    ax.legend()
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_altitude_speed(history, output_path):
    t = _times(history)
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    axes[0].plot(t, [row.altitude_m for row in history])
    axes[0].set_ylabel("Altitude (m)")
    axes[0].grid(True)
    axes[1].plot(t, [row.airspeed_m_s for row in history])
    axes[1].set_ylabel("Airspeed (m/s)")
    axes[1].set_xlabel("Time (s)")
    axes[1].grid(True)
    fig.suptitle("Altitude and airspeed")
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_attitude(history, output_path):
    t = _times(history)
    fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True)
    axes[0].plot(t, [row.roll_deg for row in history])
    axes[0].set_ylabel("Roll (deg)")
    axes[0].grid(True)
    axes[1].plot(t, [row.pitch_deg for row in history])
    axes[1].set_ylabel("Pitch (deg)")
    axes[1].grid(True)
    axes[2].plot(t, [row.heading_deg for row in history])
    axes[2].set_ylabel("Heading (deg)")
    axes[2].set_xlabel("Time (s)")
    axes[2].grid(True)
    fig.suptitle("Attitude (derived from DCM, display only)")
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_control_surfaces(history, output_path):
    t = _times(history)
    fig, axes = plt.subplots(4, 1, figsize=(9, 10), sharex=True)
    axes[0].plot(t, [row.aileron_deg for row in history])
    axes[0].set_ylabel("Aileron (deg)")
    axes[0].grid(True)
    axes[1].plot(t, [row.elevator_deg for row in history], label="elevator")
    axes[1].plot(t, [row.elevator_trim_deg for row in history], label="trim")
    axes[1].set_ylabel("Elevator (deg)")
    axes[1].legend()
    axes[1].grid(True)
    axes[2].plot(t, [row.rudder_deg for row in history])
    axes[2].set_ylabel("Rudder (deg)")
    axes[2].grid(True)
    axes[3].plot(t, [row.throttle_fraction for row in history])
    axes[3].set_ylabel("Throttle")
    axes[3].set_xlabel("Time (s)")
    axes[3].grid(True)
    fig.suptitle("Control surfaces")
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_aero_coefficients(history, output_path):
    t = _times(history)
    fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True)
    axes[0].plot(t, [row.cl for row in history])
    axes[0].axhline(0.5, color="gray", linestyle="--", linewidth=1)
    axes[0].set_ylabel("CL")
    axes[0].grid(True)
    axes[1].plot(t, [row.alpha_deg for row in history], label="alpha")
    axes[1].plot(t, [row.beta_deg for row in history], label="beta")
    axes[1].set_ylabel("deg")
    axes[1].legend()
    axes[1].grid(True)
    axes[2].plot(t, [row.cd for row in history])
    axes[2].set_ylabel("CD")
    axes[2].set_xlabel("Time (s)")
    axes[2].grid(True)
    fig.suptitle("Aerodynamic coefficients / flow angles")
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_all(history, target_xy_m, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    plot_trajectory_topdown(history, target_xy_m, os.path.join(output_dir, "trajectory.png"))
    plot_altitude_speed(history, os.path.join(output_dir, "altitude_speed.png"))
    plot_attitude(history, os.path.join(output_dir, "attitude.png"))
    plot_control_surfaces(history, os.path.join(output_dir, "control_surfaces.png"))
    plot_aero_coefficients(history, os.path.join(output_dir, "aero_coefficients.png"))
