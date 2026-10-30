// CNV (Chi Ni Vidimu) – phone version.
// The data (films, shows, coming soon) is rebuilt every morning on GitHub and published
// as data.json; this file turns it into the same pages as the PC version. Votes and the
// Letterboxd export state are saved on the phone (localStorage).
"use strict";

const WEEKDAYS = ["dom", "lun", "mar", "mer", "gio", "ven", "sab"];
const MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];
const VOTES = ["V", "?", "X"];
const VOTE_TITLES = { "V": "Voglio vederlo", "?": "Non so", "X": "Non mi interessa" };
const VOTE_PRIORITY = { "V": 3, "?": 2, "X": 1 }; // two merged copies keep the most interested vote
const LATE_SHOW_CUTOFF = "06:00"; // shows listed before this hour run after midnight
const STALE_AFTER_HOURS = 30;
const POSTER_CACHE = "cnv-posters"; // same name as in sw.js

let DATA = null;
let FILMS = new Map();
let CINEMAS = new Map();
let votes = load("cnv.votes", {});        // film id -> "V" | "?" | "X"
let exported = load("cnv.exported", {});  // film id -> date the CSV was imported on Letterboxd
let shownPage = "";                       // HTML of the page on screen, for the minute refresh

// ------------------------------------------------------------------ helpers

function load(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode: not saved */ }
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pad = (n) => String(n).padStart(2, "0");
const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const hhmm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
function parseDate(iso) { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); }
function addDays(iso, n) { const d = parseDate(iso); d.setDate(d.getDate() + n); return isoDate(d); }
const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1);

/** The cinema day in progress: until 06:00 it is still the previous evening's programme. */
function programmeDay(now) {
    return hhmm(now) < LATE_SHOW_CUTOFF ? addDays(isoDate(now), -1) : isoDate(now);
}
/** Real start of a show listed under `day`: shows before 06:00 run after midnight. */
function showStart(day, time) {
    const [h, m] = time.split(":").map(Number);
    const d = parseDate(day);
    d.setHours(h, m, 0, 0);
    if (time < LATE_SHOW_CUTOFF) d.setDate(d.getDate() + 1);
    return d;
}
function formatDay(iso, today) {
    if (iso === today) return "oggi";
    if (iso === addDays(today, 1)) return "domani";
    const d = parseDate(iso);
    return `${WEEKDAYS[d.getDay()]} ${d.getDate()}/${d.getMonth() + 1}`;
}
function longDate(iso, today) {
    const d = parseDate(iso);
    const text = `${d.getDate()} ${MONTHS[d.getMonth()]}`;
    return d.getFullYear() === parseDate(today).getFullYear() ? text : `${text} ${d.getFullYear()}`;
}

// ------------------------------------------------------------------ derived data

/** Remaining shows of today and upcoming shows, grouped as the pages need them. */
function buildContext(now) {
    const day = programmeDay(now);
    const today = new Map();          // film -> cinema slug -> sala -> [{start, url}]
    const firstByCinema = new Map();  // film -> cinema slug -> first upcoming day
    const byCinemaDay = new Map();    // cinema slug -> day -> film -> sala -> [{start, url}]
    for (const s of DATA.shows) {
        if (s.d < day) continue;
        const start = showStart(s.d, s.t);
        if (s.d === day && start < now) continue; // already started
        const show = { start, url: s.u || (CINEMAS.get(s.c) || {}).url || "#" };
        if (s.d === day) push(nested(today, s.f, s.c), s.s, show);
        const firsts = nested(firstByCinema, s.f);
        if (!firsts.has(s.c) || s.d < firsts.get(s.c)) firsts.set(s.c, s.d);
        push(nested(byCinemaDay, s.c, s.d, s.f), s.s, show);
    }
    const announced = new Map();      // film -> cinema slug -> [dates]
    for (const c of DATA.coming) {
        const list = nested(announced, c.f).get(c.c) || [];
        if (c.d) list.push(c.d);
        nested(announced, c.f).set(c.c, list);
    }
    return { now, day, today, firstByCinema, byCinemaDay, announced };
}
function nested(map, ...keys) {
    let m = map;
    for (const k of keys) {
        if (!m.has(k)) m.set(k, new Map());
        m = m.get(k);
    }
    return m;
}
function push(map, key, value) {
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(value);
}
/** {sala: [shows]} -> [{sala, shows}] sorted by first show, without duplicate times. */
function salas(bySala) {
    return [...bySala.entries()]
        .map(([sala, shows]) => {
            const unique = new Map(shows.map((s) => [s.start.getTime(), s]));
            return { sala, shows: [...unique.values()].sort((a, b) => a.start - b.start) };
        })
        .sort((a, b) => a.shows[0].start - b.shows[0].start || a.sala.localeCompare(b.sala));
}
function cinemaReleases(film, ctx) {
    const shows = ctx.firstByCinema.get(film.id) || new Map();
    const list = [...shows.entries()].map(([slug, d]) => ({ slug, date: d, announced: false }));
    for (const [slug, dates] of ctx.announced.get(film.id) || new Map()) {
        if (!shows.has(slug)) list.push({ slug, date: dates.sort()[0] || null, announced: true });
    }
    return list.sort((a, b) => (a.date === null) - (b.date === null) || (a.date || "").localeCompare(b.date || "") || a.slug.localeCompare(b.slug));
}
const hasShows = (film, ctx) => (ctx.firstByCinema.get(film.id) || new Map()).size > 0;
const cinemaName = (slug) => (CINEMAS.get(slug) || { name: slug }).name;
const watched = (f) => f.status === "uscito" && ["V", "?"].includes(votes[f.id]);
/** Films that go in the next Letterboxd file: without TMDB they cannot be imported. */
const toExport = () => DATA.films.filter((f) => watched(f) && !exported[f.id] && f.tmdb);

