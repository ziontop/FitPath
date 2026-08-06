import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setMockEnabled } from '.'
import { appleHealth, appleHealthTokens } from './endpoints'

function jsonResponse(body: unknown, status = 200): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    statusText: 'stub',
    headers: { get: (k: string) => (k.toLowerCase() === 'content-type' ? 'application/json' : null) },
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response
}

describe('Apple Health API surface', () => {
  beforeEach(() => {
    setMockEnabled(false)
    document.cookie = 'fitpath_csrf=csrf-apple'
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uploads FormData without forcing Content-Type and with credentials + CSRF', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ filename: 'export.xml', counts_by_type: {}, warnings: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await appleHealth.preview(new File(['<HealthData />'], 'export.xml', { type: 'text/xml' }))

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/integrations/apple-health/preview')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('include')
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.headers['X-CSRF-Token']).toBe('csrf-apple')
    expect('Content-Type' in init.headers).toBe(false)
  })

  it('re-uploads the retained file and sends selected types on import', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ batch_id: 1, results: {}, totals: {} }))
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['xml'], 'export.xml')

    await appleHealth.import(file, ['steps', 'sleep'])

    const form = fetchMock.mock.calls[0][1].body as FormData
    expect(form.get('file')).toBe(file)
    expect(form.get('types')).toBe(JSON.stringify(['steps', 'sleep']))
  })

  it('token list never requires or exposes a secret shape', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [{ id: 1, name: 'Phone', prefix: 'fpk_demo', created_at: '2026-01-01T00:00:00' }] }))
    vi.stubGlobal('fetch', fetchMock)
    const tokens = await appleHealthTokens.list()
    expect(tokens.items[0]).not.toHaveProperty('token')
  })
})
