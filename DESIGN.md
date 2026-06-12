---
name: Mini Apps
description: Polished single-file browser artifacts with compact, credible interface craft.
colors:
  ivory: "oklch(0.985 0.005 25)"
  white: "oklch(0.995 0.003 25)"
  slate: "oklch(0.205 0.01 25)"
  clay: "oklch(0.50 0.14 25)"
  clay-deep: "oklch(0.40 0.12 25)"
  oat: "oklch(0.94 0.03 25)"
  olive: "oklch(0.56 0.12 145)"
  rust: "oklch(0.40 0.12 25)"
  gray-50: "oklch(0.97 0.006 25)"
  gray-200: "oklch(0.922 0.006 25)"
  gray-500: "oklch(0.556 0.01 25)"
  gray-800: "oklch(0.30 0.01 25)"
typography:
  display:
    fontFamily: "Geist, Arial, sans-serif"
    fontSize: "clamp(2rem, 4vw, 3rem)"
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: "0"
  headline:
    fontFamily: "Geist, Arial, sans-serif"
    fontSize: "30px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "0"
  title:
    fontFamily: "Geist, Arial, sans-serif"
    fontSize: "17px"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "0"
  body:
    fontFamily: "Geist, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "\"Geist Mono\", ui-monospace, \"SF Mono\", Menlo, Consolas, monospace"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0.04em"
rounded:
  xs: "4px"
  sm: "6px"
  md: "8px"
  panel: "10px"
  display: "14px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  page: "32px"
components:
  button-primary:
    backgroundColor: "{colors.slate}"
    textColor: "{colors.ivory}"
    rounded: "{rounded.sm}"
    padding: "9px 16px"
    typography: "{typography.label}"
  button-primary-accent:
    backgroundColor: "{colors.clay}"
    textColor: "{colors.white}"
    rounded: "{rounded.sm}"
    padding: "9px 16px"
    typography: "{typography.label}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.gray-800}"
    rounded: "{rounded.sm}"
    padding: "8px 15px"
    typography: "{typography.label}"
  panel:
    backgroundColor: "{colors.white}"
    textColor: "{colors.slate}"
    rounded: "{rounded.panel}"
    padding: "16px"
  chip:
    backgroundColor: "{colors.gray-50}"
    textColor: "{colors.gray-800}"
    rounded: "{rounded.sm}"
    padding: "3px 8px"
    typography: "{typography.label}"
---

# Design System: Mini Apps

## 1. Overview

**Creative North Star: "The Finished Field Note"**

Mini Apps should feel like compact artifacts made by someone who knows the subject and respects the recipient's time. The interface is dense enough to be useful at first open, but not so dense that it becomes a wall of controls. The app, board, report, diagram, or editor should be visible immediately and carry the page's visual weight.

The system is precise, quiet, and tool-like. It borrows the seriousness of an operations console without becoming dark, cold, or infrastructural. Warm clay and olive accents identify priority, state, and motion; near-white surfaces, fine borders, and compact type keep the artifact portable and easy to inspect.

This system rejects generic SaaS landing pages, decorative gradient heroes, hollow metrics, over-carded dashboards, and any page that hides the usable artifact behind marketing structure.

**Key Characteristics:**
- Artifact-first composition with the main useful surface above the fold.
- Low-radius, border-led surfaces with almost no decorative shadow.
- Geist-based typography, using mono sparingly for metadata, code, counters, and machine-readable labels.
- OKLCH color tokens, with clay as the primary accent and slate as the primary command color.
- Responsive layouts that collapse cleanly without changing the core task.

## 2. Colors

The palette is a warm technical neutral system: ivory and white carry the surface, slate anchors text and primary actions, clay marks attention, and olive marks success or completion.

### Primary
- **Workbench Slate** (`oklch(0.205 0.01 25)`): Primary text, dark panels, and default primary actions. Use it when the command is structural, such as copy, save, export, or run.
- **Fired Clay** (`oklch(0.50 0.14 25)`): Main accent for links, active states, warnings, selected nodes, progress, and visual emphasis. It should be rare enough to matter.
- **Deep Clay** (`oklch(0.40 0.12 25)`): Stronger clay tone for text on tinted clay backgrounds, warning labels, and hover states.

