# Test: Overlapping PDF evidence inspection

## Purpose

Verify native highlight clicks cycle exact evidence associations while annotation
action controls remain usable. Inspection focus must persist visibly and remain
independent of saved findings, review decisions and annotation labels.

## Prerequisites

- A source-bound build of the real application with isolated copied data/media.
- Two eligible evidence quotations with overlapping PDF bounds and different
  owning results. Include repeated quotation text with distinct associations.
- Retained original/corrected versions and a result without eligible evidence.
- Native browser recording and before/after source-association fingerprints.

No model or ingestion call is needed. Do not change shared sources or saved
assessments while inspecting. Keep exact private-case IDs in the
[private issue](https://github.com/pi-squared/OpenContracts-Development/issues/40)
and private receipts.

## Steps

1. Select the exact document, extract and effective finding version. Expand the
   source group and use its source card to navigate to the PDF. Wait for scroll
   animation and rendering to settle before measuring the actual bounds.
2. Verify the two visible PDF evidence rectangles overlap and identify their
   exact annotation/result associations. Hover the shared passage, then click
   the same point three times. The two owning evidence items must alternate,
   with the first selected again on the third click. Never force a DOM click.
3. Begin with the corresponding result off-screen or its group collapsed.
   Clicking its highlight must reveal the exact source card, expand the group
   and scroll it into view. Repeated text must not select an unrelated item.
4. Move the pointer away. The active highlight must retain distinct blue
   inspection appearance and its card must stay focused. Select the other
   highlight; the previous highlight returns to its inactive appearance. Saved
   semantic labels, values, corrections and review decisions must not change.
5. Open the annotation actions using pointer and keyboard. Activate a harmless
   action or open and cancel a child dialog. Visible action buttons remain
   interactive and Escape restores the launcher. Empty space around the action
   buttons must pass pointer clicks to the PDF. The launcher's actual measured
   hit target must fit its label; no invisible extension may cover the passage.
6. Tab to an evidence highlight and use Enter/Space to inspect it. Navigate from
   a source card to the PDF and from the PDF back to its exact source card.
7. Repeat at small, normal and enlarged zoom and after resizing. Wait for each
   layout/scroll animation before checking bounds. Source rectangles remain at
   the same normalized PDF positions; label placement may adjust around them.
8. Switch document, extract and original/effective version. Verify stale focus
   clears. Suppressed or missing evidence cannot inherit a highlight or reveal
   a different finding. Preserve dragging, text selection, modifier actions and
   deliberate annotation menu activation.

## Automated regression

`PdfEvidenceOverlap.ct.tsx` exercises the actual production selection, label,
action menu, focus hooks and page pointer handlers on a synthetic canvas. It
uses native browser clicks at actual rectangle intersections at three scales,
checks persistent focus appearance and context clearing, and exercises keyboard
inspection and action controls. `RadialButtonCloud.ct.tsx` covers empty-space
pointer passage and existing menu/confirmation behavior. `SelectionInfo.ct.tsx`
retains label background controls.

Run those component tests with the repository Playwright toolchain, explicit
`--reporter=list`, and an unused owned test-server port. Also run affected unit
tests and `tsc --noEmit`. The synthetic canvas is a CSS/callsite regression;
source-bound real PDF recordings remain required for application acceptance.

## Cleanup

Remove temporary observers without changing application handlers. Retain native
videos, source/build manifests, hashes and private state fingerprints. Stop only
owned test processes and preserve unrelated services and historical evidence.
