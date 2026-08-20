---
name: TeamChat
description: Internal LAN team hub for chat, QA defect tracking, schedule, and Excel tools
colors:
  signal-blue: "#4f6df5"
  signal-blue-hover: "#3b53d9"
  alert-coral: "#e05252"
  mention-amber: "#fff3cd"
  mention-indigo: "#3554d1"
  leave-orange: "#e0762e"
  work-teal: "#2e86ab"
  online-green: "#2ecc71"
  unread-orange: "#f5a623"
  surface: "#ffffff"
  neutral-bg: "#f5f6f8"
  border: "#e2e4e8"
  text: "#1a1d23"
  text-muted: "#6b7280"
typography:
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Malgun Gothic', sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "normal"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Malgun Gothic', sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "normal"
  subtitle:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Malgun Gothic', sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: "normal"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Malgun Gothic', sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Malgun Gothic', sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.03em"
  caption:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Malgun Gothic', sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: "normal"
rounded:
  2xs: "4px"
  xs: "6px"
  sm: "8px"
  md: "10px"
  lg: "12px"
  full: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.signal-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "6px 12px"
  button-primary-hover:
    backgroundColor: "{colors.signal-blue-hover}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "6px 12px"
  button-secondary:
    backgroundColor: "{colors.neutral-bg}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "6px 12px"
  button-danger:
    backgroundColor: "{colors.alert-coral}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "6px 12px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "6px 12px"
  badge-count:
    backgroundColor: "{colors.alert-coral}"
    textColor: "#ffffff"
    rounded: "{rounded.full}"
    padding: "0 5px"
    height: "18px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "16px"
  input:
    backgroundColor: "{colors.neutral-bg}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "8px 10px"
  message-bubble-mine:
    backgroundColor: "{colors.signal-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.lg}"
    padding: "8px 12px"
  message-bubble-theirs:
    backgroundColor: "{colors.neutral-bg}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    padding: "8px 12px"
---

# Design System: TeamChat

## Overview

**Creative North Star: "The Shift Log"**

TeamChat reads like a tool people duck into mid-task, not a product they spend time in. Everything about it — the flat gray panels, the single blue accent reserved for one action per screen, the system font stack with a Korean fallback baked in — says internal utility over showcase. It is calm and unapologetically plain: no illustration, no marketing chrome, no attempt to feel like a consumer chat app. The restraint isn't cold, though — rounded corners on nearly everything (8–12px, going fully pill-shaped for anything that's a count or a tag), soft emoji used as functional icons (🌙/☀️ for theme, 🔒 for private rooms, colored dots for status), and a warm amber highlight for mentions keep it from reading as sterile. The overall character the team confirmed: **restrained, but warm.**

The system is fully dark-mode mirrored via a `data-theme` attribute the user toggles explicitly (falling back to `prefers-color-scheme` when unset) — every token below has a light and dark value, and both are load-bearing, not an afterthought.

**Key Characteristics:**
- One accent color (signal-blue) used sparingly, for the single primary action on a screen — not scattered across secondary buttons.
- Flat by default: every resting surface (panel, card, button, input) is bordered, not shadowed.
- Elevation is reserved for floating/transient layers only (pickers, dropdowns, modal scrims).
- Pill shape (999px) marks anything representing a count, status, or tag; 8–10px marks containers and controls.
- Full light/dark parity — no color exists in only one theme.

## Colors

Mostly neutral grayscale with one blue action accent and a small set of role-specific signal colors (danger, mention, and two schedule-category colors); no secondary or tertiary brand accent exists.

### Primary
- **Signal Blue** (`#4f6df5` light / `#6b85ff` dark — `oklch(58.9% 0.206 269.6)`): the one primary-action color. Used only on the send/submit button, the "+ 방 만들기" create-room button, the active sidebar nav link, "my" chat bubble, and the checked state of the visibility toggle. Its rarity is deliberate — see the Named Rule below.
- **Signal Blue Hover** (`#3b53d9` light / `#829fff` dark — one step deeper in light mode, one step lighter in dark mode along the same hue/chroma): the `.btn-primary` hover state only. This is the one deliberate exception to "no hover anywhere" — see Components > Buttons.

