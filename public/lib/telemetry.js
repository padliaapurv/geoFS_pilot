(function () {
  function finiteNumber(...values) {
    for (const value of values) {
      const number = Number(value);
      if (Number.isFinite(number)) return number;
    }
    return null;
  }

  function telemetryFor(instance) {
    const telemetry = instance?.telemetry || null;
    if (!telemetry) return {};
    const lla = Array.isArray(telemetry.lla) ? telemetry.lla : [];
    const htr = Array.isArray(telemetry.htr) ? telemetry.htr : [];
    const altitudeMeters = finiteNumber(telemetry.altitudeMeters, lla[2]);
    const speedKts = finiteNumber(
      telemetry.speed_kts,
      telemetry.ktas,
      telemetry.kias,
      telemetry.groundSpeedKnt,
      telemetry.groundSpeedMS != null ? Number(telemetry.groundSpeedMS) * 1.94384 : null,
      telemetry.speedMS != null ? Number(telemetry.speedMS) * 1.94384 : null
    );

    return {
      raw: telemetry,
      aircraft: telemetry.aircraft || instance?.hello?.aircraft || instance?.label || '-',
      lat_deg: finiteNumber(telemetry.lat_deg, lla[0]),
      lon_deg: finiteNumber(telemetry.lon_deg, lla[1]),
      altitude_ft: finiteNumber(
        telemetry.altitude_ft,
        telemetry.altitudeFeet,
        altitudeMeters != null ? altitudeMeters * 3.28084 : null
      ),
      heading_deg: finiteNumber(telemetry.heading_deg, telemetry.headingDeg, htr[0]),
      pitch_deg: finiteNumber(telemetry.pitch_deg, telemetry.tiltDeg, htr[1]),
      roll_deg: finiteNumber(telemetry.roll_deg, telemetry.rollDeg, htr[2]),
      speed_kts: speedKts,
      throttle: finiteNumber(telemetry.throttle),
      time: finiteNumber(telemetry.time),
    };
  }

  window.GeoFsTelemetry = {
    telemetryFor,
  };
})();
