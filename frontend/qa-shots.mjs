// FitPath UI QA screenshot capture.
// Drives the real production build served at http://127.0.0.1:8137 and captures
// full-page PNGs for {theme} x {viewport} x {route}. See STEP 3 of the QA brief.
import { chromium } from 'playwright'
import path from 'node:path'

const BASE = 'http://127.0.0.1:8137'
const OUT = 'C:/Users/t-zinaokoye/.copilot/session-state/89dd793c-aedb-4826-aa91-fd2fcea86a6f/files/ui-screenshots'

const THEMES = ['light', 'dark']
const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  mobile: { width: 390, height: 844 },
}

// Logged-in routes captured as sam_bulk. readySel = '.page h1' (skeletons have no h1).
const PAGE_H1 = '.page h1'
const LOGGED_IN = [
  { route: '/', name: 'today', ready: PAGE_H1 },
  { route: '/workout', name: 'workout', ready: PAGE_H1 },
  { route: '/nutrition', name: 'nutrition', ready: PAGE_H1 },
  { route: '/programs', name: 'programs', ready: PAGE_H1 },
  { route: '/performance', name: 'performance', ready: PAGE_H1 },
  { route: '/insights', name: 'insights', ready: PAGE_H1 },
  { route: '/settings', name: 'settings', ready: PAGE_H1 },
]
const LOGGED_OUT = [
  { route: '/login', name: 'login', ready: 'h1.auth-title' },
  { route: '/register', name: 'register', ready: 'h1.auth-title' },
]
const ONBOARDING = { route: '/onboarding', name: 'onboarding', ready: '.onb-hero__title' }

const SAM = { identifier: 'sam_bulk', password: 'FitPathDemo!2' }
const rand = Math.random().toString(36).slice(2, 8)
const TW = { email: `uaq_${rand}@fitpath.demo`, username: `uaq_${rand}`, password: 'FitPathDemo!9' }

const results = []
let throwawayCreated = false

function initScript(theme) {
  // Runs before any page script: force the theme + live backend (mocks off).
  return `
    try {
      localStorage.setItem('fitpath-theme', ${JSON.stringify(theme)});
      localStorage.setItem('fitpath-mock', 'off');
    } catch (e) {}
  `
}

async function login(page, creds) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('h1.auth-title', { timeout: 20000 })
  await page.fill('input[name="identifier"]', creds.identifier)
  await page.fill('input[name="password"]', creds.password)
  await page.click('button[type="submit"]')
  await page.waitForFunction(() => !location.pathname.includes('login'), null, { timeout: 20000 })
}

