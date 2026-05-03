# Feeld — Platform Automation

**STATUS: DEFERRED — feasibility testing needed**

Feeld is primarily a mobile app. Desktop web access may be limited. This file will be populated after feasibility testing.

## Feasibility questions to answer

1. Does Feeld have a functional web interface?
2. Can Feeld be accessed via mobile emulation in Chrome?
3. What features are available in the web/mobile-web version vs. the native app?

## Platform-specific notes

- Feeld profiles have desire/interest fields and relationship structure indicators
- Core membership (free) vs. Majestic membership (paid) affect visible features
- "Ping" feature to boost visibility
- Group and event features for community connections
- Profile structure: desires, interests, photos, bio, relationship status, looking-for

## When ready to field-test

Follow the same process as `tinder.md`:
1. Navigate to Feeld URL
2. `capture_screenshot()` of each page state
3. `js()` to explore DOM structure
4. Document stable selectors
5. Test click targets
6. Record timing requirements
