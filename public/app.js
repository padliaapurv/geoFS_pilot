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
  const followToggleButton = document.getElementById('follow-toggle');
  const resetButton = document.getElementById('reset-formation');

  const CONFIG = {
    controlHz: 4,
    commandIntervalMs: 250,
    requiredAircraft: 2,
    startPose: {
      lat_rad: window.GeoFsUnits.degreesToRadians(37.618999),
      lon_rad: window.GeoFsUnits.degreesToRadians(-122.375),
      altitude_m: window.GeoFsUnits.feetToMeters(3500),
      heading_rad: window.GeoFsUnits.degreesToRadians(270),
      speed_mps: window.GeoFsUnits.knotsToMetersPerSecond(150),
    },
    resetOffset: {
      behind_m: 1000,
      right_m: 100,
      above_m: 100,
    },
  };

  const { telemetryFor } = window.GeoFsTelemetry;
  const { distanceMeters, hasPosition } = window.GeoFsGeodesy;
  const { buildFollowerCommands, buildResetCommands } = window.GeoFsFormation;
  const Commands = window.GeoFsCommands;

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

  function formatPosition(telemetry) {
    if (!hasPosition(telemetry)) return 'position -';
    return `${Number(telemetry.lat_rad).toFixed(6)} rad, ${Number(
      telemetry.lon_rad
    ).toFixed(6)} rad`;
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
      telemetry.altitude_m,
      'm'
    )} | Hdg: ${formatNumber(telemetry.heading_rad, 'rad', 3)}`;
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
      formatNumber(telemetry.altitude_m, 'm'),
      formatNumber(telemetry.heading_rad, 'rad', 3),
      formatNumber(telemetry.speed_mps, 'm/s', 1),
      formatPosition(telemetry),
    ].join(' | ');
  }

  function algorithmTelemetryFor(instance) {
    const { raw: _raw, ...telemetry } = telemetryFor(instance);
    return telemetry;
  }

  function sendCommand(bridgeId, commandOrCommands) {
    const commands = Array.isArray(commandOrCommands)
      ? commandOrCommands
      : [commandOrCommands];
    if (!uiSocket || uiSocket.readyState !== WebSocket.OPEN || !bridgeId) return;

    commands.filter(Boolean).forEach((command) => {
      uiSocket.send(
        JSON.stringify({
          type: 'autopilot_command',
          bridge_id: bridgeId,
          ...command,
        })
      );
    });
  }

  function readyPair() {
    const leader = instanceById(leaderBridgeId);
    const follower = instanceById(followerBridgeId);
    if (!leader?.connected || !follower?.connected) return null;
    return { leader, follower };
  }

  function resetFormation() {
    const pair = readyPair();
    if (!pair) {
      setMessage('Connect a leader and follower GeoFS window before resetting.');
      return;
    }

    const leaderTelemetry = algorithmTelemetryFor(pair.leader);
    const commands = buildResetCommands(CONFIG, leaderTelemetry);
    if (!commands.length) {
      setMessage('Leader telemetry does not include a usable SI position yet.');
      return;
    }

    sendCommand(pair.follower.bridge_id, commands);
    lastCommandSentAt = 0;
    setMessage('Follower reset 1000 m behind, 100 m right, and 100 m above the leader.');
  }

  function renderView() {
    syncRoles();
    renderInstances();

    const connectedCount = connectedInstances().length;
    const leader = instanceById(leaderBridgeId);
    const follower = instanceById(followerBridgeId);
    const leaderTelemetry = telemetryFor(leader);
    const followerTelemetry = telemetryFor(follower);
    const spacing = distanceMeters(leaderTelemetry, followerTelemetry);
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
    spacingReadoutEl.textContent = spacing == null ? '-' : formatNumber(spacing, 'm', 0);
    leaderTelemetryEl.textContent = telemetryLine(leader);
    followerTelemetryEl.textContent = telemetryLine(follower);
    followToggleButton.disabled = !ready;
    resetButton.disabled = !ready;
    followToggleButton.textContent = controlEnabled ? 'Pause following' : 'Resume following';

    if (ready && !initialResetSent) {
      initialResetSent = true;
      resetFormation();
    }
  }

  function controlFormation() {
    if (!controlEnabled) return;
    const now = Date.now();
    if (now - lastCommandSentAt < CONFIG.commandIntervalMs) return;

    const pair = readyPair();
    if (!pair) return;

    const commands = buildFollowerCommands(
      CONFIG,
      algorithmTelemetryFor(pair.leader),
      algorithmTelemetryFor(pair.follower)
    );
    if (!commands.length) return;

    sendCommand(pair.follower.bridge_id, commands);
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

  followToggleButton.addEventListener('click', () => {
    controlEnabled = !controlEnabled;
    const follower = instanceById(followerBridgeId);
    if (follower?.connected) {
      sendCommand(
        follower.bridge_id,
        controlEnabled
          ? [Commands.autopilotEnable()]
          : [Commands.autopilotDisable(), Commands.controlsNeutral()]
      );
    }
    renderView();
  });

  resetButton.addEventListener('click', () => {
    initialResetSent = true;
    resetFormation();
  });

  connectUiSocket();
  startControlLoop();
})();
