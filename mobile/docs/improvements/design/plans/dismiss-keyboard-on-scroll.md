# Fix: The keyboard stays open while scrolling

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/dismiss-keyboard-on-scroll
- **Needs new dependency**: none

## Why

After typing in a search or login field, scrolling the list leaves the keyboard covering half the screen. Scrolling means the user is done typing, so the keyboard should close.

## Where

Four scrollables contain a text field (no chat screens in the app, so all of them get the fix):

```dart
// lib/pages/in_sala_page.dart:~104 — current (search field "Cerca un titolo")
      child: ListView(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
```

```dart
// lib/pages/in_uscita_page.dart:~70 — current (search field)
      child: ListView(
```

```dart
// lib/pages/account_page.dart:~280 — current (email + password)
          body: ListView(
            padding: const EdgeInsets.all(16).copyWith(bottom: BottomPadding.of(context, minimum: 16)),
```

```dart
// lib/pages/account_page.dart:~403 — current (page "Ammessi", email field)
          body: ListView(
            padding: const EdgeInsets.all(16).copyWith(bottom: BottomPadding.of(context, minimum: 16)),
```

## The fix

Add this argument to each of the four `ListView(`s, as the first argument:

```dart
keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
```

## Steps

1. `lib/pages/in_sala_page.dart`: add the argument to the `ListView` at ~104.
2. `lib/pages/in_uscita_page.dart`: same for the `ListView` at ~70.
3. `lib/pages/account_page.dart`: same for the two `ListView`s (~280 and ~403).

## Check it

- `flutter analyze` clean; `flutter test` passes.
- `grep -c "keyboardDismissBehavior" lib/pages/in_sala_page.dart` → 1; `in_uscita_page.dart` → 1; `account_page.dart` → 2.
- By eye: in "In sala" tap the search field (keyboard opens), drag the list: the keyboard closes.

## Don't touch

- The search/filter logic, the other lists (no text field inside them). No new dependencies.

## STOP if

- The code in "Where" doesn't match, or a check fails twice.

## When you're done

Tell the developer that scrolling the list now closes the keyboard in the search fields and the login pages. Try it in "In sala".
