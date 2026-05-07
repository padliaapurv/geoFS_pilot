(function () {
  const EARTH_RADIUS_M = 6371008.8;
  const { normalizeAngleRad } = window.GeoFsAngles;

  function hasPosition(telemetry) {
    return (
      telemetry &&
      Number.isFinite(Number(telemetry.lat_rad)) &&
      Number.isFinite(Number(telemetry.lon_rad))
    );
  }

  function normalizeLonRad(lonRad) {
    return ((Number(lonRad) + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
  }

  function offsetPosition(origin, bearingRad, distanceM) {
    const lat1 = Number(origin.lat_rad);
    const lon1 = Number(origin.lon_rad);
    const angularDistance = Number(distanceM) / EARTH_RADIUS_M;
    const bearing = Number(bearingRad);

    const lat2 = Math.asin(
      Math.sin(lat1) * Math.cos(angularDistance) +
        Math.cos(lat1) * Math.sin(angularDistance) * Math.cos(bearing)
    );
    const lon2 =
      lon1 +
      Math.atan2(
        Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(lat1),
        Math.cos(angularDistance) - Math.sin(lat1) * Math.sin(lat2)
      );

    return {
      lat_rad: lat2,
      lon_rad: normalizeLonRad(lon2),
    };
  }

  function distanceMeters(a, b) {
    if (!hasPosition(a) || !hasPosition(b)) return null;
    const lat1 = Number(a.lat_rad);
    const lat2 = Number(b.lat_rad);
    const dLat = lat2 - lat1;
    const dLon = Number(b.lon_rad) - Number(a.lon_rad);
    const h =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
    return 2 * EARTH_RADIUS_M * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
  }

  function bearingRad(a, b) {
    if (!hasPosition(a) || !hasPosition(b)) return null;
    const lat1 = Number(a.lat_rad);
    const lat2 = Number(b.lat_rad);
    const dLon = Number(b.lon_rad) - Number(a.lon_rad);
    const y = Math.sin(dLon) * Math.cos(lat2);
    const x =
      Math.cos(lat1) * Math.sin(lat2) -
      Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
    return normalizeAngleRad(Math.atan2(y, x));
  }

  window.GeoFsGeodesy = {
    EARTH_RADIUS_M,
    hasPosition,
    offsetPosition,
    distanceMeters,
    bearingRad,
  };
})();
