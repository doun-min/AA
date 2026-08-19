# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: a QA/test team whose core daily workflow is the defect/issue board (TC-number tracking, reproduction steps). Secondary: the wider office staff, who rely on the chat rooms, shared leave/work calendar, and Excel/CSV conversion tool day to day. Both groups are the same small internal team working on one office LAN.

## Product Purpose

A self-hosted internal team hub that combines real-time chat, QA defect/issue tracking, a shared leave/work-schedule calendar, and Excel/CSV conversion into one tool, so the team doesn't need to stitch together separate SaaS products for these workflows.

## Positioning

Two things together make this irreplaceable by an off-the-shelf combo (e.g. Slack + Jira): it must run entirely inside the office LAN with no external SaaS dependency (self-signed HTTPS, internal IP, single Python process, one shared SQLite file), and it is shaped exactly to this team's existing process rather than a generic one — TC-number-based defect tracking with admin-configurable custom fields, Korean leave categories (연차/반차/업무일정), and an `@전체` mention-all reserved word. A neighboring product could copy one of those, not both.

## Operating Context

One office PC runs the server on the internal LAN (self-signed cert, internal IP, port 5000 by default); team members reach it via browser or a distributed Electron desktop client (`TeamChat.exe`) that adds tray icon and OS notifications on top of the same web pages. Login is nickname-only — no password or account system; a nickname is reserved while its session/socket is active. All data lives in one shared SQLite database. An admin role (auto-seeded once, then managed via a role column) handles user management, period-based log deletion with automatic backup, and issue-board configuration (subjects, custom fields).

## Capabilities and Constraints

- **Chat**: a default public "전체" global room plus user-created public/private group rooms, 1:1 DMs, @mentions including the reserved `@전체` mention-all, emoji reactions with a visible reactor list, per-room unread badges, own-message deletion, file/image upload (50MB cap, fixed extension allowlist), browser + desktop notifications, and per-room log download as `.txt`.
- **Schedule**: a shared team calendar for 연차 (annual leave), 반차 (half-day leave), and 업무일정 (work schedule), with a per-day list view and a banner surfaced in chat for today's entries.
- **Issue/defect board ("이슈 공유")**: per-subject defect entries with TC number, defect content, reproduction steps, and reporter, plus admin-defined custom fields; filterable by subject and reporter.
- **Excel tool**: in-browser CSV↔Excel conversion with multi-encoding CSV detection (utf-8-sig / utf-8 / cp949).
- **Admin capabilities**: promote/demote admins, delete user accounts, period-scoped log deletion that backs up removed content before deleting, and manage issue-board subjects/custom fields.
- **Constraints**: Korean-only UI; no password auth; intranet-only deployment is assumed throughout (the self-signed cert exists specifically so the Notification API's secure-context requirement is met on a private IP); a single initial admin nickname is seeded on first run and admin status is then managed manually.
- `auto_ask.py` and `excel_convert.py` at the repo root are standalone scripts unrelated to this app (the latter explicitly documents this) — not part of this product.

## Brand Commitments

"TeamChat" is the settled product name (used in the distributed desktop build, `TeamChat.exe`). No logo or visual identity has been established yet.

## Evidence on Hand

No marketing copy, testimonials, or public-facing assets exist — this is an internal tool with no external audience. All existing UI copy is Korean; do not introduce English marketing language or fabricate content the team hasn't provided.

## Product Principles

- Every feature must work fully offline on the office LAN; never assume internet or external API access.
- Follow this team's actual process (TC-based defects, Korean leave categories) over generic project-management conventions.
- Keep login friction at zero — nickname-only identity; don't reintroduce account/password concepts.
- Destructive admin actions (log purge, account deletion) stay paired with a backup or clear confirmation.
- Chat is the home base; schedule, the defect board, and Excel conversion are reachable from it, not separate products.