// ------------------------------------------------------------------ pieces of page

function voteBox(film) {
    const buttons = VOTES.map((v, i) => {
        const active = votes[film.id] === v;
        return `<button data-vote="${esc(v)}" data-film="${film.id}" class="btn-vote vote-opt-${i + 1}${active ? " active" : ""}"
            title="${active ? "Togli il voto" : VOTE_TITLES[v]}">${esc(v)}</button>`;
    }).join("");
    return `<div class="vote-buttons" id="vote-${film.id}">${buttons}</div>`;
}
function salaShows(s) {
    const times = s.shows.map((show) =>
        `<a class="show-time" href="${esc(show.url)}" target="_blank" rel="noopener" title="Acquista sul sito del cinema">${hhmm(show.start)}</a>`
    ).join("");
    return `<span class="sala">${esc(s.sala || "Sala")}</span>${times}`;
}
function poster(film, cls) {
    return film.poster
        ? `<img src="${esc(film.poster)}" alt="" class="${cls}" loading="lazy">`
        : `<div class="${cls} placeholder">🎬</div>`;
}
function meta(film) {
    return `<div class="meta">
        ${film.year ? `<span>${film.year}</span>` : ""}
        ${film.event ? `<span class="tag">Evento</span>` : ""}
        ${film.tmdb ? `<a href="https://www.themoviedb.org/movie/${film.tmdb}" target="_blank" rel="noopener" class="ext-link">TMDB ↗</a>` : ""}
    </div>`;
}
function filmCard(film, ctx, mode) {
    let body = "";
    if (mode === "oggi") {
        const today = ctx.today.get(film.id);
        if (today && today.size) {
            const cinemas = [...today.entries()]
                .map(([slug, bySala]) => ({ slug, salas: salas(bySala) }))
                .sort((a, b) => a.salas[0].shows[0].start - b.salas[0].shows[0].start);
            body = `<div class="today"><p class="today-label">Oggi</p>${cinemas.map((c) => `
                <div class="today-cinema">
                    <p class="cinema"><a href="#/cinema/${esc(c.slug)}">${esc(cinemaName(c.slug))}</a></p>
                    ${c.salas.map((s) => `<p class="today-sala">${salaShows(s)}</p>`).join("")}
                </div>`).join("")}</div>`;
        } else {
            body = `<p class="small no-shows">Oggi non ci sono altri spettacoli.</p>`;
        }
        const elsewhere = cinemaReleases(film, ctx).filter((r) => r.announced);
        if (elsewhere.length) {
            body += `<p class="small">In arrivo anche: ${elsewhere.map((r) => esc(cinemaName(r.slug)) + (r.date ? ` (dal ${longDate(r.date, ctx.day)})` : "")).join(", ")}</p>`;
        }
    } else if (mode === "uscita") {
        const releases = cinemaReleases(film, ctx);
        const first = releases.find((r) => r.date)?.date;
        body = `<ul class="release-cinemas">${releases.map((r) => `<li>
            <a class="cinema" href="#/cinema/${esc(r.slug)}">${esc(cinemaName(r.slug))}</a>
            ${!r.date ? `<span class="small">data da definire</span>` : r.date !== first ? `<span class="small">dal ${longDate(r.date, ctx.day)}</span>` : ""}
        </li>`).join("")}</ul>`;
    }
    return `<article class="film-card">${poster(film, "poster")}
        <div class="film-info"><h3>${esc(film.title)}</h3>${meta(film)}${body}${voteBox(film)}</div>
    </article>`;
}

