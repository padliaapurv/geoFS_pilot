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
  bridgeSocket: null,
  lastTelemetry: null,
  lastHello: null,
  lastBridgeSeenAt: null,
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
    bridge_connected: Boolean(state.bridgeSocket),
    telemetry: state.lastTelemetry,
  };
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
  if (state.bridgeSocket && state.bridgeSocket !== ws) {
    state.bridgeSocket.close();
  }

  state.bridgeSocket = ws;
  state.lastBridgeSeenAt = Date.now();
  broadcastUi(currentSnapshot());

  ws.on('message', (raw) => {
    let message;
    try {
      message = JSON.parse(raw.toString());
    } catch {
      return;
    }

    state.lastBridgeSeenAt = Date.now();

    switch (message.type) {
      case 'hello':
        state.lastHello = message;
        sendJson(ws, { type: 'ack', version: '3.0.0' });
        broadcastUi(currentSnapshot());
        break;

      case 'telemetry':
        state.lastTelemetry = message;
        broadcastUi({
          type: 'telemetry',
          telemetry: message,
          bridge_connected: true,
          last_seen_at: state.lastBridgeSeenAt,
        });
        break;

      case 'pong':
        break;

      default:
        break;
    }
  });

  ws.on('close', () => {
    if (state.bridgeSocket === ws) {
      state.bridgeSocket = null;
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

    if (!state.bridgeSocket) {
      sendJson(ws, {
        type: 'command_result',
        ok: false,
        error: 'GeoFS bridge is not connected',
      });
      return;
    }

    sendJson(state.bridgeSocket, message);
    sendJson(ws, {
      type: 'command_result',
      ok: true,
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
  console.log(`GeoFS autopilot app running at http://${HOST}:${PORT}`);
});
