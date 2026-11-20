# Fix: The keyboard's action key doesn't move through the forms

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/text-input-action
- **Needs new dependency**: none

## Why

On the "Accedi con email" page the user types the email, then has to tap the password field, then tap the button. With the right action keys, "next" moves to the password and "done" submits.

## Where

```dart
// lib/pages/account_page.dart:~295-310 — current
              TextField(
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                autofillHints: const [AutofillHints.email],
                autocorrect: false,
                decoration: const InputDecoration(labelText: 'Email', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _password,
                obscureText: _hidden,
                autofillHints: [_register ? AutofillHints.newPassword : AutofillHints.password],
                onSubmitted: (_) => _submit(),
```

Single-field cases (the keyboard key should say what it does):

```dart
// lib/pages/in_sala_page.dart:~108 and lib/pages/in_uscita_page.dart:~83 — search fields "Cerca un titolo"
          TextField(
            controller: _search,
            onChanged: (_) => setState(() {}),
```

```dart
// lib/pages/account_page.dart:~413 — page "Ammessi" (field + button "Aggiungi")
                    child: TextField(
                      controller: _email,
                      keyboardType: TextInputType.emailAddress,
                      autocorrect: false,
                      onSubmitted: (_) => _add(),
```

## The fix

- Email field: `textInputAction: TextInputAction.next,` (add after `autocorrect: false,`).
- Password field: `textInputAction: TextInputAction.done,` (it already has `onSubmitted: (_) => _submit()`).
- The two search fields: `textInputAction: TextInputAction.search,`.
- "Ammessi" email field: `textInputAction: TextInputAction.done,` (it already submits with `_add()`).

## Steps

1. `lib/pages/account_page.dart`: add the three `textInputAction:` lines.
2. `lib/pages/in_sala_page.dart` and `lib/pages/in_uscita_page.dart`: add `textInputAction: TextInputAction.search,` to the search `TextField`.

## Check it

- `flutter analyze` clean; `flutter test` passes.
- `grep -c "textInputAction" lib/pages/account_page.dart` → 3; `in_sala_page.dart` → 1; `in_uscita_page.dart` → 1.
- By eye: "Accedi con email": the keyboard key on the email field says "next" and moves to the password; on the password it is "done" and submits.

## Don't touch

- `onSubmitted` handlers, the form logic. No new dependencies.

## STOP if

- The code in "Where" doesn't match, or a check fails twice.

## When you're done

Tell the developer the keyboard key now moves from email to password and submits on the last field, and shows a search key in the search fields. Open Voti → account → "Accedi con email".
