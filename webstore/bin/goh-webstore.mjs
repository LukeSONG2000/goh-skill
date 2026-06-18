#!/usr/bin/env node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');
const runtimeDir = process.env.GOH_WEBSTORE_HOME || path.join(os.homedir(), '.goh-webstore-automation');
const configPath = path.join(runtimeDir, 'config.json');
const tokenPath = path.join(runtimeDir, 'token');
const pidPath = path.join(runtimeDir, 'service.pid');
const defaultConfig = JSON.parse(fs.readFileSync(path.join(rootDir, 'config/default.json'), 'utf8'));

function ensureRuntime() {
  fs.mkdirSync(runtimeDir, { recursive: true });
  fs.mkdirSync(path.join(runtimeDir, 'logs'), { recursive: true });
  if (!fs.existsSync(configPath)) {
    fs.writeFileSync(configPath, JSON.stringify({ ...defaultConfig, userDataDir: path.join(runtimeDir, 'chrome-profile') }, null, 2));
  }
}
function readConfig() { ensureRuntime(); return JSON.parse(fs.readFileSync(configPath, 'utf8')); }
function readToken() { ensureRuntime(); if (!fs.existsSync(tokenPath)) return ''; return fs.readFileSync(tokenPath, 'utf8').trim(); }
function base() { const c = readConfig(); return `http://${c.host}:${c.port}`; }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function nodePath() { return process.execPath; }
function servicePath() { return path.join(rootDir, 'src/service.mjs'); }
function standaloneOutPath() { return path.join(runtimeDir, 'logs', 'standalone.out.log'); }
function standaloneErrPath() { return path.join(runtimeDir, 'logs', 'standalone.err.log'); }
function plistPath() { return path.join(os.homedir(), 'Library/LaunchAgents/com.lukesong.goh-webstore-automation.plist'); }
function dailyPlistPath() { return path.join(os.homedir(), 'Library/LaunchAgents/com.lukesong.goh-webstore-claim-daily.plist'); }

