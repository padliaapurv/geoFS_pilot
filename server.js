const http = require('http');
const fs = require('fs');
const path = require('path');
const { WebSocketServer } = require('ws');

const HOST = '127.0.0.1';
const PORT = 52137;
const PUBLIC_DIR = path.join(__dirname, 'public');

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
};

const state = {
  bridges: new Map(),
};

function sendJson(ws, payload) {
  if (!ws || ws.readyState !== ws.OPEN) return;
  ws.send(JSON.stringify(payload));
}

function broadcastUi(payload) {
  const message = JSON.stringify(payload);
  for (const client of uiWss.clients) {
    if (client.readyState === client.OPEN) {
      client.send(message);
    }
  }
}

function currentSnapshot() {
  return {
    type: 'snapshot',
    instances: Array.from(state.bridges.values())
      .map((bridge) => ({
        bridge_id: bridge.bridgeId,
        connected: Boolean(bridge.ws && bridge.ws.readyState === bridge.ws.OPEN),
        label: bridge.label || bridge.hello?.label || bridge.telemetry?.label || bridge.bridgeId,
        hello: bridge.hello,
        telemetry: bridge.telemetry,
        last_seen_at: bridge.lastSeenAt,
      }))
      .sort((a, b) => {
        if (a.connected !== b.connected) return a.connected ? -1 : 1;
        return (a.label || '').localeCompare(b.label || '');
      }),
  };
}

function getBridgeState(bridgeId) {
  let bridge = state.bridges.get(bridgeId);

  if (!bridge) {
    bridge = {
      bridgeId,
      ws: null,
      hello: null,
      telemetry: null,
      lastSeenAt: null,
      label: bridgeId,
    };
    state.bridges.set(bridgeId, bridge);
  }

  return bridge;
}

function allocateBridgeId(requestedBridgeId, ws) {
  if (ws.bridgeId) return ws.bridgeId;

  let bridgeId = requestedBridgeId;
  let bridge = state.bridges.get(bridgeId);
  let suffix = 2;

  while (bridge && bridge.ws && bridge.ws.readyState === bridge.ws.OPEN && bridge.ws !== ws) {
    bridgeId = `${requestedBridgeId}:${suffix}`;
    bridge = state.bridges.get(bridgeId);
    suffix += 1;
  }

  ws.bridgeId = bridgeId;
  return bridgeId;
}

function serveFile(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const requestPath = url.pathname === '/' ? '/index.html' : url.pathname;
  const safePath = path.normalize(requestPath).replace(/^(\.\.[/\\])+/, '');
  const filePath = path.join(PUBLIC_DIR, safePath);

  if (!filePath.startsWith(PUBLIC_DIR)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(err.code === 'ENOENT' ? 404 : 500);
      res.end(err.code === 'ENOENT' ? 'Not found' : 'Server error');
      return;
    }

    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { 'Content-Type': MIME_TYPES[ext] || 'text/plain; charset=utf-8' });
    res.end(data);
  });
}

const server = http.createServer((req, res) => {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { Allow: 'GET, HEAD' });
    res.end('Method not allowed');
    return;
  }

  if (req.method === 'HEAD') {
    res.writeHead(200);
    res.end();
    return;
  }

  serveFile(req, res);
});

const bridgeWss = new WebSocketServer({ noServer: true });
const uiWss = new WebSocketServer({ noServer: true });

bridgeWss.on('connection', (ws) => {
  let activeBridgeId = null;

  ws.on('message', (raw) => {
    let message;
    try {
      message = JSON.parse(raw.toString());
    } catch {
      return;
    }

    const requestedBridgeId = message.bridge_id;
    if (!requestedBridgeId) return;

    const bridgeId = allocateBridgeId(requestedBridgeId, ws);
    const normalizedMessage =
      bridgeId === requestedBridgeId
        ? message
        : { ...message, bridge_id: bridgeId, source_bridge_id: requestedBridgeId };
    const bridge = getBridgeState(bridgeId);
    bridge.lastSeenAt = Date.now();
    bridge.label = normalizedMessage.label || bridge.label;
    bridge.ws = ws;
    activeBridgeId = bridgeId;

    switch (message.type) {
      case 'hello':
        bridge.hello = normalizedMessage;
        bridge.label = normalizedMessage.label || bridge.label;
        sendJson(ws, { type: 'ack', version: '3.0.0' });
        broadcastUi(currentSnapshot());
        break;

      case 'telemetry':
        bridge.telemetry = normalizedMessage;
        bridge.label = normalizedMessage.label || bridge.label;
        broadcastUi({
          type: 'telemetry',
          bridge_id: bridge.bridgeId,
          instance: {
            bridge_id: bridge.bridgeId,
            connected: true,
            label: bridge.label,
            hello: bridge.hello,
            telemetry: bridge.telemetry,
            last_seen_at: bridge.lastSeenAt,
          },
        });
        break;

      case 'command_result':
        broadcastUi({
          ...normalizedMessage,
          bridge_id: bridge.bridgeId,
        });
        break;

      case 'pong':
        break;

      default:
        break;
    }
  });

  ws.on('close', () => {
    if (activeBridgeId) {
      const bridge = state.bridges.get(activeBridgeId);
      if (bridge && bridge.ws === ws) {
        bridge.ws = null;
        bridge.lastSeenAt = Date.now();
      }
    }
    broadcastUi(currentSnapshot());
  });
});

uiWss.on('connection', (ws) => {
  sendJson(ws, currentSnapshot());

  ws.on('message', (raw) => {
    let message;
    try {
      message = JSON.parse(raw.toString());
    } catch {
      return;
    }

    if (message.type !== 'autopilot_command') return;

    const bridgeId = message.bridge_id;
    if (!bridgeId) {
      sendJson(ws, {
        type: 'command_result',
        ok: false,
        error: 'No GeoFS instance selected',
      });
      return;
    }

    const bridge = state.bridges.get(bridgeId);
    if (!bridge || !bridge.ws || bridge.ws.readyState !== bridge.ws.OPEN) {
      sendJson(ws, {
        type: 'command_result',
        ok: false,
        error: 'Selected GeoFS instance is not connected',
      });
      return;
    }

    sendJson(bridge.ws, message);
    sendJson(ws, {
      type: 'command_result',
      ok: true,
      bridge_id: bridgeId,
      command: message.command,
      value: message.value ?? null,
    });
  });
});

server.on('upgrade', (req, socket, head) => {
  const url = new URL(req.url, `http://${req.headers.host}`);

  if (url.pathname === '/ui') {
    uiWss.handleUpgrade(req, socket, head, (ws) => {
      uiWss.emit('connection', ws, req);
    });
    return;
  }

  if (url.pathname === '/' || url.pathname === '') {
    bridgeWss.handleUpgrade(req, socket, head, (ws) => {
      bridgeWss.emit('connection', ws, req);
    });
    return;
  }

  socket.destroy();
});

server.listen(PORT, HOST, () => {
  console.log(`GeoFS formation pilot app running at http://${HOST}:${PORT}`);
});
