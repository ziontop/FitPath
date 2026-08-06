# FitPath UI Playbook — "Ridgeline"

> The shared design language, component library, and conventions for building
> FitPath's pages. **Read this fully before touching a page.**
>
> Locked visual contract: **`UI-V2-DIRECTION.md`**. Why it looks this way:
> **`UI-V2-RESEARCH.md`**. What was wrong before: **`UI-V2-AUDIT.md`**.

FitPath is a **dark-first, high-contrast performance instrument** in the register
of WHOOP, Oura, Strava, Hevy, and Linear. **Space Grotesk** sets display/headings/
hero metrics; **Inter** sets UI/body; **tabular lining numerals** are used on all
data. The palette is cool ink/graphite neutrals, an **indigo-violet** primary, and
a **volt** energy accent reserved for PRs, streaks, and goal completion. Surfaces
are flat with quiet borders, tight radii, neutral shadows, and calm 120–220ms
ease-out motion.

> Retired: Fredoka, Poppins, dominant orange, orange gradients, the orange→blue
> "AI" gradient, colored glow shadows, 22px radii, and springy bounce.

---

## 0. The golden rule (parallel-safe CSS)

The shared foundation (`src/styles/*`, `src/components/**`, `src/layout/AppShell.tsx`,
`Logo`) has been **re-skinned to Ridgeline** and is **frozen again** so page work
stays parallel-safe.

**Do NOT edit `src/styles/*` or `src/components/**`.** You may only edit:
- **your page's `.tsx`** (e.g. `src/pages/Workout.tsx`), and
- **one co-located, prefixed CSS file** imported at the **top** of that page.

- **USE** shared classes and components as-is.
- To tweak a shared component on your page, **wrap it** in your own prefixed
  element and override from your page CSS — do not modify the component or shared CSS.
- Every selector in your page CSS **must** start with your page prefix. No bare
  element selectors, no shared utility names.
- **Never hard-code** color/font/radius/shadow/timing — always use `var(--token)`.

### Prefix map (one namespace per page)

| Page | Prefix | CSS file |
| --- | --- | --- |
| Dashboard (Today) | `dash-` | `Dashboard.css` |
| Workout | `wk-` | `Workout.css` |
| Nutrition | `nut-` | `Nutrition.css` |
| Programs | `prog-` | `Programs.css` |
| Performance (Progress) | `perf-` | `Performance.css` |
| Insights (Coach) | `ins-` | `Insights.css` |
| Settings | `set-` | `Settings.css` |
| Onboarding | `onb-` | `Onboarding.css` |
| Auth (Login/Register) | `auth-` | co-located |

> Rules still in `src/styles/pages.css` are legacy. Migrate **only your page's**
> rules into your prefixed file; leave other pages' and shared-component rules alone.

---

## 1. Definition of "premium" (Ridgeline bar)

A page clears the bar when it has **all** of these:

1. **Glanceable hierarchy** — one clear focal point; the most important number/
   action is big, bold, and first. No field of equal-weight cards.
2. **Instrument-grade numerals** — Space Grotesk (`--font-num`) for hero values,
   Inter for dense inline data, always with tabular lining figures (`.num`).
3. **Restraint over decoration** — flat surfaces, quiet 1px borders, neutral
   low-spread shadows. Depth comes from surface steps + borders, not glow.
4. **One accent per context** — indigo carries the primary action/active state;
   **volt only** for PRs/streaks/goal completion. Icon badges neutral by default.
5. **Confident motion** — 120–220ms ease-out, no overshoot; minimal hover lift;
   restrained entrance/stagger. Respect `prefers-reduced-motion` (global).
6. **Polished loading** — skeletons that mirror the layout, never a bare spinner.
7. **Friendly empty states** — icon + title + one-line help + a clear CTA.
8. **Accessible** — WCAG AA contrast, visible focus rings, keyboard support,
   `aria-label`s on icon-only controls.
9. **Responsive** — great from 360px to desktop; both light **and** dark.
10. **Behavior unchanged** — presentational only. Do not touch API calls, routes,
    data logic, or prop contracts.

---

## 2. Design tokens (`src/styles/tokens.css`)

Use tokens via `var(--token)`. Full contract in **`UI-V2-DIRECTION.md §2`**.

### Type
`--font-display`/`--font-head` (Space Grotesk), `--font-body` (Inter),
`--font-num` (Space Grotesk, hero metrics), `--font-mono` (Space Grotesk),
`--numeric` (`tabular-nums lining-nums`). Sizes `--fs-display`,`--fs-h1…h4`,
`--fs-body`,`--fs-sm`,`--fs-xs`,`--fs-metric`; weights `--fw-*`; tracking
`--tracking-tight|tighter|wide`. Helpers: `.num`/`.tabular-nums`, `.metric-num`,
`.eyebrow`, `.text-display`.

