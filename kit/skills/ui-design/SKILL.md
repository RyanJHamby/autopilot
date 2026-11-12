---
name: ui-design
description: MANDATORY whenever you build, edit or restyle any user interface, even if the user never mentions design: a landing page, marketing site, dashboard, app screen, component, form, email template, or any HTML, CSS, TSX, JSX, Vue or Svelte file. Prevents the vibe-coded look (pastel and neon colors, gradients, Inter, Lucide, em dashes, three-card rows, glass, emojis). Load it before writing the first line of UI.
---

# UI design (no vibe-coded tells)

Applies to every UI you build, whether or not the request mentions design. The owner does not want to have to ask. The same
rules are in `STANDARD.md` ("UI and landing pages") and checked by `ap standard check . ` (rule `ui-no-vibe-tells`), which
fails a new repo's CI. Passing the check is necessary, not sufficient: it sees source patterns, not layout or truth.

## Before writing any UI
1. Pick a palette and a type pair from the product itself: its logo, its domain, a reference the owner names. If none exists,
   propose two options and ask. Do not default to anything.
2. Write the palette as CSS variables or theme tokens first. Use them everywhere. No stray hex values.
3. Pick one corner radius and one shadow level (or none) and use them deliberately.

## Never (the owner's list, with the pastel rule added)
- **Color:** pastels (washed-out blue, mint, peach, lavender, pink tints), rainbow, neon, purple-and-black, harsh gradients,
  radial orbs and glow blobs, a pure white `#fff` page background (use an off-white or a real dark).
- **Layout:** three feature cards in a row, bento grids, three pricing tiers by default, colored left stripes on cards, dot
  grids, a fake terminal window as decoration.
- **Surface:** liquid glass or backdrop blur, drop shadows as the main depth cue, one big soft radius on everything.
- **Type and icons:** Inter, Geist, Space Grotesk; Lucide icons; sparkle icons; emojis; checkmark bullets.
- **Copy:** em dashes (use a period, comma or colon); "it's not X, it's Y"; fake testimonials (none, or a real quote with a
  name and a source).
- **Motion:** hover animations for their own sake, animated arrows, everything fading in on scroll, cursor-following beams. Use
  skeleton loaders for loading states.
- **Craft:** an untouched shadcn/ui theme, low-contrast dark mode (4.5:1 minimum), inconsistent one-off spacing, vague button
  labels ("Learn more", "Get started", "Submit"), clickable divs and missing focus styles, forms asking for too much (5 fields max),
  generic buzzword copy (seamless, supercharge, game-changer), badges above headlines, placeholder business info, broken
  third-party embeds.
- **Substance:** show the real product (screenshot, recording, live demo), not a mockup of one. Back every claim with proof or drop it. A page that collects an email
  or takes payment needs a terms page and a privacy policy.

If the owner explicitly asks for one of these, do it for that item only and say so in your reply.

## Before you say it is done
1. Run `ap standard check .` from the repo root (or `uv run ap standard check .` in autopilot) and read the `ui-no-vibe-tells`
   result. Fix every finding. Do not edit `checks.yaml` or add a waiver to get past it: a waiver is the owner's call.
2. Check by eye what the lint cannot: no three-up card rows or bento layouts, no badge above a headline, no decorative terminal window, a real product demo is present,
   every claim has proof, third-party embeds actually load, tab through the page to check the keyboard path, nothing reads
   like template copy, contrast is readable in the palette you chose.
3. Say plainly what you verified (the check output, a screenshot you looked at) and what you did not.
