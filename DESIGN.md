---
name: Table Topics
description: A live Table Topics board for Zoom, built on the Toastmasters brand system.
colors:
  loyal-blue: "#004165"
  blissful-blue: "#006094"
  true-maroon: "#772432"
  happy-yellow: "#f2df74"
  cool-gray: "#a9b2b1"
  white: "#ffffff"
  fair-gray: "#f5f6f6"
  surface-2: "#eceeef"
  line: "#dde2e2"
  line-2: "#c5cccc"
  ink: "#11252f"
  ink-soft: "#3a4d56"
  muted: "#54656d"
  faint: "#8a979d"
  primary-tint: "#e7eef3"
  primary-tint-2: "#cfe0ea"
  accent-deep: "#6b560f"
  accent-tint: "#fbf4d4"
  danger: "#772432"
  stage-bg: "#05202e"
  stage-deep: "#021019"
  stage-card: "#0c2c3d"
  stage-line: "#1e4a60"
  stage-ink: "#f4fafc"
  stage-soft: "#bcd2dc"
  stage-muted: "#88a3b0"
typography:
  display:
    fontFamily: "Montserrat, system-ui, sans-serif"
    fontSize: "clamp(2.4rem, 6.5vw, 6rem)"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Montserrat, system-ui, sans-serif"
    fontSize: "clamp(1.6rem, 1.2rem + 1.3vw, 2.15rem)"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Source Sans 3, system-ui, sans-serif"
    fontSize: "1.05rem"
    fontWeight: 600
    lineHeight: 1.28
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Source Sans 3, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "Source Sans 3, system-ui, sans-serif"
    fontSize: "0.7rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.08em"
rounded:
  xs: "7px"
  sm: "11px"
  md: "15px"
  lg: "22px"
  pill: "999px"
components:
  button-primary:
    backgroundColor: "{colors.loyal-blue}"
    textColor: "{colors.white}"
    rounded: "{rounded.sm}"
    padding: "13px 22px"
  button-primary-hover:
    backgroundColor: "#002f49"
  button-secondary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.white}"
    rounded: "{rounded.xs}"
    padding: "10px 16px"
  button-ghost:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.xs}"
    padding: "10px 16px"
  topic-card:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "15px 17px 14px"
  input:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xs}"
    padding: "11px 14px"
  status-open:
    backgroundColor: "{colors.primary-tint}"
    textColor: "{colors.loyal-blue}"
    rounded: "{rounded.pill}"
    padding: "3px 9px"
  focus-headline:
    textColor: "{colors.stage-ink}"
    typography: "{typography.display}"
---

# Design System: Table Topics

## 1. Overview

The creative north star is **"Center Stage."**

This is a tool with two temperaments, and the whole system lives in the gap
between them. The host's board is the calm preparation at the lectern: a white,
composed control surface where a facilitator queues people and prompts without
fumbling in front of a room. The pick reveal and the full-screen focus view are
the moment of stepping into the light: the room dims to a deep Loyal Blue
auditorium and a warm Happy Yellow spotlight finds the speaker. Same design
system, dialed all the way down for work and all the way up for the show.

It is built on the **Toastmasters International** brand (Brand Manual v2.0):
Loyal Blue carries the product, Happy Yellow is the spotlight, True Maroon is a
secondary accent, Montserrat and Source Sans 3 stand in for Gotham and Myriad
Pro. The look should read as credibly Toastmasters to a club officer and as a
confident, modern tool to anyone else. It is professional and warm at once,
which is exactly the brand's stated voice: "clear, yet respectful; friendly, yet
professional."

What it explicitly rejects: the old cream-and-terracotta "paper" look it
replaced; childish or gamified treatments (cartoon confetti, bubbly rounding,
game-show kitsch); a dark "hacker terminal" aesthetic; and the generic
cool-gray-cards-plus-safe-blue SaaS dashboard. The energy comes from one warm
light in a dark room, not from novelty.