### Color
Brand: `--color-primary`(+`-hover`,`-active`,`-soft`,`-contrast`). **Accent (volt,
achievements only):** `--color-accent`(+`-strong`,`-soft`,`-contrast`). Data/info:
`--color-secondary`(cyan), `--color-info`. Semantic: `--color-success`,
`--color-warning`, `--color-error` (+ `-soft`). Surfaces/text: `--bg`, `--surface`,
`--surface-2/3`, `--border`, `--border-strong`, `--text`, `--text-muted`,
`--text-subtle`. Rings: `--ring-move-*`(indigo), `--ring-exercise-*`(volt),
`--ring-hydrate-*`(cyan). Charts: `--chart-1…4`, `--chart-pr`, `--chart-grid`,
`--chart-axis`, `--chart-area-opacity`.

### Space / shape / elevation / motion
Spacing `--sp-1`(4)…`--sp-8`(64). Card density `--card-pad`(20), `--card-pad-lg`(24).
Radii `--radius-sm`(8), `--radius-md`(10, controls), `--radius-lg`(14, cards),
`--radius-xl`(18, one hero/overlays), `--radius-pill`, `--radius-circle`. Shadows
`--shadow-xs…xl` (neutral; `--shadow-primary*` aliased to neutral). Motion
`--dur-fast`(120)/`--dur`(180)/`--dur-slow`(220)/`--dur-slower`(280); easings
`--ease-standard`, `--ease-out`, `--ease-spring` (no-bounce alias).

### Animation utilities (`base.css`)
`.fade-in`, `.slide-up`, `.scale-in`, `.stagger` (on a parent; children animate in
sequence), `.skeleton` (+`--text|title|circle|block`). All respect reduced motion.

---

## 3. Icons — lucide-react

```tsx
import { Dumbbell, Plus } from 'lucide-react'
<Dumbbell size={18} aria-hidden="true" />
```
- **Monochrome `currentColor` only.** Sizes: 16 (inline), 18 (buttons/actions),
  20 (sidebar), 22 (bottom nav), 24–28 (empty-state/hero).
- Default `strokeWidth={2}`. Add `aria-hidden="true"` when decorative; give
  icon-only buttons a real label (`IconButton`).
- **Reduce tinted icon badges** — neutral by default; at most **one** accent icon
  per card. Never use emoji.
- Nav mapping: Today→`Home`, Workout→`Dumbbell`, Nutrition→`Apple`,
  Programs→`ClipboardList`, Progress→`TrendingUp`, Coach→`Sparkles`,
  Settings→`Settings`. Common: add→`Plus`, streak→`Flame`, water→`Droplet`,
  steps→`Footprints`, timer→`Timer`, rest→`Moon`.

---

## 4. Component library (`import { ... } from '../components/ui'`)

Strict-typed; import from the `ui` barrel. Ridgeline behavior notes are **bold**.

### Layout & headers
```tsx
<PageHeader eyebrow={friendlyDate(todayISO())} title="Good morning, Zina"
  subtitle="Here's your day" actions={<Button leftIcon={<Plus size={18}/>}>Quick add</Button>} />
<SectionTitle action={<Link to="/x">See all</Link>}>Recent workouts</SectionTitle>
```
**Eyebrows are muted (neutral), not accent.** One primary action per header.

### Cards
```tsx
<Card variant="hero">…</Card>   // hero = subtle indigo wash, radius 18
<CardHeader title="Nutrition" action={<Link to="/nutrition">Log meal</Link>} />
<StatCard label="Steps" value="8,210" sub="82% of goal" icon={<Footprints size={20}/>} center />
```
**Non-interactive cards do not lift on hover.** Add `interactive` for a subtle 1px
lift on clickable cards. Default padding `--card-pad`, radius 14, `--shadow-xs`.

### Metrics
```tsx
<MetricTile label="Protein" value={128} unit="g" icon={<Beef size={18}/>}
  delta={{ direction: 'up', label: '+6%' }} accentIcon />
```
Values render in `--font-num` + tabular numerals automatically. **Icon badge is
neutral by default; pass `accentIcon` to opt one tile into the soft-indigo badge.**

