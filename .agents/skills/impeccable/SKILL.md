---
name: impeccable
description: >-
  Frontend craft, design auditing, and anti-slop system by Paul Bakaus. Use when the
  user wants to design, critique, audit, polish, simplify, or harden a frontend interface
  (web, components, forms, dashboards, settings, empty states). Enforces typographic hierarchy,
  accessibility standards, 4/8px spacing rhythms, design tokens, and eliminates generic AI slop.
---

# Impeccable Design Skill (`impeccable`)

Impeccable is a rigorous design engineering and critique framework created by Paul Bakaus to stop AI agents from outputting generic, cookie-cutter "AI slop" (predictable purple gradients, timid font sizes, unformatted form fields, and redundant cards).

---

## 1. Operating Modes & Commands

When invoked or triggered, apply the appropriate mindset:

- **`/impeccable critique`**: Visual hierarchy, layout clarity, visual weight, tone of voice, and aesthetic tension. Identifies what is weak, redundant, or confusing.
- **`/impeccable audit`**: Technical inspection: accessibility (WCAG AA contrast, semantic HTML, focus rings), responsiveness, tap target sizes ($\ge 44 \times 44\text{px}$), and layout overflow.
- **`/impeccable polish`**: High-craft refinement pass: alignment, micro-spacing consistency, optical centering, subtle border contrasts, and typographic refinement.
- **`/impeccable harden`**: Defensive frontend design: empty states, long text truncation, localization overflows, disabled states, loading skeletons, and error handling.

---

## 2. Anti-Slop Rules

1. **Ban Generic AI Aesthetics:**
   - No gratuitous purple/indigo-to-cyan gradient text or backgrounds without deliberate brand purpose.
   - No floating translucent glassmorphism cards with illegible text.
   - No generic 3-column feature cards with identical abstract emoji icons in circles.
   - No unstyled standard checkboxes or browser-native select dropdowns in modern designs.

2. **Typography & Hierarchy:**
   - Create distinct scale: Headlines must be confident and clearly differentiated from body text in size, weight, and letter-spacing (e.g. `tracking-tight` on large display headings).
   - Optical sizing & line heights: Headings need tighter line-height (`leading-tight` or `1.1–1.2`); body copy needs comfortable breathing room (`leading-relaxed` or `1.5–1.6`).
   - Limit font weight variations to 2–3 per view (e.g. Regular 400, Medium 500, Semibold 600).

3. **Spatial Rhythm & The 4/8px Grid:**
   - Use strict spatial multipliers: 4px, 8px, 12px, 16px, 24px, 32px, 48px, 64px.
   - Related items sit close together; distinct groups sit far apart. (Law of Proximity).
   - Avoid equal spacing everywhere (which flattens visual hierarchy).

4. **Design Tokens & Systems:**
   - Extract raw colors, radii, and spacings into CSS variables / Tailwind tokens (`--bg-surface`, `--text-primary`, `--border-subtle`).
   - Never sprinkle arbitrary hex codes or magic pixel values across individual components.

5. **Accessibility as a Foundation:**
   - Body text must meet minimum 4.5:1 contrast against background; large headings must meet 3:1.
   - All interactive controls have distinct `:focus-visible` outlines.
   - Icon-only buttons must have descriptive `aria-label` attributes.
