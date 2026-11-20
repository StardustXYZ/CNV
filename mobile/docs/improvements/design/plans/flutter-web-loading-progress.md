# Fix: A blank page while the web version loads

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/flutter-web-loading-progress
- **Needs new dependency**: none

## Why

The web version needs a few seconds to download the engine and the app. In that time `<body>` is empty (dark `#121212`) and the user sees nothing. A small progress bar in the app's violet shows that the app is coming.

## Where

```html
<!-- web/index.html:36-38 — current -->
<body style="background: #121212">
  <script src="flutter_bootstrap.js" async></script>
</body>
```

`web/` has no `flutter_bootstrap.js` of its own (Flutter generates one). The CI build is `flutter build web --release --base-href /CNV/ --pwa-strategy=none`.

## The fix

1. In `web/index.html`, inside `<head>` just before `</head>`, add the style (inline, so there is no extra file to cache):

```html
  <style>
    .progress-container {
      position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
      width: 120px; height: 8px; background: #2a2a2a; border-radius: 10px; overflow: hidden;
    }
    .progress-bar { height: 100%; width: 0; background: #bb86fc; transition: width 0.4s ease; }
  </style>
```

2. Replace the body:

```html
<body style="background: #121212">
  <div class="progress-container"><div class="progress-bar"></div></div>
  <script src="flutter_bootstrap.js" async></script>
</body>
```

3. Create `web/flutter_bootstrap.js` (Flutter uses it instead of the generated one):

```js
{{flutter_js}}
{{flutter_build_config}}

const bar = document.querySelector('.progress-bar');
const setProgress = (pct) => { if (bar) bar.style.width = pct + '%'; };

setProgress(20); // bootstrap running

_flutter.loader.load({
  onEntrypointLoaded: async function (engineInitializer) {
    setProgress(50); // main.dart.js downloaded
    const appRunner = await engineInitializer.initializeEngine();
    setProgress(80); // engine ready
    await appRunner.runApp();
  },
});
```

## Steps

1. Edit `web/index.html` as in points 1 and 2.
2. Create `web/flutter_bootstrap.js` as in point 3 (keep the two `{{...}}` lines exactly).

## Check it

- `flutter build web --release --base-href /CNV/ --pwa-strategy=none` ends with success.
- `grep -c "progress-bar" web/index.html` → 2 (the style and the div); `grep -c "initializeEngine" web/flutter_bootstrap.js` → 1.
- By eye: `flutter run -d chrome`, reload with throttled network (DevTools → Network → Slow 4G): a violet bar shows, then the app appears and the bar is gone.

## Don't touch

- `web/sw.js`, `manifest.json`, the icons, the existing meta tags and `<title>`. No Dart code.

## STOP if

- The build fails after adding `flutter_bootstrap.js`, or the app does not start in Chrome: delete the new file, restore `index.html` and report.
- A check fails twice.

## When you're done

Tell the developer the web version now shows a small violet bar while it loads instead of a blank page. Open it in Chrome on a slow connection to see it.
