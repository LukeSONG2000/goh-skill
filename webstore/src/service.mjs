import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');
const runtimeDir = process.env.GOH_WEBSTORE_HOME || path.join(os.homedir(), '.goh-webstore-automation');
const logsDir = path.join(runtimeDir, 'logs');
const dataDir = path.join(runtimeDir, 'data');
const configFile = path.join(runtimeDir, 'config.json');
const tokenFile = path.join(runtimeDir, 'token');
fs.mkdirSync(logsDir, { recursive: true });
fs.mkdirSync(dataDir, { recursive: true });

const defaults = JSON.parse(fs.readFileSync(path.join(rootDir, 'config/default.json'), 'utf8'));
const userConfig = fs.existsSync(configFile) ? JSON.parse(fs.readFileSync(configFile, 'utf8')) : {};
const config = {
  ...defaults,
  ...userConfig,
  userDataDir: userConfig.userDataDir || path.join(runtimeDir, 'chrome-profile'),
};
if (!fs.existsSync(configFile)) fs.writeFileSync(configFile, JSON.stringify(config, null, 2));
if (!fs.existsSync(tokenFile)) fs.writeFileSync(tokenFile, crypto.randomBytes(32).toString('base64url') + '\n', { mode: 0o600 });
const token = fs.readFileSync(tokenFile, 'utf8').trim();
const logFile = path.join(logsDir, 'service.log');
const stateFile = path.join(dataDir, 'state.json');

const runtime = {
  status: 'idle',
  operation: null,
  message: 'ready',
  startedAt: null,
  updatedAt: new Date().toISOString(),
  awaiting: null,
  lastError: null,
  lastRun: null,
  logs: [],
};
let currentTask = null;
let pending = null; // { context, page, after, email, timeout }

class NeedsInput extends Error {
  constructor(type, message) {
    super(message);
    this.name = 'NeedsInput';
    this.type = type;
  }
}

