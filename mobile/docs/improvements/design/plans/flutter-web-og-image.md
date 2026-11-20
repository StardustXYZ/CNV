# Fix: The web link shows as a bare URL when shared

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/flutter-web-og-image
- **Needs new dependency**: none

## Why

Shared in WhatsApp, Telegram or X, the link to CNV shows as a bare URL. With Open Graph tags it shows a card with title, description and image.

## Where

`web/index.html` has a `<title>` and a description, but no `og:` or `twitter:` tags (`grep -c "og:" web/index.html` → 0). The site is published at `https://stardustxyz.github.io/CNV/` (repo `StardustXYZ/CNV`, Pages path `/CNV/`).

```html
<!-- web/index.html:21-22 — current -->
  <meta name="description" content="Cinema di Cosenza e Rende: film in sala, in uscita e watchlist per Letterboxd">
  <meta name="theme-color" content="#1e1e1e">
```

## The fix

Add after the `theme-color` meta. The image must be an absolute URL. The app has no 1200×630 preview image yet, so use the 512px icon with the small card type (`summary`); when the developer adds `web/og-image.png` (1200×630), switch to `summary_large_image` and that file.

```html
  <!-- Link preview (WhatsApp, Telegram, X) -->
  <meta property="og:title" content="CNV – Chi Ni Vidimu">
  <meta property="og:description" content="Cinema di Cosenza e Rende: film in sala, in uscita e watchlist per Letterboxd">
  <meta property="og:image" content="https://stardustxyz.github.io/CNV/icons/Icon-512.png">
  <meta property="og:url" content="https://stardustxyz.github.io/CNV/">
  <meta property="og:type" content="website">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="CNV – Chi Ni Vidimu">
  <meta name="twitter:description" content="Cinema di Cosenza e Rende: film in sala, in uscita e watchlist per Letterboxd">
  <meta name="twitter:image" content="https://stardustxyz.github.io/CNV/icons/Icon-512.png">
```

## Steps

1. Add the block above to `web/index.html`, inside `<head>`, after the `theme-color` line.

## Check it

- `grep -c "og:image" web/index.html` → 1; `grep -c "twitter:image" web/index.html` → 1.
- `flutter build web --release --base-href /CNV/ --pwa-strategy=none` succeeds.
- The real preview can only be seen after publishing (paste the link in WhatsApp).

## Don't touch

- The other meta tags, the `<title>`, the icons. No Dart code.

## STOP if

- The Pages address is not `https://stardustxyz.github.io/CNV/` (check the repository settings) — report instead of guessing.
- A check fails twice.

## When you're done

Tell the developer that the link will show a card with the CNV name, description and icon once the site is published, and that a 1200×630 image would make it look better.
