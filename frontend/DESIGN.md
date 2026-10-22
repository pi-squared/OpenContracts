---
version: alpha
name: OpenContracts
description: Evidence-first workspace for reading documents and reviewing findings.
colors:
  primary: "#0F766E"
  primary-hover: "#0D9488"
  primary-active: "#115E59"
  application-accent-hover: "#0d6860"
  ink: "#0F172A"
  text-primary: "#1E293B"
  text-body: "#334155"
  text-secondary: "#475569"
  text-metadata: "#64748b"
  text-muted: "#94A3B8"
  canvas: "#FAFAFA"
  warm-paper: "#FAFAF7"
  surface: "#FFFFFF"
  surface-hover: "#F8FAFC"
  surface-subtle: "#F1F5F9"
  border: "#E2E8F0"
  border-strong: "#CBD5E1"
  interactive-blue: "#3b82f6"
  annotation-purple: "#7c3aed"
  supported-text: "#166534"
  supported-surface: "#dcfce7"
  rejected-text: "#991b1b"
  rejected-surface: "#fee2e2"
  uncertain-text: "#92400e"
  uncertain-surface: "#fef3c7"
  warning-text: "#854d0e"
  warning-surface: "#fefce8"
  info-text: "#0369a1"
  info-surface: "#f0f9ff"
typography:
  display:
    fontFamily: 'Georgia, "Times New Roman", serif'
    fontSize: "42px"
    fontWeight: 400
    lineHeight: 1.2
  brand:
    fontFamily: '"Source Serif 4", "Source Serif Pro", Georgia, "Times New Roman", serif'
    fontSize: "19px"
    fontWeight: 400
    letterSpacing: "-0.4px"
  section-title:
    fontFamily: 'Georgia, "Times New Roman", serif'
    fontSize: "24px"
    fontWeight: 400
  body:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  subtitle:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.6
  finding-body:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "13px"
    fontWeight: 500
  caption:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "12px"
    fontWeight: 400
rounded:
  list-item: "6px"
  button: "8px"
  card: "12px"
  empty-state: "16px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  2xl: "48px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.button}"
    height: "36px"
    padding: "0px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-primary-active:
    backgroundColor: "{colors.primary-active}"
  button-secondary:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.text-primary}"
    typography: "{typography.label}"
    rounded: "{rounded.button}"
    height: "36px"
    padding: "0px 16px"
  input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.text-primary}"
    typography: "{typography.label}"
    rounded: "{rounded.button}"
    height: "36px"
  navigation:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    padding: "12px 24px"
  finding-supported:
    backgroundColor: "{colors.supported-surface}"
    textColor: "{colors.supported-text}"
    rounded: "{rounded.card}"
    padding: "4px 10px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.card}"
  finding-inline:
    textColor: "{colors.text-body}"
    typography: "{typography.finding-body}"
    padding: "10px"
---

# Design System: OpenContracts

## Overview

**Creative North Star: "Evidence-first workspace"**

A clear, practical, restrained workspace for reading documents and reviewing findings. Deep teal marks actions and selection; slate text and white surfaces keep the document and its results prominent. Subtle layers and softly rounded controls organize dense information without competing with it.

This records the implemented system, the inline-results layout accepted on 20 October 2026, and the simplified finding summary accepted on 22 October 2026. Existing screen families have local variations: list pages pair serif headings with sans-serif controls, while document tools use compact sans-serif labels and findings. Preserve those distinctions when extending a screen.

**Key Characteristics:**

- Deep teal and slate on white and off-white surfaces.
- Readable content with a compact, task-focused control layer.
- Subtle elevation and softly rounded controls.
- Finding outcomes, reviewer decisions, and source quotations remain distinct.

## Colors

The palette combines deep teal and slate with white surfaces and subtle layers. Frontmatter contains the extracted values; the descriptions below explain their roles.

### Primary

**Deep teal** (`primary`) marks selection, links, and the UI library’s primary actions. `primary-hover` and `primary-active` are the library’s existing states. The application token module also has a darker `application-accent-hover`; use the state belonging to the component being extended.

### Secondary

**Interactive blue** remains in existing viewer controls and older interactive components. **Annotation purple** identifies agent-related material. These are observed local roles, rather than interchangeable primary accents.

### Neutral

**Ink** anchors navigation and existing navy actions. Primary and body slate carry reading text; secondary slate and metadata slate provide hierarchy. Muted slate is reserved for low-emphasis decoration and disabled content, rather than essential small text. Canvas, warm paper, white surfaces, hover surfaces, and subtle surfaces remain separate tokens. Borders use the existing light and stronger slate separators.

### Semantic states

Supported, rejected, uncertain, warning, and information treatments pair a text color with a tinted surface. Always retain a text label. A finding outcome and its reviewer approval are separate pieces of information.

## Typography

**Display:** Georgia and Times New Roman on the shared list-page hero and section headings. The brand stack starts with Source Serif 4 and Source Serif Pro, with Georgia fallbacks.

**Body and controls:** Inter with the existing platform sans-serif fallback stack. Global browser-body CSS has a broader system stack; document and page components apply their own Inter stack. Code views keep their existing monospace treatment.

List-page heroes use the `display` role and reduce to 32 px at the shared 768 px breakpoint. Some dedicated token-based views also use the existing 26 px mobile hero size; follow the owning view. Subtitles use the `subtitle` role with relaxed leading and a maximum width of 600 px. The accepted document results use `finding-body`; their field headings are semibold and secondary text remains clearly legible.

## Layout

The shared page shell scrolls vertically and centers a main column: 900 px for standard list pages and 1200 px for wide detail pages. Shared desktop content padding is 48 px above, 24 px at each side, and 80 px below. At 768 px and below it reduces to 32 px, 16 px, and 60 px. Compact detail pages use their established smaller top padding. Section gaps follow the existing spacing scale.

