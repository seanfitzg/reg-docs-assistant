# Locators for non-clause-numbered documents include a page number

For `heading_sections` and `academic_sections` Chunks, the `locator` is the heading (or section title) plus the page number it starts on, e.g. `"Overview (p. 12)"` — not the heading alone, and not a page range with no heading.

A clause number like a CP's "1.1" is already directly verifiable: search the source PDF for it. A bare heading isn't — headings repeat across a document (and across documents) and give no way to find the passage short of reading the whole thing, which can run to 185 pages (the Annual Report). Citation depends on being checkable against the original (ADR-0010); the page number is what makes that check cheap, while the heading is what keeps the locator meaningful rather than an arbitrary page slice.
