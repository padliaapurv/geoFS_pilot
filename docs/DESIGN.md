# GeoFS wake simulation design

## Goal

Use the native GeoFS Boeing 777-200 flight model for the aircraft. Add only an external local wake field, relative-position guidance, and a peak-seeking controller.

The first test has two GeoFS tabs:

1. Leader: Boeing 777-200 in steady level flight at `CL = 0.5`.
2. Follower: Boeing 777-200 behind the leader at the same trim condition.
3. The leader tab sends its state to the follower tab with `BroadcastChannel`.
4. The follower evaluates the wake field at its current position relative to the leader.
5. The wake vector is injected through `weather.currentWindVector`.
6. GeoFS computes the aerodynamic reaction with its normal aircraft model.
7. The follower guidance changes heading, altitude, and KIAS targets.

## Coordinate systems

Wake coordinates use the leader flight frame:

- `downstreamM`: positive behind the leader.
- `crossM`: positive to the leader right.
- `verticalM`: positive up.

Wake velocity uses physical air-mass velocity in the same frame:

- `uMps`: forward.
- `vMps`: right.
- `wMps`: up.

GeoFS uses an east-north-up wind vector. Its flight code adds `weather.currentWindVector` to aircraft velocity to form air-relative velocity. Therefore the code transforms the physical wake velocity to east-north-up and changes its sign before injection.

## Grid interface

Load a 2-D cross-plane field in the follower tab:

```js
geofsWake.grid.load({
  xM: [-60, -30, 0, 30, 60],       // lateral position, m, positive right
  yM: [-30, -15, 0, 15, 30],       // vertical position, m, positive up
  uMps: [[/* ... */]],              // forward air-mass velocity
  vMps: [[/* ... */]],              // lateral air-mass velocity
  wMps: [[/* ... */]],              // vertical air-mass velocity
  ideal: { xM: 25, yM: 5 },         // optional; debug/truth mode only
  inputConvention: 'airMassVelocity',
  downstreamReferenceM: 300,
  downstreamDecayLengthM: 2000,
})
```

Each velocity matrix has layout `[yIndex][xIndex]`. The sampler uses bilinear interpolation.

For a cross-plane grid without an axial component, use:

```js
geofsWake.grid.load({
  xM,
  yM,
  vxMps,   // same as vMps
  vyMps,   // same as wMps
})
```

The code then sets `uMps = 0`.

Use `inputConvention: 'geofsAirVelocity'` only if the input values already use the GeoFS air-relative sign convention.

## Temporary wake model

If no grid is loaded, the simulation uses a temporary model with:

- a counter-rotating vortex pair,
- wake descent,
- slow lateral and vertical meander,
- downstream circulation decay,
- a known moving favorable point.

This model is only for controller development. Replace `js/wake/field.js` with the final wake model or load the computed grid.

## Guidance modes

### `hold`

Keep a fixed lateral and vertical point. Use this mode first to validate wake injection and aircraft response.

### `truth`

Track the temporary model or grid `ideal` point directly. This tests the formation guidance without peak-seeking uncertainty.

### `seek`

Do not use the known ideal point for the command. Apply independent lateral and vertical dithers. Estimate the local objective gradient from the measured follower response. Move the dither center uphill.

The current measured objective is approximately:

```text
J = 1 - throttle - tracking penalties
```

At fixed KIAS and altitude, lower required throttle gives a larger objective. This is a placeholder measurement. Replace it with the final energy, force, pressure, or wake-sensing metric later.

## Current fidelity limit

`weather.currentWindVector` is one vector for the full aircraft. It gives the correct first-stage test for a local wake vector at the aircraft reference point and lets the normal GeoFS airfoil model react.

It does not represent a different wake velocity at the left and right wing sections.

A later high-fidelity extension can sample the wake at several span stations. Use the center sample as `weather.currentWindVector`. Convert the differential spanwise samples to extra roll/yaw forces or moments and apply them through the GeoFS rigid body force/torque interface.

## Test sequence

1. Run both aircraft outside the wake and verify `CL = 0.5` trim.
2. Run follower in `hold` mode with a constant injected vector.
3. Load a static grid and sweep known lateral/vertical points.
4. Run `truth` mode against the moving temporary ideal point.
5. Run `seek` mode and compare seeker center with the truth point only in telemetry.
6. Replace the temporary grid/model with the final computed wake.
7. Add spanwise differential wake effects if required.
