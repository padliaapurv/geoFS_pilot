# GeoFS Boeing 777-200 trim test

This repository contains one GeoFS userscript for one test case:

- aircraft: Boeing 777-200
- flight condition: steady, level flight
- target lift coefficient: `CL = 0.5`

The script computes the required true airspeed from

```text
L = W = 0.5 * rho * V^2 * S * CL
Vtrim = sqrt(2 * m * g / (rho * S * CL))
```

It uses:

- Boeing 777-200 wing area: `S = 427.8 m^2`
- GeoFS aircraft mass when that value is available
- ISA density at the commanded altitude
- GeoFS autopilot for altitude, heading, and KIAS speed hold

## Run

1. Install Tampermonkey.
2. Add `js/b777_trim.user.js` as a userscript.
3. Open GeoFS.
4. Select the Boeing 777-200.
5. Open the browser console.
6. Run:

```js
b777Trim.start()
```

The default target is `CL = 0.5`. If the aircraft starts near the ground, the script tries to place it at 10,000 ft before it enables the GeoFS autopilot.

Use a specific mass or altitude when required:

```js
b777Trim.start({
  cl: 0.5,
  massKg: 200000,
  altitudeFt: 10000,
  headingDeg: 90,
})
```

Read the current trim state:

```js
b777Trim.status()
```

The script converts the `CL` target to the equivalent KIAS command used by the GeoFS autopilot. It uses actual TAS and ISA density to estimate the aerodynamic `CL`.

The status includes target KIAS, target TAS, actual KIAS, actual TAS, estimated `CL`, altitude error, vertical speed, angle of attack, pitch, and throttle. The script reports `trim converged` after the speed, altitude, and vertical-speed errors remain inside the set tolerances for five seconds.
