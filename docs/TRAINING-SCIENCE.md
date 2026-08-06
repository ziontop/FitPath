# FitPath Training Science Reference

> Evidence-based reference for the FitPath **algorithmic** (non-LLM) recommendation
> engine. Every number below is intended to be encoded directly in
> [`app/training/params.py`](../app/training/params.py). Each claim carries a
> source; full URLs are in [Sources](#sources).
>
> **Audience personas / goals** the engine serves:
> 1. **CUTTING + POWERLIFTING** — lose fat while preserving Squat/Bench/Deadlift (SBD) strength.
> 2. **BULKING + HYPERTROPHY** — gain muscle in a surplus, hypertrophy-focused, SBD as the compound base.
> 3. **MAINGAINING + INCONSISTENT** — maintenance, minimalist, resilient to missed sessions.
>
> Distinctions by **experience level** (beginner / intermediate / advanced) are called
> out wherever they change the recommendation.

---

## 1. Core definitions

### 1.1 Volume landmarks (Renaissance Periodization / Mike Israetel)
Volume is counted as **hard working sets per muscle group per week**, where a "working
set" is 30–85% 1RM, 5–30 reps, taken to within 0–4 reps in reserve (RIR). Only sets
where the muscle is the prime mover / direct isolation are counted (indirect volume is
already baked into the landmarks). [RP-VOL]

| Landmark | Meaning |
| --- | --- |
| **MV** — Maintenance Volume | Least volume that *maintains* current muscle (~6 sets/muscle/week when trained ≥2×/wk). [RP-VOL] |
| **MEV** — Minimum Effective Volume | Least volume that *grows* muscle; the start of a mesocycle. [RP-VOL] |
| **MAV** — Maximum Adaptive Volume | The progression zone between MEV and MRV where best gains happen. [RP-VOL] |
| **MRV** — Maximum Recoverable Volume | Upper limit; training beyond it outpaces recovery and stalls progress. [RP-VOL] |

### 1.2 RPE / RIR (autoregulation)
**RPE** (Rating of Perceived Exertion, RIR-based) and **RIR** (Reps In Reserve) are
inversely linked: **RPE = 10 − RIR**. RPE 10 = 0 reps left (true failure), RPE 9 = 1
RIR, RPE 8 = 2 RIR, etc. Most lifters predict RIR within ~1 rep, and accuracy improves
at lower rep counts (≤12) and closer to the end of a set. RIR-based autoregulation has
largely superseded fixed %1RM prescriptions for day-to-day load selection. [SBS-RIR]

### 1.3 Estimated 1RM (e1RM)
Used to translate a working set (weight × reps) into a strength estimate and to derive
target loads. See [§7](#7-estimated-1rm-e1rm-formulas).

---

## 2. Rep ranges & intensity per goal

Hypertrophy occurs across a wide load spectrum (~30–85% 1RM) **provided sets are taken
close to failure**; low- and high-load training grow similar muscle when effort is
matched. Strength, by contrast, is load-specific and favors heavy, low-rep work on the
target lift. [SBS-RIR][SCH-FREQ]

| Goal | Reps | % 1RM | Target RPE (RIR) | Notes |
| --- | --- | --- | --- | --- |
| **Max strength** (SBD) | 1–5 | 80–95% | 7–9 (1–3 RIR) | Heavy, specific to the lift; long rests. |
| **Strength–hypertrophy** | 4–6 | 80–87% | 7–8 (2–3 RIR) | Bridges the two; good for cutting powerlifters. |
| **Hypertrophy** | 6–12 (up to 15–20) | 65–80% | 7–9 (1–3 RIR) | Most volume-efficient; leave 1–3 in reserve on compounds. [RP-VOL][SBS-RIR] |
| **Metabolite / endurance** | 15–30 | <65% | 8–10 (0–2 RIR) | Higher failure proximity needed for growth at light loads. |

Practical rules for the engine:
- Powerlifting main-lift work sits at **1–5 reps, RPE 7–9**; accessories at **6–12**.
- Hypertrophy compounds: **6–10 @ RPE 7–9**; isolations: **10–15 @ RPE 8–10**.
- Going to failure is **not required** on compounds and, done constantly, adds fatigue
  without extra growth — bias toward 1–3 RIR on multi-joint lifts. [SBS-RIR]

---

## 3. Weekly volume landmarks per muscle (sets/week)

Consolidated from RP / Israetel muscle-specific guides. These are **starting points**,
skew low for beginners (start at/near MEV) and matter most for intermediate+ lifters who
progress from MEV toward MRV across a mesocycle. [RP-VOL][RP-MUSCLE]

| Muscle | MV | MEV | MAV (range) | MRV |
| --- | --- | --- | --- | --- |
| Chest | 6 | 8 | 12–20 | 22 |
| Back (lats + upper back) | 6 | 10 | 14–22 | 25 |
| Quads | 6 | 8 | 12–18 | 20 |
| Hamstrings | 4 | 6 | 10–16 | 20 |
| Glutes | 0 | 4 | 8–12 | 16 |
| Shoulders (side/rear delts) | 6 | 8 | 16–22 | 26 |
| Biceps | 5 | 8 | 14–20 | 26 |
| Triceps | 4 | 6 | 10–14 | 18 |
| Calves | 6 | 8 | 12–16 | 20 |
| Abs | 0 | 0 | 16–20 | 25 |

**Mesocycle volume progression** (intermediate+): start the block at MEV, add ~1–3 sets
per muscle per week based on recovery/performance, approach MRV, then **deload to ~MV**
and reset. Example: 12 → 14 → 16 → 18 → 20 sets, then a 6-set deload week. [RP-VOL]

**Cutting caveat:** in a deficit, recovery is reduced — hold volume near **MV–MEV** to
*maintain* muscle rather than chasing MRV. [RP-VOL]

---

## 4. Training frequency

Training each muscle **≥2×/week** beats 1×/week for hypertrophy when volume is equated
(effect size 0.49 vs 0.30 favoring higher frequency). Once weekly volume is matched,
frequency's independent effect is small; 2× is the practical sweet spot to distribute
volume into higher-quality sessions. Higher frequencies (3×+) are mostly a tool to fit
more weekly volume without overly long sessions. [SCH-FREQ]

| Goal / persona | Sessions/week | Times each muscle trained/week |
| --- | --- | --- |
| Beginner (any goal) | 3 (full-body) | 3× |
| Cutting + Powerlifting | 3–4 (upper/lower or SBD-focused) | SBD pattern 2×; muscles 2× |
| Bulking + Hypertrophy | 4–6 (PPL or Upper/Lower) | 2× (up to 3× at high volume) |
| Maingaining + Inconsistent | 2–3 (full-body A/B) | 2× when consistent, ≥1× worst case |

---

## 5. Rest intervals

Longer rests (≥3 min) produced **greater strength AND hypertrophy** than 1 min in
resistance-trained men, because they preserve load/reps in later sets. [SCH-REST]

| Exercise type / goal | Rest |
| --- | --- |
| Heavy compounds (SBD, strength) | 180–300 s (3–5 min) |
| Compounds (hypertrophy) | 120–180 s (2–3 min) |
| Isolation / accessory | 60–120 s (1–2 min) |

Engine default: **compound = 180 s, isolation = 90 s**, biased up for strength goals and
down (toward the low end) only when time-constrained.

---

## 6. Progression schemes

### 6.1 Linear progression — **beginners**
Add a fixed load each session while reps/sets are hit. r/Fitness Basic Beginner Routine:
**+2.5 lb (1.25 kg) upper-body lifts, +5 lb (2.5 kg) lower-body lifts each session**; if
you fail the rep target across sessions, **deload −10%** and climb back. Runs ~3 months
until linear gains stall, then graduate to intermediate programming. [RFIT-BBR]

### 6.2 Double progression — **intermediate**
Fix a rep window (e.g., 3×8–12). Add reps session to session until you hit the top of the
window on all sets, then **add load and drop back to the bottom** of the window. Works for
accessories and for intermediates who've outrun session-to-session linear gains.

### 6.3 RPE / RIR autoregulation — **intermediate+**
Prescribe a target reps @ target RPE (e.g., 5 reps @ RPE 8). The lifter selects load that
matches that effort *that day*, absorbing fatigue/readiness fluctuations. Combine with an
e1RM estimate to seed a starting load. [SBS-RIR]

### 6.4 Powerlifting periodization — **intermediate/advanced**
- **5/3/1 (Wendler):** work off a **Training Max = 90% of 1RM**. 4-week waves on the main
  lifts: Wk1 65/75/**85**×5+, Wk2 70/80/**90**×3+, Wk3 75/85/**95**×1+ (top set AMRAP),
  Wk4 **deload** (~40/50/60). Increase TM +5 lb upper / +10 lb lower per cycle. [531]
- **Block periodization:** **Accumulation** (higher volume, moderate intensity, ~65–75%,
  hypertrophy) → **Transmutation/Intensification** (lower volume, higher intensity,
  80–90%, strength) → **Realization/Peak** (taper volume, 90%+, express strength) →
  **Deload**. Matters most for advanced lifters peaking for a total. [GENERAL]

### 6.5 Deload triggers & prescription
Trigger a deload when any of: you **can't match the previous week's performance** despite
rest (RP's MRV signal), ≥2 consecutive failed/ground-out sessions, persistent joint pain
or multi-day soreness, or on a planned schedule (every ~4–8 weeks). Deload = drop volume
to **~MV (≈6 sets/muscle)** and/or cut load ~10% and reps/effort for one week. [RP-VOL]

---

## 7. Estimated 1RM (e1RM) formulas

Given weight `w` lifted for `r` reps:

- **Epley:** `1RM = w × (1 + 0.0333 × r)` — equivalently `w × (1 + r/30)`. [EPLEY]
- **Brzycki:** `1RM = w × 36 / (37 − r)` — equivalently `w / (1.0278 − 0.0278 × r)`. [BRZYCKI]

Both are estimates and diverge at high reps; Epley reads slightly higher than Brzycki
above ~5 reps. Worked example, 100 kg × 5: Epley ≈ 116.7 kg, Brzycki ≈ 112.5 kg.
The engine uses these to (a) track strength trend on SBD and (b) back-calculate a target
load for a prescribed reps@%1RM. Recommend averaging the two, and only trusting estimates
at **≤10 reps**.

---

## 8. Nutrition per goal

### 8.1 Calorie delta
| Goal | Rate | Daily kcal delta |
| --- | --- | --- |
| **Cut** | −0.5 to −1.0 % bodyweight/week | ~ **−500 kcal/day** (range −300 to −750; leaner → 0.5%, higher body-fat → 1%) [RATE][RFIT-MB] |
| **Lean bulk** | +0.25 to +0.5 % bodyweight/week | ~ **+250 to +500 kcal/day** (+250 for intermediates to limit fat gain) [RATE] |
| **Maintain** | ~0 | ±0 (adjust ±100–200 to hold weight) |

Slower rates on both ends preserve/maximize muscle and minimize fat gain. The scale is
the source of truth — TDEE calculators are only a starting estimate. [RFIT-MB]

### 8.2 Protein (g per kg bodyweight/day)
- **General maximum benefit:** ~**1.6 g/kg** (95% CI 1.03–2.20); little added lean mass
  beyond 1.6. [MORTON]
- **ISSN range for exercisers:** **1.4–2.0 g/kg**. [ISSN]
- **Cutting (preserve muscle in a deficit):** go higher — Helms et al. recommend
  **2.3–3.1 g/kg of LEAN body mass**, ≈ **1.8–2.7 g/kg bodyweight**; the engine uses
  **~2.4 g/kg bodyweight** on a cut. Higher protein also aids satiety and offsets loss. [HELMS]
- **Bulk:** **1.6–2.2 g/kg** (engine default ~2.0). **Maintain:** ~**1.6 g/kg**.

### 8.3 Fat floor
Do **not** drop below ~**0.5–0.6 g/kg/day** (hormonal / vitamin-absorption health);
typical target **0.6–1.0 g/kg** or ~20–30% of calories. Engine floor: **0.6 g/kg**. [HELMS-FAT]

### 8.4 Carbohydrate fill
After protein and fat are set, **fill remaining calories with carbohydrate**. Carbs fuel
hard training and glycogen; prioritize them peri-workout. Powerlifting/high-output work
benefits from higher carbs (≈3–5+ g/kg where calories allow). [HELMS-FAT]

### 8.5 Refeeds & diet breaks (cutting only)
- **Refeed:** 1–2 days/week raising calories (carb-driven) to ~maintenance to restore
  glycogen and training output. [RATE][RP-DIET]
- **Diet break:** 1–2 weeks at maintenance after ~8–12 weeks of dieting, **or sooner** if
  triggered by stalled fat loss despite adherence, strength loss, poor sleep/recovery, or
  diet fatigue. Often paired with a training deload. [RP-DIET]

---

## 9. Weekly program templates (SBD-based)

Sets × reps @ RPE, with rest in seconds. Loads are chosen by RPE/e1RM at runtime.

### 9.1 CUTTING + POWERLIFTING — 4-day Upper/Lower (preserve strength, MV–MEV volume)
Priority: keep SBD **intensity** high (low reps, RPE 7–8), minimal accessory volume so
fatigue stays recoverable in a deficit.

- **Day 1 — Lower (Squat focus):** Squat 4×4 @8 (rest 240) · Romanian DL 3×6 @7 (180) ·
  Leg press 2×10 @8 (120) · Hanging leg raise 3×12 (90)
- **Day 2 — Upper (Bench focus):** Bench 4×4 @8 (240) · Overhead press 3×6 @7 (180) ·
  Barbell row 3×6 @8 (150) · Lat pulldown 2×12 @8 (90) · Triceps pushdown 2×12 @9 (75)
- **Day 3 — Lower (Deadlift focus):** Deadlift 3×3 @8 (300) · Front squat 3×5 @7 (180) ·
  Leg curl 3×10 @9 (90) · Standing calf raise 3×12 @9 (75)
- **Day 4 — Upper (Bench volume / back):** Close-grip bench 4×5 @8 (180) ·
  Weighted pull-up 3×6 @8 (150) · Incline DB press 3×10 @8 (120) ·
  Lateral raise 3×15 @9 (60) · Barbell curl 2×12 @9 (75)

### 9.2 BULKING + HYPERTROPHY — 6-day Push/Pull/Legs (SBD compounds, MAV volume)
Priority: accumulate volume toward MAV, SBD as the strength anchor, 2× frequency/muscle.

- **Push A:** Bench 4×6 @8 (180) · OHP 3×8 @8 (150) · Incline DB press 3×10 @9 (120) ·
  Lateral raise 4×15 @9 (60) · Triceps pushdown 3×12 @9 (75)
- **Pull A:** Deadlift 3×5 @8 (240) · Barbell row 4×8 @8 (150) · Lat pulldown 3×12 @9 (90) ·
  Face pull 3×15 @9 (60) · Barbell curl 3×10 @9 (75)
- **Legs A:** Squat 4×6 @8 (240) · Romanian DL 3×8 @8 (180) · Leg press 3×12 @9 (120) ·
  Leg curl 3×12 @9 (90) · Standing calf raise 4×12 @9 (75)
- **Push B:** Incline bench 4×8 @8 (180) · Seated DB press 3×10 @9 (120) ·
  Cable fly 3×15 @9 (75) · Lateral raise 4×15 @9 (60) · Overhead triceps ext 3×12 @9 (75)
- **Pull B:** Pull-up 4×8 @9 (150) · Chest-supported row 4×10 @9 (120) ·
  Rear-delt fly 3×15 @9 (60) · Shrug 3×12 @9 (90) · Incline DB curl 3×12 @9 (75)
- **Legs B:** Front squat 4×8 @8 (210) · Hip thrust 3×10 @9 (150) · Leg extension 3×15 @9 (90) ·
  Seated leg curl 3×12 @9 (90) · Seated calf raise 4×15 @9 (60)

### 9.3 MAINGAINING + INCONSISTENT — 2–3-day Full-Body A/B (minimalist, MV volume)
Priority: resilience. Every session hits the whole body around SBD, so a missed day
doesn't unbalance the week. No make-up sessions needed; just run A, B, A, B… whenever you
train. Autoregulate load by RPE.

- **Full-Body A:** Squat 3×5 @8 (180) · Bench 3×5 @8 (180) · Barbell row 3×8 @8 (120) ·
  Optional: curl or lateral raise 2×12 @9 (75)
- **Full-Body B:** Deadlift 2×5 @8 (240) · Overhead press 3×5 @8 (150) ·
  Lat pulldown 3×10 @9 (90) · Optional: triceps or leg curl 2×12 @9 (75)

---

## 10. Experience-level adjustments (summary)

| Dimension | Beginner | Intermediate | Advanced |
| --- | --- | --- | --- |
| Progression | Linear (per-session load add) | Double progression / weekly RPE | Block periodization + autoregulation |
| Volume | Start at/near MEV, low end | MEV→MRV mesocycle progression | Individualized, closer to MRV |
| %1RM precision | Low (form-limited) | Moderate | High, uses e1RM + RPE |
| Frequency | 3× full-body | 4–6 split | 4–6 individualized |
| Deloads | Reactive (−10% on stall) | Planned every 4–8 wk | Programmed into blocks |

---

## 11. How the algorithmic engine should consume this

- **Everything is a lookup or closed-form calc** — no runtime LLM. Goal + experience →
  rep range, RPE, rest, volume landmark, frequency. Weight targets come from e1RM + %1RM
  or RPE. Nutrition targets come from bodyweight × the g/kg constants and TDEE ± kcal delta.
- **Weekly set targets** should be clamped to the per-muscle `[MEV, MRV]` band for the goal
  (cut → hold near MV–MEV; bulk → progress MEV→MRV; maintain → MV).
- **Progression is a state machine**: hit all reps@target RPE → advance (add load / add
  set / add rep per the scheme); miss → repeat or deload per triggers in §6.5.
- **Estimates are bounded**: trust e1RM only at ≤10 reps; treat volume landmarks as
  starting points that individualize with logged recovery/performance.

---

## Sources

- **[RP-VOL]** Renaissance Periodization — *Training Volume Landmarks for Muscle Growth* (MV/MEV/MAV/MRV, working-set definition, deload). https://rpstrength.com/blogs/articles/training-volume-landmarks-muscle-growth
- **[RP-MUSCLE]** Renaissance Periodization / Dr. Mike Israetel — muscle-specific volume guides (per-muscle MEV/MAV/MRV). https://rpstrength.com/blogs/articles/complete-hypertrophy-training-guide · https://drmikeisraetel.com/dr-mike-israetel-mv-mev-mav-mrv-explained/
- **[SBS-RIR]** Stronger By Science (Greg Nuckols / Pak) — *How To Perfect Your Ability To Predict Repetitions In Reserve* (RPE=10−RIR, autoregulation, load selection). https://www.strongerbyscience.com/reps-in-reserve/ · Autoregulation: https://www.strongerbyscience.com/autoregulation/
- **[SCH-FREQ]** Schoenfeld BJ, Ogborn D, Krieger JW (2016). *Effects of Resistance Training Frequency on Measures of Muscle Hypertrophy: A Systematic Review and Meta-Analysis.* Sports Med 46(11):1689–1697. https://pubmed.ncbi.nlm.nih.gov/27102172/
- **[SCH-REST]** Schoenfeld BJ, Pope ZK, Benik FM, et al. (2016). *Longer Interset Rest Periods Enhance Muscle Strength and Hypertrophy in Resistance-Trained Men.* J Strength Cond Res 30(7):1805–1812. https://pubmed.ncbi.nlm.nih.gov/26605807/
- **[MORTON]** Morton RW, et al. (2018). *A systematic review, meta-analysis and meta-regression of the effect of protein supplementation on resistance training-induced gains in muscle mass and strength.* Br J Sports Med 52(6):376–384 (~1.6 g/kg optimum, CI 1.03–2.20). https://pubmed.ncbi.nlm.nih.gov/28698222/
- **[ISSN]** Jäger R, et al. (2017). *International Society of Sports Nutrition Position Stand: protein and exercise* (1.4–2.0 g/kg). J Int Soc Sports Nutr 14:20. https://jissn.biomedcentral.com/articles/10.1186/s12970-017-0177-8
- **[HELMS]/[HELMS-FAT]** Helms ER, Aragon AA, Fitschen PJ (2014). *Evidence-based recommendations for natural bodybuilding contest preparation: nutrition and supplementation* (protein 2.3–3.1 g/kg LBM on a cut; fat floor ~0.5–0.6 g/kg; carbs fill remainder). J Int Soc Sports Nutr 11:20. https://jissn.biomedcentral.com/articles/10.1186/1550-2783-11-20
- **[EPLEY]** Epley e1RM formula `1RM = w(1 + 0.0333r)`. https://en.wikipedia.org/wiki/One-repetition_maximum
- **[BRZYCKI]** Brzycki e1RM formula `1RM = w × 36/(37 − r)`. https://en.wikipedia.org/wiki/One-repetition_maximum
- **[RFIT-BBR]** r/Fitness Basic Beginner Routine (linear progression rules, +2.5/+5 lb, −10% deload). https://thefitness.wiki/routines/r-fitness-basic-beginner-routine/
- **[RFIT-MB]** r/Fitness (thefitness.wiki) *Muscle Building 101* (calorie surplus, protein target, scale as truth) and *Strength Training / Muscle Building routines* (5/3/1, GZCLP, PPL, nSuns, PHAT). https://thefitness.wiki/muscle-building-101/ · https://thefitness.wiki/routines/strength-training-muscle-building/
- **[531]** Jim Wendler 5/3/1 (Training Max = 90% 1RM, 65/75/85 → 70/80/90 → 75/85/95 waves, AMRAP, wk4 deload). https://thefitness.wiki/5-3-1-primer/ · https://jimwendler.com/blogs/jimwendler-com/101077382-boring-but-big
- **[GZCLP]** GZCL Method / GZCLP (T1/T2/T3 tiers, linear progression). https://thefitness.wiki/routines/gzclp/
- **[RATE]** Evidence-based rate-of-change guidance: cut −0.5 to −1%/wk, lean bulk +0.25 to +0.5%/wk; ±250–500 kcal; refeeds. (Aragon/Helms, Nuckols/SBS) https://www.strongerbyscience.com/how-much-muscle/
- **[RP-DIET]** Renaissance Periodization — diet-break / refeed guidance during fat loss. https://rpstrength.com/blogs/articles/diet-break
- **[GENERAL]** Block periodization overview (accumulation / transmutation / realization). https://www.strongerbyscience.com/complete-strength-training-guide/