### Secondary
- **Operational Olive** (`oklch(0.56 0.12 145)`): Success, completion, passed states, resolved items, and positive flow edges. It should not replace clay as the brand accent.
- **Rust Fault** (`oklch(0.40 0.12 25)`): Failure, incident, deletion, or regression states. Keep it contextual and paired with text labels.

### Neutral
- **Ivory Workspace** (`oklch(0.985 0.005 25)`): Default body background. It is nearly white and subtly warm, not paper-themed.
- **Clean Surface** (`oklch(0.995 0.003 25)`): Panels, controls, canvases, card interiors, and popover-like surfaces.
- **Oat Wash** (`oklch(0.94 0.03 25)`): Soft highlighted regions, inactive avatars, inline slots, and warm emphasis backgrounds.
- **Gray 50** (`oklch(0.97 0.006 25)`): Toolbar fills, code backgrounds, table headers, counters, and quiet chips.
- **Gray 200** (`oklch(0.922 0.006 25)`): Standard borders and dividers.
- **Gray 500** (`oklch(0.556 0.01 25)`): Secondary text, metadata, placeholder text when contrast remains AA, and inactive icon strokes.
- **Gray 800** (`oklch(0.30 0.01 25)`): Strong secondary text and hover foregrounds.

### Named Rules

**The Accent Rarity Rule.** Clay should identify state, selection, or a primary visual cue. Do not spread it across every heading, icon, and divider.

**The Surface Clarity Rule.** Panels sit on ivory and use white interiors with one-pixel borders. Avoid tinted card piles unless the artifact needs grouped state.

## 3. Typography

**Display Font:** Geist with Arial and sans-serif fallbacks.
**Body Font:** Geist with Arial and sans-serif fallbacks.
**Label/Mono Font:** Geist Mono with ui-monospace, SF Mono, Menlo, Consolas, and monospace fallbacks.

**Character:** The typography should read like a finished technical artifact, not a marketing page. Sans text carries most hierarchy; mono is a utility material for code, labels, counters, and compact metadata.

### Hierarchy
- **Display** (500, `clamp(2rem, 4vw, 3rem)`, `1.1`): Rare large headings for overview and design reference pages. Keep letter spacing at `0`.
- **Headline** (500, `30px`, `1.2`): Default page title for editors, boards, diagrams, reports, and prototypes.
- **Title** (500 to 600, `17px`, `1.3`): Panel headers, column headers, ticket titles, and card titles.
- **Body** (400, `14px`, `1.5`): Standard readable copy. Keep prose blocks at roughly `65ch` or less.
- **Small Body** (400, `13px` to `13.5px`, `1.55` to `1.7`): Dense explanations, side-panel copy, code-adjacent annotations, and secondary rows.
- **Label** (500, `11px`, `0.04em` to `0.08em`): Short metadata, toolbar hints, counters, badges, and section labels. Uppercase is allowed only for brief labels, not sentences.
- **Code** (Geist Mono, `11px` to `13px`, `1.55` to `1.7`): Code blocks, editor content, IDs, timestamps, diffs, and flowchart text.

### Named Rules

**The Mono Has a Job Rule.** Use mono when the text is machine-adjacent, measured, or metadata-like. Do not use it as generic personality.

**The Flat Heading Rule.** Headings use weight, size, and spacing, not tight tracking, gradients, or ornamental font pairing.

## 4. Elevation

The system is flat by default. Depth comes from tonal separation, one-pixel borders, sticky toolbars, active outlines, and rare hover shadows. Most panels and cards should explicitly use `box-shadow: none`.

### Shadow Vocabulary
- **Resting Surface** (`box-shadow: none`): Default for panels, cards, canvases, stages, reports, slides, metrics, and token cards.
- **Tiny Hover Lift** (`box-shadow: 0 1px 3px rgba(20,20,19,0.06)`): Optional for draggable or clickable cards when hover needs tactile feedback.
- **Reference Small** (`box-shadow: 0 1px 2px rgba(20,20,19,0.06)`): Use only for isolated reference demonstrations or small floating affordances.
- **Reference Medium** (`box-shadow: 0 4px 10px rgba(20,20,19,0.08)`): Rare, for transient overlays where a border alone is not enough.
- **Reference Large** (`box-shadow: 0 12px 28px rgba(20,20,19,0.12)`): Avoid in ordinary mini apps. Reserve for deliberate design-system examples or modal-like focus.

### Named Rules

**The Border Before Shadow Rule.** Use a single solid border before reaching for elevation. Do not pair decorative wide shadows with bordered cards.

