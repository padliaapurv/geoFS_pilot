# geoFS Pilot — B777-200 cruise dynamics, guidance, and wake sandbox

A from-scratch Python flight-dynamics sandbox: a 6-DOF Boeing 777-200 model
trimmed for cruise, a pluggable atmosphere/wake model, and a high-level
guidance layer that flies the aircraft to a target (x, y). Built as four
independent modules with narrow API boundaries so any one of them — the
aircraft, the wake, the guidance — can be swapped for a higher-fidelity
implementation later, in particular to support minimum-seeking control
against an induced wake from another aircraft of the same type.

## Design choices

- **No Euler angles in the state or dynamics.** Attitude is a 3x3 direction
  cosine matrix (`Aircraft.state.attitude_dcm`), propagated with the
  rotation-matrix exponential map (`aircraft/geometry.py:integrate_dcm`),
  which is exact and free of gimbal lock. Euler angles only ever appear as a
  derived scalar (`euler_from_dcm`) for human-readable logs/plots and for
  autopilot loop feedback (e.g. bank-angle hold) — never as propagated state.
- **YAML config everywhere.** Aircraft mass/geometry/aero/actuator data
  (`config/aircraft_b772.yaml`), the wake model (`config/wake.yaml`), and the
  run/guidance/logging setup (`config/simulation.yaml`) are all data, not
  code.
- **Independent modules, explicit contracts:**
  - `Aircraft.step(control_command, wind_field, dt) -> AircraftState`
  - `WindField.wind_ned(x, y, z, t) -> np.ndarray([Vn, Ve, Vd])`
  - `Navigator.compute(state) -> GuidanceCommand`
  - `Autopilot.compute_control(state, guidance_command, dt) -> ControlSurfaceCommand`
  
  Any of these can be replaced by a drop-in implementation of the same
  contract (e.g. a CFD-backed `WindField`, an RL-based `Autopilot`, an
  online-optimization `Navigator` for wake minimum-seeking) without touching
  the rest of the stack.

## Layout

```
config/
  aircraft_b772.yaml   # mass, geometry, aero derivatives, actuator limits, engine
  wake.yaml            # wind/wake field selection + params (default: zero wind)
  simulation.yaml       # trim target, integration, guidance gains, logging
src/
  aircraft/
    geometry.py         # DCM/rotation-matrix utilities (skew, exp-map integration)
    state.py            # AircraftState, ControlSurfaceState/Command dataclasses
    aerodynamics.py      # linear stability-derivative aero model
    propulsion.py         # thrust model with density/Mach lapse
    control_surfaces.py    # actuator rate/position-limited first-order lag
    dynamics.py             # 6-DOF equations of motion + RK4 integrator
    trim.py                  # closed-form cruise trim solver (CL, alpha, elevator trim, throttle)
    aircraft.py               # top-level Aircraft API composing the above
  atmosphere/
    isa.py               # ISA 1976 standard atmosphere
    wind_field.py          # WindField ABC, ZeroWind, LambOseenVortexPairWake
    factory.py              # builds a WindField from wake.yaml
  guidance/
    commands.py           # GuidanceCommand dataclass (the Navigator/Autopilot contract)
    pid.py                  # PID with derivative-on-measurement + anti-windup
    autopilot.py             # inner loop: bank/climb-rate/airspeed -> control surfaces
    navigator.py              # outer loop: go-to-(x, y) -> GuidanceCommand
  sim/
    simulation.py         # wires Aircraft + WindField + Navigator + Autopilot, runs the loop
    logger.py               # human log setup + per-step CSV telemetry
  viz/
    plots.py               # trajectory / altitude / attitude / controls / CL-CD plots
    wake_field.py            # wake cross-section quiver plot, independent of any aircraft run
scripts/
  run_sim.py             # entry point: trim, run to waypoint, save plots + telemetry
tests/                   # geometry, ISA, and trim/force-balance unit tests
```

## Running it

```bash
pip install -r requirements.txt
python scripts/run_sim.py
```

This trims the 777-200 at FL350, CL = 0.5, then commands it to a waypoint
20 km north / 15 km east of the start. Plots land in `output/`, telemetry in
`logs/telemetry.csv`, and the human-readable run log in `logs/simulation.log`.

To try the wake: set `type: "lamb_oseen_pair"` in `config/wake.yaml` (a
counter-rotating trailing-vortex pair behind a lead 777-200 flying a
straight track) and rerun — a wake cross-section plot is added to `output/`.

Run the tests with:

```bash
pytest tests/ -v
```

## Trim

`aircraft/trim.py` solves cruise trim in closed form: given altitude and a
target CL, it gets airspeed from `CL = 2W / (rho S V^2)`, then solves the 2x2
linear system for angle of attack and elevator-trim deflection that
simultaneously hits the target CL and zeroes the pitching moment (main
elevator held at zero, reserved for maneuvering), and finally solves throttle
to balance thrust against the resulting drag. The initial attitude DCM is
built by rotating the wings-level heading frame up by exactly alpha, which is
the condition for a purely horizontal (zero flight-path-angle) NED velocity —
verified in `tests/test_trim.py`.

## Data caveats

The aerodynamic/mass/actuator numbers in `config/aircraft_b772.yaml` are
engineering-grade public estimates for the 777-200 (Boeing airport-planning
data, generic transport stability-derivative tables), not certified
flight-test data. They're accurate enough to produce believable cruise
trim and closed-loop dynamics, not for anything safety-critical.

## Roadmap: wake minimum-seeking

The intended next step is to induce a `LambOseenVortexPairWake` (or a
multi-aircraft superposition of several) and have a higher-level controller
perturb the aircraft's lateral/vertical offset relative to the wake to
minimize some cost (e.g. induced drag or fuel flow) — a live extremum-seeking
or Bayesian-optimization loop sitting above `Navigator`. Because `WindField`
and `Navigator` are both narrow, swappable interfaces, that loop can be built
as a new `WindField` (multi-vortex superposition) and a new `Navigator`
(perturb-and-observe) without changing `Aircraft`, `Autopilot`, or the
dynamics/aero code at all.
