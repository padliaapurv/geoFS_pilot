(function () {
  const { finiteNumber } = window.GeoFsMath;
  const {
    degreesToRadians,
    feetToMeters,
    knotsToMetersPerSecond,
  } = window.GeoFsUnits;
  const { normalizeAngleRad } = window.GeoFsAngles;

  function finiteRadiansFromDegrees(...values) {
    const value = finiteNumber(...values);
    return value == null ? null : degreesToRadians(value);
  }

  function finiteRadians(rawRadians, ...degreeValues) {
    const radians = finiteNumber(rawRadians);
    return radians == null ? finiteRadiansFromDegrees(...degreeValues) : radians;
  }

  function telemetryFor(instance) {
    const telemetry = instance?.telemetry || null;
    if (!telemetry) return {};
    const lla = Array.isArray(telemetry.lla) ? telemetry.lla : [];
    const htr = Array.isArray(telemetry.htr) ? telemetry.htr : [];
    const altitudeM = finiteNumber(
      telemetry.altitude_m,
      telemetry.altitudeMeters,
      lla[2],
      telemetry.altitude_ft != null ? feetToMeters(telemetry.altitude_ft) : null,
      telemetry.altitudeFeet != null ? feetToMeters(telemetry.altitudeFeet) : null
    );
    const speedMps = finiteNumber(
      telemetry.speed_mps,
      telemetry.speedMS,
      telemetry.groundSpeedMS,
      telemetry.airspeedMS,
      telemetry.speed_kts != null ? knotsToMetersPerSecond(telemetry.speed_kts) : null,
      telemetry.ktas != null ? knotsToMetersPerSecond(telemetry.ktas) : null,
      telemetry.kias != null ? knotsToMetersPerSecond(telemetry.kias) : null,
      telemetry.groundSpeedKnt != null ? knotsToMetersPerSecond(telemetry.groundSpeedKnt) : null
    );

    const headingRad = finiteRadiansFromDegrees(
      telemetry.heading_deg,
      telemetry.headingDeg,
      htr[0]
    );

    return {
      raw: telemetry,
      aircraft: telemetry.aircraft || instance?.hello?.aircraft || instance?.label || '-',
      lat_rad: finiteRadians(telemetry.lat_rad, telemetry.lat_deg, lla[0]),
      lon_rad: finiteRadians(telemetry.lon_rad, telemetry.lon_deg, lla[1]),
      altitude_m: altitudeM,
      heading_rad: headingRad == null ? null : normalizeAngleRad(headingRad),
      pitch_rad: finiteRadiansFromDegrees(telemetry.pitch_deg, telemetry.tiltDeg, htr[1]),
      roll_rad: finiteRadiansFromDegrees(telemetry.roll_deg, telemetry.rollDeg, htr[2]),
      speed_mps: speedMps,
      throttle: finiteNumber(telemetry.throttle),
      time: finiteNumber(telemetry.time),
    };
  }

  window.GeoFsTelemetry = {
    telemetryFor,
  };
})();
