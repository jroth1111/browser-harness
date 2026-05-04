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

**STATUS: PARTIALLY CONFIRMED** (TinderBotz, davidteather/tinder-bot, shashank-100/tinder-cli, Copy Conversation Gist)

Tinder uses Yahoo-style obfuscated CSS classes (`Px(16px)`, `Bdrs(100px)`, `Ta(e)`, `Typs(subheading-1)`) that change across deployments. Prefer `data-*`, `aria-*`, `role` attributes and keyboard shortcuts over CSS-class or XPath selectors.

### Confirmed from field testing (our project)
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

### Selectors from open-source projects (cross-reference)

TinderBotz (Selenium + undetected-chromedriver, most complete):
```
name:           XPath {content}/div/div[1]/div/main/div[1]/div/div/div[1]/div[1]/div/div[2]/div[1]/div/div[1]/div/h1
age:            XPath {content}/div/div[1]/div/main/div[1]/div/div/div[1]/div[1]/div/div[2]/div[1]/div/div[1]/span
verified:       XPath ...div[1]/div[2] existence check
bio:            CSS div[class*="Px(16px) Py(12px) Us(t)"]
looking_for:    CSS div[class="Px(16px) My(12px)"]>div[class="D(b)"] div[class="Typs(subheading-1) CenterAlign"]
passions:       CSS div[class='Px(16px) Py(12px)'] h2 + div[class^='Bdrs(100px)'] items
row_data:       XPath //div[@class="Row"] with SVG d-attribute path matching
images:         XPath //div[@aria-label='Profile slider'] → value_of_css_property('background-image').split('"')[1]
profile_open:   ActionChains.send_keys(Keys.ARROW_UP)
like:           ActionChains.send_keys(Keys.ARROW_RIGHT)
dislike:        ActionChains.send_keys(Keys.ARROW_LEFT)
superlike:      ActionChains.drag_and_drop_by_offset(card, 0, -200)
```

davidteather/tinder-bot (Selenium + selenium-stealth):
```
card:           XPath //span[@class='keen-slider__slide Wc($transform) Fxg(1)']/div
name:           card.get_attribute("aria-label")
bio:            XPath //div[@aria-hidden='false' and @class='Toa(n) Wc($transform)...']/div[@tabindex='0']/div[@class='Tsh($tsh-s)...']/div/div/div[@class='BreakWord Whs(pl)...']
images:         XPath //div[@class='Expand Pos(a) D(f) Ov(h) Us(n) keen-slider']/span/div[@aria-label='{name}'] → outerHTML.split("url(&quot;")[1]
school:         XPath //div[@aria-hidden='false']...div[@itemprop='affiliation']
like_button:    XPath //div[@class='Pos(r) Py(16px)...']/div/button[2]
dislike_button: XPath //div[@class='Pos(r) Py(16px)...']/div/button[1]
image_cycle:    body.send_keys(Keys.SPACE) with 0.4s pause
```

shashank-100/tinder-cli (Chrome remote debugging + agent-browser CLI):
```
profile_text:   snapshot matching button "([^"]+Open profile[^"]*)" [ref
like:           snapshot → button "LIKE" [ref=e\d+] → click @ref
nope:           snapshot → button "NOPE" [ref=e\d+] → click @ref
photos_region:  region "[^"]*photos[^"]*" [ref=e\d+]
photo_tabs:     tab "Photo \d+" [ref=e\d+] — click each, get html, regex https://images.*gotinder.*
```

Youngermaster/Tinder-Automatic-Swiper (Chrome extension, content.js):
```
like_button:    document.getElementsByClassName("button Lts($ls-s) Z(0) CenterAlign...Bgi($g-ds-background-like):a")[0]
dislike_button: document.getElementsByClassName("button Lts($ls-s) Z(0) CenterAlign...Bgi($g-ds-background-nope):a")[0]
```

liplylie/tinder-web-scraper (raw Selenium, minimal):
```
dismiss_popup:  XPath //*[@id="modal-manager"]/div/div/div[2]/div[1]/div/div[3]/button[1]
login_btn:      XPath //*[@id="content"]/div/span/div/div[2]/div/div[1]/div[1]/div/button
like_button:    XPath //*[@id="content"]/div/span/div/div[1]/div/main/div/div/div/div[1]/div[2]/button[4]
dislike_button: XPath //*[@id="content"]/div/span/div/div[1]/div/main/div/div/div/div[1]/div[2]/button[2]
dismiss_after:  driver.actions().sendKeys(webdriver.Key.ESCAPE).perform()
```

