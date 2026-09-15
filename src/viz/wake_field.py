# Visualizes a WindField as a quiver plot over a cross-section plane, useful
# for sanity-checking a wake model independent of any aircraft simulation.

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_wake_cross_section(wind_field, x_m: float, t_s: float, y_range_m, z_range_m, output_path: str, grid_n: int = 25):
    # Cross-section at fixed along-track position x_m and time t_s, spanning
    # lateral (east) and vertical (down) offsets.
    y_values = np.linspace(*y_range_m, grid_n)
    z_values = np.linspace(*z_range_m, grid_n)
    z_center = 0.5 * (z_range_m[0] + z_range_m[1])
    Y, Z = np.meshgrid(y_values, z_values)
    V_east = np.zeros_like(Y)
    V_down = np.zeros_like(Y)

    for i in range(grid_n):
        for j in range(grid_n):
            wind = wind_field.wind_ned(x_m, Y[i, j], Z[i, j], t_s)
            V_east[i, j] = wind[1]
            V_down[i, j] = wind[2]

    fig, ax = plt.subplots(figsize=(8, 7))
    ax.quiver(Y, -(Z - z_center), V_east, -V_down)
    ax.set_xlabel("East offset from track centerline (m)")
    ax.set_ylabel("Altitude offset from cross-section center (m)")
    ax.set_title(f"Wake cross-section at x={x_m:.0f} m, t={t_s:.0f} s")
    ax.axis("equal")
    ax.grid(True)
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
