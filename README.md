# GeoFS formation pilot

```bash
npm install
npm start
```

Open `http://127.0.0.1:52137` and connect two GeoFS browser windows with `js/geofs_bridge.user.js` enabled in Tampermonkey.

The app assigns one connected GeoFS window as the leader and another as the follower. It resets them to a starting formation with the follower behind the leader, reads telemetry from both windows, and continuously commands the follower to track a point behind the leader. Placeholder wake-injection functions are present in `public/app.js` for future wake modeling.
