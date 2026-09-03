# GeoFS Boeing 777-200 wake simulation

This repository uses the native GeoFS Boeing 777-200 flight model to test wake following and peak seeking.

The current system has:

- Boeing 777-200 trim at `CL = 0.5`
- two GeoFS tabs: leader and follower
- leader-to-follower state transfer with browser `BroadcastChannel`
- a local 3-D wake velocity input
- a loadable 2-D wake grid
- a temporary moving vortex/wake model
- fixed-point, truth-tracking, and peak-seeking modes
- run history and CSV output

No Node server is required.

## Install

Install `js/geofs_wake_sim.user.js` in Tampermonkey.

Open two GeoFS tabs. Select the Boeing 777-200 in both tabs.

## 1. Start the leader

In the first tab:

```js
geofsWake.startLeader({
  cl: 0.5,
  altitudeFt: 10000,
  headingDeg: 90,
  massKg: 200000,
})
```

The leader holds the `CL = 0.5` trim KIAS, altitude, and heading.

## 2. Start the follower

In the second tab:

```js
geofsWake.startFollower({
  cl: 0.5,
  massKg: 200000,
  targetDownstreamM: 300,
  initialCrossM: 0,
  initialVerticalM: 0,
  mode: 'seek',
})
```

The follower is placed approximately 300 m behind the leader. It receives leader state, evaluates the wake at its current relative position, and injects that wake into the GeoFS wind input.

## Load your wake grid

Load the grid in the follower tab before `startFollower()`:

```js
geofsWake.grid.load({
  xM,             // lateral coordinates, m; positive right
  yM,             // vertical coordinates, m; positive up
  uMps,           // forward physical air-mass velocity, [y][x]
  vMps,           // lateral physical air-mass velocity, [y][x]
  wMps,           // vertical physical air-mass velocity, [y][x]
  ideal: { xM: 25, yM: 5 }, // optional; used only for truth/debug
})
```

If the grid only has cross-plane velocity:

```js
geofsWake.grid.load({ xM, yM, vxMps, vyMps })
```

This maps `vxMps -> vMps`, `vyMps -> wMps`, and sets `uMps = 0`.

The sampler uses bilinear interpolation. See `docs/DESIGN.md` for sign conventions and optional downstream settings.

## Modes

Use one of these modes:

```js
geofsWake.guidance.setMode('hold')
geofsWake.guidance.setMode('truth')
geofsWake.guidance.setMode('seek')
```

`hold` keeps a fixed lateral/vertical point. Use it to validate wake injection first.

`truth` follows the known temporary/grid ideal point. Use it to validate formation guidance.

`seek` does not command the known ideal point. It dithers lateral and vertical position and moves the dither center using the measured follower objective. The placeholder objective rewards lower throttle while the aircraft holds speed and altitude.

## Useful commands

```js
geofsWake.status()
geofsWake.guidance.hold(20, 5)
geofsWake.data.history()
geofsWake.data.csv()
geofsWake.grid.example()
geofsWake.grid.clear()
geofsWake.stop()
```

## Testing

The coordinate transforms, grid interpolation, extremum-seeking controller, and leader/follower runtime loop are covered by an offline Node test suite that mocks the GeoFS globals (`geofs`, `weather`, `controls`, `performance`, `BroadcastChannel`). It requires Node 18+ and no other dependencies.

```sh
npm test
```

This does not replace testing in a real browser: the mocked `geofs.autopilot` API surface (`setCourse`/`setAltitude`/`setSpeed`/`turnOn`, with several documented fallbacks) is a best guess at GeoFS's real API from reading `js/wake/core.js`, and only an actual GeoFS session can confirm those calls exist and behave as assumed.

## Implementation

The follower writes a dynamic east-north-up vector to `weather.currentWindVector`. GeoFS uses this vector in its native air-relative velocity and airfoil calculations. The script therefore does not replace the Boeing 777 flight model.

The current injection is one wake vector at the aircraft reference point. It does not yet apply different velocity values across the wing span. The next fidelity step is described in `docs/DESIGN.md`.
