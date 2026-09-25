---
name: Nordic Telephony & AI Operations
colors:
  surface: '#e7fef9'
  surface-dim: '#c8dfda'
  surface-bright: '#e7fef9'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#e1f8f3'
  surface-container: '#dcf3ee'
  surface-container-high: '#d6ede8'
  surface-container-highest: '#d0e7e2'
  on-surface: '#0a1f1c'
  on-surface-variant: '#404946'
  inverse-surface: '#203431'
  inverse-on-surface: '#dff6f0'
  outline: '#707976'
  outline-variant: '#bfc9c4'
  surface-tint: '#33675c'
  primary: '#00362d'
  on-primary: '#ffffff'
  primary-container: '#164e43'
  on-primary-container: '#88beb0'
  inverse-primary: '#9bd1c3'
  secondary: '#546508'
  on-secondary: '#ffffff'
  secondary-container: '#d4ea82'
  on-secondary-container: '#586a0e'
  tertiary: '#00334a'
  on-tertiary: '#ffffff'
  tertiary-container: '#004b6a'
  on-tertiary-container: '#80bbe0'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#b6eede'
  primary-fixed-dim: '#9bd1c3'
  on-primary-fixed: '#00201a'
  on-primary-fixed-variant: '#184f44'
  secondary-fixed: '#d6ec85'
  secondary-fixed-dim: '#bbd06c'
  on-secondary-fixed: '#171e00'
  on-secondary-fixed-variant: '#3e4c00'
  tertiary-fixed: '#c6e7ff'
  tertiary-fixed-dim: '#93cef4'
  on-tertiary-fixed: '#001e2d'
  on-tertiary-fixed-variant: '#004c6b'
  background: '#e7fef9'
  on-background: '#0a1f1c'
  surface-variant: '#d0e7e2'
typography:
  display-lg:
    fontFamily: Manrope
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.03em
  display-lg-mobile:
    fontFamily: Manrope
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Manrope
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Manrope
    fontSize: 22px
    fontWeight: '700'
    lineHeight: 30px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Manrope
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 30px
    letterSpacing: -0.015em
  headline-sm:
    fontFamily: Manrope
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  label-lg:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.04em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-lg: 1.5rem
  margin: 1rem
  margin-md: 1.5rem
  margin-lg: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system establishes a confident, grounded, and human-centered aesthetic tailored for enterprise-grade Danish AI telephony, reception, and communication workflows. Built on the tenets of modern Scandinavian product design—clarity, functional warmth, and purposeful restraint—it prioritizes operational transparency over decorative embellishments.

### Core Character
- **Calm & Capable:** Telephony management and incoming queue spikes require an interface that reduces cognitive noise. The atmosphere feels deliberate, quiet, and trustworthy.
- **Approachable & Contemporary:** Technical AI mechanics (natural language routing, voice-to-text transcripts, and outbound dialer queues) are framed through accessible layouts and clean visual semantics.
- **Danish Functionalism:** Every element serves an intent. Crisp micro-copy in natural Danish, robust tabular data presentation, and high legibility ensure seamless everyday operations.

### Aesthetic Movement
Modern Corporate B2B with Warm Nordic Minimalist influences:
- Soft off-white backdrops eliminate the clinical sterility of pure cold whites.
- High-contrast pine ink provides crisp typographic hierarchy.
- Vibrant lime-citron acts as a laser-targeted accent for active calls, positive indicators, and high-priority states.

## Colors

The palette is rooted in organic Scandinavian tones, pairing an architectural spruce green with a functional warm foundation and a high-vitality accent.

### Color Architecture
- **Canvas / Background (`#F6F7F3`):** Warm off-white foundation that reduces eye strain in prolonged shift usage across dispatchers and operators.
- **Surface (`#FFFFFF`):** High-clarity white reserved for distinct interactive panels, modals, data tables, and call cards.
- **Surface Subtle / Container (`#EEF2ED`):** Used for sidebar rails, search inputs, active selection pills, and secondary card panels.
- **Borders & Dividers (`#DCE3DC`):** 1px structural boundaries defining operational panels without harsh contrast.

### Brand & Interactive Colors
- **Primary Ink / Headings (`#172B28`):** Deep pine ink, replacing harsh pure black for all structural text and title headers.
- **Primary Action (`#164E43`):** Forest spruce green indicating key tasks (e.g., *Start opkald*, *Gem ændringer*, *Opret kampagne*).
- **Primary Hover (`#113D34`):** Deepened spruce state for mouse focus and press interactions.
- **Highlight Accent (`#D8EE86`):** Acid lime-citron. Always paired with `#172B28` text for contrast compliance. Used for active badges, live call status, and selected navigation nodes.
- **Muted Text (`#56635D`):** Slate moss for metadata, time stamps, secondary descriptions, and table headers.

### Semantic Tones
- **Success (`#1B7A4B`):** Completed calls, positive agent availability, successful campaign dispatches.
- **Warning (`#C87D12`):** Queues nearing SLA thresholds, requested callbacks approaching timeout.
- **Error (`#C93B2B`):** Failed calls, unassigned dropped connections, API errors.
- **Info (`#2C6B8D`):** System notes, IVR routing metadata, telecommunication carrier updates.

## Typography