### Selector stability assessment

| Approach | Stability | Reason |
|---|---|---|
| Keyboard shortcuts (Arrow keys) | HIGH | Tinder uses these for accessibility; unlikely to change |
| `aria-label`, `role`, `data-testid` | HIGH | Accessibility attributes are stable |
| `button "LIKE"` / `button "NOPE"` from a11y tree | HIGH | Screen reader labels, stable |
| `region "Card stack"`, `region "{name}'s photos"` | HIGH | ARIA roles for accessibility |
| `div[class*="Px(16px)"]` Yahoo-style CSS classes | LOW | Obfuscated, change across builds |
| Absolute XPaths like `/div[1]/div[2]/div[3]/...` | VERY LOW | Break on any DOM restructuring |
| `//span[@class='keen-slider__slide Wc($transform) Fxg(1)']` | VERY LOW | Full class string match, brittle |

### Recommended approach for our project

Use a11y tree selectors (button/region/tab roles) + keyboard shortcuts, which aligns with our existing confirmed selectors. Fall back to screenshot + OCR if a11y tree is stale after a Tinder update.

## Swipe mechanics

**STATUS: CONFIRMED** (multiple projects + our field testing)

### Keyboard shortcuts (preferred — most stable)
```
Like:        Right arrow (ARROW_RIGHT)
Nope:        Left arrow (ARROW_LEFT)
Open profile: Up arrow (ARROW_UP)
Super Like:  Enter key (or drag up by 200px)
Dismiss:     Escape key
```
TinderBotz confirms keyboard shortcuts are more reliable than button clicks. Arrow keys work because Tinder maps them for power users. This is the recommended approach.

### Button selectors
```
like_button:     button "LIKE"
nope_button:     button "NOPE"
super_like:      button "SUPER LIKE"
rewind_button:   button "REWIND" (paid feature)
```
These come from the a11y tree (confirmed in our field testing and by shashank-100/tinder-cli).

### CSS class selectors (from Chrome extension — less stable)
```
like_button:    class contains "Bgi($g-ds-background-like):a"
dislike_button: class contains "Bgi($g-ds-background-nope):a"
```

### ActionChains approach (TinderBotz)
```python
like:    ActionChains.send_keys(Keys.ARROW_RIGHT)
dislike: ActionChains.send_keys(Keys.ARROW_LEFT)
super:   ActionChains.drag_and_drop_by_offset(card, 0, -200)
```

### Post-swipe handling
- After each swipe, check for "no more matches" state: `div[class*='Pos(a) B(20px) Ta(c) C($c-secondary)']` containing "unable to find any potential matches"
- On "no more matches": refresh page, re-dismiss popups
- Press Escape after each swipe to dismiss any overlay (liplylie approach)
- Handle "It's a Match!" modal separately

## Match notification

**STATUS: PARTIALLY CONFIRMED** (from TinderBotz popup handling)

"It's a Match!" overlay detection:
- TinderBotz handles this as one of many popup types in sequence
- The session dismisses popups by clicking dismiss/close buttons in modal-manager
- The overlay does NOT auto-close — requires explicit dismissal
- After dismissing, the next profile card loads automatically

TinderBotz popup handler sequence (7+ popup types handled in order):
1. Cookie consent (`//button` with "accept" text)
2. Location permission (`//button[@data-testid="allow"]`)
3. Notification permission (`//button[@data-testid="decline"]`)
4. "It's a Match!" modal
5. Add to homescreen prompt
6. Tinder Gold/Plus upgrade prompt
7. Various rate-limit or out-of-likes modals

```
match_overlay:    TO_BE_FIELD_TESTED — "It's a Match!" modal
dismiss_button:   TO_BE_FIELD_TESTED
popup_container:  //*[@id="modal-manager"]/div/div
```

## Chat list extraction

**STATUS: CONFIRMED** (our field testing + TinderBotz match_helper.py)

Navigate to `https://tinder.com/app/messages`. Extract conversation entries from the sidebar.

### Confirmed selectors (our project)
```
sidebar_link:  "nav a[href*='/app/messages/']"
chat_name:     link.textContent.trim()
match_id:      url.split('/app/messages/')[1]
```