### Neutral
- **Surface** (`#ffffff` light / `#1e2126` dark): panel, card, modal, and auth-card backgrounds — the "raised" layer.
- **Neutral Canvas** (`#f5f6f8` light / `#14161a` dark): page background, and also the resting fill for inputs and secondary/ghost buttons — inputs sit visually one step "recessed" from their container.
- **Border** (`#e2e4e8` light / `#2c2f36` dark): the universal 1px edge on every panel, card, button, and input. This is how surfaces are delineated — see Shapes.
- **Text** (`#1a1d23` light / `#eef0f3` dark): primary text color.
- **Text Muted** (`#6b7280` light / `#9aa0aa` dark): secondary text — meta lines, hints, timestamps, placeholder-like labels.

### Named Rules
**The One Accent Rule.** Signal Blue appears on at most one control per screen — the primary action. Secondary, danger, and ghost buttons all stay neutral; adding blue to more than the single primary action breaks the system's restraint.

**The Border-Not-Shadow Rule.** A surface's edge is drawn with a 1px `border` in the neutral border color, never a shadow. Shadows are reserved for floating layers only (see Elevation & Depth).

### Signal Colors
- **Alert Coral** (`#e05252` light / `#ff6b6b` dark): danger actions (delete buttons), the admin role badge, unread-count badges, and the `@전체` (mention-all) highlight.
- **Mention Amber** (`#fff3cd` light / `#4a3c00` dark): soft highlight background — the active/hover row in the @-mention autocomplete list, the schedule banner in chat, and the background of a reaction pill the current user has added.
- **Mention Indigo** (`#3554d1` light / `#ffd166` dark, paired with `#ffffff`/`#1a1200` text): the inline highlight for an `@nickname` mention inside a message body (distinct from `@전체`, which uses Alert Coral instead).
- **Leave Orange** (`#e0762e` light / `#ff9a56` dark): schedule calendar dot/bar for 연차 (annual leave) and 반차 (half-day leave) entries.
- **Work Teal** (`#2e86ab` light / `#5ab4d6` dark): schedule calendar dot/bar for 업무일정 (work-schedule) entries.
- **Online Green** (`#2ecc71`, same value in both themes): the single "online" state — the filled dot next to a nickname anywhere a person's connection status is shown (active-users rows, the 1:1 people list, admin/user-management rows). The offline counterpart is just `{colors.text-muted}`, not a distinct color.
- **Unread Orange** (`#f5a623`, same value in both themes): the small "안읽음" (unread) marker text on a message a recipient hasn't seen yet — deliberately different from Alert Coral so a per-message unread marker doesn't compete visually with the room-level unread count badge.

## Typography

**Body Font:** `-apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", sans-serif` — a single system-font stack for every role; no separate display or mono face. The Korean fallback (Malgun Gothic) is load-bearing since all shipped copy is Korean.

**Character:** Plain system typography throughout — hierarchy comes entirely from size and weight, never from a second typeface.

### Hierarchy
- **Headline** (700, 22px, line-height 1.3): the login screen's title — the only page-level headline in the app.
- **Title** (700, 16px, line-height 1.3): section and modal headers (`panel-header h2`, `chat-header h1`, `modal-header h2`).
- **Subtitle** (400, 14px, line-height 1.3): a step down from Title — the login screen's subtext, form inputs, and compact section sub-headers (calendar/list panel titles, the Excel page's section headings).
- **Body** (400, 13px, line-height 1.4): default UI text — buttons, list rows, message text.
- **Label** (600, 12px, sometimes uppercase with 0.03em tracking): emphasized micro-text — table column headers, admin sub-group headings.
- **Caption** (400, 11px, line-height 1.3): the smallest tier — badge text, meta/timestamp lines, calendar weekday labels; bumped to 700 for the same emphasis cases the Two-Weight Rule covers (unread markers, count badges).

Two sizes sit outside this text hierarchy on purpose: **18px** marks icon-sized glyphs (☰ sidebar toggle, × modal close, the 🔓/🔒 room-visibility icon) rather than a reading-text step, and **15px** is a single intentional one-off on the drag-and-drop overlay prompt. Neither should be reused as a general text size.

### Named Rules
**The Two-Weight Rule.** Text is either regular weight or bumped to 600–700 for emphasis (names, titles, badges) — there is no intermediate 500 weight anywhere in the system.

