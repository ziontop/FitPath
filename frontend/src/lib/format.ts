import type { Units } from '../api'

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ')

export const clampPct = (n: number) => Math.max(0, Math.min(100, n))

export function pct(value: number, target: number): number {
  if (!target) return 0
  return clampPct(Math.round((value / target) * 100))
}

export const round = (n: number, dp = 0) => {
  const f = 10 ** dp
  return Math.round(n * f) / f
}

// ---- units ----
export const KG_PER_LB = 0.45359237
export const kgToLb = (kg: number) => kg / KG_PER_LB
export const lbToKg = (lb: number) => lb * KG_PER_LB
export const cmToIn = (cm: number) => cm / 2.54

export function displayWeight(kg: number, units: Units): string {
  return units === 'imperial' ? `${round(kgToLb(kg), 1)} lb` : `${round(kg, 1)} kg`
}

export function weightUnitLabel(units: Units): string {
  return units === 'imperial' ? 'lb' : 'kg'
}

// ---- dates ----
export function todayISO(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function formatDateLabel(iso: string): string {
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso)
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

export function formatTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso)
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

export function friendlyDate(iso: string): string {
  return new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso).toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

export function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

export const capitalize = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)

export const humanize = (s: string) => capitalize(s.replace(/_/g, ' '))

/** mm:ss timer formatting */
export function mmss(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
