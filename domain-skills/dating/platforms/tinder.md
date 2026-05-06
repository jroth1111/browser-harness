# Tinder — Platform Automation

## URLs

| Page | URL |
|---|---|
| Swiping | `https://tinder.com/app/recs` |
| Matches | `https://tinder.com/app/matches` |
| Chat list | `https://tinder.com/app/messages` |
| Individual chat | `https://tinder.com/app/messages/<match_id>` |
| Profile | `https://tinder.com/app/profile` |

## Auth detection

Logged-in indicators (to be confirmed via field testing):
- Profile cards visible on `/app/recs`
- Navigation bar with user avatar
- No redirect to login page

Not-logged-in indicators:
- Redirect to `tinder.com` landing/login page
- Login prompt or phone number entry form

## Profile card selectors

**STATUS: PARTIALLY CONFIRMED.** Card name/age + photo carousel confirmed. Bio, prompts, job, education, distance, lifestyle tags need field testing after expanding the profile card.

Tinder uses Yahoo-style obfuscated CSS classes (`Px(16px)`, `Bdrs(100px)`, `Ta(e)`, `Typs(subheading-1)`) that change across deployments. Use a11y-tree selectors (`role`, `aria-label`, `data-testid`) and keyboard shortcuts as primary; fall back to obfuscated classes only when a11y is unavailable; never rely on absolute XPaths.

### Confirmed (field-tested in this project)

```
card_container:  region "Card stack"
name_age:        button "{name} {age} Open profile"
photos_carousel: region "{name}'s photos"
photo_tabs:      tab "Photo {N}"
photo_nav_prev:  button "Previous Photo"
photo_nav_next:  button "Next photo"
like_button:     button "LIKE"
nope_button:     button "NOPE"
super_like:      button "SUPER LIKE"
```

### Selector stability ranking

| Approach | Stability | Notes |
|---|---|---|
| Keyboard shortcuts (Arrow keys, SPACE, Enter) | HIGH | Tinder maps these for power users |
| `aria-label`, `role`, `data-testid` from a11y tree | HIGH | Stable across builds |
| Yahoo-style classes (`Px(16px)`, `Ta(e)`, `Bdrs(100px)`) | LOW | Obfuscated, change across builds — fallback only |
| Absolute XPaths (`/div[1]/div[2]/...`) | VERY LOW | Break on any DOM restructuring — never use |
| Full class-string matches (`span[class='keen-slider__slide Wc($transform) Fxg(1)']`) | VERY LOW | Brittle — never use |

### When primary selectors fail

If a11y-tree selectors miss after a Tinder update:
1. `capture_screenshot()` and confirm DOM still renders the expected layout.
2. Re-derive selectors via `js()` exploration and update this file + `surface-map.json`.
3. Fall back to screenshot + click-by-coordinates while selectors are repaired.
4. If the page structure has changed materially, stop the session and notify the user.

## Swipe mechanics

**STATUS: CONFIRMED.**

### Keyboard shortcuts (primary — most stable)

```
Like:         Right arrow
Nope:         Left arrow
Open profile: Up arrow
Super Like:   Enter (or drag card up by 200px)
Cycle photos: SPACE (~0.4s pause between photos)
Dismiss:      Escape
```

Keyboard shortcuts beat button clicks for stability and look more human-like.

### Button selectors (fallback)

```
like_button:     button "LIKE"
nope_button:     button "NOPE"
super_like:      button "SUPER LIKE"
rewind_button:   button "REWIND" (paid feature)
```

### Post-swipe handling

- After each swipe, press Escape to clear any overlay.
- Watch for "It's a Match!" modal — handle separately (see Match notification).
- Watch for "out of likes" / "no more matches" state — stop and notify the user.

## Match notification

**STATUS: NEEDS FIELD TESTING.** "It's a Match!" overlay does NOT auto-close — requires explicit dismissal. After dismiss, the next profile card loads automatically.

```
match_overlay:    TO_BE_FIELD_TESTED — "It's a Match!" modal
dismiss_button:   TO_BE_FIELD_TESTED
popup_container:  #modal-manager descendant
```