function persist() {
  fs.writeFileSync(stateFile, JSON.stringify({ ...runtime, logs: runtime.logs.slice(-100) }, null, 2));
}
function log(...args) {
  const line = `${new Date().toISOString()} ${args.map(a => typeof a === 'string' ? a : JSON.stringify(a)).join(' ')}`;
  runtime.logs.push(line);
  runtime.logs = runtime.logs.slice(-300);
  runtime.updatedAt = new Date().toISOString();
  fs.appendFileSync(logFile, line + '\n');
  persist();
  console.log(line);
}
function setStatus(status, patch = {}) {
  Object.assign(runtime, patch, { status, updatedAt: new Date().toISOString() });
  persist();
}
function publicState() {
  return {
    status: runtime.status,
    operation: runtime.operation,
    message: runtime.message,
    startedAt: runtime.startedAt,
    updatedAt: runtime.updatedAt,
    awaiting: runtime.awaiting,
    lastError: runtime.lastError,
    lastRun: runtime.lastRun,
    runtimeDir,
    logs: runtime.logs.slice(-80),
  };
}
async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString('utf8');
  return raw ? JSON.parse(raw) : {};
}
function send(res, statusCode, data) {
  res.writeHead(statusCode, { 'content-type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(data, null, 2));
}
function requireAuth(req, res) {
  if (req.url === '/health') return true;
  const got = req.headers['x-api-key'] || (req.headers.authorization || '').replace(/^Bearer\s+/i, '');
  if (got === token) return true;
  send(res, 401, { error: 'Unauthorized' });
  return false;
}
function resolveEmail(email) {
  return String(email || config.email || '').trim();
}
function validateEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}
function closePending(reason) {
  if (!pending) return;
  const p = pending;
  pending = null;
  if (p.timeout) clearTimeout(p.timeout);
  p.context?.close().catch(() => {});
  log('pending browser cleaned', reason || 'cleanup');
  setStatus('idle', { operation: null, awaiting: null, message: reason || 'pending browser cleaned' });
}
function clearWaitingWithoutBrowser(reason) {
  if (pending) return closePending(reason);
  if (runtime.status === 'awaiting_email') {
    log('waiting state cleared', reason || 'cleanup');
    setStatus('idle', { operation: null, awaiting: null, message: reason || 'waiting state cleared' });
  }
}
function setPending(context, page, after, email) {
  if (pending?.timeout) clearTimeout(pending.timeout);
  const timeout = setTimeout(() => closePending('验证码等待超时，已关闭浏览器'), config.pendingTimeoutMs || 900000);
  pending = { context, page, after, email, timeout };
}
async function launchBrowser() {
  return chromium.launchPersistentContext(config.userDataDir, {
    headless: !!config.headless,
    executablePath: config.chromeExecutable,
    viewport: config.viewport,
    locale: config.locale,
    args: ['--no-first-run', '--no-default-browser-check', '--disable-blink-features=AutomationControlled'],
  });
}
async function getPage(context) { return context.pages()[0] || await context.newPage(); }
async function pageStatus(page) {
  return page.evaluate(() => {
    try { return JSON.parse(localStorage.getItem('st-core') || '{}')?.state?.status || null; }
    catch { return null; }
  });
}
async function playerSummary(page) {
  return page.evaluate(async () => {
    try {
      const st = JSON.parse(localStorage.getItem('st-core') || '{}')?.state;
      const headers = { 'Content-Type': 'application/json', 'Accept-Language': 'en' };
      if (st?.auth?.authId) headers['X-Rpc-Auth-Id'] = st.auth.authId;
      const r = await fetch('/player', { headers });
      const j = await r.json().catch(() => null);
      if (!r.ok) return { ok: false, status: r.status, body: j };
      return { ok: true, name: j.name, allyCode: j.allyCode, playerId: j.playerId };
    } catch (e) { return { ok: false, error: e.message }; }
  });
}
async function waitForAuthorized(page, timeout = 180000) {
  await page.waitForFunction(() => {
    try { return JSON.parse(localStorage.getItem('st-core') || '{}')?.state?.status === 'AUTHORIZED'; }
    catch { return false; }
  }, null, { timeout });
}
async function fillOtp(page, code) {
  const clean = String(code || '').replace(/\D/g, '');
  if (!/^\d{6}$/.test(clean)) throw new Error('验证码必须是 6 位数字');
  await page.locator('#code-1').waitFor({ state: 'visible', timeout: 30000 });
  for (let i = 0; i < 6; i++) {
    const box = page.locator(`#code-${i + 1}`);
    await box.click();
    await box.fill(clean[i]);
  }
  await page.evaluate(value => {
    for (const el of document.querySelectorAll('input[name="verification"]')) {
      el.value = value;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }, clean);
}
async function ensureAuthorized(page, context, after, email) {
  await page.goto(config.storeUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(config.uiSettleMs);
  if (await pageStatus(page) === 'AUTHORIZED') return { ok: true, mode: 'already_authorized' };
  if (!validateEmail(email)) {
    setStatus('awaiting_email', {
      operation: after === 'claim' ? 'claim' : 'login',
      message: '需要 EA 账号邮箱才能继续登录',
      awaiting: { type: 'ea_email', after },
    });
    throw new NeedsInput('ea_email', 'EA email required');
  }
  log('not authorized; starting EA login', { email, after });
  const login = page.getByRole('link', { name: /log in/i }).or(page.locator('a:has-text("LOG IN")')).first();
  await login.waitFor({ state: 'visible', timeout: 30000 });
  await login.click();
  await page.waitForTimeout(3000);
  if (page.url().includes('signin.ea.com')) {
    if (await page.locator('#email').isVisible({ timeout: 20000 }).catch(() => false)) {
      await page.locator('#email').fill(email);
      await page.locator('#rememberMe').check().catch(() => {});
      await page.locator('#logInBtn').click();
      await page.waitForTimeout(2000);
    }
    if (await page.locator('#code-1').isVisible({ timeout: 60000 }).catch(() => false)) {
      setPending(context, page, after, email);
      setStatus('awaiting_code', {
        operation: after === 'claim' ? 'claim' : 'login',
        message: `验证码已发送到 ${email}`,
        awaiting: { type: 'ea_email_code', email, after, timeoutMs: config.pendingTimeoutMs },
      });
      throw new NeedsInput('ea_email_code', 'EA email verification code required');
    }
  }
  await waitForAuthorized(page);
  return { ok: true, mode: 'authorized_after_redirect' };
}
async function continuePendingWithCode(code) {
  if (!pending) throw new Error('当前没有等待验证码的登录流程');
  const { context, page, after, timeout } = pending;
  if (timeout) clearTimeout(timeout);
  pending = null;
  setStatus('running', { operation: after === 'claim' ? 'claim' : 'login', awaiting: null, message: 'submitting verification code' });
  try {
    await fillOtp(page, code);
    await page.locator('#logInBtn').click();
    await waitForAuthorized(page);
    log('EA login authorized after code');
    if (after === 'claim') {
      const run = await claimAll(page);
      setStatus('idle', { operation: null, message: 'claim completed after login', lastError: null, lastRun: run });
    } else {
      const player = await playerSummary(page);
      setStatus('idle', { operation: null, message: 'login completed', lastError: null, lastRun: { type: 'login', player } });
    }
  } catch (e) {
    setStatus('error', { operation: null, message: e.message, lastError: { message: e.message, stack: e.stack } });
    throw e;
  } finally {
    await context.close().catch(() => {});
    log('browser closed after code flow');
  }
}
async function claimVisibleFreeGifts(page) {
  const claims = [];
  for (let round = 1; round <= 5; round++) {
    await page.goto(config.storeUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(config.uiSettleMs);
    const clicked = await page.evaluate(() => {
      const norm = s => (s || '').replace(/\s+/g, ' ').trim();
      const bad = /\$|HKD|BUY NOW|Upgrade|Pass Plus|Crystals/i;
      const candidates = [...document.querySelectorAll('div,button,a')].map(el => {
        const r = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        const text = norm(el.innerText || el.textContent || el.value);
        return { el, text, r, cursor: style.cursor, visible: !!(r.width && r.height) && style.display !== 'none' && style.visibility !== 'hidden' };
      }).filter(x => x.visible && x.cursor === 'pointer' && /FREE|COLLECT NOW|Daily Rewards|Mystery Chest/i.test(x.text) && !bad.test(x.text) && x.r.width > 100 && x.r.height > 50)
        .sort((a, b) => a.text.length - b.text.length);
      const picked = candidates[0];
      if (!picked) return null;
      picked.el.scrollIntoView({ block: 'center', inline: 'center' });
      picked.el.click();
      return { text: picked.text.slice(0, 300), rect: { x: picked.r.x, y: picked.r.y, w: picked.r.width, h: picked.r.height } };
    });
    if (!clicked) break;
    await page.waitForTimeout(4000);
    const claimButton = page.locator('button:has-text("CLAIM")').first();
    if (!(await claimButton.isVisible({ timeout: 5000 }).catch(() => false))) break;
    await claimButton.click();
    await page.waitForTimeout(10000);
    claims.push({ source: 'ui', round, clicked });
    log('claimed visible free gift', claims.at(-1));
  }
  return claims;
}
async function claimFreeStoreApi(page, player) {
  return page.evaluate(async ({ playerId }) => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const st = JSON.parse(localStorage.getItem('st-core') || '{}')?.state;
    const headers = { 'Content-Type': 'application/json', 'Accept-Language': 'en', 'X-Rpc-Auth-Id': st.auth.authId };
    const get = async url => { const r = await fetch(url, { headers }); const j = await r.json().catch(() => null); if (!r.ok) throw new Error(`${url} ${r.status} ${JSON.stringify(j)}`); return j; };
    const post = async (url, body) => { const r = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) }); const j = await r.json().catch(() => null); if (!r.ok) throw new Error(`${url} ${r.status} ${JSON.stringify(j)}`); return j; };
    const offers = await get('/store/offers?countryCode=&includeCouponDetails=true');
    const purchases = await get('/purchases?limitedPurchasesOnly=true');
    const bought = purchases.purchases || {};
    const now = Math.floor(Date.now() / 1000);
    const candidates = (offers.items || []).filter(item => {
      const offer = (item.offers || [])[0];
      if (!offer || offer.currencyType !== 'FREE') return false;
      if (!(item.startTime <= now && (item.endTime === 0 || now <= item.endTime))) return false;
      if (item.dailyFreeOfferClaimed === true) return false;
      const limit = Number(item.purchaseLimit || 0);
      const count = Number(bought[item.id] || 0);
      return !limit || count < limit;
    });
    const results = [];
    for (const item of candidates) {
      try {
        const res = await post('/store/purchase', { itemId: item.id, requestId: crypto.randomUUID(), currencyType: 'FREE', giftable: !!item.giftable, recipientPlayerId: playerId });
        results.push({ id: item.id, name: item.name, state: res.state, currencyType: res.currencyType });
      } catch (e) { results.push({ id: item.id, name: item.name, error: e.message }); }
      await sleep(1500);
    }
    return { candidates: candidates.map(i => ({ id: i.id, name: i.name })), results };
  }, { playerId: player.playerId });
}
async function claimLoyaltyApi(page) {
  return page.evaluate(async ({ maxRounds }) => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const st = JSON.parse(localStorage.getItem('st-core') || '{}')?.state;
    const headers = { 'Content-Type': 'application/json', 'Accept-Language': 'en', 'X-Rpc-Auth-Id': st.auth.authId };
    const get = async url => { const r = await fetch(url, { headers }); const j = await r.json().catch(() => null); if (!r.ok) throw new Error(`${url} ${r.status} ${JSON.stringify(j)}`); return j; };
    const post = async (url, body) => { const r = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) }); const j = await r.json().catch(() => null); if (!r.ok) throw new Error(`${url} ${r.status} ${JSON.stringify(j)}`); return j; };
    const claims = [], rounds = [];
    for (let round = 1; round <= maxRounds; round++) {
      const [eventsResp, progressResp] = await Promise.all([get('/loyalty/milestones/'), get('/loyalty/milestones/progress/')]);
      const eventMap = Object.fromEntries((eventsResp.events || []).map(e => [e.id, e]));
      const claimables = [];
      for (const p of progressResp.progress || []) {
        const ev = eventMap[p.eventInstanceId.split(':')[0]];
        if (!ev) continue;
        (ev.tiers || []).forEach((tier, tierIndex) => {
          const progress = Number(p.progress || 0), amount = Number(tier.amount || 0), claimed = !!(p.tiersClaimed || [])[tierIndex];
          if (!claimed && progress >= amount) claimables.push({ title: ev.title, eventInstanceId: p.eventInstanceId, tierIndex, amount, progress });
        });
      }
      rounds.push({ round, claimables });
      if (claimables.length === 0) break;
      for (const c of claimables) {
        try { claims.push({ ...c, ok: true, response: await post('/loyalty/milestones/claim', { eventInstanceIds: [c.eventInstanceId], eventTiers: [c.tierIndex] }) }); }
        catch (e) { claims.push({ ...c, ok: false, error: e.message }); }
        await sleep(1500);
      }
      await sleep(2500);
    }
    return { rounds, claims, finalProgress: await get('/loyalty/milestones/progress/') };
  }, { maxRounds: config.maxClaimRounds });
}
async function claimAll(page) {
  const startedAt = new Date().toISOString();
  await page.goto(config.storeUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(config.uiSettleMs);
  const player = await playerSummary(page);
  if (!player.ok) throw new Error(`player check failed: ${JSON.stringify(player)}`);
  const uiFreeClaims = await claimVisibleFreeGifts(page);
  await page.goto(config.storeUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(config.uiSettleMs);
  const apiFree = await claimFreeStoreApi(page, player);
  const loyalty = await claimLoyaltyApi(page);
  return { type: 'claim', startedAt, finishedAt: new Date().toISOString(), player, uiFreeClaims, apiFree, loyalty };
}
async function startLoginTask(emailArg) {
  if (currentTask || pending) throw new Error('已有任务正在运行或等待用户输入');
  const email = resolveEmail(emailArg);
  if (!validateEmail(email)) {
    setStatus('awaiting_email', { operation: 'login', message: '请输入 EA 账号邮箱', awaiting: { type: 'ea_email', after: 'login' }, startedAt: new Date().toISOString(), lastError: null });
    return;
  }
  setStatus('running', { operation: 'login', message: 'starting login', startedAt: new Date().toISOString(), awaiting: null, lastError: null });
  currentTask = (async () => {
    const context = await launchBrowser();
    const page = await getPage(context);
    try {
      await ensureAuthorized(page, context, null, email);
      const player = await playerSummary(page);
      setStatus('idle', { operation: null, message: 'login completed', lastRun: { type: 'login', player }, lastError: null });
      await context.close();
      log('browser closed after login');
    } catch (e) {
      if (e instanceof NeedsInput) {
        if (e.type === 'ea_email') {
          await context.close().catch(() => {});
          log('browser closed while waiting for email');
        }
        return;
      }
      await context.close().catch(() => {});
      setStatus('error', { operation: null, message: e.message, lastError: { message: e.message, stack: e.stack } });
    } finally { currentTask = null; }
  })();
}
async function startClaimTask(emailArg) {
  if (currentTask || pending) throw new Error('已有任务正在运行或等待用户输入');
  const email = resolveEmail(emailArg);
  setStatus('running', { operation: 'claim', message: 'starting claim', startedAt: new Date().toISOString(), awaiting: null, lastError: null });
  currentTask = (async () => {
    const context = await launchBrowser();
    const page = await getPage(context);
    try {
      await ensureAuthorized(page, context, 'claim', email);
      const run = await claimAll(page);
      setStatus('idle', { operation: null, message: 'claim completed', lastRun: run, lastError: null });
      await context.close();
      log('browser closed after claim');
    } catch (e) {
      if (e instanceof NeedsInput) {
        if (e.type === 'ea_email') {
          await context.close().catch(() => {});
          log('browser closed while waiting for email');
        }
        return;
      }
      await context.close().catch(() => {});
      setStatus('error', { operation: null, message: e.message, lastError: { message: e.message, stack: e.stack } });
    } finally { currentTask = null; }
  })();
}
async function continueWithEmail(emailArg) {
  const awaiting = runtime.awaiting;
  if (!awaiting || awaiting.type !== 'ea_email') throw new Error('当前没有等待邮箱的流程');
  const email = resolveEmail(emailArg);
  if (!validateEmail(email)) throw new Error('邮箱格式不正确');
  if (awaiting.after === 'claim') await startClaimTask(email);
  else await startLoginTask(email);
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`);
    if (!requireAuth(req, res)) return;
    if (req.method === 'GET' && url.pathname === '/health') return send(res, 200, { ok: true, service: 'goh-webstore-automation', runtimeDir });
    if (req.method === 'GET' && url.pathname === '/status') return send(res, 200, publicState());
    if (req.method === 'GET' && url.pathname === '/logs') return send(res, 200, { logs: runtime.logs.slice(-Number(url.searchParams.get('limit') || 100)) });
    if (req.method === 'POST' && url.pathname === '/login/start') { const b = await readBody(req); await startLoginTask(b.email); return send(res, 202, publicState()); }
    if (req.method === 'POST' && url.pathname === '/login/email') { const b = await readBody(req); await continueWithEmail(b.email); return send(res, 202, publicState()); }
    if (req.method === 'POST' && url.pathname === '/login/code') { const b = await readBody(req); continuePendingWithCode(b.code).catch(e => log('code continuation failed', e.message)); return send(res, 202, publicState()); }
    if (req.method === 'POST' && url.pathname === '/claim/run') { const b = await readBody(req); await startClaimTask(b.email); return send(res, 202, publicState()); }
    if (req.method === 'POST' && url.pathname === '/cleanup') { clearWaitingWithoutBrowser('手动清理'); return send(res, 200, publicState()); }
    return send(res, 404, { error: 'Not found' });
  } catch (e) { log('request error', e.message); return send(res, 500, { error: e.message }); }
});
server.listen(config.port, config.host, () => log(`service listening on http://${config.host}:${config.port}`, { runtimeDir }));
process.on('SIGTERM', () => { closePending('SIGTERM'); process.exit(0); });
