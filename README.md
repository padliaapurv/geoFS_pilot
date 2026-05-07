# GeoFS formation pilot

```bash
npm install
npm start
```

Open `http://127.0.0.1:52137` and connect two GeoFS browser windows with `js/geofs_bridge.user.js` enabled in Tampermonkey.

The Tampermonkey geoBridge script is the source of truth for telemetry and supported commands. It connects each GeoFS tab to the local WebSocket server, streams the camelCase geoBridge telemetry payload, and accepts the supported `control_enable`, `control_disable`, `controls_neutral`, `controls_set`, and `discrete` commands.

The web app assigns one connected GeoFS window as the leader and another as the follower. It normalizes the synced Tampermonkey telemetry for display/control math, then sends supported continuous control commands to the follower so it tracks a point behind the leader. Placeholder wake-injection functions are present in `public/app.js` for future wake modeling.
