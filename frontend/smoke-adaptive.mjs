// Adaptive-UI smoke test: drives the Vite dev server with the in-memory MOCK
// backend (adaptive data) across {theme} x {viewport} x {route}, asserting the
// new adaptive surfaces render with no errors/skeletons. Temporary; deleted after.
import { chromium } from 'playwright'

const BASE = process.env.SMOKE_BASE || 'http://127.0.0.1:5219'
const THEMES = ['light', 'dark']
const VIEWPORTS = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } }
const USER = { id: 1, email: 'zina@fitpath.dev', username: 'zina', created_at: '2026-01-01T00:00:00' }

function initScript(theme) {
  return `try {
    localStorage.setItem('fitpath-theme', ${JSON.stringify(theme)});
    localStorage.setItem('fitpath-mock', 'on');
    localStorage.setItem('fitpath-mock-auth', ${JSON.stringify(JSON.stringify(USER))});
  } catch (e) {}`
}

const results = []
function record(name, ok, note = '') {
  results.push({ name, ok, note })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  ${note}`.trim())
}

async function launch() {
  for (const t of [{ channel: 'msedge' }, { channel: 'chrome' }, {}]) {
    try {
      return await chromium.launch(t.channel ? { channel: t.channel } : {})
    } catch (e) {
      console.log(`channel ${t.channel || 'chromium'} unavailable: ${e.message.split('\n')[0]}`)
    }
  }
  throw new Error('no browser channel')
}

async function checkRoute(page, tag, route, asserts) {
  const errs = []
  const onErr = (e) => errs.push(String(e))
  const onConsole = (m) => m.type() === 'error' && errs.push(m.text())
  page.on('pageerror', onErr)
  page.on('console', onConsole)
  try {
    await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.page h1', { timeout: 20000, state: 'visible' })
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
    await page.waitForTimeout(400)
    const skel = await page.locator('.skeleton:visible').count().catch(() => 0)
    const theme = await page.evaluate(() => document.documentElement.getAttribute('data-theme'))
    let note = `theme=${theme}`
    let ok = skel === 0
    if (skel) note += ` skeleton(${skel})`
    for (const a of asserts) {
      const n = await page.locator(a.sel).count().catch(() => 0)
      if (n < 1) { ok = false; note += ` MISSING:${a.label}` }
    }
    const appErrs = errs.filter((e) => !/favicon|ResizeObserver/i.test(e))
    if (appErrs.length) { ok = false; note += ` errors:${appErrs.length}` }
    record(tag, ok, note + (appErrs[0] ? ` [${appErrs[0].slice(0, 80)}]` : ''))
  } catch (e) {
    record(tag, false, `EXC ${e.message.split('\n')[0]}`)
  } finally {
    page.off('pageerror', onErr)
    page.off('console', onConsole)
  }
}

async function run() {
  const browser = await launch()
  for (const theme of THEMES) {
    for (const [vp, viewport] of Object.entries(VIEWPORTS)) {
      const ctx = await browser.newContext({ viewport, colorScheme: theme })
      await ctx.addInitScript(initScript(theme))
      const page = await ctx.newPage()
      const p = (r) => `${theme}/${vp}${r}`

      await checkRoute(page, p(' Today'), '/', [{ sel: 'text=Built from your history', label: 'card' }])
      await checkRoute(page, p(' Workout'), '/workout', [{ sel: 'text=Why this target', label: 'adaptive-plan' }])
      await checkRoute(page, p(' Nutrition'), '/nutrition', [
        { sel: 'text=Based on your eating history', label: 'card' },
        { sel: 'button:has-text("Log this")', label: 'log-btn' },
      ])
      // Insights: switch to the insights view, then assert the summary.
      try {
        await page.goto(`${BASE}/insights`, { waitUntil: 'domcontentloaded' })
        await page.waitForSelector('.page h1', { timeout: 20000, state: 'visible' })
        await page.getByRole('radio', { name: /insights/i }).click()
        await page.waitForTimeout(300)
        const n = await page.locator('text=What your history is changing').count()
        record(p(' Insights'), n >= 1, n >= 1 ? '' : 'MISSING:summary')
      } catch (e) {
        record(p(' Insights'), false, `EXC ${e.message.split('\n')[0]}`)
      }

      await ctx.close()
    }
  }
  await browser.close()

  const pass = results.filter((r) => r.ok).length
  console.log(`\n===== SMOKE SUMMARY: ${pass}/${results.length} clean =====`)
  process.exit(pass === results.length ? 0 : 2)
}

run().catch((e) => { console.error('FATAL', e); process.exit(1) })
