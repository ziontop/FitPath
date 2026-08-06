import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { http, setMockEnabled, ApiError } from '.'

/** Minimal stand-in for a fetch Response the client wrapper understands. */
function jsonResponse(body: unknown, status = 200): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    statusText: 'stub',
    headers: {
      get: (k: string) => (k.toLowerCase() === 'content-type' ? 'application/json' : null),
    },
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response
}

describe('API client request wrapper', () => {
  beforeEach(() => {
    // Exercise the real fetch path, not the in-memory dev mock.
    setMockEnabled(false)
    document.cookie = 'fitpath_csrf=tok-123'
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('attaches the CSRF header + credentials on mutating requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 1 }))
    vi.stubGlobal('fetch', fetchMock)

    await http.post('/logs/meals', { name: 'oats', kcal: 300 })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/logs/meals')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('include')
    expect(init.headers['X-CSRF-Token']).toBe('tok-123')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(init.body).toBe(JSON.stringify({ name: 'oats', kcal: 300 }))
  })

  it('does not attach a CSRF header on safe GET requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await http.get('/logs/meals')

    const [, init] = fetchMock.mock.calls[0]
    expect(init.credentials).toBe('include')
    expect('X-CSRF-Token' in init.headers).toBe(false)
  })

  it('raises a typed ApiError carrying the server detail on non-2xx', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'nope' }, 401)))

    const err = (await http
      .get('/auth/me', { redirectOn401: false })
      .catch((e) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(401)
    expect(err.detail).toBe('nope')
  })
})
