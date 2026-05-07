(function () {
  function normalizeHeading(degrees) {
    return ((Number(degrees) % 360) + 360) % 360;
  }

  function shortestHeadingDelta(fromDeg, toDeg) {
    return ((normalizeHeading(toDeg) - normalizeHeading(fromDeg) + 540) % 360) - 180;
  }

  function degToRad(degrees) {
    return (Number(degrees) * Math.PI) / 180;
  }

  function radToDeg(radians) {
    return (Number(radians) * 180) / Math.PI;
  }

  function hasPosition(telemetry) {
    return (
      telemetry &&
      Number.isFinite(Number(telemetry.lat_deg)) &&
      Number.isFinite(Number(telemetry.lon_deg))
    );
  }

  function offsetPositionByNm(origin, bearingDeg, distanceNm) {
    const radiusNm = 3440.065;
    const lat1 = degToRad(origin.lat_deg);
    const lon1 = degToRad(origin.lon_deg);
    const bearing = degToRad(bearingDeg);
    const angularDistance = distanceNm / radiusNm;

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
      lat_deg: radToDeg(lat2),
      lon_deg: ((radToDeg(lon2) + 540) % 360) - 180,
    };
  }

  function distanceNm(a, b) {
    if (!hasPosition(a) || !hasPosition(b)) return null;
    const radiusNm = 3440.065;
    const lat1 = degToRad(a.lat_deg);
    const lat2 = degToRad(b.lat_deg);
    const dLat = degToRad(b.lat_deg - a.lat_deg);
    const dLon = degToRad(b.lon_deg - a.lon_deg);
    const h =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
    return 2 * radiusNm * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
  }

  function bearingDeg(a, b) {
    if (!hasPosition(a) || !hasPosition(b)) return null;
    const lat1 = degToRad(a.lat_deg);
    const lat2 = degToRad(b.lat_deg);
    const dLon = degToRad(b.lon_deg - a.lon_deg);
    const y = Math.sin(dLon) * Math.cos(lat2);
    const x =
      Math.cos(lat1) * Math.sin(lat2) -
      Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
    return normalizeHeading(radToDeg(Math.atan2(y, x)));
  }

  window.GeoFsGeo = {
    normalizeHeading,
    shortestHeadingDelta,
    hasPosition,
    offsetPositionByNm,
    distanceNm,
    bearingDeg,
  };
})();