## Layout

The app shell is a sidebar + content pattern. Below 1024px the sidebar (240px) is an off-canvas drawer with a scrim backdrop, toggled by a fixed top-left button; at 1024px and above it becomes an always-visible fixed left rail — a deliberate "desktop app / internal system" tone rather than a marketing-site responsive collapse.

Content is centered in role-specific max-widths rather than one global container: 1100px for the rooms dashboard, 900px for the chat thread, 1200px for the issue/defect table, 900px for the admin page, and 560px for narrow single-column pages (excel).

The rooms dashboard is the one page with a genuine multi-region grid: 채팅방 (rooms) and 1:1 대화 (people) sit side by side in the top row, and a full-width row below holds the schedule widget (its own calendar + list two-column sub-grid, `minmax(260px, 340px) 1fr`) — so a person's daily view (rooms, people, calendar) loads in one place instead of three separate pages. The room/people lists scroll internally; the schedule widget doesn't need to since its own list is already height-capped.

**Spacing rhythm:** primarily 8 / 12 / 16 / 24px, with 4px for the tightest gaps (icon-to-label) and 6/10/14/20px as one-off in-between values inside dense rows (form fields, list items). A second breakpoint (720px for excel, 1023px for the rooms dashboard) collapses multi-column layouts to one column.

## Elevation & Depth

Flat by default — panels, cards, buttons, and inputs carry no shadow at all; a 1px border does all the work of separating a surface from its background (see the Border-Not-Shadow Rule). Shadow is reserved for layers that float above the page and must read as temporary: the emoji reaction picker, the @-mention autocomplete dropdown, and the modal/sidebar backdrop scrims. The toggle-switch knob carries a hairline shadow of its own for the same reason — it's the one control that visibly lifts off its track.

### Shadow Vocabulary
- **Floating panel** (`box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18)`): reaction picker, @-mention autocomplete dropdown.
- **Modal scrim** (`background: rgba(0, 0, 0, 0.45)`, full-viewport overlay, no shadow on the modal card itself — the card stays flat/bordered like everything else): the dimming layer behind any modal.
- **Sidebar scrim** (`background: rgba(0, 0, 0, 0.35)`): the lighter backdrop behind the off-canvas sidebar drawer below 1024px — deliberately less opaque than the modal scrim since the drawer is a navigation surface, not an interrupting one.
- **Knob lift** (`box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25)`): the visibility-toggle switch's sliding knob.

### Named Rules
**The Grounded-Except-Floating Rule.** If it sits in the document flow, it's flat and bordered. If it floats above the page (picker, dropdown, scrim), it gets a shadow. Nothing in between.

## Shapes

Six radius steps, applied by role rather than by component size:
- **4px** — the smallest interactive glyphs: reaction/delete icon buttons on a message, the inline `@mention` highlight.
- **6px** — compact interactive rows one step down from a full control: calendar day cells, @-mention autocomplete rows.
- **8px** — controls: buttons, inputs, room-list items, sidebar nav links.
- **10px** — containers: panels, cards, modals, the auth card.
- **12px** — chat message bubbles and inline image previews.
- **999px (full pill)** — anything representing a count, status, or tag: badges, unread counts, reaction pills, issue-subject tags, the theme toggle track.

Every bordered surface uses the same 1px, solid, neutral-border-color stroke — there is no secondary border weight or color anywhere in the system.

## Components