Common popup chain after login/navigation (dismiss each with Escape, in order):
1. Cookie consent
2. Location permission
3. Notification permission
4. "It's a Match!" modal
5. Add-to-homescreen prompt
6. Tinder Gold/Plus upgrade nag
7. Rate-limit / "out of likes" modals

If a popup is not in this list and Escape does not dismiss it, stop the session and screenshot for diagnosis (per `safety.md`).

## Chat list extraction

**STATUS: CONFIRMED.** Navigate to `https://tinder.com/app/messages`. Extract conversation entries from the sidebar.

```
sidebar_link:  "nav a[href*='/app/messages/']"
chat_name:     link.textContent.trim()
match_id:      url.split('/app/messages/')[1]
```

Filter out non-chat sidebar links: `likes-you`, `my-likes`.

Sidebar is a virtualized list. To load more, scroll the sidebar container via JS (`el.scrollTop = el.scrollHeight`) and compare `scrollHeight` before/after with 2–4s waits. Saturation at 3 consecutive scrolls with 0 new entries.

For the full extraction protocol with checkpointing, see `chat-audit.md`.

## Conversation extraction

**STATUS: CONFIRMED.** Navigate to an individual chat and extract messages from the DOM.

```
conversation_log:  "[role='log']"
message_article:   "[role='log'] [role='article']"
sender:            "strong.Hidden"   → textContent minus ":"
sender_fallback:   class contains "Ta(e)" → user-sent; "Ta(start)" → received (Yahoo-style, less stable)
message_text:      "span.text"       → fallback: "span[class*='text']" → "div.msg > span"
timestamp:         "time"            → textContent + datetime attribute
is_user_sent:      sender === "You"  → fallback: class contains "Ta(e)"
```

Selector priority: a11y attributes (`role`, `strong.Hidden`) over Yahoo-style CSS classes which churn across builds.

Scroll up within `[role='log']` (`log.scrollTop = 0`) to load older messages. Wait 2–4s between scrolls. Saturation at 3 consecutive scrolls with 0 new messages.

Track processed `match_id`s across iterations to avoid re-extracting conversations.

## Message input

**STATUS: CONFIRMED.**

```
message_input: textbox "Type a message ..."   (multiline)
send_button:   button "SEND"                  (disabled when input empty)
```

Approach: `type_text(message)` into the input field, then dispatch Enter or click the send button. Wait ~1.5s after sending to let the message land before further actions.

## Gotchas

- Tinder aggressively detects bots. Keep human-like timing. See `safety.md`.
- Do not call Tinder private APIs or `api.gotinder.com`.
- Do not read `localStorage`, cookies, or browser storage for auth tokens.
- Full chat extraction is allowed through slow UI-only crawl with checkpointing (see `chat-audit.md`).
- Live conversation review (`reply.md` / `escalate.md`) is user-selected and UI-only. No hard cap — pacing rules in `safety.md` self-limit throughput. Full chat extraction (see `chat-audit.md`) is also uncapped.
- Rate limits: free accounts may see soft locks around 100 swipes. If an "out of likes" or rate limit prompt appears, stop and notify the user.
- A/B tests may change DOM structure between sessions. Verify selectors each session.
- Profile content may be lazy-loaded. Scroll or expand before extraction.
- Some profiles show limited info until matched.
- "Out of likes" state: detect and stop immediately.
- Yahoo-style CSS classes (`Px(16px)`, `Bdrs(100px)`, `Ta(e)`) are obfuscated and change across builds. Never rely on them as primary selectors.
- Absolute XPaths break on any DOM restructuring. Prefer a11y tree roles and keyboard shortcuts.
- TinderBotz needed to handle 7+ popup types in sequence after login — plan for popup fatigue.
- The `keen-slider` library handles the photo carousel. SPACE key cycles photos (davidteather approach).
- Image URLs are extracted from `background-image` CSS property, not `<img>` tags.
- Chat messages use `div[role=log]` as container (confirmed by both our testing and the Copy Conversation Gist).
- Match IDs are embedded in `/app/messages/<id>` URL paths.
- Some match list entries use `likes-you` or `my-likes` in href — filter these out when collecting chat IDs.

## Anti-detection notes

