# FitPath UI V2 — "Ridgeline" Direction & Page-Agent Handoff

> The locked visual contract for FitPath V2. The **shared foundation** (tokens,
> base, components, layout, shell, Logo) has been re-skinned to Ridgeline. This
> document is the source of truth for the **page agent** who now updates each
> page's `.tsx` + co-located prefixed `.css`.
>
> Companion docs: `UI-V2-RESEARCH.md` (why), `UI-V2-AUDIT.md` (what was wrong),
> `UI-PLAYBOOK.md` (how to build a page).

---

## 1. The system in one paragraph

FitPath is a **dark-first, high-contrast performance instrument**. Type is
**Space Grotesk** (display/headings/hero metrics) + **Inter** (UI/body), with
**tabular lining numerals** on every metric, timer, chart, set table, and
numeric badge. The palette is cool ink/graphite neutrals, an **indigo-violet**
primary (`#5B57E0` light / `#8B87FF` dark), and a **volt** energy accent
(`#C4F439`/`#CBFF47`) **reserved for PRs, streaks, and goal completion** — never
default chrome or body text. Data-viz/info use **cyan**. Surfaces are flat with
quiet borders, tight radii (8/10/14, 18 for one hero), neutral low-spread
shadows, and confident **120–220ms ease-out** motion with no overshoot.

**Retired for good:** Fredoka, Poppins, dominant orange, orange gradients, the
orange→blue "AI" gradient, colored glow shadows, 22px radii, and springy
bounce motion.

---

## 2. Locked token contract (`src/styles/tokens.css`)

Consume everything via `var(--token)`. **Never hard-code** color, font, radius,
shadow, or timing on a page. Legacy names below are **preserved as aliases** and
already remapped to Ridgeline — keep using them; they will not glow orange.

### Fonts
| Token | Value | Use |
|---|---|---|
| `--font-display` / `--font-head` | Space Grotesk | headings, hero metric values, titles |
| `--font-body` | Inter | body, UI, labels, dense inline data |
| `--font-num` | Space Grotesk | big glanceable metric values |
| `--font-mono` | Space Grotesk | timers, code-like numerals |
| `--numeric` | `tabular-nums lining-nums` | apply to **all** numeric data |

Helpers in `base.css`: `.num` / `.tabular-nums` (tabular figures on any element),
`.metric-num` (display font + tabular for hero numbers).

### Color (light → dark)
| Token | Light | Dark | Meaning |
|---|---|---|---|
| `--bg` | `#f6f7f9` | `#0b0f14` | app background |
| `--surface` | `#ffffff` | `#12171f` | card/base surface |
| `--surface-2` / `--surface-3` | `#f1f3f6` / `#e9ecf1` | `#171e28` / `#1e2733` | raised / inset steps |
| `--border` / `--border-strong` | `#e3e7ed` / `#cfd5de` | `#232c38` / `#33404f` | hairlines |
| `--text` / `--text-muted` / `--text-subtle` | `#0e1420` / `#566072` / `#8a93a3` | `#eaeef3` / `#a3adbb` / `#6b7686` | text ramp |
| `--color-primary` (+`-hover`,`-active`,`-soft`,`-contrast`) | `#5b57e0` | `#8b87ff` | indigo brand |
| `--color-accent` (+`-strong`,`-soft`,`-contrast`) | `#c4f439` / `#7cb518` | `#cbff47` | **volt — achievements only** |
| `--color-secondary` (+`-hover`,`-soft`) | `#0e8aa3` | `#38bdf8` | cyan — data/info |
| `--color-success` / `-warning` / `-error` / `-info` (+ `-soft`) | green / amber / red / cyan | brighter variants | semantic |

**Accent rule:** `--color-accent` (volt) is used by the streak chip and is meant
for PR values, streak counts, and goal-completion moments. Do **not** use volt
for buttons, nav, icon chrome, or body text on white.

### Rings & charts
- Rings: **Move = indigo** (`--ring-move-*`), **Exercise = volt** (`--ring-exercise-*`),
  **Hydrate = cyan** (`--ring-hydrate-*`), track `--ring-track`.
- Charts: `--chart-1` indigo (primary series), `--chart-2` cyan, `--chart-3`
  volt, `--chart-4` amber, `--chart-pr` volt (PR marker), `--chart-grid`,
  `--chart-axis`, `--chart-area-opacity` (0.10). Recharts can't resolve CSS vars
  inside SVG, so keep a **per-theme JS palette** in the page and mirror these
  values (see §5 for `Performance.tsx`).

### Shape, elevation, motion
- Radii: `--radius-sm` 8 · `--radius-md` 10 (controls) · `--radius-lg` 14 (cards)
  · `--radius-xl` 18 (one hero / overlays) · `--radius-pill` · `--radius-circle`.
- Card density: `--card-pad` 20 · `--card-pad-lg` 24.
- Shadows: `--shadow-xs…xl` are neutral and low-spread. `--shadow-primary` /
  `--shadow-primary-lg` are **aliased to neutral** (no colored glow).
- Motion: `--dur-fast` 120 · `--dur` 180 · `--dur-slow` 220 · `--dur-slower` 280.
  Easings: `--ease-standard`, `--ease-out` (confident decelerate). `--ease-spring`
  is **aliased to ease-out (no bounce)**. Everything respects
  `prefers-reduced-motion` globally.

### Gradients (single-hue indigo only)
`--gradient-hero` is a low-contrast single-hue indigo wash. `--gradient-brand`,
`--gradient-brand-vivid`, `--gradient-ai` are all indigo now (no orange, no
orange→blue). Prefer **solid** fills; reach for a gradient only for the hero
wash.