## 5. Components

Components should feel compact, inspectable, and complete. Each mini app can invent the surface it needs, but controls should share a common material language.

### Buttons
- **Shape:** Low-radius rectangle (`6px`), never oversized pill unless the control is a chip or segmented toggle.
- **Primary:** Slate background with ivory text, one-pixel slate border, `9px 16px` padding, compact label type.
- **Accent Primary:** Clay background with white text for brand-forward or destructive-adjacent commands when the surrounding context makes the action clear.
- **Hover / Focus:** Darken slate or shift border color. Active states can use `translateY(1px)` for tactile feedback. Focus states must be visible.
- **Secondary / Ghost:** Transparent or white background, gray border, gray-800 text. Hover by increasing border contrast rather than adding decoration.

### Chips
- **Style:** Mono labels, `6px` radius, tight padding, gray-50 or state-tinted backgrounds.
- **State:** Active filters use clay-tinted backgrounds with deep clay text. Success chips use olive-tinted backgrounds. Neutral chips use gray-50 and gray-800.

### Cards / Containers
- **Corner Style:** Compact panels use `10px`; repeated row cards use `6px`; larger canvases may use `14px`.
- **Background:** White on ivory, with gray-200 borders. Dark code or diff panels may use slate with ivory or gray-50 text.
- **Shadow Strategy:** Flat at rest. Add only the tiny hover lift for clickable or draggable items that need feedback.
- **Border:** One pixel solid gray-200 or gray-300. Do not use decorative side-stripe borders.
- **Internal Padding:** Dense rows use `10px` to `12px`; panels use `16px` to `24px`; large canvases use `28px` to `32px`.

### Inputs / Fields
- **Style:** White background, slate text, gray-200 border, `6px` to `8px` radius, compact padding.
- **Focus:** Clay border with a restrained ring such as `0 0 0 3px rgba(217, 119, 87, 0.15)`.
- **Placeholder:** Use gray-500 only when contrast is acceptable. For long helper copy, prefer visible labels or hints outside the field.
- **Disabled:** Reduce opacity only after preserving legibility; pair with cursor and label treatment.

### Navigation
- **Style:** Sticky local toolbars are preferred over global navigation. Use ivory backgrounds, gray-200 bottom borders, compact gaps, and right-aligned command groups.
- **State:** Active filters or modes should be visible as chips, segmented controls, or selected buttons, not only by color.

### Diagrams / Canvases
- **Style:** Use white or clean-surface canvases with gray borders and compact mono labels. Keep diagrams interactive when the example implies inspection.
- **State:** Clay marks selection, olive marks passed or yes paths, rust marks failed or no paths, and gray marks neutral flow.

### Motion
- **Style:** Motion should explain the interaction: dragged tickets, completed tasks, selected flow nodes, copied states, and short-lived success feedback.
- **Timing:** Most UI transitions should sit between `120ms` and `280ms`. Use easing deliberately and respect `prefers-reduced-motion`.
- **Reduced Motion:** Provide instant state changes or opacity-only alternatives for nonessential motion.

## 6. Do's and Don'ts

### Do
- Put the artifact, editor, board, diagram, or report in the first viewport.
- Start each mini app with local OKLCH tokens in `:root` so the file stays portable.
- Use Geist as the primary family and Geist Mono only where the content benefits from measured, code-like texture.
- Keep body text readable, with slate or gray-800 for important copy and gray-500 only for secondary metadata.
- Use one-pixel borders, compact radii, and measured spacing to build credibility.
- Give every interactive surface hover, active, focus, empty, and narrow-screen behavior.
- Let each brief have a specific point of view while preserving the shared material language.

### Don't
- Do not build marketing-first landing pages around a hidden or tiny artifact.
- Do not use gradient text, decorative glass panels, repeated feature-card grids, or hero metric blocks.
- Do not add side-stripe borders to cards or callouts.
- Do not over-round panels, cards, inputs, or sections beyond the established scale.
- Do not use repeated tiny uppercase eyebrows as section scaffolding.
- Do not rely on gray text for core body copy on tinted backgrounds.
- Do not ship colored placeholder rectangles where the brief requires actual imagery, screenshots, diagrams, or interactive visuals.
- Do not introduce a new palette just because a mini app has a different subject. Extend the existing palette with a named role only when the artifact needs it.