// ------------------------------------------------------------------ pages

function pageInSala(ctx, params) {
    const voto = params.get("voto");
    const filters = [[null, "Tutti"], ["nessuno", "Da votare"], ["V", "V"], ["?", "?"], ["X", "X"]];
    let films = DATA.films.filter((f) => f.status === "in_sala");
    if (voto === "nessuno") films = films.filter((f) => !votes[f.id]);
    else if (VOTES.includes(voto)) films = films.filter((f) => votes[f.id] === voto);
    const showing = films.filter((f) => hasShows(f, ctx))
        .sort((a, b) => !ctx.today.has(a.id) - !ctx.today.has(b.id) || a.title.localeCompare(b.title));
    const gone = films.filter((f) => !hasShows(f, ctx)).sort((a, b) => a.title.localeCompare(b.title));

    const chips = filters.map(([value, label]) =>
        `<a href="#/${value ? "?voto=" + encodeURIComponent(value) : ""}" class="chip${(voto || null) === value ? " active" : ""}">${label}</a>`).join("");
    let html = `<header class="page-header"><h1>Film in sala</h1><nav class="chips">${chips}</nav></header>`;
    html += showing.length
        ? `<div class="film-grid">${showing.map((f) => filmCard(f, ctx, "oggi")).join("")}</div>`
        : `<p class="empty-state">${voto ? "Nessun film in sala con questo filtro." : "Nessun film in programmazione."}</p>`;
    if (gone.length) {
        html += `<details class="gone-section" data-key="gone"><summary>Non più in programmazione <span class="count">${gone.length}</span>
            <span class="small">— spariti dai siti dei cinema, in attesa di essere segnati come usciti</span></summary>
            <ul class="gone-list">${gone.map((f) => {
                const days = f.event ? DATA.settings.days_to_uscito_evento : DATA.settings.days_to_uscito;
                const exit = f.last_seen ? addDays(f.last_seen, days) : null;
                return `<li><span class="gone-title">${esc(f.title)}</span>
                    <span class="small">${f.last_seen ? `visto l'ultima volta ${formatDay(f.last_seen, ctx.day)}` : ""}${exit ? ` · uscito dalle sale dal ${longDate(exit, ctx.day)} se non ricompare` : ""}</span>
                    ${voteBox(f)}</li>`;
            }).join("")}</ul></details>`;
    }
    return html;
}

function pageInUscita(ctx) {
    const cards = DATA.films
        .filter((f) => f.status === "in_uscita")
        .map((f) => ({ f, releases: cinemaReleases(f, ctx) }))
        .filter((c) => c.releases.length)
        .map((c) => ({ ...c, first: c.releases.find((r) => r.date)?.date || null }))
        .sort((a, b) => (a.first === null) - (b.first === null) || (a.first || "").localeCompare(b.first || "") || a.f.title.localeCompare(b.f.title));
    let html = `<header class="page-header"><h1>In uscita</h1>
        <p class="subtitle">Film annunciati dai cinema o con spettacoli solo futuri (prevendite e anteprime), con i cinema che li avranno.</p></header>`;
    if (!cards.length) return html + `<p class="empty-state">Nessun film in uscita al momento.</p>`;
    return html + `<div class="film-grid">${cards.map((c) => `<div class="release-group">
        <p class="release-date${c.first ? "" : " undated"}">${c.first ? `Dal ${longDate(c.first, ctx.day)}` : "Data da definire"}</p>
        ${filmCard(c.f, ctx, "uscita")}</div>`).join("")}</div>`;
}

