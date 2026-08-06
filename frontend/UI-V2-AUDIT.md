# FitPath UI V2 — Visual / UX Audit

> Brutally honest, evidence-based review of why FitPath still reads as *amateur / template*
> despite the refinement pass, and a concrete plan to make it look **actually premium**.
> Author: Visual/UX audit agent. Scope: `frontend/` presentation only.

**Method.** Read the full design system (`styles/tokens.css`, `base.css`, `components.css`,
`layout.css`, `pages.css`), the shell (`layout/AppShell.tsx`), the shared components
(`components/**`, incl. `Progress.tsx`), auth (`auth/*` + `Auth.css`), the reference page
(`Dashboard.tsx/.css`), the data-viz page (`Performance.tsx` + `pages.css`), the coach
(`Insights.tsx` + `Insights.css`), and the `UI-PLAYBOOK.md`. Viewed a representative
sample of the 40 screenshots (Today, Workout, Nutrition, Programs, Progress, Coach,
Settings, Onboarding, Login, Register) across **desktop/mobile × light/dark**.

**Headline.** The *engineering* of this UI is good — tokens, skeletons, empty states,
a11y, recharts, a real dark theme. The **art direction is the problem.** It's a
competently-built **template**: one loud accent used everywhere, a playful display font
doing jobs it shouldn't (numbers), card-soup density, and demo data full of zeros. None of
those are bugs; together they cap the ceiling at "nice bootstrap starter," not "premium
fitness app."

---

## 1. Executive diagnosis (the brutal version)

