'use strict';
// Optional AISStream receiver for Koku94 ferries. Never expose API keys to clients.
const WebSocket = require('ws');
const FEED = 'wss://stream.aisstream.io/v0/stream';
const AREA = [[[32.75, 131.65], [33.55, 132.65]]];
const MAX_AGE_MS = 15 * 60 * 1000;
const TARGETS = ['速なみ', '遊なぎ', '涼かぜ'];

function parseShips(value) {
  const entries = (value || '').split(',').map(s => s.trim()).filter(Boolean);
  const mapping = new Map();
  for (const entry of entries) {
    const [name, mmsi] = entry.split(':').map(s => s && s.trim());
    if (!TARGETS.includes(name) || !/^\d{9}$/.test(mmsi || '')) continue;
    mapping.set(mmsi, name);
  }
  return mapping;
}
function createFerryAIS({ apiKey = process.env.AISSTREAM_API_KEY, ships = process.env.AIS_FERRY_MMSI } = {}) {
  const identifiers = parseShips(ships);
  const positions = new Map();
  let socket = null, reconnectTimer = null, stopped = false, attempts = 0;
  const enabled = Boolean(apiKey && identifiers.size);
  function connect() {
    if (!enabled || stopped) return;
    socket = new WebSocket(FEED, { perMessageDeflate: true });
    socket.on('open', () => {
      attempts = 0;
      socket.send(JSON.stringify({
        APIKey: apiKey, BoundingBoxes: AREA,
        FiltersShipMMSI: [...identifiers.keys()],
        FilterMessageTypes: ['PositionReport', 'StandardClassBPositionReport', 'ExtendedClassBPositionReport']
      }));
    });
    socket.on('message', raw => {
      let msg;
      try { msg = JSON.parse(raw.toString()); } catch { return; }
      if (!['PositionReport', 'StandardClassBPositionReport', 'ExtendedClassBPositionReport'].includes(msg.MessageType)) return;
      const m = msg.MetaData || {};
      const data = msg.Message?.[msg.MessageType] || {};
      const id = String(m.MMSI ?? data.UserID ?? '');
      const name = identifiers.get(id);
      if (!name) return;
      const latitude = Number(m.latitude ?? m.Latitude ?? data.Latitude);
      const longitude = Number(m.longitude ?? m.Longitude ?? data.Longitude);
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180 || !latitude || !longitude) return;
      if (latitude < 32.75 || latitude > 33.55 || longitude < 131.65 || longitude > 132.65) return;
      const speedKnots = Number(data.Sog);
      const courseDegrees = Number(data.Cog);
      positions.set(name, {
        name, mmsi: id, latitude, longitude,
        speedKnots: Number.isFinite(speedKnots) && speedKnots >= 0 && speedKnots < 102.3 ? speedKnots : null,
        courseDegrees: Number.isFinite(courseDegrees) && courseDegrees >= 0 && courseDegrees < 360 ? courseDegrees : null,
        receivedAt: new Date().toISOString(), source: 'AIS'
      });
    });
    socket.on('error', err => console.warn('[ferry-ais] connection error:', err.message));
    socket.on('close', () => {
      socket = null;
      if (stopped) return;
      const delay = Math.min(120000, 3000 * Math.pow(2, Math.min(attempts++, 5)));
      reconnectTimer = setTimeout(connect, delay);
      reconnectTimer.unref?.();
    });
  }
  function snapshot() {
    const now = Date.now();
    return {
      enabled,
      status: !enabled ? 'not-configured' : socket?.readyState === WebSocket.OPEN ? 'connected' : 'reconnecting',
      vessels: TARGETS.map(name => {
        const p = positions.get(name);
        if (!p) return { name, status: 'unknown', source: null };
        const ageSeconds = Math.max(0, Math.round((now - Date.parse(p.receivedAt)) / 1000));
        if (ageSeconds * 1000 > MAX_AGE_MS) return { name, status: 'stale', source: 'AIS', lastReceivedAt: p.receivedAt, ageSeconds };
        return { ...p, status: 'observed', ageSeconds };
      })
    };
  }
  function stop() {
    stopped = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (socket) socket.close();
  }
  return { start: connect, stop, snapshot };
}
module.exports = { createFerryAIS, parseShips };
