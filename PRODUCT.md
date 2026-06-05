# Product

## Register

product

> Operationally this is a product (a live control tool with forms, state, and
> real-time updates), so product rigor applies to the working surfaces. But the
> guiding emphasis is **"lean into the show"**: the pick reveal and the
> full-screen focus view are projected to a whole room and should be treated
> with brand-level expressiveness. See Design Principle 1.

## Users

**Primary — the host / facilitator.** Someone running Table Topics live in a
video meeting: Toastmasters clubs, team standups and retros, classes,
workshops. They're mid-meeting, screen-sharing a browser tab, and operating in
real time in front of an audience. Their tolerance for fumbling is near zero —
hunting through UI while everyone watches is the failure they fear. The app runs
as one local process (`uv run board.py`) and auto-reads the Zoom Participants
panel on macOS/Windows, with manual entry as the fallback everywhere else.

**Secondary — the room.** Every participant watching the shared screen. They
don't interact; they watch. They experience the random-roll suspense and the
full-screen prompt. The person who gets picked reads their topic off the shared
screen, often from a distance. This audience never touches the UI but is half
the reason it exists.

**The job to be done:**

- *Host:* roll a random participant who hasn't gone yet (the host is excluded),
  hand them a prompt, show it big to the room, mark them done, repeat — keeping
  the activity moving and fair so everyone speaks once.
- *Room:* instantly see who's up and what they've been asked, readable from the
  back row.

## Product Purpose

Run Table Topics in a live meeting from a single local process. Auto-read the
Zoom participant panel, roll a random eligible participant, assign them a prompt,
and display it full-screen for the screen-shared room — while tracking who has
gone so the round stays fair. Topics live only in the host's browser; the
participant roster and matching are ephemeral to the meeting.

Success looks like: the host never fumbles, the room stays engaged and can read
everything, the picked speaker feels encouraged rather than ambushed, and the
whole activity flows without anyone opening a settings panel.

## Brand Personality

**Three words: energetic, playful, confident** — playful in a grown-up way, fun
without being childish.

- **Voice:** warm, encouraging, low-pressure, plain-spoken. The app puts people
  on the spot, so its language should make that feel like an invitation, not an
  interrogation. No corporate jargon.
- **Emotional goals:** for the room — anticipation and a little suspense on the
  roll, delight at the reveal; for the speaker who's up — encouragement and
  ease, never anxiety; for the host — calm, total control.

## Anti-references

- **Not childish or gamified.** No cartoon confetti, no bubbly-rounded
  everything, no game-show kitsch. It has to stay credible in a real meeting.
- **Not a dark "hacker" terminal.** No neon-on-black, no monospace-everything,
  no developer-tool vibe.
- **Not the current warm cream + terracotta "paper" look.** A stated redesign
  goal is a fresh, distinct identity — move clearly and obviously off the
  generic warm-neutral default it has today.
- **Not generic SaaS/admin sameness.** Avoid the cool-gray-cards-plus-safe-blue
  dashboard default; the identity should be deliberate and recognizable.

## Design Principles

1. **The stage leads.** The pick reveal and full-screen focus view are the
   product's face — projected to a whole room. Give them brand-level
   expressiveness and drama. The host's control board stays quiet so the stage
   can be loud.
2. **Two surfaces, two temperaments.** The operating board is clean, calm, and
   low-noise so the host never fumbles. The projected stage is energetic,
   theatrical, and legible from across a room. Same design system, dialed
   differently for each.
3. **Lower the stakes, raise the energy.** Being put on the spot is stressful.
   The roll should feel like a fun beat of suspense and the reveal should feel
   celebratory and encouraging — never like a spotlight interrogation.
4. **Readable from the back row.** Every projected element is sized and
   contrasted to be read at a distance on a shared screen. Legibility is a
   feature, not a finishing touch.
5. **Playful, but it's a real meeting.** Carry personality through motion,
   color, and a confident voice — not novelty. It should look intentional and
   credible to a Toastmasters club and a corporate team alike.

## Accessibility & Inclusion

- **WCAG AA contrast across the whole UI** — 4.5:1 for body text, 3:1 for large
  text — on the host board, not only on the stage.
- **Colorblind-safe states.** Open / on-now / done are never carried by color
  alone; each pairs color with an icon and a text label.
- **Legible at a distance.** Large type and high contrast on the projected
  pick/focus views is a primary requirement, not an afterthought.
- **Respect reduced motion.** The roll shuffle and every reveal keep an instant
  or crossfade fallback (already honored in the current code — preserve it).
- **Keyboard-operable** controls with visible focus states throughout.
