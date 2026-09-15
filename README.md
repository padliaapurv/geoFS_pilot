# geoFS Pilot — B777-200 cruise dynamics, guidance, and wake sandbox

A from-scratch Python flight-dynamics sandbox: a 6-DOF Boeing 777-200 model
trimmed for cruise, a pluggable atmosphere/wake model, and a high-level
guidance layer that flies the aircraft to a target (x, y). Built as four
independent modules with narrow API boundaries so any one of them — the
aircraft, the wake, the guidance — can be swapped for a higher-fidelity
implementation later, in particular to support minimum-seeking control
against an induced wake from another aircraft of the same type.

Two interchangeable aircraft/dynamics backends implement the same `Aircraft`
API (see `dynamics_backend` in `config/simulation.yaml`):
- **`custom`** — our own RK4 + rotation-matrix 6-DOF model, described below.
- **`jsbsim`** — [JSBSim](https://jsbsim.org/), a real, widely-validated
  nonlinear flight dynamics engine, running a custom 777-200 model generated
  from the same `config/aircraft_b772.yaml` (see "JSBSim backend" below).

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
    aircraft.py               # top-level Aircraft API composing the above (custom backend)
    jsbsim_aircraft.py         # same Aircraft API, backed by JSBSim (jsbsim backend)
jsbsim_models/
  aircraft/777-200/777-200.xml # generated JSBSim aircraft def (see scripts/generate_jsbsim_aircraft.py)
  engine/GE90-94B.xml           # generic large-turbofan deck, retargeted thrust
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
  run_sim.py                    # entry point: trim, run to waypoint, save plots + telemetry
  generate_jsbsim_aircraft.py    # regenerates jsbsim_models/aircraft/777-200 from the YAML
tests/                   # geometry, ISA, trim/force-balance, and JSBSim-backend unit tests
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

## JSBSim backend

`src/aircraft/jsbsim_aircraft.py` wraps [JSBSim](https://jsbsim.org/) (`pip
install jsbsim`) behind the exact same `Aircraft` API as the custom model, so
`Navigator`/`Autopilot`/`Simulation`/the plotting code need zero changes to
run against it. `jsbsim_models/aircraft/777-200/777-200.xml` is a JSBSim
aircraft definition generated by `scripts/generate_jsbsim_aircraft.py` from
`config/aircraft_b772.yaml` — same mass/geometry/aero-derivative numbers as
the custom model, just re-expressed as JSBSim `<function>` elements, so
re-run that script after editing the YAML. `jsbsim_models/engine/GE90-94B.xml`
is a generic large-turbofan deck (table shapes borrowed from JSBSim's bundled
TRENT-900) re-targeted to the GE90-94B's ~93,700 lbf sea-level thrust — not a
validated GE90 deck, a stand-in for cruise-regime thrust/fuel-flow behavior.

Attitude comes straight from JSBSim's own `FGPropagate::GetTl2b()` (the
local-to-body DCM it maintains internally via quaternion integration) —
transposed to body-to-NED, our convention — so even the JSBSim boundary never
touches Euler angles. Trim uses JSBSim's own `do_trim(tFull)` at a true
airspeed computed from the same `CL = 2W/(rho S V^2)` closed form the custom
model uses, so both backends target the same CL at the same speed.

One easy-to-miss JSBSim quirk this wrapper works around: `run_ic()` resets
engines to `set-running=0`, and `do_trim()` doesn't leave them running
afterward either — `JSBSimAircraft` explicitly calls
`get_propulsion().init_running(-1)` after both, or the aircraft flies as an
unpowered glider with the throttle doing nothing (which is exactly what
happened before this was found and fixed).

**FlightGear was intentionally not installed.** Its Windows installer
requires an interactive UAC elevation prompt that can't be scripted (a
`winget` silent-install attempt failed for exactly this reason), so
visualization here is the matplotlib plots in `src/viz/` instead. JSBSim
itself needs no GUI. If you want live 3D visualization, install FlightGear
yourself and run it in "external FDM" mode (`--fdm=external` /
`--native-fdm`) fed by `JSBSimAircraft`'s state each step.

### Known limitation: long-duration altitude hold on the JSBSim backend

The custom model's simplified linear aerodynamics don't exhibit a strong
phugoid; JSBSim's full nonlinear 777-200 does (a real, lightly damped
long-period pitch/speed/altitude oscillation, as real aircraft have). Getting
a classical cascaded autopilot to null that mode over long runs turned out to
be a genuinely hard tuning problem: PID gains that work well on the custom
model excite the JSBSim phugoid into a growing oscillation, and a
climb-rate-driven elevator loop resonates with it even when heavily damped.
The gains in `config/simulation.yaml` are tuned to be *stable and bounded* —
verified out to 1800s without divergence — at the cost of a slow, P-only
steady-state altitude droop (no integral term survives against the phugoid
without winding up during the initial transient). `max_duration_s` defaults
to 600s, a window with smooth, non-oscillatory behavior and a well-behaved
guided turn onto the waypoint. Fixing the droop properly needs a more
sophisticated longitudinal design (e.g. a notch/complementary filter on the
phugoid frequency, or full state-feedback/LQR) than a hand-tuned PID cascade.

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
