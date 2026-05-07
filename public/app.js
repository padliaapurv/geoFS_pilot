(function () {
  const instanceListEl = document.getElementById('instance-list');
  const bridgeStatusEl = document.getElementById('bridge-status');
  const leaderLabelEl = document.getElementById('leader-label');
  const followerLabelEl = document.getElementById('follower-label');
  const formationStatusEl = document.getElementById('formation-status');
  const spacingReadoutEl = document.getElementById('spacing-readout');
  const leaderTelemetryEl = document.getElementById('leader-telemetry');
  const followerTelemetryEl = document.getElementById('follower-telemetry');
  const messageLogEl = document.getElementById('message-log');
  const resetFormationButton = document.getElementById('reset-formation');
  const followToggleButton = document.getElementById('follow-toggle');

  const CONFIG = {
    controlHz: 4,
    commandIntervalMs: 250,
    requiredAircraft: 2,
    desiredSpacingNm: 0.75,
    startPose: {
      lat_deg: 37.618999,
      lon_deg: -122.375,
      altitude_ft: 3500,
      heading_deg: 270,
      speed_kts: 150,
    },
    gains: {
      closureKtsPerNm: 35,
      maxClosureKts: 35,
    },
  };

  let uiSocket = null;
  let instances = [];
  let leaderBridgeId = null;
  let followerBridgeId = null;
  let controlEnabled = true;
  let initialResetSent = false;
  let lastCommandSentAt = 0;
  let controlTimer = null;
  const instanceNodes = new Map();

  function setMessage(text) {
    messageLogEl.textContent = text;
  }

  function setBridgeStatus(connectedCount) {
    const ready = connectedCount >= CONFIG.requiredAircraft;
    bridgeStatusEl.textContent = ready
      ? `${connectedCount} aircraft connected`
      : `${connectedCount}/${CONFIG.requiredAircraft} aircraft connected`;
    bridgeStatusEl.className = ready ? 'ok' : 'bad';
  }

  function formatNumber(value, suffix, digits = 0) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '-';
    return `${number.toFixed(digits)} ${suffix}`;
  }


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

  function hasPosition(telemetry) {
    return (
      telemetry &&
      Number.isFinite(Number(telemetry.lat_deg)) &&
      Number.isFinite(Number(telemetry.lon_deg))
    );
  }

  function connectedInstances() {
    return instances.filter((instance) => instance.connected);
  }

  function instanceById(bridgeId) {
    return instances.find((instance) => instance.bridge_id === bridgeId) || null;
  }

  function syncRoles() {
    const connected = connectedInstances();
    if (!connected.some((instance) => instance.bridge_id === leaderBridgeId)) {
      leaderBridgeId = connected[0]?.bridge_id || null;
    }
    if (
      !connected.some((instance) => instance.bridge_id === followerBridgeId) ||
      followerBridgeId === leaderBridgeId
    ) {
      followerBridgeId =
        connected.find((instance) => instance.bridge_id !== leaderBridgeId)?.bridge_id ||
        null;
    }
  }

  function setRole(bridgeId, role) {
    if (role === 'leader') {
      leaderBridgeId = bridgeId;
      if (followerBridgeId === bridgeId) followerBridgeId = null;
    } else {
      followerBridgeId = bridgeId;
      if (leaderBridgeId === bridgeId) leaderBridgeId = null;
    }
    syncRoles();
    initialResetSent = false;
    renderView();
  }

  function createInstanceNode(instance) {
    const card = document.createElement('div');
    card.className = 'instance-card';
    card.dataset.bridgeId = instance.bridge_id;
    card.innerHTML = `
      <span class="instance-card-header">
        <strong class="instance-card-label"></strong>
        <span class="instance-card-status"></span>
      </span>
      <span class="instance-card-meta instance-card-aircraft"></span>
      <span class="instance-card-meta instance-card-flight"></span>
      <div class="instance-card-actions">
        <button type="button" class="leader-button">Leader</button>
      </div>
    `;
    card.querySelector('.leader-button').addEventListener('click', () => {
      setRole(instance.bridge_id, 'leader');
      setMessage(`Assigned ${instance.label || instance.bridge_id} as leader.`);
    });
    instanceNodes.set(instance.bridge_id, card);
    return card;
  }

  function patchInstanceNode(instance) {
    let card = instanceNodes.get(instance.bridge_id);
    if (!card) card = createInstanceNode(instance);

    const telemetry = telemetryFor(instance);
    const isLeader = instance.bridge_id === leaderBridgeId;
    const isFollower = instance.bridge_id === followerBridgeId;
    const status = card.querySelector('.instance-card-status');
    const leaderButton = card.querySelector('.leader-button');

    card.classList.toggle('leader', isLeader);
    card.classList.toggle('follower', isFollower);
    card.querySelector('.instance-card-label').textContent =
      instance.label || instance.bridge_id;
    status.textContent = instance.connected ? 'Connected' : 'Disconnected';
    status.className = `instance-card-status ${instance.connected ? 'ok' : 'bad'}`;
    card.querySelector('.instance-card-aircraft').textContent =
      telemetry.aircraft || instance.hello?.aircraft || '-';
    card.querySelector('.instance-card-flight').textContent = `Alt: ${formatNumber(
      telemetry.altitude_ft,
      'ft'
    )} | Hdg: ${formatNumber(telemetry.heading_deg, 'deg')}`;
    leaderButton.textContent = isLeader ? 'Leader' : 'Make leader';
    leaderButton.classList.toggle('secondary', !isLeader);

    return card;
  }

  function renderInstances() {
    const nextIds = new Set(instances.map((instance) => instance.bridge_id));
    for (const [bridgeId, node] of instanceNodes.entries()) {
      if (!nextIds.has(bridgeId)) {
        node.remove();
        instanceNodes.delete(bridgeId);
      }
    }

    if (!instances.length) {
      instanceListEl.innerHTML = '<p class="empty-state">No GeoFS windows connected.</p>';
      instanceNodes.clear();
      return;
    }

    const emptyState = instanceListEl.querySelector('.empty-state');
    if (emptyState) instanceListEl.innerHTML = '';

    instances.forEach((instance) => {
      const node = patchInstanceNode(instance);
      if (node.parentNode !== instanceListEl) instanceListEl.appendChild(node);
    });
  }

  function telemetryLine(instance) {
    const telemetry = telemetryFor(instance);
    return [
      instance?.label || '-',
      formatNumber(telemetry.altitude_ft, 'ft'),
      formatNumber(telemetry.heading_deg, 'deg'),
      formatNumber(telemetry.speed_kts, 'kt'),
      hasPosition(telemetry)
        ? `${Number(telemetry.lat_deg).toFixed(5)}, ${Number(telemetry.lon_deg).toFixed(5)}`
        : 'position -',
    ].join(' | ');
  }

  function renderView() {
    syncRoles();
    renderInstances();

    const connectedCount = connectedInstances().length;
    const leader = instanceById(leaderBridgeId);
    const follower = instanceById(followerBridgeId);
    const spacing = distanceNm(telemetryFor(leader), telemetryFor(follower));
    const ready = Boolean(leader?.connected && follower?.connected);

    setBridgeStatus(connectedCount);
    leaderLabelEl.textContent = leader?.label || 'Waiting for leader';
    followerLabelEl.textContent = follower?.label || 'Waiting for follower';
    formationStatusEl.textContent = ready
      ? controlEnabled
        ? 'Following active'
        : 'Following paused'
      : 'Waiting for two connected GeoFS windows';
    formationStatusEl.className = ready ? 'ok' : 'bad';
    spacingReadoutEl.textContent = spacing == null ? '-' : formatNumber(spacing, 'nm', 2);
    leaderTelemetryEl.textContent = telemetryLine(leader);
    followerTelemetryEl.textContent = telemetryLine(follower);
    resetFormationButton.disabled = !ready;
    followToggleButton.disabled = !ready;
    followToggleButton.textContent = controlEnabled ? 'Pause following' : 'Resume following';

    if (ready && !initialResetSent) {
      initialResetSent = true;
      resetFormation();
    }
  }

  function sendCommand(bridgeId, command, fields = {}) {
    if (!uiSocket || uiSocket.readyState !== WebSocket.OPEN || !bridgeId) return;
    uiSocket.send(
      JSON.stringify({
        type: 'autopilot_command',
        bridge_id: bridgeId,
        command,
        ...fields,
      })
    );
  }

  function resetFormation() {
    const follower = instanceById(followerBridgeId);
    if (!follower?.connected) {
      setMessage('Connect a follower GeoFS window before priming the formation controls.');
      return;
    }

    sendCommand(follower.bridge_id, 'control_enable');
    sendCommand(follower.bridge_id, 'controls_neutral');
    lastCommandSentAt = 0;
    setMessage('Follower controls primed from the synced Tampermonkey geoBridge API. Hand-fly the leader; the follower will track behind it.');
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function wakeFromLeaderToFollower(_leaderTelemetry, _followerTelemetry) {
    return null;
  }

  function injectWakeIntoFollowerCommand(followerCommand, _wakeModel) {
    return followerCommand;
  }

  function buildFollowerCommand(leaderTelemetry, followerTelemetry) {
    if (!hasPosition(leaderTelemetry) || !hasPosition(followerTelemetry)) return null;

    const leaderHeading = normalizeHeading(
      leaderTelemetry.heading_deg || CONFIG.startPose.heading_deg
    );
    const targetPosition = offsetPositionByNm(
      leaderTelemetry,
      leaderHeading + 180,
      CONFIG.desiredSpacingNm
    );
    const spacing = distanceNm(leaderTelemetry, followerTelemetry);
    const rangeToTarget = distanceNm(followerTelemetry, targetPosition) || 0;
    const headingToTarget = bearingDeg(followerTelemetry, targetPosition);
    if (headingToTarget == null) return null;

    const closure = clamp(
      rangeToTarget * CONFIG.gains.closureKtsPerNm,
      0,
      CONFIG.gains.maxClosureKts
    );
    const leaderSpeed = Number(leaderTelemetry.speed_kts) || CONFIG.startPose.speed_kts;
    const targetSpeed =
      spacing != null && spacing < CONFIG.desiredSpacingNm * 0.5
        ? Math.max(90, leaderSpeed - CONFIG.gains.maxClosureKts)
        : leaderSpeed + closure;
    const headingError = shortestHeadingDelta(followerTelemetry.heading_deg || 0, headingToTarget);
    const altitudeError =
      (Number(leaderTelemetry.altitude_ft) || CONFIG.startPose.altitude_ft) -
      (Number(followerTelemetry.altitude_ft) || CONFIG.startPose.altitude_ft);
    const speedError = targetSpeed - (Number(followerTelemetry.speed_kts) || targetSpeed);
    const throttleBase =
      Number.isFinite(Number(followerTelemetry.throttle)) ? Number(followerTelemetry.throttle) : 0.65;

    return {
      controls: {
        roll: clamp(headingError / 35, -0.8, 0.8),
        pitch: clamp(altitudeError / 1500, -0.4, 0.4),
        yaw: 0,
        throttle: clamp(throttleBase + speedError / 120, 0, 1),
      },
      target_spacing_nm: CONFIG.desiredSpacingNm,
      current_spacing_nm: spacing,
      heading_error_deg: headingError,
    };
  }

  function controlFormation() {
    if (!controlEnabled) return;
    const now = Date.now();
    if (now - lastCommandSentAt < CONFIG.commandIntervalMs) return;

    const leader = instanceById(leaderBridgeId);
    const follower = instanceById(followerBridgeId);
    const leaderTelemetry = telemetryFor(leader);
    const followerTelemetry = telemetryFor(follower);
    if (!leader?.connected || !follower?.connected || !leaderTelemetry || !followerTelemetry) {
      return;
    }


    const wake = wakeFromLeaderToFollower(leaderTelemetry, followerTelemetry);
    const followerCommand = injectWakeIntoFollowerCommand(
      buildFollowerCommand(leaderTelemetry, followerTelemetry),
      wake
    );
    if (!followerCommand) return;

    sendCommand(follower.bridge_id, 'controls_set', { controls: followerCommand.controls });
    lastCommandSentAt = now;
  }

  function startControlLoop() {
    if (controlTimer) window.clearInterval(controlTimer);
    controlTimer = window.setInterval(controlFormation, 1000 / CONFIG.controlHz);
  }

  function connectUiSocket() {
    uiSocket = new WebSocket(`ws://${window.location.host}/ui`);

    uiSocket.addEventListener('open', () => {
      setMessage('UI connected. Waiting for two GeoFS bridge telemetry streams.');
    });

    uiSocket.addEventListener('message', (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }

      if (message.type === 'snapshot') {
        instances = Array.isArray(message.instances) ? message.instances : [];
        renderView();
        return;
      }

      if (message.type === 'telemetry') {
        const next = message.instance;
        if (next) {
          const index = instances.findIndex(
            (instance) => instance.bridge_id === next.bridge_id
          );
          if (index >= 0) instances[index] = next;
          else instances.push(next);
          renderView();
        }
        return;
      }

      if (message.type === 'command_result' && !message.ok) {
        setMessage(message.error || 'Command failed.');
      }
    });

    uiSocket.addEventListener('close', () => {
      instances = [];
      leaderBridgeId = null;
      followerBridgeId = null;
      initialResetSent = false;
      for (const node of instanceNodes.values()) node.remove();
      instanceNodes.clear();
      renderView();
      setMessage('UI socket disconnected. Retrying...');
      window.setTimeout(connectUiSocket, 1000);
    });
  }

  resetFormationButton.addEventListener('click', () => {
    initialResetSent = true;
    resetFormation();
  });

  followToggleButton.addEventListener('click', () => {
    controlEnabled = !controlEnabled;
    const follower = instanceById(followerBridgeId);
    if (follower?.connected) {
      sendCommand(follower.bridge_id, controlEnabled ? 'control_enable' : 'control_disable');
    }
    renderView();
  });

  connectUiSocket();
  startControlLoop();
})();