### Buttons
- **Shape:** 8px radius; all variants (secondary/danger/ghost) keep a 1px border, including ghost — only its background drops to transparent. `.btn-primary` has no border (its fill is the edge).
- **Primary** (`.btn-primary`: `{colors.signal-blue}` bg, white text, no border, padding `6px 12px` — same footprint as secondary/danger/ghost, weight 600, `align-self: flex-start` so it never stretches to its container's full width): the reusable primary button, currently just "+ 방 만들기" (create room). Reserve it for the one thing a screen most wants the visitor to do; everything else on that screen stays secondary/ghost/danger (The One Accent Rule). The send-message and login buttons are older, larger one-off instances of the same color (`10px 16px` / `10px` padding) predating this class — don't copy their sizing for a new primary button, use `.btn-primary`.
- **Secondary** (`{colors.neutral-bg}` bg, `{colors.text}` text, bordered): the default button for most actions (save, add, "+ 일정 추가").
- **Danger** (`{colors.alert-coral}` bg + border, white text): destructive actions only (delete room/message/user, demote admin).
- **Ghost** (transparent bg, bordered, `{colors.text}` text): tertiary/cancel actions, and links styled as buttons (e.g. "다크모드").
- **Hover / Focus:** `.btn-primary` is the one button variant with a hover state — it deepens to `{colors.signal-blue-hover}` over 0.2s ease, color only, no shadow or movement. Every other button/panel/list row still has none; don't assume one exists elsewhere when extending a button.

### Badges & Pills
- **Status badge:** pill, muted `{colors.border}` bg + `{colors.text-muted}` text; the admin-role variant swaps to solid Alert Coral + white.
- **Count badge:** pill, Alert Coral bg, white bold text, 18px minimum diameter — used for unread counts everywhere except inside the active (already-blue) sidebar nav link, where it inverts to a white pill with coral text so it still reads against the fill.
- **Reaction pill:** pill, `{colors.surface}` bg + border by default; becomes Mention Amber bg + Signal Blue border + bold text when the current user is one of the reactors.
- **Issue subject tag:** pill, muted bg; an "archived" subject drops to a transparent, dashed-border pill instead of being hidden.

### Cards / Panels
- **Corner style:** 10px.
- **Background:** `{colors.surface}`; 1px border; no shadow (see Elevation).
- **Internal padding:** 16px standard.

### Inputs / Fields
- **Style:** `{colors.neutral-bg}` background (recessed relative to the surface it sits on), 1px border, 8px radius.
- **Focus:** no custom focus ring exists on text inputs, selects, or textareas — they fall back to the browser default outline. The one component with an explicit focus treatment is the visibility toggle switch (`2px solid {colors.signal-blue}` outline, 2px offset).
- **Readonly:** dims to `{colors.text-muted}` (e.g. the reporter field on the issue form, which is set automatically from the logged-in nickname).

### Navigation (sidebar)
- Off-canvas drawer below 1024px (with scrim backdrop), fixed 240px left rail at 1024px and above.
- **Link style:** neutral-bg pill row with a transparent 3px left border by default; the active link fills solid with `{colors.signal-blue}`, switches text to white, and turns that left border to the text color — the only place a left-border accent is used in the whole system.
- Unread-count badges on nav links use the inverted (white-bg/coral-text) count-badge variant so they stay legible against the active blue fill.

### Chat Message Bubble (signature component)
- **Own messages:** right-aligned, `{colors.signal-blue}` background, white text, 12px radius, no border.
- **Others' messages:** left-aligned, `{colors.neutral-bg}` background, 1px border, 12px radius.
- **Deleted messages:** italic, `{colors.text-muted}` text, background stripped to transparent regardless of sender.
- **Inline mentions:** `@nickname` gets Mention Indigo bg + white text, bold, 4px radius; the reserved `@전체` mention-all instead uses Alert Coral, so a mention-everyone message is visually distinct from a targeted one.

### Scrollbars (signature interaction)
- Every scrollable area in the app (message list, room/people lists, modals, the sidebar, dropdowns) uses one themed, overlay-style scrollbar instead of the browser default — this is deliberate per the craft floor's rule that browser-default surfaces still carry the design.
- **At rest:** fully transparent — invisible, matching the flat/no-chrome character of the rest of the system.
- **While scrolling or hovering the region:** a thin (6px), fully pill-rounded (999px) thumb fades in at `{colors.text}` reduced to ~22% opacity (`--scrollbar-thumb`), strengthening to ~40% opacity on direct thumb-hover (`--scrollbar-thumb-strong`). No new hue — it's the existing Text color at low opacity, the same restraint as everywhere else in the palette.
- **Timing:** the thumb fades using the same 0.2s ease transition as every other state change in the system (see the Two-Weight-adjacent single-timing convention in Elevation). It reappears immediately on scroll and holds for ~900ms of inactivity before fading back out — modeled on KakaoTalk's chat-room scrollbar.
- Implemented via themed `::-webkit-scrollbar` pseudo-elements plus a small global scroll listener (`scrollbars.js`) that toggles an `.is-scrolling` class; Firefox gets the same colors through `scrollbar-color` without the fade (an accepted platform limitation, not a redesign).

### Confirm Modal (signature interaction)
- Every destructive/dangerous confirmation (delete a room, a message, a user account, an issue, a schedule entry, a log range; demote/promote an admin) goes through one shared themed modal (`#confirm-modal`, driven by `confirm-modal.js`'s `window.confirmDialog(message)`) instead of the browser's native `confirm()`.
- **Why:** native `confirm()`/`prompt()` were found to leave renderer input dead after the dialog closes in the Electron desktop build (it stays tray-resident and hides/shows its window rather than being destroyed, which appears to be what triggers it) — a themed in-page modal sidesteps the native dialog entirely.
- **Look:** identical to every other modal — `{colors.surface}` card, 1px border, no shadow, centered over the standard `rgba(0,0,0,0.45)` scrim. Title "확인", the message as body text, `.btn-ghost` "취소" + `.btn-danger` "확인" in `.modal-actions`.
- **Behavior:** resolves a Promise (`true`/`false`) so call sites read exactly like the native API did — `if (!(await confirmDialog(msg))) return;`. Backdrop click, Escape, and Enter all work (cancel / cancel / confirm respectively).
- Markup lives once in `base.html` (available on every page); don't add a second instance or a page-local variant.

### Calendar Cell (signature component)
- Day cells show small colored dots (Leave Orange / Work Teal) for entries on that day, plus a bar that visually spans from a range's start cell to its end cell (achieved with negative margins so adjacent-day bars touch with no gap).
- The "today" cell gets a `{colors.neutral-bg}` fill and bold date; a user-selected cell instead gets a `{colors.signal-blue}` border.
- **Sizing:** cells are a fixed `height: 42px` (not `min-height`), with `overflow: hidden` — this calendar always shares the rooms-dashboard row with 채팅방/1:1 대화, never a full page of its own, so it stays deliberately small rather than letting a 6-row month grid dominate the layout. Fixed rather than min matters here specifically: a day with several overlapping schedule bars must clip, not grow the cell (and therefore the whole week row, and therefore the whole dashboard) — schedule.js caps rendered bar tracks at `MAX_BAR_TRACKS = 2` for exactly this reason. Don't grow the cell back toward a standalone-calendar-app scale, and don't raise the track cap without re-checking it still fits in 42px.

## Do's and Don'ts

### Do:
- **Do** keep Signal Blue on exactly one control per screen (The One Accent Rule) — don't reach for it as a general "important button" color.
- **Do** draw every surface edge with the shared 1px neutral border, not a shadow.
- **Do** reserve box-shadow for floating/transient layers (pickers, dropdowns, the modal scrim) — never on a resting card, panel, or button.
- **Do** add any new color to both the light and dark theme blocks together; this system has no color that exists in only one mode.
- **Do** use the full pill radius (999px) for anything that represents a count, status, or tag, and 8–10px for containers/controls.
- **Do** theme scrollbars (and any other browser-default surface — focus rings, selection color) from the existing palette rather than leaving them unstyled or inventing a new color for them.

### Don't:
- **Don't** add hover or focus-visible styling to a button, panel, or list row and assume it matches an existing pattern — most of the system has none; only reaction pills, table rows, calendar cells, the mention-autocomplete list, and `.btn-primary` currently define hover feedback.
- **Don't** introduce a second brand/accent color for a new feature. The palette is deliberately one action color plus role-bound signal colors (danger, mention, and the two schedule categories) — a new feature should reuse one of these roles, not add a new hue.
- **Don't** give English marketing copy or decorative illustration a home here — every string in the product is Korean, and the tone is internal-tool plain, not promotional (see PRODUCT.md's Positioning and Evidence on Hand).
- **Don't** size a widget for the standalone page it used to be once it's embedded in the shared rooms dashboard (`.layout`'s `auto` schedule row sizes to content — a full-size calendar squeezed 채팅방/1:1 대화 down to almost nothing). Widgets sharing that grid should stay compact enough that every region stays usable.
- **Don't** use the native `confirm()`/`prompt()`/`alert()` for a new destructive action — use `window.confirmDialog(message)` (see Confirm Modal). The native dialogs are the known cause of dead renderer input in the desktop build.
