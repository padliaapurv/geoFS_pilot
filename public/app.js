(function () {
  const bridgeStatusEl = document.getElementById('bridge-status');
  const aircraftNameEl = document.getElementById('aircraft-name');
  const autopilotStatusEl = document.getElementById('autopilot-status');
  const autopilotModeEl = document.getElementById('autopilot-mode');
  const altitudeReadoutEl = document.getElementById('altitude-readout');
  const headingReadoutEl = document.getElementById('heading-readout');
  const speedReadoutEl = document.getElementById('speed-readout');
  const vsReadoutEl = document.getElementById('vs-readout');
  const messageLogEl = document.getElementById('message-log');

  let uiSocket = null;

  function setMessage(text) {
    messageLogEl.textContent = text;
  }

  function setConnected(connected) {
    bridgeStatusEl.textContent = connected ? 'Connected' : 'Disconnected';
    bridgeStatusEl.className = connected ? 'ok' : 'bad';
  }

  function formatNumber(value, suffix) {
    if (value == null || Number.isNaN(Number(value))) return '-';
    return `${Math.round(Number(value))} ${suffix}`;
  }

  function renderTelemetry(telemetry) {
    if (!telemetry) return;

    aircraftNameEl.textContent = telemetry.aircraft || '-';
    altitudeReadoutEl.textContent = formatNumber(telemetry.altitude_ft, 'ft');
    headingReadoutEl.textContent = formatNumber(telemetry.heading_deg, 'deg');
    speedReadoutEl.textContent = formatNumber(telemetry.speed_kts, 'kt');
    vsReadoutEl.textContent = formatNumber(telemetry.vertical_speed_fpm, 'fpm');

    const autopilot = telemetry.autopilot || {};
    autopilotStatusEl.textContent = autopilot.on ? 'On' : 'Off';
    autopilotModeEl.textContent = autopilot.mode || '-';
  }

  function renderSnapshot(message) {
    setConnected(Boolean(message.bridge_connected));
    renderTelemetry(message.telemetry);
  }

  function sendCommand(command, value) {
    if (!uiSocket || uiSocket.readyState !== WebSocket.OPEN) {
      setMessage('UI socket is not connected.');
      return;
    }

    const payload = { type: 'autopilot_command', command };
    if (value != null) payload.value = value;
    uiSocket.send(JSON.stringify(payload));
  }

  function attachButtons() {
    document.querySelectorAll('button[data-command]').forEach((button) => {
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
        renderSnapshot(message);
        return;
      }

      if (message.type === 'telemetry') {
        setConnected(Boolean(message.bridge_connected));
        renderTelemetry(message.telemetry);
        return;
      }

      if (message.type === 'command_result') {
        setMessage(
          message.ok
            ? `Sent ${message.command}${message.value != null ? ` = ${message.value}` : ''}.`
            : message.error || 'Command failed.'
        );
      }
    });

    uiSocket.addEventListener('close', () => {
      setConnected(false);
      setMessage('UI socket disconnected. Retrying...');
      window.setTimeout(connectUiSocket, 1000);
    });
  }

  attachButtons();
  connectUiSocket();
})();
