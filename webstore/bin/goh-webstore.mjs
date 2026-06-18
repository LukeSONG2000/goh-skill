#!/usr/bin/env node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');
const runtimeDir = process.env.GOH_WEBSTORE_HOME || path.join(os.homedir(), '.goh-webstore-automation');
const configPath = path.join(runtimeDir, 'config.json');
const tokenPath = path.join(runtimeDir, 'token');
const defaultConfig = JSON.parse(fs.readFileSync(path.join(rootDir, 'config/default.json'), 'utf8'));
function ensureRuntime() {
  fs.mkdirSync(runtimeDir, { recursive: true });
  if (!fs.existsSync(configPath)) fs.writeFileSync(configPath, JSON.stringify({ ...defaultConfig, userDataDir: path.join(runtimeDir, 'chrome-profile') }, null, 2));
}
function readConfig() { ensureRuntime(); return JSON.parse(fs.readFileSync(configPath, 'utf8')); }
function readToken() { ensureRuntime(); if (!fs.existsSync(tokenPath)) return ''; return fs.readFileSync(tokenPath, 'utf8').trim(); }
function base() { const c = readConfig(); return `http://${c.host}:${c.port}`; }
async function request(method, endpoint, body) {
  const headers = { 'content-type': 'application/json' };
  const t = readToken();
  if (t) headers['x-api-key'] = t;
  const res = await fetch(`${base()}${endpoint}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`${method} ${endpoint} ${res.status}: ${JSON.stringify(json)}`);
  return json;
}
function summarizeRun(run) {
  if (!run) return null;
  if (run.type === 'login') return run;
  return { type: run.type, player: run.player, uiFreeClaims: run.uiFreeClaims?.length || 0, apiFreeResults: run.apiFree?.results?.length || 0, loyaltyClaims: run.loyalty?.claims?.length || 0, finishedAt: run.finishedAt };
}
function printStatus(s) {
  console.log(JSON.stringify({ status: s.status, operation: s.operation, message: s.message, awaiting: s.awaiting, updatedAt: s.updatedAt, runtimeDir: s.runtimeDir, lastError: s.lastError?.message || null, lastRunSummary: summarizeRun(s.lastRun) }, null, 2));
}
async function poll() {
  while (true) {
    const s = await request('GET', '/status');
    printStatus(s);
    if (!['running'].includes(s.status)) return s;
    await new Promise(r => setTimeout(r, 3000));
  }
}
function nodePath() { return process.execPath; }
function plistPath() { return path.join(os.homedir(), 'Library/LaunchAgents/com.lukesong.goh-webstore-automation.plist'); }
function installService() {
  ensureRuntime();
  const c = readConfig();
  const plist = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.lukesong.goh-webstore-automation</string>
  <key>ProgramArguments</key><array><string>${nodePath()}</string><string>${path.join(rootDir, 'src/service.mjs')}</string></array>
  <key>WorkingDirectory</key><string>${rootDir}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${path.join(runtimeDir, 'launchd.out.log')}</string>
  <key>StandardErrorPath</key><string>${path.join(runtimeDir, 'launchd.err.log')}</string>
  <key>EnvironmentVariables</key><dict><key>GOH_WEBSTORE_HOME</key><string>${runtimeDir}</string><key>NODE_ENV</key><string>production</string></dict>
</dict></plist>\n`;
  fs.mkdirSync(path.dirname(plistPath()), { recursive: true });
  fs.writeFileSync(plistPath(), plist);
  console.log(plistPath());
}

function dailyPlistPath() { return path.join(os.homedir(), 'Library/LaunchAgents/com.lukesong.goh-webstore-claim-daily.plist'); }
function installDaily(hour = 0, minute = 0) {
  installService();
  const plist = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.lukesong.goh-webstore-claim-daily</string>
  <key>ProgramArguments</key><array><string>${nodePath()}</string><string>${path.join(rootDir, 'bin/goh-webstore.mjs')}</string><string>claim</string></array>
  <key>WorkingDirectory</key><string>${rootDir}</string>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>${hour}</integer><key>Minute</key><integer>${minute}</integer></dict>
  <key>StandardOutPath</key><string>${path.join(runtimeDir, 'daily.out.log')}</string>
  <key>StandardErrorPath</key><string>${path.join(runtimeDir, 'daily.err.log')}</string>
  <key>EnvironmentVariables</key><dict><key>GOH_WEBSTORE_HOME</key><string>${runtimeDir}</string></dict>
</dict></plist>\n`;
  fs.mkdirSync(path.dirname(dailyPlistPath()), { recursive: true });
  fs.writeFileSync(dailyPlistPath(), plist);
  console.log(dailyPlistPath());
}

function launchctl(args) { const r = spawnSync('launchctl', args, { stdio: 'inherit' }); if (r.status) process.exit(r.status); }
function usage() {
  console.log(`Usage:
  goh-webstore status
  goh-webstore logs [limit]
  goh-webstore login [--email EMAIL] [--wait]
  goh-webstore email EMAIL [--wait]
  goh-webstore code 123456 [--wait]
  goh-webstore claim [--email EMAIL] [--wait]
  goh-webstore cleanup
  goh-webstore install-service | start-service | stop-service | restart-service
  goh-webstore install-daily [hour] [minute] | start-daily | stop-daily
  goh-webstore health`);
}
const argv = process.argv.slice(2);
const cmd = argv[0];
const getOpt = name => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : undefined; };
try {
  if (!cmd || cmd === 'help') usage();
  else if (cmd === 'install-service') installService();
  else if (cmd === 'start-service') launchctl(['bootstrap', `gui/${process.getuid()}`, plistPath()]);
  else if (cmd === 'stop-service') launchctl(['bootout', `gui/${process.getuid()}/com.lukesong.goh-webstore-automation`]);
  else if (cmd === 'restart-service') { spawnSync('launchctl', ['bootout', `gui/${process.getuid()}/com.lukesong.goh-webstore-automation`]); launchctl(['bootstrap', `gui/${process.getuid()}`, plistPath()]); }
  else if (cmd === 'install-daily') installDaily(Number(argv[1] ?? 0), Number(argv[2] ?? 0));
  else if (cmd === 'start-daily') launchctl(['bootstrap', `gui/${process.getuid()}`, dailyPlistPath()]);
  else if (cmd === 'stop-daily') launchctl(['bootout', `gui/${process.getuid()}/com.lukesong.goh-webstore-claim-daily`]);
  else if (cmd === 'health') console.log(JSON.stringify(await request('GET', '/health'), null, 2));
  else if (cmd === 'status') printStatus(await request('GET', '/status'));
  else if (cmd === 'logs') console.log((await request('GET', `/logs?limit=${Number(argv[1] || 100)}`)).logs.join('\n'));
  else if (cmd === 'login') { printStatus(await request('POST', '/login/start', { email: getOpt('--email') })); if (argv.includes('--wait')) await poll(); }
  else if (cmd === 'email') { if (!argv[1]) throw new Error('缺少邮箱'); printStatus(await request('POST', '/login/email', { email: argv[1] })); if (argv.includes('--wait')) await poll(); }
  else if (cmd === 'code') { if (!argv[1]) throw new Error('缺少验证码'); printStatus(await request('POST', '/login/code', { code: argv[1] })); if (argv.includes('--wait')) await poll(); }
  else if (cmd === 'claim') { printStatus(await request('POST', '/claim/run', { email: getOpt('--email') })); if (argv.includes('--wait')) await poll(); }
  else if (cmd === 'cleanup') printStatus(await request('POST', '/cleanup'));
  else throw new Error(`未知命令: ${cmd}`);
} catch (e) { console.error(e.message); process.exit(1); }
