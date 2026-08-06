import { mockRequest } from './mock'

export const API_BASE = '/api'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
const MUTATIONS: HttpMethod[] = ['POST', 'PUT', 'PATCH', 'DELETE']

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** Reads a cookie value by name (used for the JS-readable CSRF token). */
export function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'))
  return match ? decodeURIComponent(match[1]) : null
}

// ---------------- Mock toggle (dev flag) ----------------
const MOCK_KEY = 'fitpath-mock'

/** Whether the typed mock backend is active. Defaults ON in dev so screens are demoable. */
export function isMockEnabled(): boolean {
  try {
    const v = localStorage.getItem(MOCK_KEY)
    if (v === 'off') return false
    if (v === 'on') return true
  } catch {
    // ignore storage errors
  }
  return import.meta.env.DEV
}

export function setMockEnabled(on: boolean): void {
  localStorage.setItem(MOCK_KEY, on ? 'on' : 'off')
}

// ---------------- Query helper ----------------
export function toQuery(params?: Record<string, string | number | boolean | undefined>): string {
  if (!params) return ''
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}

export interface RequestOptions {
  /** Redirect to /login on a 401 response. Defaults to true. */
  redirectOn401?: boolean
  signal?: AbortSignal
}

function redirectToLogin() {
  const path = window.location.pathname
  if (path !== '/login' && path !== '/register') {
    window.location.assign('/login')
  }
}

/**
 * Core request wrapper.
 * - Always sends credentials so the httpOnly session cookie travels with the request.
 * - Echoes the readable `fitpath_csrf` cookie in `X-CSRF-Token` on state-changing calls.
 * - Redirects to /login on 401 (unless opted out).
 * - Dispatches to the in-memory mock backend when the dev mock flag is on.
 */
export async function request<T>(
  method: HttpMethod,
  path: string,
  body?: unknown,
  opts: RequestOptions = {},
): Promise<T> {
  const { redirectOn401 = true } = opts

  if (isMockEnabled()) {
    try {
      return (await mockRequest(method, path, body)) as T
    } catch (err) {
      if (err instanceof ApiError && err.status === 401 && redirectOn401) redirectToLogin()
      throw err
    }
  }

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (MUTATIONS.includes(method)) {
    const csrf = getCookie('fitpath_csrf')
    if (csrf) headers['X-CSRF-Token'] = csrf
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: 'include',
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: opts.signal,
  })

  if (res.status === 401) {
    if (redirectOn401) redirectToLogin()
    throw new ApiError(401, await extractDetail(res, 'Not authenticated'))
  }
  if (!res.ok) {
    throw new ApiError(res.status, await extractDetail(res, res.statusText))
  }
  if (res.status === 204) return undefined as T
  const ct = res.headers.get('content-type') ?? ''
  return (ct.includes('application/json') ? await res.json() : await res.text()) as T
}

async function extractDetail(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json()
    if (data && typeof data.detail === 'string') return data.detail
    return fallback
  } catch {
    return fallback
  }
}

export async function upload<T>(
  path: string,
  formData: FormData,
  opts: RequestOptions = {},
): Promise<T> {
  const { redirectOn401 = true } = opts

  if (isMockEnabled()) {
    try {
      return (await mockRequest('POST', path, formData)) as T
    } catch (err) {
      if (err instanceof ApiError && err.status === 401 && redirectOn401) redirectToLogin()
      throw err
    }
  }

  const headers: Record<string, string> = {}
  const csrf = getCookie('fitpath_csrf')
  if (csrf) headers['X-CSRF-Token'] = csrf

  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers,
    body: formData,
    signal: opts.signal,
  })

  if (res.status === 401) {
    if (redirectOn401) redirectToLogin()
    throw new ApiError(401, await extractDetail(res, 'Not authenticated'))
  }
  if (!res.ok) {
    throw new ApiError(res.status, await extractDetail(res, res.statusText))
  }
  const ct = res.headers.get('content-type') ?? ''
  return (ct.includes('application/json') ? await res.json() : await res.text()) as T
}

export const http = {
  get: <T>(path: string, opts?: RequestOptions) => request<T>('GET', path, undefined, opts),
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('POST', path, body, opts),
  put: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('PUT', path, body, opts),
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('PATCH', path, body, opts),
  del: <T>(path: string, opts?: RequestOptions) => request<T>('DELETE', path, undefined, opts),
  delWithBody: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('DELETE', path, body, opts),
  upload,
}
