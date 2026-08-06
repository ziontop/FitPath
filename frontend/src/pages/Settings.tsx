import './Settings.css'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Save, ArrowRight, Moon, Database, LogOut, ClipboardList, User, UploadCloud, KeyRound, Trash2, RotateCw } from 'lucide-react'
import { profile as profileApi, isMockEnabled, setMockEnabled } from '../api'
import { appleHealth, appleHealthTokens } from '../api/endpoints'
import type { AppleHealthImportBatch, AppleHealthImportResponse, AppleHealthImportType, AppleHealthPreview, AppleHealthToken, AppleHealthTokenSecret, NutritionGoal, Profile, TrainingGoal, Units } from '../api'
import { useAsync } from '../lib/useAsync'
import { capitalize, displayWeight, humanize } from '../lib/format'
import { useAuth } from '../auth/useAuth'
import { useTheme } from '../theme/useTheme'
import { ThemeToggle } from '../components/ThemeToggle'
import {
  Button,
  Card,
  CardHeader,
  Checkbox,
  EmptyState,
  Input,
  PageHeader,
  Segmented,
  Skeleton,
  useToast,
} from '../components/ui'

const importTypes: { value: AppleHealthImportType; label: string }[] = [
  { value: 'steps', label: 'Steps' },
  { value: 'weight', label: 'Body mass' },
  { value: 'sleep', label: 'Sleep' },
  { value: 'water', label: 'Water' },
  { value: 'workouts', label: 'Workouts' },
]

function totalFor(result?: AppleHealthImportResponse) {
  if (!result) return 0
  return result.totals.inserted + result.totals.updated + result.totals.skipped + result.totals.invalid + result.totals.conflict
}

