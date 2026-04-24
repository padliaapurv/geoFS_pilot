(function () {
  const instanceListEl = document.getElementById('instance-list');
  const selectedLabelEl = document.getElementById('selected-label');
  const bridgeStatusEl = document.getElementById('bridge-status');
  const aircraftNameEl = document.getElementById('aircraft-name');
  const autopilotStatusEl = document.getElementById('autopilot-status');
  const autopilotModeEl = document.getElementById('autopilot-mode');
  const altitudeReadoutEl = document.getElementById('altitude-readout');
  const headingReadoutEl = document.getElementById('heading-readout');
  const speedReadoutEl = document.getElementById('speed-readout');
  const vsReadoutEl = document.getElementById('vs-readout');
  const messageLogEl = document.getElementById('message-log');
  const commandButtons = Array.from(
    document.querySelectorAll('button[data-command]')
  );

  let uiSocket = null;
  let selectedBridgeId = null;
  let instances = [];
  const instanceNodes = new Map();

  function setMessage(text) {
    messageLogEl.textContent = text;
  }

  function setControlsEnabled(enabled) {
    commandButtons.forEach((button) => {
      button.disabled = !enabled;
    });
  }

  function setConnected(connected) {
    bridgeStatusEl.textContent = connected ? 'Connected' : 'Disconnected';
    bridgeStatusEl.className = connected ? 'ok' : 'bad';
  }

  function formatNumber(value, suffix) {
    if (value == null || Number.isNaN(Number(value))) return '-';
    return `${Math.round(Number(value))} ${suffix}`;
  }

  function resetDetails() {
    selectedLabelEl.textContent = 'None';
    aircraftNameEl.textContent = '-';
    altitudeReadoutEl.textContent = '-';
    headingReadoutEl.textContent = '-';
    speedReadoutEl.textContent = '-';
    vsReadoutEl.textContent = '-';
    autopilotStatusEl.textContent = '-';
    autopilotModeEl.textContent = '-';
  }

  function renderTelemetry(telemetry, label) {
    if (!telemetry) {
      resetDetails();
      return;
    }

    selectedLabelEl.textContent = label || telemetry.label || '-';
    aircraftNameEl.textContent = telemetry.aircraft || '-';
    altitudeReadoutEl.textContent = formatNumber(telemetry.altitude_ft, 'ft');
    headingReadoutEl.textContent = formatNumber(telemetry.heading_deg, 'deg');
    speedReadoutEl.textContent = formatNumber(telemetry.speed_kts, 'kt');
    vsReadoutEl.textContent = formatNumber(telemetry.vertical_speed_fpm, 'fpm');

    const autopilot = telemetry.autopilot || {};
    autopilotStatusEl.textContent = autopilot.on ? 'On' : 'Off';
    autopilotModeEl.textContent = autopilot.mode || '-';
  }

  function getSelectedInstance() {
    return (
      instances.find((instance) => instance.bridge_id === selectedBridgeId) || null
    );
  }

  function syncSelection() {
    const connected = instances.filter((instance) => instance.connected);
    const selected = getSelectedInstance();

    if (selected && selected.connected) return;

    if (connected.length === 1) {
      selectedBridgeId = connected[0].bridge_id;
      return;
    }

    if (!selected || !selected.connected) {
      selectedBridgeId = null;
    }
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
      <span class="instance-card-meta instance-card-mode"></span>
      <span class="instance-card-meta instance-card-flight"></span>
      <div class="instance-card-actions">
        <button type="button" class="instance-select-button">Select</button>
      </div>
    `;

    card
      .querySelector('.instance-select-button')
      .addEventListener('click', () => {
        selectedBridgeId = instance.bridge_id;
        setMessage(`Selected ${instance.label || instance.bridge_id}.`);
        renderView();
      });

    instanceNodes.set(instance.bridge_id, card);
    return card;
  }

  function patchInstanceNode(instance) {
    let card = instanceNodes.get(instance.bridge_id);
    if (!card) {
      card = createInstanceNode(instance);
    }

    const telemetry = instance.telemetry || {};
    const autopilot = telemetry.autopilot || {};
    const isSelected = instance.bridge_id === selectedBridgeId;
    const button = card.querySelector('.instance-select-button');
    const status = card.querySelector('.instance-card-status');

    card.classList.toggle('selected', isSelected);
    card.querySelector('.instance-card-label').textContent =
      instance.label || instance.bridge_id;
    status.textContent = instance.connected ? 'Connected' : 'Disconnected';
    status.className = `instance-card-status ${instance.connected ? 'ok' : 'bad'}`;
    card.querySelector('.instance-card-aircraft').textContent =
      telemetry.aircraft || instance.hello?.aircraft || '-';
    card.querySelector('.instance-card-mode').textContent = `Mode: ${
      autopilot.mode || '-'
    }`;
    card.querySelector('.instance-card-flight').textContent = `Alt: ${formatNumber(
      telemetry.altitude_ft,
      'ft'
    )} | Hdg: ${formatNumber(telemetry.heading_deg, 'deg')}`;
    button.textContent = isSelected ? 'Selected' : 'Select';
    button.classList.toggle('secondary', isSelected);

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
    if (emptyState) {
      instanceListEl.innerHTML = '';
    }

    instances.forEach((instance) => {
      const node = patchInstanceNode(instance);
      if (node.parentNode !== instanceListEl) {
        instanceListEl.appendChild(node);
      }
    });
  }

  function renderView() {
    syncSelection();
    renderInstances();

    const selected = getSelectedInstance();
    setConnected(Boolean(selected && selected.connected));
    setControlsEnabled(Boolean(selected && selected.connected));

    if (!selected) {
      resetDetails();
      return;
    }

    renderTelemetry(selected.telemetry, selected.label);
  }

  function sendCommand(command, value) {
    if (!uiSocket || uiSocket.readyState !== WebSocket.OPEN) {
      setMessage('UI socket is not connected.');
      return;
    }

    if (!selectedBridgeId) {
      setMessage('Select a GeoFS window first.');
      return;
    }

    const payload = {
      type: 'autopilot_command',
      bridge_id: selectedBridgeId,
      command,
    };
    if (value != null) payload.value = value;
    uiSocket.send(JSON.stringify(payload));
  }

  function attachButtons() {
    commandButtons.forEach((button) => {
      button.addEventListener('click', () => {
        const command = button.dataset.command;
        const inputId = button.dataset.input;

        if (!inputId) {
          sendCommand(command);
          return;
        }

        const input = document.getElementById(inputId);
        const value = Number(input.value);

        if (!Number.isFinite(value)) {
          setMessage(`Enter a valid value for ${command}.`);
          input.focus();
          return;
        }

        sendCommand(command, value);
      });
    });
  }

  function connectUiSocket() {
    uiSocket = new WebSocket(`ws://${window.location.host}/ui`);

    uiSocket.addEventListener('open', () => {
      setMessage('UI connected. Waiting for GeoFS bridge telemetry.');
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
          if (index >= 0) {
            instances[index] = next;
          } else {
            instances.push(next);
          }
          renderView();
        }
        return;
      }

      if (message.type === 'command_result') {
        setMessage(
          message.ok
            ? `Sent ${message.command} to ${message.bridge_id}${
                message.value != null ? ` = ${message.value}` : ''
              }.`
            : message.error || 'Command failed.'
        );
      }
    });

    uiSocket.addEventListener('close', () => {
      instances = [];
      selectedBridgeId = null;
      for (const node of instanceNodes.values()) {
        node.remove();
      }
      instanceNodes.clear();
      renderView();
      setMessage('UI socket disconnected. Retrying...');
      window.setTimeout(connectUiSocket, 1000);
    });
  }

  attachButtons();
  setControlsEnabled(false);
  connectUiSocket();
})();
