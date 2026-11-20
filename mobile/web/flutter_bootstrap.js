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