**Key Characteristics:**

- **Two surfaces, two temperaments:** a quiet white board, a theatrical dark-blue stage.
- **The spotlight is the signature:** a Happy Yellow bloom that only fires when a name settles.
- **Brand-exact color:** every brand value is the literal hex from the Toastmasters manual.
- **Built to be read from the back row:** large Montserrat display, high contrast on both surfaces.
- **Calm by default, loud on cue:** motion and color are reserved for the reveal, not sprinkled everywhere.

## 2. Colors

A confident Loyal Blue core, a single warm Happy Yellow spotlight, and a
restrained set of blue-tinted neutrals. The full Toastmasters palette is present
but each color has exactly one job.

### Primary

- **Loyal Blue** (`#004165`): The brand spine. Carries the primary CTA ("Pick next participant"), the focus-view "Done" button, selection and link color, the microphone brand mark, body ink's underlying tint, and the dark stage's hue family. White text always rides on it (≈9:1).
- **Blissful Blue** (`#006094`): The lighter end of the Loyal Blue gradient. Used only as the hover state for the dark-stage "Done" button.

### Secondary

- **Happy Yellow** (`#f2df74`): The spotlight. The brand calls it the color "to make elements stand out," and here it does exactly one dramatic thing: the radial bloom behind the settled name, the reveal glint, the "live" dot and "IT'S" / "UP NOW" labels on the dark stage, and the on-now highlight. It is never asked to carry text on a light surface (it is too pale); on the board, gold text uses **Accent Deep** (`#6b560f`) instead.

### Tertiary

- **True Maroon** (`#772432`): The brand's third color, used sparingly. It marks the "HOST" badge in the roster and is the caution color for destructive affordances (remove topic, remove participant) on hover. Never decorative.

### Neutral

- **White** (`#ffffff`): The board body. The honest off-cream answer: a true white, no warm tint.
- **Fair Gray** (`#f5f6f6`) / **Surface-2** (`#eceeef`): Card, panel, and stat-tile fills; the editor area.
- **Line** (`#dde2e2`) / **Line-2** (`#c5cccc`): Hairlines and input borders.
- **Ink** (`#11252f`): Body and heading text on the board, a near-black tinted toward Loyal Blue (≥12:1 on white).
- **Ink Soft** (`#3a4d56`): Secondary headings, detail text, ghost-button label.
- **Muted** (`#54656d`): Secondary and placeholder text. Held dark enough for ≥4.5:1; never lighter.
- **Faint** (`#8a979d`): Decorative icons and the chip "remove" glyph at rest only. Not for text that must be read.
- **Stage Bg** (`#05202e`) / **Stage Deep** (`#021019`): The darkened auditorium and its vignette, both in the Loyal Blue family.
- **Stage Card** (`#0c2c3d`) / **Stage Line** (`#1e4a60`): Topic cards and borders on the dark stage.
- **Stage Ink** (`#f4fafc`) / **Stage Soft** (`#bcd2dc`) / **Stage Muted** (`#88a3b0`): The text ramp on the dark stage.

### Color Rules

**The One Light Rule.** Happy Yellow is the spotlight and nothing else. It appears at the reveal and on the dark stage; it never becomes a button, a card fill, or a body color. Its scarcity is what makes the reveal feel like a reveal.

**The Brand-Exact Rule.** Loyal Blue is `#004165`, Happy Yellow is `#f2df74`, True Maroon is `#772432`, full stop. These are the Toastmasters manual's literal values and must not be re-tinted, "balanced," or nudged toward a custom hue.

## 3. Typography

**Display Font:** Montserrat (with system-ui, sans-serif)
**Body Font:** Source Sans 3 (with system-ui, sans-serif)

**Character:** A geometric, wide-stance display sans paired with a humanist text
sans, the exact contrast axis the brand intends. These are the free, web-safe
stand-ins the Toastmasters manual names for **Gotham** (display) and **Myriad
Pro** (body); use them in place of the licensed originals.