1. **Everything is orange, so nothing is.** `--color-primary` (#f97316) is the fill for
   buttons, the tint behind *every* icon badge, selected chips, active nav, the streak
   pill, the FAB, PR values, the rest timer, eyebrows and badges. When the accent is the
   base, the eye has no hierarchy and the whole thing screams "single-hue template."
   (`tokens.css:13`, `components.css:224-232,436-440,471-474,509-512`.)

2. **Fredoka is rendering your *data*, and data should never look cute.** Metric values,
   stat values, calorie counts, PR e1RMs and the ring center are all set in the rounded,
   childlike display font (`--font-head`). Big numbers like `172,630` / `283.3` / `10,180`
   look like a kids' game, not an instrument. No `tabular-nums` anywhere except the rest
   timer, so numerals also wobble. (`components.css:197,240`; `Dashboard.css:198,211`;
   `pages.css:215`.)

3. **Card soup + low density.** Each screen is a vertical stack of white rounded cards on
   grey, every card padded `--sp-5/6` with `--radius-lg/xl` and a drop shadow. Today = 8+
   cards; you scroll a lot to learn very little. This is *the* generic-SaaS-dashboard tell.
   (`components.css:112-149`; `light__desktop__today.png`, `…__nutrition.png`.)

4. **The demo data makes a finished app look broken.** Today and Nutrition are mostly
   **zeros** — Water 0, Exercise 0, Protein 0, calories 0, macros 0%, streak `🔥 0`. The
   activity ring shows a bold ~81% orange arc *next to* the caption **"0/3 rings closed."**
   Progress repeats the identical `63.3kg · 47.5×14` PR four times. A premium screenshot is
   impossible when the data reads empty/contradictory. (`today.png`, `performance.png`;
   `api/mock.ts`.)

5. **Two accents fight, and the "AI" treatment is cheesy.** Links and "info"/"AI" badges
   are blue (`--color-secondary`) on an orange brand; the orange→blue **`--gradient-ai`**
   powers "SMART", "LEARNS YOU", "AI" and "Parse" pills scattered across Coach, Nutrition,
   Dashboard and Insights. It looks like hype stickers, not a product. (`base.css:76`;
   `tokens.css:80`; `components.css:483`; `Dashboard.css:244`; `Insights.tsx:211,306`.)

6. **Progress buries its best asset.** The trend charts (e1RM, per-exercise volume, weekly
   volume, bodyweight) are genuinely good recharts — but they render **after a wall of ~28
   near-identical PR cards.** The page leads with its least glanceable content; on mobile
   you thumb past 28 cards before a single graph. (`Performance.tsx:239-419`.)

7. **The auth "hero" is a flat pumpkin slab with a muddy blue smudge.** Huge black Fredoka
   on solid orange = bootcamp landing page. Worse, a `--color-secondary` radial at 70%
   opacity is mixed over the orange bottom-left corner, producing a brown/purple blob that
   reads as a rendering bug. First impression = template. (`Auth.css:48,52-62`;
   `light__desktop__login.png`, `…register.png`.)

8. **Coach's first run is a 420–620px empty box.** The chat area is a fixed tall region
   with one greeting bubble and acres of nothing; the suggestion chips sit at the very
   bottom. It looks unfinished on load. (`Insights.css:25`; `Insights.tsx:226-296`;
   `light__mobile__insights.png`.)

9. **Navigation is both redundant and gapped.** "Quick add" appears up to **three times**
   at once (sidebar button + page-header CTA + mobile FAB), and Nutrition adds a *fourth*
   orange primary ("Add meal"). Meanwhile **Coach has no mobile bottom-nav entry** at all
   (`primary:false`) — a whole top-level section reachable only by contextual links.
   (`AppShell.tsx:30-38,80-88,145-162`; `Nutrition.tsx:232`.)

10. **Over-rounded, over-springy, over-shadowed.** Radii 12/16/**22** + pill everywhere,
    spring easings, hover-lift on every card/chip/button, glow shadows on the FAB and
    dark-mode CTAs. The cumulative read is "bouncy and friendly," which is the opposite of
    the precise, restrained feel of Whoop/Oura/Linear the playbook aspires to.
    (`tokens.css:136-166`; `components.css:26-32,122-136`.)

---

## 2. What is already good — **preserve this**

Do not throw the baby out. These are real strengths and the V2 should build on them:

- **Token architecture** (`tokens.css`): full light/dark, glass surfaces, layered shadow
  ramp, motion scale, ring gradients, safe-area awareness. This is the right foundation.
- **Component library quality**: skeletons that mirror layout, friendly empty states,
  error+retry, toasts, required `aria-label` on `IconButton`, global `:focus-visible`,
  `prefers-reduced-motion` handling. (`base.css:100-118`; `Dashboard.tsx:63-107`.)
- **`ActivityRings`** is a legit Apple-Fitness-style concentric, gradient, mount-animated
  component. Keep it; just feed it better data + clarify the caption. (`Progress.tsx:129-177`.)
- **Charts are tasteful**: per-theme explicit palette (CSS vars don't resolve in SVG),
  axisLine/tickLine removed, gradient area fills, custom tooltip. (`Performance.tsx:37-50,287-419`.)
- **Dark mode is deep and mostly sophisticated** (navy `#090d14/#141b28`, layered shadows).
- **Dashboard structure** is a strong reference: setup/rest-day/empty/loading states,
  staggered entrance, semantic `PageHeader`. (`Dashboard.tsx`.)
- **Prefixed page-CSS convention** keeps the codebase parallel-safe and maintainable.

The problem is almost entirely **art direction and information architecture**, not the code
underneath. That's good news — V2 is mostly a token + a-few-components pass.

---

## 3. Tab-by-tab audit

Severity key: **P0** = credibility/looks-broken; **P1** = strong template tell / real
friction; **P2** = polish.

### 3.1 Today (Dashboard) — `Dashboard.tsx` / `Dashboard.css`
- **P0 — All-zero demo state reads as broken.** Steps 10,180 but Water/Exercise/Protein =
  0, calories 0, macros 0%. Three of four metric tiles show a giant `0`.
  *Why:* an app full of zeros looks unfinished the instant it loads. *Fix:* seed realistic,
  internally-consistent demo data in `api/mock.ts` (partial-day progress, non-zero macros);
  ensure the ring inputs and the tiles agree.
- **P0 — Ring says "0/3 rings closed" beside an 81% arc.** The prominent orange Move arc
  (407/500) visually contradicts the "0 closed" caption. *Why:* looks buggy. *Fix:* keep
  `ActivityRings`, but change the center caption to show the leading metric (e.g. "81% Move")
  or "0 of 3 closed" with a clearer visual, and make the three rings comparable in weight
  (see §5). (`Dashboard.tsx:204-212`.)
- **P1 — Duplicate primary CTAs.** Sidebar "Quick add" (`AppShell.tsx:80`) + page-header
  "Quick add" (`Dashboard.tsx:174`) + mobile FAB (`AppShell.tsx:160`). *Fix:* drop the
  page-header Quick add on Today; let the FAB/sidebar own it.
- **P1 — Blue "Program" / "Log meal" links fight the brand.** (`Dashboard.tsx:267,316`,
  colored by `base.css:76`.) *Fix:* resolve link color (see §5 palette).
- **P1 — Fredoka numbers** on the tiles and calorie value. (`Dashboard.css:198`.)
- **P2 — Coach-tip icon uses the orange→blue AI gradient** (`Dashboard.css:244`), reinforcing
  the gimmick motif.

### 3.2 Workout — `Workout.tsx` / `Workout.css`
- *Cleanest screen in the app.* Numbered list, clear scheme/RPE, two well-differentiated
  CTAs ("Start today's workout" gradient vs "Start empty session" secondary). Preserve.
- **P1 — Orange weight pills on every row** add accent noise and float far right with a big
  empty gutter between the exercise meta and the pill. *Fix:* make weight a neutral mono
  value inline, reserve the pill/orange for the one primary action.
- **P2 — `kg` letterspacing in pills** looks like `95  kg` (gap). Tighten unit rendering.

### 3.3 Nutrition — `Nutrition.tsx` / `Nutrition.css`
- **P0 — All-zero hero.** Big `0`, 0% ring, all three macro bars empty → looks unconfigured.
  Same fix as Today (seed data).
- **P1 — Four competing "add" affordances.** Sidebar Quick add + FAB + header "Add meal"
  (`Nutrition.tsx:232`) + "Parse"/"Manual" in the Quick-add card. *Fix:* one primary
  ("Add meal"); demote the rest.
- **P1 — Card soup**: hero + 3 stat tiles + quick-add card + log-again card. *Fix:* fold the
  3 stat tiles (Eaten/Remaining/Meals) into the hero (they restate the ring) to cut a whole
  card row.
- **P2 — "AI" gradient pill** on Quick add (screenshot) — de-emphasise.
- *Good:* "Log again" chips with kcal are real, useful content — keep and lean into them.

### 3.4 Programs — `Programs.tsx` / `Programs.css`
- **P1 — Nested card-in-card.** Exercise cards live inside the "Training days" card, each a
  bordered box with generous padding → heavy nesting, lots of vertical space per exercise.
  *Fix:* make exercises a bordered `List`/rows inside one container (like the Workout list),
  not individual cards. (`pages.css:169-197` legacy `.program-day`/`.ex-line` show the
  intended lighter treatment.)
- **P2 — Repeated "RPE auto" pills** and tiny grey meta icons (sets/clock/timer) are
  low-signal; consider one meta line in mono.
- *Good:* the "ACTIVE PROGRAM" hero with Goal/Split/Frequency meta chips is a nice summary.

### 3.5 Progress (Performance) — `Performance.tsx` / `Performance.css`
- **P0 — IA is inverted: 28 PR cards *before* the charts.** The valuable trend graphs render
  last. *Why:* the page's promise ("Strength, volume, and bodyweight **trends**") is invisible
  above the fold; the wall of near-identical PR cards feels like filler. *Fix:* reorder —
  lead with the "Exercise deep-dive" charts + weekly volume + bodyweight, then cap the PR
  grid to ~6 with a "Show all 28" toggle. (`Performance.tsx:239-419`.)
- **P1 — 28 identical stat cards** (Trophy badge + name + e1RM + best). Monotonous and
  space-hungry; the duplicated `63.3/47.5×14` values expose mock data. *Fix:* denser PR
  table/list; vary demo data.
- **P1 — Charts are basic/small** (near-flat e1RM area, tiny axis labels). *Fix:* larger
  default height, clearer y-domains, value labels on hover only (already), consider a
  headline "▲ +12.5kg this month" stat above each chart.
- *Good:* recharts theming, skeleton (`PerformanceSkeleton`), and the no-data `EmptyState`
  are all correct. (`Performance.tsx:98-204`.)

### 3.6 Coach & Insights — `Insights.tsx` / `Insights.css`
- **P0 — Empty-void first run.** `.ins-chat` = `clamp(420px,62vh,620px)` with one welcome
  bubble → a huge blank card. *Fix:* when `messages.length <= 1`, render a centered
  `EmptyState` (Sparkles + "Ask me anything about your training" + the starter chips
  promoted to the middle), or shrink the height until the conversation grows.
  (`Insights.css:25`; `Insights.tsx:228-254`.)
- **P1 — FAB overlaps the chat's send button.** The global Quick-add FAB is fixed
  bottom-right (`layout.css:151-154`); the Coach input + send `IconButton` sit bottom-right
  too (`Insights.tsx:271-293`). On mobile they collide. *Fix:* hide the FAB on `/insights`,
  or offset the coach footer to clear it.
- **P1 — "SMART" / "LEARNS YOU" gradient badges** = hype. *Fix:* one restrained AI treatment.
- *Good:* typing indicator, chip starters, and the Insights tab (streak tiles, patterns,
  daily-rhythm, achievements with progress bars) are well built.

### 3.7 Settings — `Settings.tsx` / `Settings.css`
- **P1 — Read-only profile "tiles" look like disabled inputs.** Sex/Age/Height/… are
  borderless grey tiles, but "Display name" right below is a real bordered input → mixed
  field grammar. *Fix:* make the read-only facts a clean definition list, visually distinct
  from editable inputs.
- **P1 — Segmented selected-state is weak in dark mode.** Selected segment = orange text on a
  barely-lighter surface; hard to see which is active. (`components.css:637-660` +
  dark tokens.) *Fix:* give the selected segment a solid `--surface` chip + shadow in both
  themes.
- **P2 — "Maingain" is a *deliberate* term** ("Lean gains near maintenance",
  `Onboarding.tsx:78`, `Settings.tsx:202`) — **not a typo** — but sitting next to a
  "Maintain" nutrition goal it *looks* like one and invites "this app has spelling errors"
  judgments. *Fix (copy):* relabel to "Recomp" or "Lean gain" for clarity; low severity.
- **P2 — Strong orange glow on "Save changes"** in dark (`--shadow-primary`) is heavy.

### 3.8 Onboarding — `Onboarding.tsx` / `Onboarding.css`
- *Most premium screen already:* centered card, clean stepper, progress bar, lucide icons
  (no emoji — the legacy `.wizard__emoji` in `pages.css:288` is unused).
- **P2 — Triple progress redundancy:** numbered stepper (1–4) + "Step 1 of 4" + "25%" +
  progress bar all say the same thing. *Fix:* keep the stepper + bar; drop the "25%".
- **P2 — Sparkles "Welcome" badge** = the AI motif again on a non-AI step.

### 3.9 Login / Register — `Login.tsx` / `Register.tsx` / `Auth.css`
- **P0 — Muddy blue blob on the orange panel.** `radial-gradient(... var(--color-secondary)
  70% ...)` at bottom-left over the orange base = brown/purple smear that looks broken.
  (`Auth.css:59`.) *Fix:* remove the secondary radial or drop it to a subtle same-hue
  highlight; keep the dot-grid if desired but lower its contrast.
- **P1 — Flat pumpkin slab + huge black Fredoka** reads as a template landing, not premium.
  (`Auth.css:48,94-101`.) *Fix:* deepen to a darker, moodier brand gradient (toward
  `--color-primary-active`/near-black), lighten the headline weight, and let the neutral
  right column breathe (see §5).
- **P1 — Number/heading font & centered form imbalance** — the right column is wide with a
  small centered card; fine on mobile (which actually looks cleaner), unbalanced on desktop.
  *Fix:* increase card max-width / add supporting content (testimonial, feature ticks) on
  desktop right column, or narrow the split.
- *Good:* input affordances (leading icon, password reveal), error alert animation, and the
  mobile-only radial background (`layout.css`/`Auth.css`) are solid.

### 3.10 App shell / navigation — `AppShell.tsx` / `layout.css`
- **P1 — Coach missing from mobile bottom nav.** Only `primary:true` items render
  (`AppShell.tsx:146`); Coach is `primary:false` (`:36`). Settings at least has the top-bar
  gear; Coach has no persistent mobile entry. *Fix:* either add a "Coach" tab (6 items is
  fine) or a "More" overflow, or promote Coach and move Programs into overflow.
- **P2 — Streak chip shows `0`.** `StreakChip` renders whenever streak `!== null`, so a
  brand-new user sees `🔥 0`. *Fix:* hide when `< 1`. (`AppShell.tsx:52-58`.)
- **Not a bug (call-out):** the bottom-nav/FAB appearing to *overlap content* in the mobile
  full-page screenshots is a `position:fixed` capture artifact — `.content` has
  `padding-bottom: calc(var(--bottomnav-h) + var(--sp-7))` (`layout.css:87`), so real
  viewports clear it. The one *real* fixed-overlap is FAB-vs-Coach-input (§3.6).

---

## 4. Prioritized visual-debt list

| # | Sev | Debt | Where | Highest-impact fix |
|---|-----|------|-------|--------------------|
| 1 | P0 | Numbers set in Fredoka, no tabular-nums | `components.css:197,240`; `Dashboard.css:198,211`; `pages.css:215` | Add `--font-num` (grotesque/mono) + `tabular-nums`; apply to all metric/stat/value classes |
| 2 | P0 | Orange used as the base, not an accent | `tokens.css:13`; `components.css:224-232,436,471,509` | Neutralise icon badges + chips; reserve orange for 1 primary action / key metric per view |
| 3 | P0 | All-zero, self-contradictory demo data | `api/mock.ts`; `today/nutrition/performance.png` | Seed realistic, consistent partial-progress data |
| 4 | P0 | Progress leads with 28 PR cards, charts buried | `Performance.tsx:239-419` | Charts first; PR grid capped to ~6 + "Show all" |
| 5 | P0 | Auth muddy blue blob | `Auth.css:59` | Remove/soften the `--color-secondary` radial |
| 6 | P0 | Coach empty-void first run | `Insights.css:25`; `Insights.tsx:228` | `EmptyState` + promoted starters until chat grows |
| 7 | P1 | orange→blue "AI/SMART/LEARNS YOU" gradient stickers | `tokens.css:80`; `components.css:483`; `Insights.tsx:211,306` | One restrained AI style; remove gradient badge |
| 8 | P1 | Blue links vs orange brand | `base.css:76` | Neutral or primary link color, underline on hover |
| 9 | P1 | Card soup / low density / big radii+shadows | `components.css:112-149`; `tokens.css:136-151` | Tighten padding one step, 2-radius system, lighter default shadow, consolidate cards |
| 10 | P1 | Duplicate/!competing primary CTAs (Quick add ×3–4) | `AppShell.tsx:80,160`; `Dashboard.tsx:174`; `Nutrition.tsx:232` | One primary per view; FAB owns global quick-add |
| 11 | P1 | Coach absent from mobile nav | `AppShell.tsx:36,146` | Add Coach tab or a "More" entry |
| 12 | P1 | FAB overlaps Coach send button | `layout.css:151`; `Insights.tsx:285` | Hide FAB on `/insights` |
| 13 | P1 | Programs nested card-in-card | `Programs.tsx`/`Programs.css` | Exercises as rows in one container |
| 14 | P1 | Segmented selected-state weak (dark) | `components.css:637-660` | Solid chip + shadow for selected in both themes |
| 15 | P1 | Auth flat pumpkin slab | `Auth.css:48,94` | Deeper moody gradient, lighter headline |
| 16 | P2 | Streak shows `🔥 0`; onboarding triple progress; "Maingain" copy; glow-heavy dark CTAs | `AppShell.tsx:52`; `Onboarding.tsx`; `Settings.tsx:202` | Small copy/threshold tweaks |

---

## 5. Proposed V2 visual direction (grounded in the current tokens)

The goal: **restraint + precision.** Keep the LearnFlow warmth as a *signature accent*, not a
flood. Every change below is expressible in the existing token/component system.

> ⚠️ **This intentionally requires editing the "frozen" shared files** (`styles/*`,
> `components/*`). The current playbook freeze (UI-PLAYBOOK §0) exists to keep per-page work
> parallel-safe; a systemic re-skin is exactly the case that must touch shared tokens. Treat
> §6 as a single coordinated shared-foundation change, then per-page follow-ups.

### Typography
- **Add `--font-num`** — a neutral grotesque or the mono for numerals
  (`'Roboto Mono'` already loaded, or add Inter/Söhne-like). Apply to `.metric__value`,
  `.stat__value`, `.dash-kcal__value`, `.dash-rings__value`, `.perf-pr__e1rm`, `.pr-value`,
  ring captions — **with `font-variant-numeric: tabular-nums; letter-spacing:-0.01em`.**
  This single change removes ~half the "toy" feel.
- **Keep Fredoka for the wordmark and, at most, page H1s.** Consider demoting `h2–h4` to the
  body/grotesque with tight tracking for a more editorial, less bubbly feel.

### Palette
- **Demote orange to accent.** Default icon badges → neutral (`--surface-3` bg,
  `--text-muted` icon); selected chips → neutral-filled with an orange *left accent* or text,
  not full orange fill; keep orange for the **one** primary button and the active nav
  indicator only.
- **Kill `--gradient-ai`.** Replace AI/SMART badges with a single subtle style (e.g.
  `--surface-3` + primary text + a small Sparkles). No orange→blue gradients.
- **Resolve links.** Set `a` to `--text` with an underline, or to `--color-primary`; stop
  using `--color-secondary` for inline links so blue stops competing. Reserve
  `--color-secondary` strictly for charts/data series.
- **Introduce one restrained "surface accent."** A near-neutral tinted card border/hairline
  gives depth without color noise.

### Density & shape
- **Two radii, not five.** Standardise controls at `10px`, cards at `14px`; retire
  `--radius-xl` (22) and the bespoke `20px` FAB. Pills stay pill.
- **Lighter elevation.** Default cards to `--shadow-xs`; reserve `--shadow-md+` for true
  overlays (modals, sheets, FAB). Drop the dark-mode orange glow on non-hero CTAs.
- **Tighten cards.** Card padding `--sp-5 → --sp-4`; consolidate restating cards (Nutrition
  stat tiles into hero; Progress PR wall capped). Aim to raise information-per-screen.
- **Calm the motion.** Keep entrances; reduce hover-lift `translateY(-3px)→-1px` and prefer
  `--ease-standard` over `--ease-spring` for UI chrome (springs only for playful moments
  like ring fills).

### Data-viz
- **Numbers are the hero** (per §Typography). Lead Progress and each metric with the value,
  then the label. Give charts more height and a one-line headline delta.

Net effect: a **sophisticated neutral canvas with a confident single orange accent and
crisp numerals** — the Whoop/Oura/Linear register the playbook already names as the target.

---

## 6. Implementation map (shared foundations first, then pages)

Execute in order; each phase is independently shippable.

**Phase A — shared tokens (`styles/tokens.css`)**
1. Add `--font-num` (+ `@font-face`/import if new). Retune radii to a 2-step system; soften
   default shadow usage; remove or neutralise `--gradient-ai`; optionally add a neutral
   "accent-soft" for badges.

**Phase B — shared base/components (`styles/base.css`, `styles/components.css`)**
2. `base.css`: change `a` color/underline; add a `.num`/tabular-nums helper.
3. `components.css`:
   - `.metric__value`, `.stat__value` → `--font-num` + tabular-nums; smaller tracking.
   - `.metric__icon` (and page icon-badges) → neutral by default; primary as an opt-in
     modifier.
   - `.card` padding/radius/shadow retune; `.card--hero/feature` radius down.
   - `.badge--ai` → restrained; `.chip--filter.is-selected` → neutral+accent.
   - `.segmented__opt[aria-checked]/.is-selected` → solid chip + shadow (fixes dark).

**Phase C — shell (`layout/AppShell.tsx`, `styles/layout.css`)**
4. Add Coach to mobile nav (6 tabs) or a "More" entry; hide FAB on `/insights`; hide streak
   chip when `< 1`; drop the page-header Quick-add duplication.

**Phase D — page-specific (each page's `.tsx` + prefixed `.css`)**
5. `Performance.tsx` — reorder: charts first, PR grid capped to ~6 + "Show all"; taller
   charts + headline deltas.
6. `auth/Auth.css` — remove muddy secondary radial; deepen brand gradient; rebalance right
   column; lighten headline.
7. `Insights.tsx` + `Insights.css` — empty-state for first run; reduce fixed chat height when
   empty.
8. `Nutrition.tsx`/`.css` — fold stat tiles into hero; single primary CTA.
9. `Programs.tsx`/`.css` — exercises as rows, not nested cards.
10. `Dashboard.tsx`/`.css` — clarify ring caption; drop duplicate CTA; neutral links.
11. `Settings.tsx`/`.css` — distinguish read-only facts from inputs; relabel "Maingain".
12. `Onboarding.tsx` — drop redundant "25%".

**Phase E — demo data (`api/mock.ts`)**
13. Seed realistic, internally-consistent partial-day data (non-zero water/exercise/protein,
    varied PRs, a real streak). Remove the stray `🏆` emoji (`mock.ts:912`). This is what
    makes the *screenshots* finally look premium.

**Validation:** `npm run build` (zero TS errors) + `npm test` after each phase; re-shoot the
40 screenshots (`qa-shots.mjs`).

---

## 7. Acceptance criteria — "actually premium"

A screen passes V2 when **all** hold:
- [ ] **Numerals** are set in `--font-num` with `tabular-nums`; no metric is in Fredoka.
- [ ] **Orange appears ≤ ~3 times** per viewport (primary action, active nav, one key
      metric/ring). Icon badges and unselected chips are neutral.
- [ ] **No orange→blue gradient** anywhere; AI/SMART uses one restrained style.
- [ ] **One primary button** per view; no duplicated Quick-add on the same screen.
- [ ] **Links** don't read as a second brand color.
- [ ] **Radii** come from the 2-step system; **default card shadow ≤ `--shadow-sm`**.
- [ ] **No screen is a stack of >5 equal-weight cards**; restating cards are consolidated.
- [ ] **Progress leads with charts**; PR list is capped/dense.
- [ ] **Every screenshot shows lived-in, non-zero, self-consistent data.**
- [ ] **Auth** has no muddy blob and no flat-slab headline; reads premium at a glance.
- [ ] **Coach** never shows a large empty void; reachable from mobile nav.
- [ ] Dark mode: selected/active states are unambiguous; no heavy orange glows on chrome.
- [ ] A11y preserved: AA contrast, focus rings, `aria-label`s, reduced-motion.

## 8. Screenshot review checklist (per route × desktop/mobile × light/dark)

For each of Today, Workout, Nutrition, Programs, Progress, Coach, Settings, Onboarding,
Login, Register:
1. **Squint test** — is there one clear focal point, or a field of equal-weight cards?
2. **Count the orange** — >3 orange elements? Fail.
3. **Numbers** — do the big values look like an instrument (tight, tabular) or a toy (Fredoka)?
4. **Data realism** — any `0` / `0%` / `🔥 0` / repeated identical values on screen?
5. **Accent conflicts** — blue links/badges next to orange? Muddy gradient corners?
6. **Density** — how much do I learn per scroll? Any restating cards?
7. **Shape/elevation** — consistent radii; shadows subtle, not puffy.
8. **Dark parity** — is the active/selected state as obvious as in light?
9. **Chrome collisions** — FAB over a button; nav over content; overlong pills.
10. **First-run** — empty/loading states look intentional, never blank or broken.

---

### Appendix — quick-reference file index
- Tokens/shape/color: `src/styles/tokens.css`
- Base type/links/utils: `src/styles/base.css`
- Shared components: `src/styles/components.css`
- Shell + nav + FAB: `src/layout/AppShell.tsx`, `src/styles/layout.css`
- Rings/bars: `src/components/ui/Progress.tsx`
- Reference page: `src/pages/Dashboard.tsx` + `Dashboard.css`
- Data-viz: `src/pages/Performance.tsx` (+ `pages.css` legacy `.pr-item`/`.chart-box`)
- Coach: `src/pages/Insights.tsx` + `Insights.css`
- Auth: `src/auth/Login.tsx`, `Register.tsx`, `Auth.css`
- Demo data: `src/api/mock.ts`
