#!/usr/bin/env node
'use strict';

const http = require('http');
const https = require('https');

const PORT = Number(process.env.PORT || 10000);
const UPSTREAM = new URL(
  process.env.RADIO_UPSTREAM || 'https://ajiousama-radiko.onrender.com'
);

const agent = new https.Agent({ keepAlive: true });

function copyHeaders(src, res) {
  const skip = new Set([
    'connection',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'te',
    'trailers',
    'transfer-encoding',
    'upgrade'
  ]);
  for (const [name, value] of Object.entries(src)) {
    if (!skip.has(name.toLowerCase()) && value !== undefined) {
      res.setHeader(name, value);
    }
  }
  res.setHeader('access-control-allow-origin', '*');
}

const server = http.createServer((req, res) => {
  const target = new URL(req.url || '/', UPSTREAM);

  const headers = { ...req.headers };
  headers.host = UPSTREAM.host;
  headers['x-forwarded-host'] = req.headers.host || '';
  headers['x-forwarded-proto'] = 'https';

  const options = {
    protocol: UPSTREAM.protocol,
    hostname: UPSTREAM.hostname,
    port: UPSTREAM.port || 443,
    method: req.method,
    path: target.pathname + target.search,
    headers,
    agent,
  };

  const upstreamReq = https.request(options, (upstreamRes) => {
    res.statusCode = upstreamRes.statusCode || 502;
    if (upstreamRes.statusMessage) res.statusMessage = upstreamRes.statusMessage;
    copyHeaders(upstreamRes.headers, res);
    upstreamRes.pipe(res);
  });

  upstreamReq.setTimeout(30000, () => {
    upstreamReq.destroy(new Error('upstream timeout'));
  });

  upstreamReq.on('error', (err) => {
    if (!res.headersSent) {
      res.statusCode = 502;
      res.setHeader('content-type', 'text/plain; charset=utf-8');
      res.setHeader('access-control-allow-origin', '*');
    }
    res.end('freewifi-radio upstream error: ' + err.message + '\n');
  });

  req.pipe(upstreamReq);
});

server.keepAliveTimeout = 65000;
server.headersTimeout = 70000;

server.listen(PORT, '0.0.0.0', () => {
  console.log(
    'freewifi-radio listening on 0.0.0.0:' +
      PORT +
      ' -> ' +
      UPSTREAM.origin
  );
});