### Hierarchy

- **Display** (Montserrat 800, `clamp(2.4rem, 6.5vw, 6rem)`, line-height 1.05, `-0.035em`): The shuffle name and the focus-view prompt. Built to be read across a room. Capped at 6rem so it never shouts past the design.
- **Headline** (Montserrat 700, `clamp(1.6rem, 1.2rem + 1.3vw, 2.15rem)`, `-0.025em`): The "Table Topics" wordmark and empty-state headings.
- **Title** (Source Sans 3 600, `1.05rem`, line-height 1.28): Topic card headlines.
- **Body** (Source Sans 3 400, `0.9375rem`, line-height 1.5): Detail text, hints, footer. Prose measure stays within 65–75ch.
- **Label** (Source Sans 3 700, `0.7rem`, `0.08em`, uppercase): Section heads, status pills, the "UP NOW" / "IT'S" stage labels, stat captions.
- **Stat figure** (Montserrat 700, `1.9rem`, tabular): The scoreboard counts.

### Type Rules

**The Display-Is-For-The-Room Rule.** Montserrat at display weight is reserved for the name, the prompt, the wordmark, and the scoreboard numbers, the things a remote room reads. Everything operational is Source Sans 3.

**The Short-Label Rule.** Uppercase is allowed only on labels of four words or fewer (section heads, status pills, badges). Never set a sentence in caps.

## 4. Elevation

Flat by default, blue-tinted shadows on demand. The board is mostly borders and
tonal layering (white on Fair Gray); shadows appear as a response to state and
to lift the things that matter. All shadow tints are Loyal Blue
(`rgba(0,65,101,...)`), never neutral black, so depth stays on-brand. On the dark
stage, "elevation" is light, not shadow: the spotlight bloom and a yellow
hover-glow do the lifting.

### Shadow Vocabulary

- **Ambient small** (`box-shadow: 0 1px 2px rgba(0,65,101,.06), 0 2px 6px rgba(0,65,101,.05)`): Resting lift on stat tiles, the active tab, the active card.
- **Hover medium** (`box-shadow: 0 10px 34px -16px rgba(0,65,101,.26)`): A topic card lifting on hover when it is choosable.
- **CTA** (`box-shadow: 0 6px 20px -8px rgba(0,65,101,.45)`): The primary "Pick" button, so the main action sits slightly proud.
- **Spotlight glow** (`text-shadow: 0 0 52px rgba(242,223,116,.38)` / radial Happy-Yellow bloom): The stage's only "elevation," carried by light.

### Elevation Rules

**The Flat-By-Default Rule.** Surfaces rest flat. A shadow means "this is interactive or this just changed" (hover, lift, the reveal). If a shadow isn't earning a state, delete it.

**The Blue-Shadow Rule.** Shadows are tinted Loyal Blue, never gray-black. A neutral drop shadow reads as a 2014 app; the blue tint keeps it in the brand.

## 5. Components

### Buttons

- **Shape:** Gently rounded (CTA `11px`, secondary/ghost `7px`).
- **Primary (the "Pick" CTA):** Loyal Blue fill, white label, `13px 22px`, CTA shadow. The single most important action on the board.
- **Hover / Focus:** Darken to `#002f49` and lift `translateY(-1px)`; focus-visible is a 2px Loyal Blue ring at 3px offset.
- **Secondary ("Add topic", form submits):** Ink fill, white label, `7px` radius. Deliberately quieter than the blue CTA so the hierarchy stays clear.
- **Ghost / Quiet ("Add", "New round", "Cancel"):** White (or transparent) fill, Ink-Soft label, Line-2 border. On the dark stage these flip to Stage-Card fills with Stage-Soft text.
- **Done (focus view):** Loyal Blue on the dark stage, white label; hover to Blissful Blue. The one filled button that survives into the auditorium.

### Chips (roster)

