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

**STATUS: NEEDS FIELD TESTING**

Use `capture_screenshot()` + `js()` to discover selectors. Look for:
- Name element
- Age element
- Bio/description text
- Prompt/Passion items
- Job title
- Education
- Distance/location
- Photo indicators (count, current index)

Record stable selectors here after field testing. Prefer `data-*`, `aria-*`, `role` attributes over class names (classes change frequently in SPA frameworks).

```
# Field-test template — fill in during first live session
name_selector: ""
age_selector: ""
bio_selector: ""
prompts_selector: ""
job_selector: ""
education_selector: ""
distance_selector: ""
```

## Swipe mechanics

**STATUS: NEEDS FIELD TESTING**

- Like button: locate via `capture_screenshot()` → `click_at_xy(x, y)`
- Nope button: locate via screenshot → `click_at_xy(x, y)`
- Super Like button: locate via screenshot → `click_at_xy(x, y)`
- Keyboard shortcuts: test if arrow keys work (Left=Nope, Right=Like)

After field testing, record approximate button coordinates or stable selectors:
```
like_button: ""
nope_button: ""
super_like_button: ""
rewind_button: ""
```

## Match notification

**STATUS: NEEDS FIELD TESTING**

"It's a Match!" overlay detection:
- Visual indicator: screenshot shows match modal
- DOM indicator: look for match overlay element
- Auto-dismiss behavior: does the overlay auto-close?

```
match_overlay_selector: ""
dismiss_button: ""
```

## Chat list extraction

**STATUS: NEEDS FIELD TESTING**

Navigate to `https://tinder.com/app/messages`. Extract:
- Match name
- Unread indicator
- Last message preview
- Timestamp

```
chat_list_container: ""
chat_item: ""
chat_name: ""
unread_indicator: ""
last_message_preview: ""
```

## Conversation extraction

**STATUS: NEEDS FIELD TESTING**

Navigate to individual chat. Extract:
- Message bubbles (sender identification)
- Message text
- Timestamps
- Media indicators

```
message_container: ""
message_bubble: ""
sent_message_selector: ""
received_message_selector: ""
message_text: ""
timestamp: ""
```

## Message input

**STATUS: NEEDS FIELD TESTING**

```
message_input: ""
send_button: ""
```

Approach: `type_text(message)` into input field, then `dispatch_key("Enter")` or `click_at_xy` on send button.

## Gotchas

- Tinder aggressively detects bots. Keep human-like timing. See `safety.md`.
- Rate limits: approximately 100 swipes before soft lock (free accounts). Stop well before this.
- A/B tests may change DOM structure between sessions. Verify selectors each session.
- Profile content may be lazy-loaded. Scroll or expand before extraction.
- Some profiles show limited info until matched.
- "Out of likes" state: detect and stop immediately.

## Anti-detection notes

- Vary inter-swipe timing (1.5-5 seconds, randomized)
- Occasionally scroll through full profile before swiping
- Occasionally navigate away from swipe stack and back
- Don't run for extended periods without breaks
- Never send identical messages to multiple matches