### TinderBotz match_helper approach (cross-reference)
```
tab_switching:    //button[@role="tab"] matching text "Matches" or "Messages"
new_match_ids:    //div[@role="tabpanel"] → .//div/div/a → extract href, split by "/" → filter out "likes-you"/"my-likes"
messaged_ids:     //div[@class="messageList"] → .//a → extract href
```

### Infinite scroll for sidebar
TinderBotz scrolls the tab panel via JS:
```javascript
arguments[0].scrollTop = arguments[0].scrollHeight
```
Then waits 4 seconds and compares scrollHeight. If unchanged, scroll is saturated.

Our approach (chat-audit.md): saturation at 3 consecutive scrolls with 0 new entries, 2-4s between scrolls.

### Scroll-to-bottom helper (TinderBotz)
Scrolls element to bottom repeatedly until scrollHeight stabilizes (0.5s pauses). Used for loading full match list before extraction.

## Conversation extraction

**STATUS: CONFIRMED** (our field testing + Copy Conversation Gist + TinderBotz)

Navigate to individual chat. Extract messages from DOM.

### Confirmed selectors (our project)
```
conversation_log:  "[role='log']"
message_article:   "[role='article']"
sender:            "strong.Hidden" → textContent minus ":"
message_text:      "span.text"
timestamp:         "time" → textContent + datetime attribute
is_sent:           sender === "You"
```

### Copy Conversation Gist selectors (JavaScript bookmarklet, imsys/d9b8e26c90c683b83eab2d20d4d26ca1)
```
chat_container:       .chat → :first-child + div > div
current_user_name:    span.Ell
other_person_name:    div.chatAvatar span.Hidden
message_container:    div[role=log] > div
sender_class_sent:    Ta(e)       → current user
sender_class_recv:    Ta(start)   → other person
timestamp:            time element → getAttribute('datetime')
message_content:      div.msg > span → textContent.trim()
```

The Gist formats each message as: `{sender} - {time} - {messageContent}`
Critical finding: `Ta(e)` class = sent by current user, `Ta(start)` = received from other person. These Yahoo-style classes may change.

### TinderBotz match_helper selectors
```
chat_opening:         navigates to /app/messages/{chatid}
message_input:        //textarea → send_keys(message) → Keys.ENTER
send_delay:           1.5 seconds after sending
tab_check:            checks both "Matches" and "Messages" tabs
js_click:             execute_script("arguments[0].click()") for reliable clicking
```

### Scroll-up for older messages
Scroll up within `[role='log']` to load older messages. Wait 2-4s per scroll. Saturation at 3 consecutive scrolls with 0 new messages.

### Chat ID deduplication (TinderBotz)
Tracks `used_chatids` across iterations to avoid re-processing conversations. Important for resumable extraction.

For full extraction protocol with checkpointing, see `chat-audit.md`.

## Message input

**STATUS: CONFIRMED** (our field testing + TinderBotz)

```
message_input: "Type a message ..." textbox
send_button:   "SEND" button
```

Approach: `type_text(message)` into input field, then dispatch Enter or click send button.

TinderBotz approach:
```
textarea:      //textarea → send_keys(message) → Keys.ENTER
send_delay:    1.5 seconds
```

shashank-100/tinder-cli approach:
```
message_input: (not implemented — this project only swipes, no messaging)
```

## Gotchas

- Tinder aggressively detects bots. Keep human-like timing. See `safety.md`.
- Do not call Tinder private APIs or `api.gotinder.com`.
- Do not read `localStorage`, cookies, or browser storage for auth tokens.
- Full chat extraction is allowed through slow UI-only crawl with checkpointing (see `chat-audit.md`).
- Live conversation review (during pipeline stages) is user-selected, UI-only, 3 default / 5 max per session. Full chat extraction (see `chat-audit.md`) has no hard cap.
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

### Timing (from open-source projects)

| Project | Inter-action delay | Distribution |
|---|---|---|
| TinderBotz | `random.uniform(0.5, 2.3) * initial_sleep` | Scaled uniform |
| davidteather/tinder-bot | `time.sleep(0.3)` fixed | Fixed (minimal) |
| shashank-100/tinder-cli | 3000ms between profiles, 400ms between photo tabs | Fixed |
| liplylie/tinder-web-scraper | No delay (1000 iterations immediate) | None |
| Youngermaster Chrome ext | User-configurable delay seconds | User-controlled |
| Our project | 1.5 + random * 3.5 seconds | Uniform random |