---

## 3. Shared component behavior changes (already shipped)

You do **not** re-import or restyle these — just use them. Note the new behavior:

- **Button** — solid primary by default. The `gradient` prop still exists but now
  maps to a **solid primary** fill (no gradient, no glow). Hover no longer lifts.
- **Card** — default padding `--card-pad`, radius 14, `--shadow-xs`.
  Non-interactive cards **do not lift on hover**; only `interactive` cards lift a
  subtle 1px. `hero` variant = subtle indigo wash at radius 18.
- **MetricTile / StatCard** — values use `--font-num` + tabular numerals. The
  icon badge is **neutral by default**; pass **`accentIcon`** to opt one tile
  into the soft-indigo badge (use at most one accent icon per card).
- **Badge** — `variant="ai"` is now a restrained soft-indigo chip (no gradient).
  `variant="info"` is cyan.
- **Segmented** — selected option is a soft-indigo chip that is unambiguous in
  **both** themes.
- **Progress** — `gradient` prop maps to solid primary; `secondary` variant is cyan.
- **Chips / Lists / Modal / Sheet / Toast / Tooltip / Skeleton / EmptyState** —
  re-skinned to Ridgeline via tokens; APIs unchanged.
- **Shell** — desktop sidebar + mobile bottom nav (5 primary items) with a
  **subtle indigo active surface**. Coach is now reachable on mobile via a
  **top-bar Sparkles shortcut** (bottom nav stays 5 items). The global quick-add
  **FAB is hidden on `/insights`**. The streak chip is **volt** and hides when
  `< 1`.
- **Logo** — indigo "ridgeline" mark (rising ridge) + `Fit`**`Path`** wordmark.

---

## 4. Page acceptance criteria (squint test)

A page passes V2 when **all** hold:
- [ ] No Fredoka/Poppins; numerals use `--font-num`/`--font-body` + tabular figures.
- [ ] **No orange** anywhere. Volt appears only on PRs/streaks/goal completion.
- [ ] No orange→blue gradient; AI/SMART uses the restrained soft-indigo `Badge`.
- [ ] **One** primary button per view; no duplicated Quick-add on the same screen.
- [ ] Links read as primary/neutral, not a second brand color.
- [ ] Radii from the token set; default card shadow ≤ `--shadow-sm`; no glow.
- [ ] Icon badges are neutral by default (≤ one accent icon per card).
- [ ] Not a stack of >5 equal-weight cards; restating cards consolidated.
- [ ] Dark mode: active/selected states unambiguous; charts use the JS palette.
- [ ] A11y preserved: AA contrast, focus rings, `aria-label`s, reduced motion.

---

## 5. Page-agent to-do — per-page hardcodes to remove

The shared foundation resolves most colors automatically (orange tokens are now
indigo). But these files still contain **hardcoded** orange / old fonts /
gradients that must be replaced with tokens. **The page agent owns all of these.**

### `src/pages/Performance.tsx` (Progress)
- Lines ~40 & ~47: `CHART.primary: '#f97316'` / `'#fb8c3d'` (light/dark). Replace
  the whole per-theme chart palette with the Ridgeline chart tokens: primary
  `#5b57e0`/`#8b87ff`, secondary `#0e8aa3`/`#38bdf8`, PR marker volt
  `#7cb518`/`#cbff47`, grid `#e6e9ef`/`#232c38`, axis `#8a93a3`/`#6b7686`.
- IA: lead with the charts; cap the PR grid (~6 + "Show all"); PR values use
  volt (`--color-accent-strong`/`--color-accent`) + tabular numerals.

### `src/auth/Auth.css`
- Line ~48: `background: linear-gradient(150deg,#fb923c,#f97316,#ea580c)` — the
  flat orange auth hero. Replace with a deep indigo (toward
  `--color-primary-active`/near-`--bg`) single-hue treatment.
- The muddy `--color-secondary` radial blob — remove/soften (now cyan, still
  drop it for a single-hue indigo wash to match the shared `.auth` background).
- Big Fredoka headline weight → Space Grotesk via tokens; lighten.

### Page CSS still referencing brand gradients / old aliases
These compile fine (aliases remapped to indigo) but should be **audited and
tokenized** so nothing relies on a "brand gradient" for emphasis. Prefer solid
`--color-primary`, soft `--color-primary-soft`, or the neutral surfaces:
- `Dashboard.css` — `--gradient-*`, `--shadow-primary`, coach-tip icon gradient.
- `Insights.css` — `--gradient-ai`/AI "SMART/LEARNS YOU" treatments → `Badge variant="ai"`.
- `Nutrition.css` — brand-gradient/AI pill on quick-add; fold stat tiles into hero.
- `Programs.css` — brand gradient; convert nested exercise cards to `List` rows.
- `Workout.css` — orange weight pills → neutral mono + tabular; brand gradient CTA now solid.
- `Onboarding.css` — brand gradient; drop redundant "25%".

### Behavioral / IA fixes carried over from the audit (page-owned)
- Duplicate CTAs: drop page-header "Quick add" on Today; single primary on Nutrition.
- Coach first-run: render an `EmptyState` + promoted starters until chat grows.
- Settings: distinguish read-only facts from editable inputs; segmented selected
  state is fixed at the component level now.
- Demo data (`api/mock.ts`, **outside the frontend design scope** but noted):
  seed realistic, non-zero, self-consistent values; remove stray emoji.

> None of the above are shell/shared changes — they are page work. The shared
> foundation is frozen again for parallel-safe page edits (see `UI-PLAYBOOK.md §0`).
