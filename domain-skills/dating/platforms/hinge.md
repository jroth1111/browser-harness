# Hinge — Platform Automation

**STATUS: DEFERRED — feasibility testing needed**

Hinge is primarily a mobile app. Desktop web access is limited. This file will be populated after feasibility testing.

## Feasibility questions to answer

1. Does Hinge have a functional web interface at hinge.co or another URL?
2. Can Hinge be accessed via mobile emulation in Chrome?
3. What features are available in the web/mobile-web version vs. the native app?

## Platform-specific notes

- Hinge requires liking a specific photo or prompt (not the whole profile)
- "Standouts" feature surfaces highly compatible profiles (limited daily access)
- Rose mechanic: daily limited "super like" equivalent
- "We Met" feature provides post-date feedback
- Profile structure: photos with optional captions, 3 written prompts, basic info (age, location, height, job, education, smoking/drinking/kids)

## When ready to field-test

Follow the same process as `tinder.md`:
1. Navigate to Hinge URL
2. `capture_screenshot()` of each page state
3. `js()` to explore DOM structure
4. Document stable selectors
5. Test click targets
6. Record timing requirements
