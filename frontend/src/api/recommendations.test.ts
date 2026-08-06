import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { recommendations, auth, setMockEnabled } from '.'

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

describe('recommendations adaptive endpoints — URL/query construction', () => {
  beforeEach(() => {
    // Exercise the real fetch path so we can assert the request URL.
    setMockEnabled(false)
    document.cookie = 'fitpath_csrf=tok-123'
  })
  afterEach(() => vi.unstubAllGlobals())

  it('adaptive() GETs /recommendations/adaptive with no query', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}))
    vi.stubGlobal('fetch', fetchMock)
    await recommendations.adaptive()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/recommendations/adaptive')
    expect(init.method).toBe('GET')
  })

  it('meals() serialises category + limit into the query string', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}))
    vi.stubGlobal('fetch', fetchMock)
    await recommendations.meals({ category: 'dinner', limit: 5 })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/recommendations/meals?category=dinner&limit=5')
  })

  it('meals() with no args omits the query string entirely', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}))
    vi.stubGlobal('fetch', fetchMock)
    await recommendations.meals()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/recommendations/meals')
  })

  it('workout() serialises program_day_id into the query string', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}))
    vi.stubGlobal('fetch', fetchMock)
    await recommendations.workout({ program_day_id: 11 })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/recommendations/workout?program_day_id=11')
  })

  it('leaves the legacy today() endpoint unchanged', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}))
    vi.stubGlobal('fetch', fetchMock)
    await recommendations.today()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/recommendations/today')
  })
})

describe('mock adaptive backend — documented envelope shapes', () => {
  beforeEach(async () => {
    setMockEnabled(true)
    // The adaptive routes are auth-scoped; authenticate the in-memory mock.
    await auth.login({ identifier: 'zina', password: 'x' })
  })
  afterEach(() => setMockEnabled(false))

  it('adaptive() returns a well-formed envelope (meals + workout + tip)', async () => {
    const env = await recommendations.adaptive()
    expect(env.version).toBe('adaptive-v1')
    expect(env.algorithm).toBe('history-adaptive-deterministic')
    expect(typeof env.tip).toBe('string')
    expect(env.meals.suggestions.length).toBeGreaterThan(0)
    expect(['low', 'medium', 'high']).toContain(env.meals.confidence)
    expect(typeof env.workout.rest_day).toBe('boolean')
    expect(Array.isArray(env.workout.exercises)).toBe(true)
    // Every suggestion carries a ready-to-log payload that matches its macros.
    for (const s of env.meals.suggestions) {
      expect(s.meal_payload.kcal).toBe(s.kcal)
      expect(s.meal_payload.protein_g).toBe(s.protein_g)
      expect(s.portion).toBeGreaterThanOrEqual(0.5)
      expect(s.portion).toBeLessThanOrEqual(2.0)
    }
  })

  it('meals() honours the category filter deterministically', async () => {
    const a = await recommendations.meals({ category: 'dinner', limit: 3 })
    const b = await recommendations.meals({ category: 'dinner', limit: 3 })
    expect(a.suggestions.every((s) => s.category === 'dinner')).toBe(true)
    // Deterministic: same inputs → identical ranking/scaling.
    expect(a.suggestions.map((s) => [s.name, s.score, s.portion])).toEqual(
      b.suggestions.map((s) => [s.name, s.score, s.portion]),
    )
  })
})