function AppleHealthCard() {
  const toast = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<AppleHealthPreview | null>(null)
  const [selected, setSelected] = useState<AppleHealthImportType[]>(importTypes.map((t) => t.value))
  const [importResult, setImportResult] = useState<AppleHealthImportResponse | null>(null)
  const [history, setHistory] = useState<AppleHealthImportBatch[]>([])
  const [tokens, setTokens] = useState<AppleHealthToken[]>([])
  const [newToken, setNewToken] = useState<AppleHealthTokenSecret | null>(null)
  const [tokenName, setTokenName] = useState('iPhone Shortcut')
  const [busy, setBusy] = useState<string | null>(null)

  async function refresh() {
    const [imports, tokenList] = await Promise.all([
      appleHealth.imports().catch(() => ({ items: [] })),
      appleHealthTokens.list().catch(() => ({ items: [] })),
    ])
    setHistory(imports.items)
    setTokens(tokenList.items)
  }

  useEffect(() => {
    void refresh()
  }, [])

  async function onPreview(chosen: File) {
    setFile(chosen)
    setPreview(null)
    setImportResult(null)
    setBusy('preview')
    try {
      const next = await appleHealth.preview(chosen)
      setPreview(next)
      setSelected(importTypes.filter((t) => (next.counts_by_type[t.value] ?? 0) > 0).map((t) => t.value))
      toast.success('Preview ready. Choose what to import.')
    } catch {
      toast.error('Could not preview this Apple Health export.')
    } finally {
      setBusy(null)
    }
  }

  async function onImport() {
    if (!file || selected.length === 0) return
    setBusy('import')
    try {
      const result = await appleHealth.import(file, selected)
      setImportResult(result)
      await refresh()
      toast.success('Apple Health import finished.')
    } catch {
      toast.error('Import failed. Try previewing the export again.')
    } finally {
      setBusy(null)
    }
  }

  async function onDeleteImported() {
    if (!window.confirm('Delete imported Apple Health rows? Rows you manually edited will be preserved.')) return
    setBusy('delete')
    try {
      const report = await appleHealth.deleteData()
      await refresh()
      toast.info(`Deleted imported data; preserved ${Object.values(report.preserved_modified).reduce((a, b) => a + (b ?? 0), 0)} modified rows.`)
    } catch {
      toast.error('Could not delete imported Apple Health data.')
    } finally {
      setBusy(null)
    }
  }

  async function createToken() {
    setBusy('token')
    try {
      const token = await appleHealthTokens.create({ name: tokenName, expires_in_days: 365 })
      setNewToken(token)
      await refresh()
      toast.success('Token created. Copy it now.')
    } catch {
      toast.error('Could not create token.')
    } finally {
      setBusy(null)
    }
  }

  async function rotateToken(id: number) {
    setBusy(`rotate-${id}`)
    try {
      const token = await appleHealthTokens.rotate(id)
      setNewToken(token)
      await refresh()
      toast.success('Token rotated. Copy the new secret now.')
    } catch {
      toast.error('Could not rotate token.')
    } finally {
      setBusy(null)
    }
  }

  async function revokeToken(id: number) {
    setBusy(`revoke-${id}`)
    try {
      await appleHealthTokens.revoke(id)
      await refresh()
      toast.info('Token revoked.')
    } catch {
      toast.error('Could not revoke token.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card>
      <CardHeader title="Apple Health" />
      <div className="set-ah stack">
        <div className="set-ah__notice">
          <strong>Browser limitation:</strong> FitPath on the web cannot read HealthKit directly. Use a manual
          Apple Health <code>export.zip</code>/<code>export.xml</code> import, or an iOS Shortcut that you tap to
          sync daily aggregates over HTTPS.
        </div>
        <p className="set-ah__copy">
          FitPath imports only Steps, Body mass, Sleep, Water, and Workouts. It does not import dietary
          energy or macros. Raw exports are used for preview/import only; imported rows can be deleted anytime,
          and manually edited rows are preserved.
        </p>

        <div className="set-ah__panel">
          <h3>Manual export import</h3>
          <Input
            label="Apple Health export file"
            type="file"
            accept=".xml,.zip,application/zip,text/xml"
            onChange={(e) => {
              const chosen = e.target.files?.[0]
              if (chosen) void onPreview(chosen)
            }}
          />
          {preview ? (
            <div className="set-ah__preview" aria-label="Apple Health preview">
              <p className="set-ah__copy">
                Preview for <strong>{preview.filename}</strong> · {preview.date_range.start ?? 'unknown'} to{' '}
                {preview.date_range.end ?? 'unknown'}. The selected file is kept in this browser session and
                re-uploaded for import because the server does not retain preview data.
              </p>
              <div className="set-ah__type-grid">
                {importTypes.map((t) => (
                  <Checkbox
                    key={t.value}
                    label={`${t.label} (${preview.counts_by_type[t.value] ?? 0})`}
                    checked={selected.includes(t.value)}
                    onChange={(e) =>
                      setSelected((cur) => (e.target.checked ? [...cur, t.value] : cur.filter((x) => x !== t.value)))
                    }
                  />
                ))}
              </div>
              {preview.warnings.map((w) => (
                <p className="set-ah__warning" key={w}>{w}</p>
              ))}
              <Button loading={busy === 'import'} leftIcon={<UploadCloud size={16} />} onClick={onImport} disabled={!file || selected.length === 0}>
                Import selected
              </Button>
            </div>
          ) : (
            <EmptyState title="Preview before importing" text="Choose an export to see counts per type before anything is committed." />
          )}
          {importResult ? <p className="set-ah__success">Import batch #{importResult.batch_id}: {totalFor(importResult)} records processed; {importResult.totals.conflict} preserved manual edits.</p> : null}
        </div>

        <div className="set-ah__panel">
          <CardHeader
            title="Import history"
            action={<Button variant="secondary" size="sm" leftIcon={<Trash2 size={15} />} loading={busy === 'delete'} onClick={onDeleteImported}>Delete imported data</Button>}
          />
          {history.length ? (
            <ul className="set-ah__list">
              {history.map((b) => (
                <li key={b.id}>
                  <strong>#{b.id}</strong> {b.source} · {b.status} · inserted {b.records_inserted}, updated {b.records_updated}, skipped {b.records_skipped}, invalid {b.records_invalid}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No imports yet" text="Completed file imports and Shortcut syncs will appear here." />
          )}
        </div>

        <div className="set-ah__panel">
          <h3>iOS Shortcut tap-to-sync</h3>
          <p className="set-ah__copy">
            Generate a bearer token, paste it into a Shortcut, and POST JSON daily aggregates to
            <code> /api/integrations/apple-health/shortcut</code>. This requires HTTPS outside localhost; Shortcuts are
            tap-to-sync, not silent background HealthKit access.
          </p>
          <div className="set-ah__token-create">
            <Input label="Token name" value={tokenName} onChange={(e) => setTokenName(e.target.value)} />
            <Button loading={busy === 'token'} leftIcon={<KeyRound size={16} />} onClick={createToken}>Generate token</Button>
          </div>
          {newToken ? (
            <div className="set-ah__secret" role="status">
              <strong>Copy now — this token is shown once:</strong>
              <code>{newToken.token}</code>
              <Button variant="secondary" size="sm" onClick={() => void navigator.clipboard?.writeText(newToken.token)}>Copy</Button>
            </div>
          ) : null}
          {tokens.length ? (
            <ul className="set-ah__list">
              {tokens.map((t) => (
                <li key={t.id}>
                  <span><strong>{t.name}</strong> · {t.prefix} · last used {t.last_used_at ?? 'never'}{t.revoked_at ? ' · revoked' : ''}</span>
                  <span className="set-ah__actions">
                    <Button variant="secondary" size="sm" leftIcon={<RotateCw size={14} />} loading={busy === `rotate-${t.id}`} onClick={() => rotateToken(t.id)}>Rotate</Button>
                    <Button variant="ghost" size="sm" loading={busy === `revoke-${t.id}`} onClick={() => revokeToken(t.id)}>Revoke</Button>
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </Card>
  )
}

function SettingsSkeleton() {
  return (
    <div className="page" aria-busy="true" aria-label="Loading settings">
      <div className="stack-sm">
        <Skeleton variant="text" width={110} />
        <Skeleton variant="title" width={180} />
      </div>
      {[0, 1, 2].map((i) => (
        <Card key={i}>
          <Skeleton variant="title" />
          <div style={{ marginTop: 'var(--sp-4)' }}>
            <Skeleton variant="text" lines={3} />
          </div>
        </Card>
      ))}
    </div>
  )
}

export function Settings() {
  const toast = useToast()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { theme } = useTheme()

  const { data, loading } = useAsync(async () => profileApi.get().catch(() => null), [])
  const [form, setForm] = useState<Profile | null>(null)
  const [saving, setSaving] = useState(false)
  const [mock, setMock] = useState(isMockEnabled())

  const current = form ?? data
  function patch<K extends keyof Profile>(key: K, value: Profile[K]) {
    if (!current) return
    setForm({ ...current, [key]: value })
  }
  const num = (v: string) => (v === '' ? 0 : Number(v))

  async function save() {
    if (!current) return
    setSaving(true)
    try {
      await profileApi.upsert(current)
      toast.success('Settings saved.')
    } catch {
      toast.error('Could not save settings.')
    } finally {
      setSaving(false)
    }
  }

  async function onLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  function toggleMock(on: boolean) {
    setMock(on)
    setMockEnabled(on)
    toast.info(on ? 'Using demo data' : 'Using live backend')
    setTimeout(() => window.location.reload(), 600)
  }

  if (loading) return <SettingsSkeleton />

  const initial = (current?.name?.trim()?.[0] ?? user?.username?.[0] ?? 'U').toUpperCase()

  const bodyStats = current
    ? [
        { label: 'Sex', value: capitalize(current.sex) },
        { label: 'Age', value: `${current.age}` },
        { label: 'Height', value: `${current.height_cm} cm` },
        { label: 'Weight', value: displayWeight(current.weight_kg, current.units) },
        { label: 'Activity', value: humanize(current.activity_level) },
        { label: 'Experience', value: humanize(current.experience_level) },
      ]
    : []

  return (
    <div className="page stagger">
      <PageHeader
        eyebrow="Account"
        title="Settings"
        subtitle={`Signed in as ${user?.username ?? 'you'}.`}
        actions={
          current ? (
            <Button loading={saving} leftIcon={<Save size={18} aria-hidden="true" />} onClick={save}>
              Save changes
            </Button>
          ) : undefined
        }
      />

      {/* Profile */}
      {current ? (
        <Card>
          <CardHeader
            title="Profile"
            action={
              <Button
                variant="ghost"
                size="sm"
                rightIcon={<ArrowRight size={16} aria-hidden="true" />}
                onClick={() => navigate('/onboarding')}
              >
                Edit full profile
              </Button>
            }
          />
          <div className="set-profile">
            <span className="set-avatar" aria-hidden="true">
              {initial}
            </span>
            <div className="set-profile__meta">
              <div className="set-profile__name">{current.name?.trim() || 'Your profile'}</div>
              <div className="set-profile__tags">
                {capitalize(current.goal)} · {humanize(current.training_goal)} · {current.days_per_week}×/week
              </div>
            </div>
          </div>

          <p className="set-facts__note">Read-only — update these on your full profile.</p>
          <dl className="set-facts">
            {bodyStats.map((s) => (
              <div key={s.label} className="set-fact">
                <dt className="set-fact__label">{s.label}</dt>
                <dd className="set-fact__value num">{s.value}</dd>
              </div>
            ))}
          </dl>

          <div className="set-field">
            <Input
              label="Display name"
              value={current.name ?? ''}
              placeholder="Add your name"
              onChange={(e) => patch('name', e.target.value)}
            />
          </div>
        </Card>
      ) : (
        <Card>
          <EmptyState
            icon={<ClipboardList size={28} aria-hidden="true" />}
            title="Set up your profile"
            text="Add your body stats and goals so FitPath can personalise your targets."
            action={<Button onClick={() => navigate('/onboarding')}>Set up profile</Button>}
          />
        </Card>
      )}

      {/* Goals & targets */}
      {current ? (
        <Card>
          <CardHeader title="Goals & targets" />
          <div className="stack">
            <div className="set-control">
              <span className="set-control__label">Nutrition goal</span>
              <Segmented<NutritionGoal>
                block
                ariaLabel="Nutrition goal"
                value={current.goal}
                onChange={(v) => patch('goal', v)}
                options={[
                  { value: 'lose', label: 'Lose' },
                  { value: 'maintain', label: 'Maintain' },
                  { value: 'gain', label: 'Gain' },
                ]}
              />
            </div>
            <div className="set-control">
              <span className="set-control__label">Training goal</span>
              <Segmented<TrainingGoal>
                block
                ariaLabel="Training goal"
                value={current.training_goal}
                onChange={(v) => patch('training_goal', v)}
                options={[
                  { value: 'powerlifting', label: 'Powerlifting' },
                  { value: 'hypertrophy', label: 'Hypertrophy' },
                  { value: 'maingain', label: 'Lean gain' },
                ]}
              />
            </div>
            <div className="set-grid">
              <Input label="Training days / week" type="number" min={1} max={7} value={String(current.days_per_week)} onChange={(e) => patch('days_per_week', num(e.target.value))} />
              <Input label="Step goal" type="number" value={String(current.step_goal)} onChange={(e) => patch('step_goal', num(e.target.value))} />
              <Input label="Water goal (ml)" type="number" value={String(current.water_goal_ml)} onChange={(e) => patch('water_goal_ml', num(e.target.value))} />
              <Input label="Exercise goal (min)" type="number" value={String(current.exercise_goal_min)} onChange={(e) => patch('exercise_goal_min', num(e.target.value))} />
            </div>
          </div>
        </Card>
      ) : null}

      <AppleHealthCard />

      {/* Preferences */}
      <Card>
        <CardHeader title="Preferences" />
        <div className="stack">
          <div className="set-pref">
            <span className="set-pref__icon" aria-hidden="true">
              <Moon size={18} />
            </span>
            <div className="set-pref__text">
              <span className="set-pref__title">Dark mode</span>
              <span className="set-pref__desc">Currently using the {theme} theme.</span>
            </div>
            <ThemeToggle />
          </div>

          {current ? (
            <div className="set-pref set-pref--stack">
              <div className="set-pref__text">
                <span className="set-pref__title">Units</span>
                <span className="set-pref__desc">Measurement system for weights and distances.</span>
              </div>
              <Segmented<Units>
                block
                ariaLabel="Units"
                value={current.units}
                onChange={(v) => patch('units', v)}
                options={[
                  { value: 'metric', label: 'Metric (kg)' },
                  { value: 'imperial', label: 'Imperial (lb)' },
                ]}
              />
            </div>
          ) : null}

          <div className="set-pref set-pref--stack">
            <div className="set-pref__text">
              <span className="set-pref__title">
                <span className="set-pref__icon-inline" aria-hidden="true">
                  <Database size={15} />
                </span>
                Data source
              </span>
              <span className="set-pref__desc">
                Demo mode uses realistic in-app data so every screen works without the backend running.
              </span>
            </div>
            <Segmented<'demo' | 'live'>
              block
              ariaLabel="Data source"
              value={mock ? 'demo' : 'live'}
              onChange={(v) => toggleMock(v === 'demo')}
              options={[
                { value: 'demo', label: 'Demo data' },
                { value: 'live', label: 'Live backend' },
              ]}
            />
          </div>
        </div>
      </Card>

      {/* Account */}
      <Card>
        <CardHeader title="Account" />
        <div className="set-account">
          <span className="set-account__icon" aria-hidden="true">
            <User size={18} />
          </span>
          <div className="set-account__meta">
            <span className="set-account__name">{user?.username ?? 'You'}</span>
            {user?.email ? <span className="set-account__sub">{user.email}</span> : null}
          </div>
          <Button variant="secondary" leftIcon={<LogOut size={18} aria-hidden="true" />} onClick={onLogout}>
            Log out
          </Button>
        </div>
      </Card>
    </div>
  )
}