### Detection evasion techniques (from open-source projects)

**undetected-chromedriver** (TinderBotz):
- Patches chromedriver to avoid `navigator.webdriver` detection
- Chrome options: `--no-first-run`, `--no-service-autorun`, `--password-store=basic`, `--lang=en-GB`
- No headless mode (headless is more detectable)

**selenium-stealth** (davidteather/tinder-bot):
- Overrides `navigator.languages`, `navigator.vendor`, `navigator.platform`
- Sets WebGL vendor/renderer to common values
- Fixes hairline (subpixel rendering fingerprint)
- `excludeSwitches: ["enable-automation"]` removes automation indicators
- `useAutomationExtension: False`

**Chrome remote debugging** (shashank-100/tinder-cli):
- Launches real Chrome with `--remote-debugging-port=9222`
- Uses `agent-browser` CLI to connect to existing Chrome
- Most stealthy approach — uses a genuine Chrome browser session

**Chrome extension** (Youngermaster):
- Runs inside the page context as a content script
- No Selenium/webdriver footprint at all
- Limited to click-based interaction (no profile extraction)

**Like/dislike ratio mixing** (TinderBotz):
- Supports ratio-based swiping: e.g., `ratio="72.5%"` means 72.5% likes
- Randomly decides like vs dislike per profile based on ratio
- Avoids patterns of all-likes that trigger detection

### Recommended anti-detection for our project

1. Use Chrome DevTools Protocol (CDP) connection to real Chrome, not Selenium
2. Vary inter-swipe timing (1.5-5 seconds, uniform random)
3. Occasionally scroll through full profile before swiping
4. Occasionally navigate away from swipe stack and back
5. Don't run for extended periods without breaks
6. Never send identical messages to multiple matches
7. Mix in occasional passes even on high-score profiles
8. Our approach already avoids the webdriver fingerprint problem by connecting via CDP

## Login and session persistence

### Login flows (from open-source projects)

**TinderBotz** (most complete):
```
cookie_accept:   //button[@type="button"] with span containing "accept"
login_button:    XPath to "Log in" button
google_login:    //button[@aria-label="Log in with Google"] → popup → email → password
facebook_login:  //button[@aria-label="Log in with Facebook"] → popup → email → pass → loginbutton
sms_login:       //button[@aria-label="Log in with phone number"] → phone_number input
post_login:      //button[@data-testid="allow"] (location) → //button[@data-testid="decline"] (notifications)
popup_focus:     Retry up to 50 times with 0.3s sleep to find popup window
delay:           7 seconds (WebDriverWait timeout)
post_login_wait: 5 seconds sleep after login flow completion
```

**davidteather/tinder-bot**:
```
google_login:    Direct OAuth URL construction → email → password → navigate to tinder.com → login btn → google btn
sms_login:       phone_number input → verification code (manual entry) → email verification code (manual entry)
location_allow:  //button[@aria-label='Allow']
notif_deny:      //button[@aria-label='Not interested']
```

**liplylie/tinder-web-scraper**:
```
facebook_login:  Direct navigation to facebook.com → email → pass → login → navigate to tinder.com
popup_dismiss:   //*[@id="modal-manager"]/div/div/div[2]/div[1]/div/div[3]/button[1]
onboarding:      Clicks through onboarding steps via XPath chain
```

### Session persistence

**Chrome profile persistence** (TinderBotz):
```
--user-data-dir={path}  → Chrome profile directory persists cookies/sessions across launches
```
This is the primary session persistence mechanism. When using `--user-data-dir`, the Chrome profile retains login cookies so subsequent launches don't need re-login.

**Login detection** (TinderBotz):
```python
if "tinder.com/app/" in self.browser.current_url:
    # logged in
else:
    # need to login
```

**Geolocation spoofing** (TinderBotz + davidteather):
```python
browser.execute_cdp_cmd("Page.setGeolocationOverride", {
    "latitude": lat,
    "longitude": lon,
    "accuracy": 98
})
```

**Proxy support** (TinderBotz):
- IP-based: Chrome option `--proxy-server=ip:port`
- Auth-based: Chrome extension for user:pass@host:port proxy

### For our project

Our approach differs: we connect to the user's already-open Chrome via CDP. The user logs in manually. We never handle credentials. Session persistence comes from the user's Chrome profile.

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
