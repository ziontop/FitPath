# FitPath UI V2 — Competitive Research

Research date: 2026-07-14.

## Executive direction: Ridgeline

FitPath should become a dark-first, high-contrast **performance instrument**:

- Retire Fredoka, Poppins, dominant orange, multicolor AI gradients, colored
  glow shadows, oversized radii, and springy motion.
- Use **Space Grotesk** for headings and hero metrics.
- Use **Inter** for body/UI text, with tabular numerals for data.
- Use cool ink/graphite neutrals, an indigo-violet primary, and a sparing
  electric-lime accent reserved for PRs, streaks, and goal completion.
- Prefer flat surfaces, quiet borders, compact density, monochrome Lucide
  icons, neutral shadows, and confident 120–220ms ease-out motion.

## Benchmark findings

### Typography

Premium fitness products use neutral grotesk typography and intentional
numeric treatments:

- WHOOP uses a dedicated bold numeric treatment for instrument-like scores.
- Strava uses a restrained humanist sans hierarchy.
- Apple Fitness prioritizes large, glanceable numerals.
- Hevy, Strong, and MacroFactor use compact UI text and tabular set/macro data.

Rounded display fonts make performance data feel playful rather than precise.

### Color

- WHOOP and Oura rely on near-black, layered neutral surfaces, and restrained
  semantic accents.
- Strava uses orange sparingly against warm neutral surfaces.
- Nike uses Volt as a rare energy highlight.
- MacroFactor avoids shaming users with red/green adherence judgments.

Premium products use one accent per context. FitPath currently uses orange for
buttons, active navigation, icon badges, pills, metrics, rings, and glows, so
the interface lacks visual hierarchy.

### High-value product patterns

- **Today:** one hero, then a compact at-a-glance grid and actionable daily
  recommendations.
- **Workout:** Hevy-style set rows with a visible Previous column, prefill,
  one-tap completion, sticky rest timer, and bottom-reachable controls.
- **Nutrition:** calorie ring, restrained macro bars, meal grouping, and fast
  re-log without over-budget shaming.
- **Programs:** horizontal day selection and dense exercise rows.
- **Progress:** charts before long PR lists; thin lines, faint gridlines, one
  primary series, and a restrained PR marker.
- **Coach:** user/assistant differentiation, suggested prompts, and insight
  cards led by one metric and one takeaway.
- **Onboarding:** calm hero, minimal fields per step, slim progress indicator,
  and one clear CTA.

## Exact visual system

### Fonts

```html
<link
  href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap"
  rel="stylesheet"
/>
```

```css
--font-display: 'Space Grotesk', 'Segoe UI', system-ui, sans-serif;
--font-head: var(--font-display);
--font-body: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
--font-mono: 'Space Grotesk', ui-monospace, 'SFMono-Regular', Consolas, monospace;
```

Use `font-variant-numeric: tabular-nums` on metrics, timers, charts, and set
tables.

### Light palette

```css
--bg: #f6f7f9;
--surface: #ffffff;
--surface-2: #f1f3f6;
--surface-3: #e9ecf1;
--border: #e3e7ed;
--border-strong: #cfd5de;
--text: #0e1420;
--text-muted: #566072;
--text-subtle: #8a93a3;
--color-primary: #5b57e0;
--color-primary-hover: #4b47c7;
--color-primary-active: #3e3aae;
--color-primary-soft: #eeedfc;
--color-primary-contrast: #ffffff;
--color-accent: #c4f439;
--color-accent-strong: #7cb518;
--color-accent-soft: #f2fbdd;
--color-accent-contrast: #12210a;
```

### Dark palette

```css
--bg: #0b0f14;
--surface: #12171f;
--surface-2: #171e28;
--surface-3: #1e2733;
--border: #232c38;
--border-strong: #33404f;
--text: #eaeef3;
--text-muted: #a3adbb;
--text-subtle: #6b7686;
--color-primary: #8b87ff;
--color-primary-hover: #a29eff;
--color-primary-active: #7b76f5;
--color-primary-soft: rgba(139, 135, 255, 0.16);
--color-primary-contrast: #0b0f14;
--color-accent: #cbff47;
--color-accent-strong: #cbff47;
--color-accent-soft: rgba(203, 255, 71, 0.16);
--color-accent-contrast: #0e1a05;
```

### Rings and charts

- Activity: indigo/violet.
- Training: volt/lime.
- Hydration: cyan.
- Charts: 2px lines, 8–12% fills, faint dashed grid, no default dots, volt PR
  markers, and tabular axis labels.

### Shape and motion

- Radii: 8px small, 10px controls, 14px cards, 18px one hero only.
- Dark mode uses surface steps and borders more than shadows.
- Remove colored glows.
- Use 120–220ms ease-out motion; no bouncy overshoot.
- Reduce page-wide stagger and animated decoration.

## Borrow and improve

| Product | Borrow | FitPath improvement |
|---|---|---|
| WHOOP | Dark performance-instrument feel | Equally polished light mode |
| Oura | Calm layered dark surfaces | Stronger training/action focus |
| Apple Fitness | Glanceable rings | FitPath-specific indigo/volt/cyan |
| Strava | Restrained accent and hierarchy | Dark-first, non-orange identity |
| Hevy | Previous-set column and fast logging | Add program-suggested weights |
| Strong | Spreadsheet-efficient set rows | Better one-handed controls |
| Fitbod | Guided sets and muscle context | Connect to MEV/MAV volume |
| MacroFactor | Adherence-neutral nutrition | Combine with workout recommendations |
| Lifesum | Calorie ring and meal groups | More restrained visual system |
| Nike Training Club | Editorial hierarchy and Volt | Reserve Volt for achievements |

## Anti-patterns to remove

1. Fredoka for headings and metrics.
2. Dominant orange and orange gradients.
3. Orange-to-blue AI gradients.
4. Colored glow shadows.
5. Tinted icon badges on every card.
6. Oversized 22px radii.
7. Bouncy spring motion.
8. Page-wide stagger/animation everywhere.
9. Gradient CTA buttons on every screen.
10. Card-in-card nesting and low information density.

## Sources

- WHOOP Brand & Design Guidelines:
  https://developer.whoop.com/assets/files/WHOOP%20-%20Brand%20&%20Design%20Guidelines-bdea3554e94b4ea09e68695b1e8dc8e7.pdf
- Oura Brand Guidelines:
  https://static.ouraring.com/pdfs/Oura_BrandGuidelines_v1.pdf
- Strava Developer Guidelines: https://developers.strava.com/guidelines/
- Apple Human Interface Guidelines:
  https://developer.apple.com/design/human-interface-guidelines/
- Garmin Connect redesign:
  https://www.garmin.com/en-US/newsroom/press-release/wearables-health/garmin-connect-gets-a-new-look-simplified-design-provides-a-more-customized-experience/
- MacroFactor dashboard customization:
  https://macrofactor.com/dashboard-customization/
- Product references: https://hevy.com, https://strong.app,
  https://fitbod.me, https://lifesum.com, https://www.nike.com/ntc