async function request(method, endpoint, body) {
  const headers = { 'content-type': 'application/json' };
  const t = readToken();
  if (t) headers['x-api-key'] = t;
  const res = await fetch(`${base()}${endpoint}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`${method} ${endpoint} ${res.status}: ${JSON.stringify(json)}`);
  return json;
}
function isConnectionFailure(error) {
  const text = `${error?.message || ''} ${error?.cause?.message || ''} ${error?.cause?.code || ''}`;
  return /fetch failed|ECONNREFUSED|ECONNRESET|EHOSTUNREACH|UND_ERR_SOCKET/i.test(text);
}
async function requestWithAutoStart(method, endpoint, body) {
  try {
    return await request(method, endpoint, body);
  } catch (e) {
    if (!isConnectionFailure(e)) throw e;
    await startService({ quiet: true });
    return await request(method, endpoint, body);
  }
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
    const s = await requestWithAutoStart('GET', '/status');
    printStatus(s);
    if (!['running'].includes(s.status)) return s;
    await sleep(3000);
  }
}
async function waitForService(timeoutMs = 12000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      return await request('GET', '/health');
    } catch (e) {
      lastError = e;
      await sleep(500);
    }
  }
  throw new Error(`Webstore 服务启动失败：${lastError?.message || 'timeout'}。查看日志：${standaloneErrPath()}`);
}
function ensureNodeDependencies() {
  if (fs.existsSync(path.join(rootDir, 'node_modules/playwright-core/package.json'))) return;
  const npm = spawnSync('npm', ['install', '--omit=dev', '--silent'], { cwd: rootDir, stdio: 'inherit' });
  if (npm.status !== 0) throw new Error('npm install 失败，请确认远端环境已安装 npm/node，并可访问 npm registry');
}
function isPidAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}
function readPid() {
  if (!fs.existsSync(pidPath)) return null;
  const pid = Number(fs.readFileSync(pidPath, 'utf8').trim());
  return Number.isInteger(pid) && pid > 0 ? pid : null;
}
function startStandaloneService() {
  ensureRuntime();
  ensureNodeDependencies();
  const out = fs.openSync(standaloneOutPath(), 'a');
  const err = fs.openSync(standaloneErrPath(), 'a');
  const child = spawn(nodePath(), [servicePath()], {
    cwd: rootDir,
    detached: true,
    stdio: ['ignore', out, err],
    env: { ...process.env, GOH_WEBSTORE_HOME: runtimeDir, NODE_ENV: 'production' },
  });
  fs.writeFileSync(pidPath, `${child.pid}\n`);
  child.unref();
}
function installService() {
  ensureRuntime();
  if (process.platform !== 'darwin') {
    const unitDir = path.join(os.homedir(), '.config/systemd/user');
    const unitPath = path.join(unitDir, 'goh-webstore-automation.service');
    fs.mkdirSync(unitDir, { recursive: true });
    fs.writeFileSync(unitPath, `[Unit]
Description=GOH Webstore Automation

[Service]
WorkingDirectory=${rootDir}
ExecStart=${nodePath()} ${servicePath()}
Restart=always
Environment=GOH_WEBSTORE_HOME=${runtimeDir}
Environment=NODE_ENV=production

[Install]
WantedBy=default.target
`);
    console.log(unitPath);
    return;
  }
  const plist = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.lukesong.goh-webstore-automation</string>
  <key>ProgramArguments</key><array><string>${nodePath()}</string><string>${servicePath()}</string></array>
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
async function startService({ quiet = false } = {}) {
  ensureRuntime();
  try {
    const health = await request('GET', '/health');
    if (!quiet) console.log(JSON.stringify({ ok: true, alreadyRunning: true, ...health }, null, 2));
    return health;
  } catch (e) {
    if (!isConnectionFailure(e)) throw e;
  }
  if (process.platform === 'darwin' && fs.existsSync(plistPath())) {
    spawnSync('launchctl', ['bootstrap', `gui/${process.getuid()}`, plistPath()], { stdio: quiet ? 'ignore' : 'inherit' });
    try {
      const health = await waitForService(3000);
      if (!quiet) console.log(JSON.stringify({ ok: true, started: true, ...health }, null, 2));
      return health;
    } catch {
      // Fall back to a standalone process when launchd is unavailable or stale.
    }
  }
  const pid = readPid();
  if (isPidAlive(pid)) {
    try { process.kill(pid, 'SIGTERM'); } catch {}
  }
  startStandaloneService();
  const health = await waitForService();
  if (!quiet) console.log(JSON.stringify({ ok: true, started: true, ...health }, null, 2));
  return health;
}
async function stopService() {
  if (process.platform === 'darwin') {
    spawnSync('launchctl', ['bootout', `gui/${process.getuid()}/com.lukesong.goh-webstore-automation`], { stdio: 'inherit' });
  }
  const pid = readPid();
  if (isPidAlive(pid)) process.kill(pid, 'SIGTERM');
  if (fs.existsSync(pidPath)) fs.rmSync(pidPath, { force: true });
  console.log(JSON.stringify({ ok: true, stopped: true }, null, 2));
}
async function restartService() {
  await stopService();
  await sleep(1000);
  await startService();
}
function installDaily(hour = 0, minute = 0) {
  installService();
  if (process.platform !== 'darwin') {
    const marker = '# goh-webstore-claim-daily';
    const cmd = `${minute} ${hour} * * * cd ${rootDir} && ${nodePath()} ${path.join(rootDir, 'bin/goh-webstore.mjs')} claim ${marker}`;
    const existing = spawnSync('crontab', ['-l'], { encoding: 'utf8' });
    const lines = (existing.stdout || '').split('\n').filter(line => line.trim() && !line.includes(marker));
    lines.push(cmd);
    const updated = `${lines.join('\n')}\n`;
    const write = spawnSync('crontab', ['-'], { input: updated, encoding: 'utf8', stdio: ['pipe', 'inherit', 'inherit'] });
    if (write.status !== 0) throw new Error('写入 crontab 失败；可改用 systemd user timer 或由 OpenClaw 外部调度定时执行 claim');
    console.log('crontab: goh-webstore-claim-daily');
    return;
  }
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
function startDaily() {
  if (process.platform !== 'darwin') {
    console.log(JSON.stringify({ ok: true, message: 'Linux daily task is managed by crontab after install-daily' }, null, 2));
    return;
  }
  const r = spawnSync('launchctl', ['bootstrap', `gui/${process.getuid()}`, dailyPlistPath()], { stdio: 'inherit' });
  if (r.status) process.exit(r.status);
}
function stopDaily() {
  if (process.platform !== 'darwin') {
    const marker = '# goh-webstore-claim-daily';
    const existing = spawnSync('crontab', ['-l'], { encoding: 'utf8' });
    const lines = (existing.stdout || '').split('\n').filter(line => line.trim() && !line.includes(marker));
    const write = spawnSync('crontab', ['-'], { input: `${lines.join('\n')}\n`, encoding: 'utf8', stdio: ['pipe', 'inherit', 'inherit'] });
    if (write.status !== 0) throw new Error('移除 crontab 失败');
    console.log(JSON.stringify({ ok: true, stopped: true }, null, 2));
    return;
  }
  const r = spawnSync('launchctl', ['bootout', `gui/${process.getuid()}/com.lukesong.goh-webstore-claim-daily`], { stdio: 'inherit' });
  if (r.status) process.exit(r.status);
}
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
  else if (cmd === 'start-service') await startService();
  else if (cmd === 'stop-service') await stopService();
  else if (cmd === 'restart-service') await restartService();
  else if (cmd === 'install-daily') installDaily(Number(argv[1] ?? 0), Number(argv[2] ?? 0));
  else if (cmd === 'start-daily') startDaily();
  else if (cmd === 'stop-daily') stopDaily();
  else if (cmd === 'health') console.log(JSON.stringify(await requestWithAutoStart('GET', '/health'), null, 2));
  else if (cmd === 'status') printStatus(await requestWithAutoStart('GET', '/status'));
  else if (cmd === 'logs') console.log((await requestWithAutoStart('GET', `/logs?limit=${Number(argv[1] || 100)}`)).logs.join('\n'));
  else if (cmd === 'login') { printStatus(await requestWithAutoStart('POST', '/login/start', { email: getOpt('--email') })); if (argv.includes('--wait')) await poll(); }
  else if (cmd === 'email') { if (!argv[1]) throw new Error('缺少邮箱'); printStatus(await requestWithAutoStart('POST', '/login/email', { email: argv[1] })); if (argv.includes('--wait')) await poll(); }
  else if (cmd === 'code') { if (!argv[1]) throw new Error('缺少验证码'); printStatus(await requestWithAutoStart('POST', '/login/code', { code: argv[1] })); if (argv.includes('--wait')) await poll(); }
  else if (cmd === 'claim') { printStatus(await requestWithAutoStart('POST', '/claim/run', { email: getOpt('--email') })); if (argv.includes('--wait')) await poll(); }
  else if (cmd === 'cleanup') printStatus(await requestWithAutoStart('POST', '/cleanup'));
  else throw new Error(`未知命令: ${cmd}`);
} catch (e) {
  console.error(e.message);
  process.exit(1);
}