function pageCinema(ctx, slug, params) {
    const cinema = CINEMAS.get(slug);
    if (!cinema) return `<p class="empty-state">Cinema non trovato.</p>`;
    const byDay = ctx.byCinemaDay.get(slug) || new Map();
    const days = [...byDay.keys()].sort();
    let selected = params.get("giorno");
    if (!byDay.has(selected)) selected = days[0] || null;

    let html = `<header class="page-header"><h1>${esc(cinema.name)}</h1>
        <a href="${esc(cinema.url)}" target="_blank" rel="noopener" class="btn">Sito del cinema ↗</a>
        <p class="subtitle">Tocca un orario per aprire la pagina d'acquisto sul sito del cinema.</p></header>`;
    if (!selected) {
        return html + `<p class="empty-state">Il sito del cinema non ha spettacoli in programma.<br>
            <a href="${esc(cinema.url)}" target="_blank" rel="noopener">Controlla sul sito del cinema ↗</a></p>`;
    }
    html += `<nav class="calendar">${days.map((d) =>
        `<a href="#/cinema/${esc(slug)}?giorno=${d}" class="day-chip${d === selected ? " active" : ""}">${d === ctx.day ? "Oggi" : capitalize(formatDay(d, ctx.day))}</a>`).join("")}</nav>`;
    const films = [...byDay.get(selected).entries()]
        .map(([id, bySala]) => ({ film: FILMS.get(id), salas: salas(bySala) }))
        .filter((x) => x.film)
        .sort((a, b) => Math.min(...a.salas.map((s) => s.shows[0].start)) - Math.min(...b.salas.map((s) => s.shows[0].start)));
    return html + `<div class="day-films">${films.map(({ film, salas: list }) => `<article class="day-film">
        ${poster(film, "thumb")}
        <div class="day-film-info"><h3>${esc(film.title)}</h3>${meta(film)}
            ${list.map((s) => `<p class="day-sala">${salaShows(s)}</p>`).join("")}
            ${voteBox(film)}</div></article>`).join("")}</div>`;
}

function pageWatchlist() {
    const watch = DATA.films.filter(watched);
    const ready = toExport();
    const missing = watch.filter((f) => !exported[f.id] && !f.tmdb);
    const done = watch.filter((f) => exported[f.id]).sort((a, b) => exported[b.id].localeCompare(exported[a.id]));
    let html = `<header class="page-header"><h1>Watchlist</h1>
        <p class="subtitle">Film usciti dalle sale che avevi segnato V o ?, da aggiungere alla watchlist di Letterboxd.</p></header>`;
    if (ready.length) {
        html += `<section class="export-box"><h2>Da esportare <span class="count">${ready.length}</span></h2>
            <ol class="steps"><li>Scarica il file CSV.</li><li>Importalo nella tua watchlist su Letterboxd (importazione da CSV).</li>
            <li>Torna qui e segna i film come esportati, così non finiscono nel prossimo file.</li></ol>
            <div class="export-actions">
                <button class="btn btn-export" data-action="export-csv">📥 Scarica CSV per Letterboxd</button>
                <button class="btn" data-action="mark-exported">✓ Li ho importati su Letterboxd</button>
            </div></section>
            <div class="film-grid">${ready.map((f) => filmCard(f, null, "")).join("")}</div>`;
    }
    if (missing.length) {
        html += `<section class="notice"><p><b>${missing.length} film senza abbinamento TMDB</b> non sono nel file:
            ${missing.map((f) => `<i>${esc(f.title)}</i>`).join(", ")}. Sistemali dalla versione di CNV sul PC.</p></section>`;
    }
    if (!ready.length && !missing.length) {
        html += `<p class="empty-state">Nessun film da esportare per ora.<br>Quando un film segnato <strong>V</strong> o <strong>?</strong> esce da tutte le sale, apparirà qui.</p>`;
    }
    if (done.length) {
        html += `<details class="gone-section" data-key="done"><summary>Già esportati <span class="count">${done.length}</span></summary>
            <ul class="gone-list">${done.map((f) => `<li><span class="gone-title">${esc(f.title)}${f.year ? ` (${f.year})` : ""}</span>
                <span class="small">esportato il ${formatDay(exported[f.id], isoDate(new Date()))}</span>
                <button class="btn" data-action="export-again" data-film="${f.id}">Esporta di nuovo</button></li>`).join("")}</ul></details>`;
    }
    return html;
}