async function register(page, creds) {
  await page.goto(`${BASE}/register`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('h1.auth-title', { timeout: 20000 })
  await page.fill('input[name="email"]', creds.email)
  await page.fill('input[name="username"]', creds.username)
  await page.fill('input[name="password"]', creds.password)
  await page.click('button[type="submit"]')
  await page.waitForFunction(() => location.pathname.includes('onboarding'), null, { timeout: 20000 })
}

async function capture(page, theme, vpName, spec) {
  const file = `${theme}__${vpName}__${spec.name}.png`
  const dest = path.join(OUT, file)
  const rec = { file, ok: false, note: '' }
  try {
    await page.goto(`${BASE}${spec.route}`, { waitUntil: 'domcontentloaded' })
    let readyOk = true
    try {
      await page.waitForSelector(spec.ready, { timeout: 20000, state: 'visible' })
    } catch {
      readyOk = false
      rec.note += `ready-selector "${spec.ready}" not visible; `
    }
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(900) // let rings/charts finish animating

    const dataTheme = await page.evaluate(() => document.documentElement.getAttribute('data-theme'))
    if (dataTheme !== theme) rec.note += `data-theme="${dataTheme}" != "${theme}"; `

    const skel = await page.locator('.skeleton:visible').count().catch(() => 0)
    if (skel > 0) rec.note += `${skel} skeleton(s) still visible; `
    const errText = await page
      .locator('text=/something went wrong/i')
      .count()
      .catch(() => 0)
    if (errText > 0) rec.note += `error state shown; `

    await page.screenshot({ path: dest, fullPage: true })
    rec.ok = readyOk && skel === 0 && errText === 0
  } catch (e) {
    rec.note += `EXCEPTION: ${e.message}`
    try {
      await page.screenshot({ path: dest, fullPage: true })
    } catch {}
  }
  results.push(rec)
  console.log(`${rec.ok ? 'PASS' : 'WARN'}  ${file}  ${rec.note}`.trim())
}

async function launchBrowser() {
  const tries = [
    { channel: 'msedge', label: 'msedge' },
    { channel: 'chrome', label: 'chrome' },
    { channel: undefined, label: 'chromium(bundled)' },
  ]
  for (const t of tries) {
    try {
      const b = await chromium.launch(t.channel ? { channel: t.channel } : {})
      console.log(`Launched browser channel: ${t.label}`)
      return { browser: b, channel: t.label }
    } catch (e) {
      console.log(`Channel ${t.label} unavailable: ${e.message.split('\n')[0]}`)
    }
  }
  throw new Error('No usable browser channel (msedge/chrome/chromium).')
}

async function run() {
  const { browser, channel } = await launchBrowser()

  // Ensure the throwaway account exists once (no profile => fresh onboarding).
  {
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    try {
      await register(page, TW)
      throwawayCreated = true
      console.log(`Created throwaway user ${TW.username}`)
    } catch (e) {
      console.log(`Throwaway register note: ${e.message.split('\n')[0]}`)
    }
    await ctx.close()
  }

  for (const theme of THEMES) {
    for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
      // --- Logged-in as sam_bulk ---
      const ctx = await browser.newContext({ viewport, colorScheme: theme, deviceScaleFactor: 1 })
      await ctx.addInitScript(initScript(theme))
      const page = await ctx.newPage()
      try {
        await login(page, SAM)
        for (const spec of LOGGED_IN) await capture(page, theme, vpName, spec)
      } catch (e) {
        console.log(`login(sam) failed [${theme}/${vpName}]: ${e.message.split('\n')[0]}`)
        for (const spec of LOGGED_IN) results.push({ file: `${theme}__${vpName}__${spec.name}.png`, ok: false, note: 'login failed' })
      }
      await ctx.close()

      // --- Logged-out (fresh, no cookies) ---
      const ctx2 = await browser.newContext({ viewport, colorScheme: theme, deviceScaleFactor: 1 })
      await ctx2.addInitScript(initScript(theme))
      const page2 = await ctx2.newPage()
      for (const spec of LOGGED_OUT) await capture(page2, theme, vpName, spec)
      await ctx2.close()

      // --- Onboarding (throwaway account, no profile) ---
      const ctx3 = await browser.newContext({ viewport, colorScheme: theme, deviceScaleFactor: 1 })
      await ctx3.addInitScript(initScript(theme))
      const page3 = await ctx3.newPage()
      try {
        if (throwawayCreated) {
          await login(page3, { identifier: TW.username, password: TW.password })
        } else {
          await register(page3, TW)
          throwawayCreated = true
        }
        await capture(page3, theme, vpName, ONBOARDING)
      } catch (e) {
        console.log(`onboarding failed [${theme}/${vpName}]: ${e.message.split('\n')[0]}`)
        results.push({ file: `${theme}__${vpName}__onboarding.png`, ok: false, note: 'auth failed' })
      }
      await ctx3.close()
    }
  }

  await browser.close()

  const pass = results.filter((r) => r.ok).length
  console.log('\n===== SUMMARY =====')
  console.log(`Browser channel: ${channel}`)
  console.log(`Captured: ${results.length}  Clean: ${pass}  Flagged: ${results.length - pass}`)
  for (const r of results.filter((r) => !r.ok)) console.log(`  FLAG: ${r.file}  ${r.note}`)
  console.log(`Output dir: ${OUT}`)
}

run().catch((e) => {
  console.error('FATAL', e)
  process.exit(1)
})