- **Style:** White pill, Line-2 border, name in Ink (600). Answered chips drop to Fair Gray with Muted text and a check icon.
- **State (colorblind-safe):** Present uses a Loyal Blue ring icon; answered uses a check; left fades to 50% opacity. State is always icon + color, never color alone. The **HOST** badge is a filled True Maroon pill.

### Topic Cards

- **Corner Style:** `15px` radius.
- **Background:** White on the board; Stage Card (`#0c2c3d`) on the dark stage.
- **Shadow Strategy:** Flat at rest; Hover-medium lift only when the card is choosable (picking mode). On the dark stage, hover is a Happy Yellow ring + glow.
- **Border:** 1px Line at rest; Loyal Blue (board) or Happy Yellow (stage) on choosable hover.
- **Status pill:** Open = Loyal Blue on Primary-Tint; On-now = Accent-Deep on Accent-Tint; Done = Muted on Surface-2. Always icon + word + color.
- **Internal Padding:** `15px 17px 14px`.

### Inputs / Fields

- **Style:** White fill, Line-2 stroke, `7px` radius.
- **Focus:** Border shifts to Loyal Blue with a 3px Primary-Tint-2 glow ring. No browser default outline.

### Navigation

There is no nav. The app is three full-screen views (board, picking, focus) switched by state, not by chrome. Keep it that way; do not add a nav bar.

### Signature Component: The Spotlight Reveal

The defining moment. On a new pick the stage cycles eligible names (~70ms each)
for ~1s, then settles: the name snaps to white with a `name-pop` scale, a Happy
Yellow radial bloom blooms in behind it (`.stage.lit`), the glint and banner
fade up, and the topic choices appear. The board→stage transition is the house
lights going down. Under `prefers-reduced-motion`, the shuffle is skipped and the
spotlight is simply on: the reveal never depends on motion to deliver the name.

## 6. Do's and Don'ts

### Do

- **Do** use the literal Toastmasters hex values: Loyal Blue `#004165`, Happy Yellow `#f2df74`, True Maroon `#772432`, Cool Gray `#a9b2b1`.
- **Do** keep Happy Yellow for the spotlight and highlights only; let Loyal Blue carry actions and structure.
- **Do** pair Montserrat (display) with Source Sans 3 (body) as the free stand-ins for Gotham and Myriad Pro.
- **Do** keep body and placeholder text at Muted (`#54656d`) or darker for ≥4.5:1; on the dark stage keep white-on-blue and never black-on-blue (per the manual's contrast note).
- **Do** carry state with icon + word + color together, so open / on-now / done survive colorblindness and a low-quality screen share.
- **Do** tint shadows Loyal Blue; keep the board flat until a state earns a lift.
- **Do** leave a clean header slot where the official Toastmasters logo could be placed for official club use.

### Don't

- **Don't** recreate, redraw, or customize the Toastmasters globe logo, and don't invent a club logo or tagline. The Brand Manual prohibits it; the current header uses a generic microphone mark, not the logo.
- **Don't** put a patterned or colored glow behind the official logo if one is ever added (a manual prohibition); the yellow bloom belongs behind the speaker's name, not behind a logo.
- **Don't** re-tint or "balance" the brand colors, and don't introduce a non-brand accent.
- **Don't** drift back toward the old cream-and-terracotta "paper" look, or any warm-neutral body background.
- **Don't** go childish or gamified: no cartoon confetti, no bubbly oversized rounding, no game-show kitsch.
- **Don't** turn the board into a dark "hacker terminal," and don't reach for the generic cool-gray-cards-plus-safe-blue SaaS dashboard.
- **Don't** let Happy Yellow carry text on a light surface (it fails contrast); use Accent-Deep `#6b560f` for gold text instead.
- **Don't** use a `border-left`/`border-right` greater than 1px as a colored accent stripe, gradient-filled text, or decorative glassmorphism.
- **Don't** use em dashes in UI copy.