function pageVoti() {
    const count = Object.keys(votes).length;
    return `<header class="page-header"><h1>I tuoi voti</h1>
        <p class="subtitle">I voti sono salvati solo su questo telefono. Fai ogni tanto una copia: se cambi telefono o cancelli i dati del browser, la ripristini da qui.</p></header>
        <p>Hai votato <b>${count}</b> film${Object.keys(exported).length ? ` e ne hai esportati <b>${Object.keys(exported).length}</b> su Letterboxd` : ""}.</p>
        <div class="backup-actions">
            <button class="btn btn-primary" data-action="export-votes">💾 Salva una copia dei voti</button>
            <label class="btn">📂 Ripristina da una copia<input type="file" accept="application/json,.json" data-action="import-votes"></label>
        </div>`;
}

// ------------------------------------------------------------------ navigation and rendering

function route() {
    const hash = location.hash.replace(/^#/, "") || "/";
    const [path, query] = hash.split("?");
    return { path, params: new URLSearchParams(query || "") };
}

/** Draw the page. ``periodic``: the minute refresh, which only redraws when something
 * changed (a show started), keeps open sections open and leaves the Voti page alone,
 * where a backup file may be being chosen. */
function render(periodic = false) {
    if (!DATA) return;
    const ctx = buildContext(new Date());
    const { path, params } = route();
    let page, active;
    if (path.startsWith("/cinema/")) {
        const slug = decodeURIComponent(path.slice("/cinema/".length));
        page = pageCinema(ctx, slug, params);
        active = "cinema:" + slug;
    } else if (path === "/uscita") { page = pageInUscita(ctx); active = "uscita"; }
    else if (path === "/watchlist") { page = pageWatchlist(); active = "watchlist"; }
    else if (path === "/voti") { page = pageVoti(); active = "voti"; }
    else { page = pageInSala(ctx, params); active = "sala"; }

    const app = document.getElementById("app");
    if (!periodic) {
        app.innerHTML = page;
    } else if (path !== "/voti" && page !== shownPage) {
        const open = [...app.querySelectorAll("details[data-key][open]")].map((d) => d.dataset.key);
        app.innerHTML = page;
        open.forEach((key) => app.querySelector(`details[data-key="${key}"]`)?.setAttribute("open", ""));
    }
    if (!periodic || path !== "/voti") shownPage = page;
    renderNav(ctx, active);
    renderMenu(ctx, active);
}

function renderNav(ctx, active) {
    const inSala = DATA.films.filter((f) => f.status === "in_sala" && hasShows(f, ctx)).length;
    const inUscita = DATA.films.filter((f) => f.status === "in_uscita" && cinemaReleases(f, ctx).length).length;
    const watch = toExport().length;
    const links = [["sala", "#/", "In sala", inSala], ["uscita", "#/uscita", "In uscita", inUscita],
        ["watchlist", "#/watchlist", "Watchlist", watch], ["voti", "#/voti", "Voti", 0]];
    document.getElementById("nav-links").innerHTML = links.map(([key, href, label, n]) =>
        `<a href="${href}" class="${active === key ? "active" : ""}">${label}${n ? ` <span class="count">${n}</span>` : ""}</a>`).join("");
}

function renderMenu(ctx, active) {
    document.getElementById("cinema-menu").innerHTML = DATA.cinemas.map((c) => {
        const day = (ctx.byCinemaDay.get(c.slug) || new Map()).get(ctx.day);
        const n = day ? day.size : 0;
        return `<li><a href="#/cinema/${esc(c.slug)}" class="${active === "cinema:" + c.slug ? "active" : ""}">
            <span>${esc(c.name)}</span>${n ? `<span class="count" title="Film ancora in programma oggi">${n}</span>` : ""}</a></li>`;
    }).join("");
}

function showUpdated(offline) {
    const when = new Date(DATA.generated_at);
    const hours = (Date.now() - when) / 36e5;
    const text = `Dati aggiornati il ${when.getDate()}/${when.getMonth() + 1} alle ${hhmm(when)}`;
    document.getElementById("updated").innerHTML = offline || hours > STALE_AFTER_HOURS
        ? `<span class="offline-note">${text}${offline ? " · senza connessione" : " · dati vecchi"}</span>`
        : text;
}

function download(name, type, content) {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function letterboxdCsv() {
    const quote = (s) => /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    const rows = toExport().map((f) => [f.tmdb, quote(f.title), f.year || ""].join(","));
    return ["tmdbID,Title,Year", ...rows].join("\n") + "\n";
}

// ------------------------------------------------------------------ events

document.addEventListener("click", (e) => {
    const menu = document.querySelector(".cinema-menu");
    if (menu && menu.open && (!menu.contains(e.target) || e.target.closest("a"))) menu.open = false;

    const vote = e.target.closest("[data-vote]");
    if (vote) {
        const id = Number(vote.dataset.film);
        if (votes[id] === vote.dataset.vote) delete votes[id]; else votes[id] = vote.dataset.vote;
        save("cnv.votes", votes);
        document.querySelectorAll(`#vote-${id}`).forEach((box) => { box.outerHTML = voteBox(FILMS.get(id)); });
        return;
    }
    const action = e.target.closest("[data-action]")?.dataset.action;
    const today = isoDate(new Date());
    if (action === "export-csv") download(`letterboxd_watchlist_${today}.csv`, "text/csv", letterboxdCsv());
    if (action === "mark-exported" && confirm("Hai importato il file su Letterboxd?")) {
        toExport().forEach((f) => { exported[f.id] = today; });
        save("cnv.exported", exported);
        render();
    }
    if (action === "export-again") {
        delete exported[Number(e.target.closest("[data-film]").dataset.film)];
        save("cnv.exported", exported);
        render();
    }
    if (action === "export-votes") {
        download(`cnv-voti-${today}.json`, "application/json", JSON.stringify({ votes, exported, saved_at: today }, null, 1));
    }
});

document.addEventListener("change", (e) => {
    if (e.target.dataset.action !== "import-votes" || !e.target.files.length) return;
    e.target.files[0].text().then((text) => {
        const backup = JSON.parse(text);
        if (!backup || typeof backup.votes !== "object") throw new Error("file non valido");
        if (!confirm(`Ripristinare ${Object.keys(backup.votes).length} voti? Quelli attuali verranno sostituiti.`)) return;
        votes = backup.votes;
        exported = backup.exported || {};
        save("cnv.votes", votes);
        save("cnv.exported", exported);
        render();
    }).catch((err) => alert(`Copia dei voti non valida (${err.message}).`));
});

window.addEventListener("hashchange", () => { render(); window.scrollTo(0, 0); });
setInterval(() => render(true), 60 * 1000); // started shows disappear while the app stays open

// ------------------------------------------------------------------ start

/** Votes given to a duplicate that the sync merged into another film move to that film. */
function applyMerges(merged) {
    let changed = false;
    for (const [old, target] of Object.entries(merged || {})) {
        if (votes[old]) {
            if ((VOTE_PRIORITY[votes[old]] || 0) > (VOTE_PRIORITY[votes[target]] || 0)) votes[target] = votes[old];
            delete votes[old];
            changed = true;
        }
        if (exported[old]) {
            if (!exported[target] || exported[old] > exported[target]) exported[target] = exported[old];
            delete exported[old];
            changed = true;
        }
    }
    if (changed) {
        save("cnv.votes", votes);
        save("cnv.exported", exported);
    }
}

/** Saved posters of films no page shows any more are removed from the phone. */
function prunePosters() {
    if (!("caches" in window)) return;
    const shown = new Set(toExport());
    const keep = new Set(DATA.films.filter((f) => f.status !== "uscito" || shown.has(f)).map((f) => f.poster));
    caches.open(POSTER_CACHE)
        .then((cache) => cache.keys().then((requests) =>
            Promise.all(requests.filter((r) => !keep.has(r.url)).map((r) => cache.delete(r)))))
        .catch(() => { /* nothing saved, nothing to remove */ });
}

function start(data, offline) {
    DATA = data;
    FILMS = new Map(data.films.map((f) => [f.id, f]));
    CINEMAS = new Map(data.cinemas.map((c) => [c.slug, c]));
    applyMerges(data.merged);
    render();
    showUpdated(offline);
    if (!offline) prunePosters();
}

fetch("data.json", { cache: "no-cache" })
    .then((resp) => {
        if (!resp.ok) throw new Error(resp.status);
        // sw.js marks the copy saved on the phone, served when the network does not answer
        const offline = resp.headers.get("X-CNV-Offline") === "1" || !navigator.onLine;
        return resp.json().then((data) => start(data, offline));
    })
    .catch(() => {
        document.getElementById("app").innerHTML =
            `<p class="empty-state">Non riesco a scaricare i dati. Controlla la connessione e riapri CNV.</p>`;
    });

if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(() => { /* works without, just not offline */ });
}