The type system blends structural geometric warmth for titles with utilitarian legibility for high-throughput telephony interfaces.

- **Headings (Manrope):** Geometric and contemporary with tight kerning (`-0.01em` to `-0.03em`). Conveys architectural authority across dashboards, call metrics, and configuration heads.
- **Body & Numerical Labels (Inter):** Highly legible across varied monitor calibrations. Must consistently enable OpenType tabular figures (`tnum`) for call timestamps (`02:43`), durations, queue counts, phone numbers (`+45 XX XX XX XX`), and currency amounts (`DKK 1.250,00`).
- **Language & Formatting:** All typography templates should natively accommodate Danish characters (`æ`, `ø`, `å`) and align to European number syntax (period as thousands separator, comma as decimal delimiter).

## Layout & Spacing

A compact, operational density model tuned for call centers, reception dispatch, and automated flow configurations.

### Grid & Layout Systems
- **Desktop (1280px+):** Fixed collapsible navigation rail (240px wide or 64px icon-only), fluid workspace container with 12-column grid, `1.5rem` gutters, and `2rem` outer padding.
- **Tablet / Responsive Desk (768px - 1279px):** 8-column layout, `1rem` gutters, drawer navigation. Dual-pane views (e.g., call list + call detail transcript) collapse to off-canvas sheets.
- **Mobile (Below 768px):** 4-column layout, `1rem` margins. Prioritizes quick status monitoring, agent status switching, and single-stream transcript inspection.

### Spacing Rhythm
Built upon a strict 4px / 8px baseline. Component interiors default to `0.5rem` (`space-sm`) and `0.75rem` (`space-md`) vertical padding to ensure dense tabular rows, rapid call log scanning, and compact interactive forms.

## Elevation & Depth

Visual hierarchy uses tonal surface layering combined with low-contrast outlines rather than heavy skeuomorphic drop shadows.

- **Structural Borders:** Surfaces rely on a 1px border (`#DCE3DC`) to cleanly segment UI regions across the `#F6F7F3` background canvas.
- **Layering & Depth Hierarchy:**
  - *Tier 0 (Canvas):* `#F6F7F3` for app background.
  - *Tier 1 (Surface Panel):* `#FFFFFF` cards and tables, bordered with `#DCE3DC`. Flat, no shadow.
  - *Tier 2 (Popovers / Dropdowns / Hovered Cards):* Elevated with a subtle pine-tinted ambient shadow: `box-shadow: 0 4px 12px rgba(23, 43, 40, 0.06), 0 1px 2px rgba(23, 43, 40, 0.04)`.
  - *Tier 3 (Active Live Call Drawer / Overlays):* `box-shadow: 0 12px 32px rgba(23, 43, 40, 0.12), 0 2px 6px rgba(23, 43, 40, 0.04)`.

## Shapes

The interface balances soft industrial ergonomics with geometric precision:

- Standard inputs, buttons, and call cards leverage an explicit **10px - 12px corner radius** (represented by Level 2, with base `0.5rem` and scale up to `1rem`).
- Pills and live badges (e.g., status tags like *Aktiv*, *I kø*, *Viderestillet*) employ full pill borders (`9999px`) to immediately distinguish contextual status elements from actionable buttons and cards.
- Avatar elements for caller profiles or agent assignments utilize soft squares with 8px radius or round circular geometry.

## Components

### Buttons
- **Primary:** Background `#164E43`, text `#FFFFFF`, border-radius `10px`, padding `10px 18px`. Hover: `#113D34`.
- **Secondary / Action Citron:** Background `#D8EE86`, text `#172B28`, font-weight `600`. Ideal for live interaction call triggers (e.g., *Besvar opkald*). Hover: slight brightness drop.
- **Tertiary / Ghost:** Border `1px solid #DCE3DC`, background `#FFFFFF`, text `#172B28`. Hover: background `#EEF2ED`.

### Badges & Status Indicators
- **Active Call / Live Session:** Pill shape, `#D8EE86` background, `#172B28` text, accompanied by an animated pulsing dot (`#164E43`).
- **Queued / Callback Requested:** `#EEF2ED` background with `#56635D` text and a warning indicator where waiting time exceeds 2 minutes.

### Form Inputs & Search
- Inputs sit on `#FFFFFF` surfaces with a 1px `#DCE3DC` stroke and `10px` corner radius.
- Padding: `8px 12px`. Text in `#172B28`, placeholder in `#56635D`.
- Focus state: `1px solid #164E43` outline with a 2px outer glow of `rgba(22, 78, 67, 0.15)`.

### Call & Transcript Cards
- Container background: `#FFFFFF`, border: `1px solid #DCE3DC`, radius: `12px`.
- Padding: `16px`. Header features caller ID in `label-lg`, with timestamp and duration right-aligned using tabular figures (`Inter`).
- AI Transcript snippets: Placed within an `#EEF2ED` nested block with `8px` radius and `13px` body text.

### Telephony Keypad & Live Routing Flow Nodes
- Dial keys: Circular `#FFFFFF` surfaces with `1px solid #DCE3DC`, active state transitions to `#EEF2ED`.
- Flow builder cards: `#FFFFFF` containers with a spruce green (`#164E43`) handle indicating trigger status, conditional branch paths, and Danish fallback voice prompts.