We connect via CDP to the user's real Chrome — no Selenium/webdriver fingerprint. Our anti-detection effort is therefore behavioral, not technical:

1. Vary inter-swipe timing per `safety.md` (1.5–5s uniform random; never fixed).
2. Occasionally scroll through the full profile (3–8s) before swiping.
3. Occasionally navigate away from the swipe stack (matches → back) to break patterns.
4. Take breaks per the pacing schedule in `safety.md`.
5. Never send identical messages to multiple matches.
6. Mix in occasional PASSes even on high-score profiles to avoid all-LIKE patterns.
7. Use keyboard shortcuts (more human-like than button clicks).

## Login and session persistence

We connect to the user's already-open Chrome via CDP. The user logs in manually. We never handle credentials. Session persistence comes from the user's Chrome profile.

Login detection: URL contains `tinder.com/app/` and the navigation/sidebar tabs are visible. Otherwise treat as not-logged-in and ask the user to log in manually.

## GDPR data export structure

**STATUS: CONFIRMED** (from Boe-Ventures/swipestats.io parser)

Tinder's GDPR data export is a JSON file with this structure:
```
{
  "User": {
    "birth_date": "date string",
    "create_date": "date string",
    "gender": "M|F|Other|More|Unknown",
    "age_filter_min": number,
    "age_filter_max": number,
    "bio": "string",
    "city": { "name": "", "region": "" },
    "education": "string",
    "jobs": [{ "company": { "name": "" }, "title": { "name": "" } }],
    "schools": [{ "name": "", "displayed": bool }],
    "interests": [{ "name": "" }],
    "descriptors": [{ "name": "category", "choices": ["values"], "visibility": "public" }],
    "sexual_orientations": ["strings"],
    "pos": { "lat": number, "lon": number },
    "instagram": { "username": "", "photos": [] },
    "spotify": { "spotify_connected": bool, "spotify_top_artists": [] },
    "email": "string",
    "full_name": "string",
    "phone_id": "string"
  },
  "Usage": {
    "app_opens": { "date": count },
    "swipes_likes": { "date": count },
    "swipes_passes": { "date": count },
    "matches": { "date": count },
    "messages_sent": { "date": count },
    "messages_received": { "date": count }
  },
  "Messages": [
    {
      "match_id": "string",
      "messages": [
        {
          "to": number,
          "from": "You" | "them",
          "message": "string (HTML entities present)",
          "sent_date": "RFC date string",
          "type": "gif|gesture|activity|contact_card|swipe_note|undefined"
        }
      ]
    }
  ],
  "Photos": ["url strings"] | [{ "id": "", "url": "", "created_at": "", "selfie_verified": bool }],
  "Purchases": { "subscription": [], "consumable": [] },
  "Spotify": {},
  "Campaigns": {},
  "Experiences": {}
}
```

Note: 2025+ exports use a new photo format with `TinderPhoto[]` objects instead of `string[]` URLs. The swipestats parser handles both formats.

Descriptor categories include: Smoking, Drinking, Workout, Zodiac, Height, Personality Type, Education, Languages, Looking for, Relationship Type, Pets, etc.

This data is useful for the user model but must be provided by the user — we do not request GDPR exports programmatically.

## Out of scope

The following Tinder surfaces are deliberately not automated by this skill:

- **Profile / bio editing** (`tinder.com/app/profile`). Onboarding generates polarising profile copy (filter line, green flags, not-for line) as guidance — the user pastes it manually. Reasons: bot-detection risk is materially higher than swipe/message automation since profile edits are a rare user behaviour; atomicity risk is real (a crash mid-edit could leave the live profile partially overwritten); Tinder's prompt UI mixes free text, multiple-choice questions, and dropdown/slider controls with no documented selectors; bios get edited rarely enough that the automation cost does not amortise; and "what goes on a public profile" is a deliberate identity decision where human-in-the-loop is the right consent posture.
- **Account settings, subscription / billing, photo upload, identity verification.** All require manual user action.

If a future session reconsiders profile-edit automation, start by field-testing one live edit through the UI to determine save behaviour (autosave vs explicit save), prompt-selection mechanics, and character limits before adding any selectors to `surface-map.json`.
