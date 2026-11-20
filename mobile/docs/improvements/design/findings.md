# Findings scelti

**1. Show what's new after an update**

After an update, users open the app and nothing tells them what's new. The bug you fixed and the feature they asked for go unnoticed. Show them as a list on first open after an update, and the user who reported that bug or asked for that feature knows you listened.

Link: https://flutterpro.design/details/md/in-app-changelog

---

**2. Don't let the system navigation bar cover the bottom of scrollable lists**

The last item of scrollable lists gets obscured by the system navigation bar. Leave space as tall as that bar at the end of the list so the last item has a breathing room against the bar.

Link: https://flutterpro.design/details/md/safe-area-replacement

---

**3. Make horizontal lists feel scrollable**

A horizontal scrollable list might not always signal that it's scrollable. Especially when the visible content just fits the view and no item is cut in half. Fading the edge hints users that there's more and they can scroll it.

Link: https://flutterpro.design/details/md/shader-mask

---

**4. Match text selection to your app's colors**

`MaterialApp` applies default tinted colors for text selection in inputs. Match them to your brand colors instead.

Link: https://flutterpro.design/details/md/selection-color

---

**5. Load network images smoothly**

Images in Flutter load with no transition, no placeholder and no failure state. They just pop in. Make it calmer: Show a plain grey box until each picture is ready and fade it in. If fails show a subtle broken image icon, never a technical message.

Link: https://flutterpro.design/details/md/smooth-image-loading

---

**6. Show loading progress while Flutter web boots**

Flutter web takes a few seconds to boot, and users stare at a blank white page wondering if the site is broken. Show a splash or progress bar instead, so they know the app is coming.

Link: https://flutterpro.design/details/md/flutter-web-loading-progress

---

**7. Add haptic feedback to key moments**

The app feels flat when taps and results happen in silence. A subtle haptic vibration on a tab switch, a successful submit or an error makes the app feel responsive in the hand.

Link: https://flutterpro.design/details/md/haptic-feedback

---

**8. Give Flutter web links a preview card**

Shared in WhatsApp, Slack or X, the app's link shows as a bare URL. It should show a proper preview card with a title, description and image.

Link: https://flutterpro.design/details/md/flutter-web-og-image

---

**9. Dismiss the keyboard when the user scrolls**

The user finishes typing and scrolls to see the rest, but the keyboard stays covering half the screen. Scrolling means they're done with the field, so close it for them.

Link: https://flutterpro.design/details/md/dismiss-keyboard-on-scroll

---

**10. Scroll to top when the current bottom nav item is tapped again**

Tapping the bottom nav bar item you're already on should scroll that page to the top. It's muscle memory for native app users, so they'll expect it from your apps too.

Link: https://flutterpro.design/details/md/bottom-nav-reselect

---

**11. Show the app version in settings**

When a user reports a bug, the first question is which version they're on, and the app has no place to answer it.

Link: https://flutterpro.design/details/md/show-app-version

---

**12. Don't use mobile page transitions on web and desktop**

Web and desktop are click and open. Mobile slide and zoom transitions between pages look cheap there, so pages should switch with no transition.

Link: https://flutterpro.design/details/md/web-page-transitions

---

**13. Scroll the tapped tab fully into view**

In a tab bar, when the user taps a tab that's only half visible, it should scroll fully into view.

Link: https://flutterpro.design/details/md/tab-visibility

---

**14. Show scrollbars on vertical scrollables**

A scrollbar shows the user where they are in the list and how much is left.

Link: https://flutterpro.design/details/md/scrollbars

---

**15. Format dates for user's locale**

`2016-06-24 14:44:00.000` is what `DateTime` prints, and no user should read a date like that. Show `24 July 2016, 14:44` instead, in the user's language.

Link: https://flutterpro.design/details/md/format-date-times

---

**16. Limit text scaling so layouts don't break**

Some users increase their device's text size for accessibility, and at high scales layouts overflow and break. After the fix, run the app at the capped scale yourself to confirm nothing breaks.

Link: https://flutterpro.design/details/md/text-scale-factor

---

**17. Let horizontal lists reach the screen edges**

When the page's scrollable has horizontal padding, horizontal lists inside get clipped at the edges instead of sliding past them. The list should reach the edges and carry its own padding.

Link: https://flutterpro.design/details/md/horizontal-list-padding

---

**18. Update the browser tab title per page**

The tab title shows in the browser tab, history and bookmarks, and when it's the same on every page, a user with several tabs open can't tell them apart. Each page should say what it is.

Link: https://flutterpro.design/details/md/browser-tab-title

---

**19. Show a friendly view when a widget breaks**

When a widget fails to build, users see an empty grey box in release. Show a friendly "Something went wrong" in the app's own colors instead.

Link: https://flutterpro.design/details/md/friendly-error-view

---

**20. Give every text field the right keyboard action**

Users should be able to fill a form and submit it with the keyboard's action key alone: it moves them to the next field, and on the last one, submits. No tapping each field by hand.

Link: https://flutterpro.design/details/md/text-input-action

---

**21. Make bottom sheets smooth and draggable**

Material's `showModalBottomSheet` opens and closes with a mechanical, soulless motion. Bottom sheets should respond to drags smoothly.

Link: https://flutterpro.design/details/md/smooth-draggable-bottom-sheets