### Buttons
```tsx
<Button variant="primary" size="md" block loading leftIcon={…}>Save</Button>
<IconButton label="Close" variant="ghost"><X size={18}/></IconButton>
```
**Solid primary by default.** The `gradient` prop still exists but now renders a
**solid primary** fill (no gradient, no glow) — you generally don't need it. One
primary button per view.

### Feedback & states
```tsx
<EmptyState icon={<Dumbbell size={28}/>} title="No session planned"
  text="Pick a program to get a workout." action={<Button>Browse programs</Button>} />
<Skeleton variant="title" /> <Skeleton variant="text" lines={3} />
const toast = useToast(); toast.success('Logged!')
```

### Inputs
```tsx
<Input label="Calories" type="number" hint="kcal" error={err} />
<Textarea label="Notes" /> <Select label="Goal"><option/></Select>
<Checkbox label="Warm-up" /> <Radio label="Male" name="sex" />
<Segmented value={cat} onChange={setCat} ariaLabel="Category"
  options={[{value:'lunch',label:'Lunch'}]} block />
```
**Segmented selected = soft-indigo chip, unambiguous in both themes.**

### Chips / badges / lists
```tsx
<FilterChip selected onClick={…}>Chest</FilterChip>
<StatusChip status="completed" />          // completed|in-progress|not-started|locked
<Badge variant="ai">SMART</Badge>          // 'ai' = restrained soft-indigo, no gradient
<List><ListRow title="Bench Press" sub="Chest · Barbell" trailing={<Badge>PR</Badge>} /></List>
```

### Progress & rings
```tsx
<ProgressBar value={80} variant="success" label="Protein" />   // 'secondary' = cyan
<ProgressRing value={72} size={78} stroke={9}><span className="num">72%</span></ProgressRing>
<ActivityRings rings={[{key:'move',value,goal},{key:'exercise',…},{key:'hydrate',…}]} />
```
Rings/bars animate their fill on mount (`animate={false}` to disable). Move=indigo,
Exercise=volt, Hydrate=cyan. **Wrap ring/center numbers in `.num`** for tabular figures.

### Overlays
```tsx
<Modal open={open} onClose={close} title="Add exercise" footer={…}>…</Modal>
<BottomSheet open={open} onClose={close} title="Quick add">…</BottomSheet>
<Tooltip content="One-rep max estimate"><Info size={16}/></Tooltip>
```

### Shared feature components (reuse, do not modify)
`Logo`, `ThemeToggle`, `QuickAddSheet`, `RestTimer`, `ExercisePicker`.

---

## 5. Patterns

- **Loading:** a `*Skeleton` mirroring the layout with `<Skeleton>` blocks inside
  real `<Card>`s while `loading`.
- **Empty state:** `<EmptyState>` with a lucide icon + CTA — never a bare "No data".
- **Entrance:** `className="page stagger"` on the page root for a calm sequenced
  slide-up. Keep it subtle; don't animate every element.
- **Error:** `<EmptyState>`/Card with a retry `Button` wired to your `reload()`.
- **Numbers:** lead with the value, then the label; set numbers in `--font-num`
  with tabular figures. Reserve **volt** for PRs/streaks/goal completion.
- **Charts (recharts):** CSS vars don't resolve inside SVG — keep a per-theme JS
  palette mirroring the `--chart-*` tokens (2px lines, 8–12% area fill, faint
  dashed grid, no default dots, volt PR markers, tabular axis labels).

---

## 6. Accessibility checklist
- [ ] Icon-only controls use `IconButton`/`aria-label`; decorative icons `aria-hidden`.
- [ ] Text/background meets WCAG AA (body copy uses `--text-muted`, not `--text-subtle`).
- [ ] Focusable interactive elements show the global `:focus-visible` ring (don't remove it).
- [ ] Modals/sheets close via keyboard (Esc handled by the components).
- [ ] Progress uses `ProgressBar`/`ProgressRing`; custom widgets get `aria-label`/`role`.

## 7. Responsive checklist
- [ ] Mobile-first (~360px); add `@media (min-width: 720px|900px)` for wider layouts.
- [ ] Grids collapse to 1 column on mobile; tiles to 2 columns.
- [ ] No fixed widths that overflow; `min-width: 0` on flex children holding text.
- [ ] Verify **both** light and dark; depth should read in both.
- [ ] Respect safe-area insets for anything pinned to screen edges.

## 8. Reference
Use **`src/pages/Dashboard.tsx`** for **structure** (page states, skeleton, empty,
entrance, semantic `PageHeader`). Use **`UI-V2-DIRECTION.md`** for the **visual/
token contract**. Validate with `npm run build` (0 TS errors), `npm test` (green),
and `npm run lint` (clean) before finishing.