Document reading uses a main document canvas beside contextual results and tools. The accepted inline result layout shows labelled rows: labels and values share two columns when the result content container is at least 320 px wide, and stack in narrower containers. Its outer cell retains 10 px padding with 14 px text and 1.6 line height. The finding summary accepted on 22 October uses a pale inset panel with 14 px internal padding, a 6 px radius, a light border, and a 12 px gap. It contains only the verdict badge and Rationale; review actions stay below it. These are finding-component choices, not new application-wide spacing scales.

Navigation changes to the custom mobile treatment below 1100 px. The component library also defines 640, 768, 1024, and 1280 px breakpoints; individual views retain their own responsive rules. Container width governs finding readability independently of viewport width.

## Elevation & Depth

Depth is subtle and structural: quiet surfaces, light dividers, and soft shadows distinguish cards, menus, and floating document tools. Dense finding rows use dividers; they do not need an individual shadow per field. The shared card shadow is `0 4px 12px rgba(0, 0, 0, 0.04)` and card hover is `0 8px 24px rgba(0, 0, 0, 0.08)`. Centered modals use `0 25px 50px -12px rgba(15, 23, 42, 0.25)`. The existing extraction table container has its own softer wide shadow; preserve it when extending that container.

Short state transitions use the library’s existing 150–300 ms timing and standard or entry easing. Floating panels have their own motion; judge their settled layout after their opening transition.

## Shapes

Controls generally use the button radius, containers use the card radius, and inset rows use the list-item radius. Empty-state panels have a softer empty-state radius. Pills are established for compact badges and filters. Retain the shape appropriate to the existing component family.

## Components

### Buttons

Restrained, softly rounded controls. The medium UI-library primary button uses teal, inverse text, the label typography, and a small shadow. Hover uses the existing hover fill and a slight lift; active returns to rest. Secondary buttons use a pale surface and a light border. Keyboard focus uses an explicit accent outline. Preserve loading and disabled states. Existing ink-colored primary actions remain valid within their owning screens.

### Inputs

A pale canvas surface, light border, and softly rounded edge distinguish editable fields. Medium library inputs are 36 px high. Focus changes the border and adds the component’s existing focus treatment; search and standard inputs have different established focus shadows. Error states retain their semantic border and message.

### Navigation

The desktop navigation uses an ink surface, light controls, and a serif wordmark. Mobile navigation is a separate implementation. Keep an explicit active state and labelled, keyboard-accessible destinations. Document-local navigation and floating tools retain their existing local accents.

### Cards and containers

White or pale containers group related material with the card radius and the surrounding screen’s border or elevation treatment. Shared list views, empty states, and document results have different density requirements; inherit the relevant component’s padding.

### Findings and inline results

The document sidebar summary shows only the real verdict badge and Rationale.
Patrick accepted the pale inset panel (option 3) on 22 October 2026, with 14 px
internal padding, a 1 px light border, 6 px radius, 14 px body text and 1.6 line
height. Keep the badge at 13 px, the Rationale label at 13 px semibold, and a
12 px gap with a light divider before the rationale. The text wraps to the pane.

Edit, Approve and Reject stay below the summary. The outcome badge does not
imply reviewer approval. The sidebar panel omits review-state text, customer
purpose, template-field state, applicability and quotation details; it does not
remove them from saved data. Full finding details elsewhere retain their
existing fields, evidence locations, error states and source-navigation controls.
Other structured sidebar values retain their labelled rows.

## Do's and Don'ts

### Do:

- **Do** reuse the owning screen’s shared tokens and components.
- **Do** keep the sidebar finding summary to verdict and Rationale, with review actions below; full structured detail views retain readable labelled values.
- **Do** retain visible verdict text and distinguish outcomes from reviewer decisions.
- **Do** wrap long text and adapt labelled rows to their available pane width.
- **Do** preserve keyboard focus, loading, error, empty, and disabled states.

### Don't:

- **Don't** require a JSON modal to read the document sidebar’s results.
- **Don't** equate a supported finding with reviewer approval.
- **Don't** show stale quotations for a not-found finding.
- **Don't** assume every screen uses the same heading font, hover color, or breakpoint.

Extracted from `src/assets/configurations/osLegalStyles.ts`, `src/index.css`, `src/components/layout/PageLayout.tsx`, `src/components/layout/NavMenu.tsx`, the installed `@os-legal/ui` styles, `FindingView.tsx`, and the accepted `SingleDocumentExtractResults.tsx` implementation. Format: [DESIGN.md specification](https://github.com/google-labs-code/design.md/blob/main/docs/spec.md).

## Extraction review accepted 22 October 2026

The Edit finding action opens the focused review form accepted as option 4.
Verdict and Evidence tabs separate the two comment fields, retaining the verdict
and rationale as context and the supporting quotations as an open disclosure.
Use 14px body text, 136px minimum textarea height and the existing teal/slate
palette. Save comments persists both fields together. Failed saves keep the form
and its draft available for retry.

Supporting quotations use the confirmation dialog accepted as option 4, with
14px spacing and text. Reject quotation opens a focused confirmation containing
the selected quote; Keep quotation or Escape cancels. Confirm rejection saves
the removal before hiding the quotation and its corresponding extracts/PDF
annotations. Preserve unsaved comment drafts through that update. The original
extraction remains available in history; reviewer metadata belongs outside its
schema-validated response. Keyboard focus returns to a useful quotation action
or the comment field after the confirmation closes.

PDF highlight inspection also reveals the corresponding right-hand extract
annotation: open its group, focus the card and scroll within the result panel.
Repeat activation brings it back into view; Escape clears the inspection focus.
Keep an active comment draft focused while background evidence queries refresh.
