// CNV (Chi Ni Vidimu) – phone version.
// The data (films, shows, coming soon) is rebuilt every morning on GitHub and published
// as data.json; this file turns it into the same pages as the PC version. Votes and the
// Letterboxd export state are saved on the phone (localStorage).
"use strict";

const WEEKDAYS = ["dom", "lun", "mar", "mer", "gio", "ven", "sab"];
const CALENDAR_DAYS = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"];
const MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];
const VOTES = ["V", "?", "S"]; // S: seen, shown as ✓
const VOTE_LABELS = { "V": "V", "?": "?", "S": "✓" };
const VOTE_TITLES = { "V": "Voglio vederlo", "?": "Indeciso", "S": "Visto" };
const VOTE_PRIORITY = { "S": 3, "V": 2, "?": 1 }; // two merged copies keep the most interested vote
const LATE_SHOW_CUTOFF = "06:00"; // shows listed before this hour run after midnight
const STALE_AFTER_HOURS = 30;
const POSTER_CACHE = "cnv-posters"; // same name as in sw.js
const DATA_CACHE = "cnv-data";       // same name as in sw.js: the votes are copied there for the notifications
// Public half of the key GitHub signs the notifications with (the private one is the VAPID_PRIVATE_KEY secret)
const PUSH_PUBLIC_KEY = "BPToHyyFGWKFimhXJ3M-oEXAhpb_JrrJiJHthg7mH6WS1yAVAHnAxtX9civmtjfUhBwpOy-yisb4B4GNrsTr5rA";

let DATA = null;
let FILMS = new Map();
let CINEMAS = new Map();
let votes = knownVotes(load("cnv.votes", {}));  // film id -> "V" | "?" | "S"
let exported = load("cnv.exported", {});  // film id -> date the CSV was imported on Letterboxd
let seen = load("cnv.seen", {});          // film id -> {date, cinema}: films marked ✓
let diary = load("cnv.diary", {});        // film id -> date the diary CSV was imported on Letterboxd
let askCinemaFor = null;                  // film just marked ✓: its box asks where it was seen
let pushState = { supported: false, code: null }; // notifications: code to copy into GitHub when active
let shownPage = "";                       // HTML of the page on screen, for the minute refresh
let swipeDirection = "";                  // "next" | "prev": slide-in of the page drawn after a swipe
let inSalaSeen = new Set();               // V films in sala whose notice was seen (see updateInSalaSeen)
const lastQuery = { "/": "", "/uscita": "" }; // filters of In sala and In uscita, kept when coming back

// ------------------------------------------------------------------ helpers

function load(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode: not saved */ }
    if (key === "cnv.votes") mirrorVotes(value);
}
/** A copy of the votes where the service worker can read them, to put the V films first in a notification. */
function mirrorVotes(value) {
    if (!("caches" in window)) return;
    caches.open(DATA_CACHE)
        .then((cache) => cache.put("votes.json", new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } })))
        .catch(() => { /* notifications just won't highlight the V films */ });
}
/** Only V and ?: the old X ("non mi interessa") is dropped and the film goes back to "da votare". */
function knownVotes(map) {
    return Object.fromEntries(Object.entries(map || {}).filter(([, v]) => VOTES.includes(v)));
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pad = (n) => String(n).padStart(2, "0");
const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const hhmm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
function parseDate(iso) { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); }
function addDays(iso, n) { const d = parseDate(iso); d.setDate(d.getDate() + n); return isoDate(d); }
const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1);
/** e.g. "1h 55m", "2h", "45m". */
function formatRuntime(minutes) {
    const h = Math.floor(minutes / 60), m = minutes % 60;
    return !h ? `${m}m` : m ? `${h}h ${pad(m)}m` : `${h}h`;
}
/** Estimated end of a show: start + runtime + ads and trailers (null without runtime). */
function showEnd(start, film) {
    if (!film || !film.runtime) return null;
    return new Date(start.getTime() + (film.runtime + (DATA.settings.show_extra_minutes ?? 10)) * 60000);
}

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

/** Shows not started yet, grouped as the pages need them (only one cinema's with ``cinema``). */
function buildContext(now, cinema = null) {
    const day = programmeDay(now);
    const upcoming = new Map();       // film -> day -> cinema slug -> sala -> [{start, url}]
    const firstByCinema = new Map();  // film -> cinema slug -> first upcoming day
    const byCinemaDay = new Map();    // cinema slug -> day -> film -> sala -> [{start, url}]
    for (const s of DATA.shows) {
        if (s.d < day || (cinema && s.c !== cinema)) continue;
        const start = showStart(s.d, s.t);
        if (s.d === day && start < now) continue; // already started
        const show = { start, end: showEnd(start, FILMS.get(s.f)), url: s.u || (CINEMAS.get(s.c) || {}).url || "#" };
        push(nested(upcoming, s.f, s.d, s.c), s.s, show);
        const firsts = nested(firstByCinema, s.f);
        if (!firsts.has(s.c) || s.d < firsts.get(s.c)) firsts.set(s.c, s.d);
        push(nested(byCinemaDay, s.c, s.d, s.f), s.s, show);
    }
    const announced = new Map();      // film -> cinema slug -> [dates]
    for (const c of DATA.coming) {
        if (cinema && c.c !== cinema) continue;
        const list = nested(announced, c.f).get(c.c) || [];
        if (c.d) list.push(c.d);
        nested(announced, c.f).set(c.c, list);
    }
    // Next shows of each film: the rest of today, or the next day with shows when today is over
    const next = new Map();           // film -> {day, cinemas: cinema slug -> sala -> [{start, url}]}
    for (const [film, byDay] of upcoming) {
        const first = [...byDay.keys()].sort()[0];
        next.set(film, { day: first, cinemas: byDay.get(first) });
    }
    return { now, day, next, firstByCinema, byCinemaDay, announced };
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
            title="${active ? "Togli il voto" : VOTE_TITLES[v]}">${VOTE_LABELS[v]}</button>`;
    }).join("");
    let extra = "";
    if (votes[film.id] === "S" && askCinemaFor === film.id) {
        extra = `<div class="seen-ask"><span class="small">Dove l'hai visto?</span>
            ${seenCinemaChoices(film).map((c) => `<button class="chip" data-seen-cinema="${esc(c.slug)}" data-film="${film.id}">${esc(c.name)}</button>`).join("")}
            <button class="chip chip-skip" data-seen-cinema="" data-film="${film.id}">Salta</button></div>`;
    } else if (votes[film.id] === "S" && seen[film.id]) {
        const where = seen[film.id].cinema ? ` · ${esc(cinemaName(seen[film.id].cinema))}` : "";
        extra = `<p class="small seen-info">✓ Visto il ${longDate(seen[film.id].date, isoDate(new Date()))}${where}</p>`;
    }
    return `<div class="vote-box" id="vote-${film.id}"><div class="vote-buttons">${buttons}</div>${extra}</div>`;
}
/** Cinemas that show the film (where it was probably seen), else all of them. */
function seenCinemaChoices(film) {
    const slugs = new Set(DATA.shows.filter((s) => s.f === film.id).map((s) => s.c));
    const list = DATA.cinemas.filter((c) => slugs.has(c.slug));
    return list.length ? list : DATA.cinemas;
}
function salaShows(s) {
    const times = s.shows.map((show) =>
        `<a class="show-time" href="${esc(show.url)}" target="_blank" rel="noopener" title="${show.end ? `Fine verso le ${hhmm(show.end)} · ` : ""}Acquista sul sito del cinema">${hhmm(show.start)}${show.end ? `<span class="show-end">→${hhmm(show.end)}</span>` : ""}</a>`
    ).join("");
    return `<span class="sala">${esc(s.sala || "Sala")}</span>${times}`;
}
const filmLink = (film) => `<a href="#/film/${film.id}" class="film-title-link" title="Tutti gli spettacoli">${esc(film.title)}</a>`;
function poster(film, cls) {
    return film.poster
        ? `<img src="${esc(film.poster)}" alt="" class="${cls}" loading="lazy">`
        : `<div class="${cls} placeholder">🎬</div>`;
}
function meta(film) {
    return `<div class="meta">
        ${film.year ? `<span>${film.year}</span>` : ""}
        ${film.genre ? `<span>${esc(film.genre)}</span>` : ""}
        ${film.runtime ? `<span title="Durata del film">${formatRuntime(film.runtime)}</span>` : ""}
        ${film.event ? `<span class="tag">Evento</span>` : ""}
        ${film.tmdb ? `<a href="https://www.themoviedb.org/movie/${film.tmdb}" target="_blank" rel="noopener" class="ext-link">TMDB ↗</a>` : ""}
    </div>`;
}
function filmCard(film, ctx, mode) {
    let body = "";
    if (mode === "oggi") {
        const next = ctx.next.get(film.id);
        if (next) {
            const cinemas = [...next.cinemas.entries()]
                .map(([slug, bySala]) => ({ slug, salas: salas(bySala) }))
                .sort((a, b) => a.salas[0].shows[0].start - b.salas[0].shows[0].start);
            const label = next.day === ctx.day
                ? `<p class="today-label">Oggi</p>`
                : `<p class="today-label next-day" title="Oggi non ci sono altri spettacoli">Prossimi spettacoli: ${formatDay(next.day, ctx.day)}</p>`;
            body = `<div class="today">${label}${cinemas.map((c) => `
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
    const since = mode === "oggi" && film.since
        ? `<p class="small in-sala-since" title="Primo giorno di programmazione a Cosenza e Rende">In sala dal ${longDate(film.since, ctx.day)}</p>` : "";
    return `<article class="film-card">${poster(film, "poster")}
        <div class="film-info"><h3>${filmLink(film)}</h3>${meta(film)}${since}${body}${voteBox(film)}</div>
    </article>`;
}

/** V films that arrived in theaters since their notice was last dismissed. */
function vArrivals(ctx) {
    return DATA.films
        .filter((f) => f.status === "in_sala" && votes[f.id] === "V" && !inSalaSeen.has(f.id) && hasShows(f, ctx))
        .sort((a, b) => a.title.localeCompare(b.title));
}
function arrivalsNotice(ctx) {
    const films = vArrivals(ctx);
    if (!films.length) return "";
    return `<section class="notice arrivals"><p>🎬 <strong>Ora in sala</strong> tra i tuoi V:
        ${films.map((f) => `<a href="#/film/${f.id}" class="film-title-link"><b>${esc(f.title)}</b></a>`).join(", ")}.</p>
        <div class="arrivals-actions"><a href="#/?voto=V" class="btn">Vedi gli orari</a>
        <button class="btn" data-action="dismiss-arrivals">Ok, visto</button></div></section>`;
}
/** Keep the seen list to films still in sala: one that leaves and comes back is news again.
 * The first time, V films already in sala count as seen: only the next arrivals get the notice. */
function updateInSalaSeen() {
    const inSala = (id) => (FILMS.get(Number(id)) || {}).status === "in_sala";
    const saved = load("cnv.inSalaSeen", null);
    const ids = saved === null ? DATA.films.filter((f) => f.status === "in_sala" && votes[f.id] === "V").map((f) => f.id) : saved;
    const merged = DATA.merged || {}; // a duplicate merged into another film: its notice was seen too
    inSalaSeen = new Set(ids.map((id) => Number(merged[id] ?? id)).filter(inSala));
    save("cnv.inSalaSeen", [...inSalaSeen]);
}

/** Notice for cinemas whose site did not answer at the last update (all of them, or the given one). */
function notUpdatedNotice(ctx, only = null) {
    const list = Object.entries(DATA.not_updated || {}).filter(([slug]) => CINEMAS.has(slug) && (!only || slug === only));
    if (!list.length) return "";
    const names = list.map(([slug, lastOk]) => {
        const c = CINEMAS.get(slug);
        return `<a href="${esc(c.url)}" target="_blank" rel="noopener"><b>${esc(c.name)}</b></a>${lastOk ? ` (orari del ${longDate(lastOk, ctx.day)})` : ""}`;
    }).join(", ");
    return `<section class="notice not-updated">⚠️ All'ultimo aggiornamento non ha risposto il sito di ${names}:
        ${list.length === 1 ? "i suoi orari potrebbero essere cambiati" : "i loro orari potrebbero essere cambiati"}. Controlla sul sito del cinema prima di andare.</section>`;
}

// ------------------------------------------------------------------ pages

/** The search box: the words typed appear in the title (TMDB or the cinema's), ignoring accents. */
const normalize = (s) => (s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^\p{L}\p{N}\s]/gu, "").replace(/\s+/g, " ").trim();
const titleMatches = (film, q) => !q || [film.title, film.raw].some((t) => t && normalize(t).includes(normalize(q)));
/** Hash of a page with its filters, some changed (null removes one). */
function filterHash(path, params, changes) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) { if (v) p.set(k, v); else p.delete(k); }
    const query = p.toString();
    return `#${path}${query ? `?${query}` : ""}`;
}
function searchBox(q) {
    return `<input type="search" id="search" data-filter="q" value="${esc(q || "")}" placeholder="Cerca un titolo" aria-label="Cerca un titolo" autocomplete="off">`;
}

function pageInSala(ctx, params) {
    const voto = params.get("voto");
    const inSala = DATA.films.filter((f) => f.status === "in_sala");
    const genres = [...new Set(inSala.map((f) => f.genre).filter(Boolean))].sort((a, b) => a.localeCompare(b));
    const genere = genres.includes(params.get("genere")) ? params.get("genere") : null;
    const cinema = CINEMAS.has(params.get("cinema")) ? params.get("cinema") : null;
    const q = (params.get("q") || "").trim();
    const filters = [[null, "Tutti"], ["nessuno", "Da votare"], ["V", "V"], ["?", "?"]];

    const chips = filters.map(([value, label]) =>
        `<a href="${filterHash("/", params, { voto: value })}" class="chip${(voto || null) === value ? " active" : ""}">${label}</a>`).join("");
    const options = (list, selected, all) => `<option value="">${all}</option>` +
        list.map(([value, label]) => `<option value="${esc(value)}"${value === selected ? " selected" : ""}>${esc(label)}</option>`).join("");
    return `<header class="page-header"><h1>Film in sala</h1><nav class="chips">${chips}</nav></header>
        ${notUpdatedNotice(ctx, cinema)}
        <div class="filters" role="search">${searchBox(q)}
            <select data-filter="genere" aria-label="Genere">${options(genres.map((g) => [g, g]), genere, "Tutti i generi")}</select>
            <select data-filter="cinema" aria-label="Cinema">${options(DATA.cinemas.map((c) => [c.slug, c.name]), cinema, "Tutti i cinema")}</select>
        </div>
        <div id="results">${inSalaResults(ctx, params, { voto, genere, cinema, q, films: inSala })}</div>`;
}

/** The films of In sala that pass the filters (the part redrawn while typing a search). */
function inSalaResults(ctx, params, { voto, genere, cinema, q, films }) {
    films = films.filter((f) => (voto === "nessuno" ? !votes[f.id] : !VOTES.includes(voto) || votes[f.id] === voto)
        && (!genere || f.genre === genere) && titleMatches(f, q));
    const showing = films.filter((f) => hasShows(f, ctx))
        .sort((a, b) => (b.since || "").localeCompare(a.since || "") || a.title.localeCompare(b.title)); // latest arrivals first
    // With a cinema chosen, films not on there are simply left out
    const gone = cinema ? [] : films.filter((f) => !hasShows(f, ctx)).sort((a, b) => a.title.localeCompare(b.title));
    const filtered = genere || cinema || q;
    let html = filtered
        ? `<p class="small filter-info">${showing.length} film · <a href="${filterHash("/", params, { genere: null, cinema: null, q: null })}">Togli filtri</a></p>` : "";
    html += showing.length
        ? `<div class="film-grid">${showing.map((f) => filmCard(f, ctx, "oggi")).join("")}</div>`
        : `<p class="empty-state">${voto || filtered ? "Nessun film in sala con questi filtri." : "Nessun film in programmazione."}</p>`;
    if (gone.length) {
        html += `<details class="gone-section" data-key="gone"><summary>Non più in programmazione <span class="count">${gone.length}</span>
            <span class="small">— spariti dai siti dei cinema, in attesa di essere segnati come usciti</span></summary>
            <ul class="gone-list">${gone.map((f) => {
                const days = f.event ? DATA.settings.days_to_uscito_evento : DATA.settings.days_to_uscito;
                const exit = f.last_seen ? addDays(f.last_seen, days) : null;
                return `<li><a href="#/film/${f.id}" class="gone-title film-title-link">${esc(f.title)}</a>
                    <span class="small">${f.last_seen ? `visto l'ultima volta ${formatDay(f.last_seen, ctx.day)}` : ""}${exit ? ` · uscito dalle sale dal ${longDate(exit, ctx.day)} se non ricompare` : ""}</span>
                    ${voteBox(f)}</li>`;
            }).join("")}</ul></details>`;
    }
    return html;
}

function pageInUscita(ctx, params) {
    const q = (params.get("q") || "").trim();
    const calendar = params.get("vista") === "calendario";
    const views = [["Elenco", null], ["Calendario", "calendario"]].map(([label, value]) =>
        `<a href="${filterHash("/uscita", params, { vista: value, mese: null })}" class="chip${(value === "calendario") === calendar ? " active" : ""}">${label}</a>`).join("");
    return `<header class="page-header"><h1>In uscita</h1>
        <p class="subtitle">Film annunciati dai cinema o con spettacoli solo futuri (prevendite e anteprime), con i cinema che li avranno.</p></header>
        <nav class="chips view-chips">${views}</nav>
        <div class="filters" role="search">${searchBox(q)}</div>
        <div id="results">${calendar ? releaseCalendar(ctx, params, q) : inUscitaResults(ctx, q)}</div>`;
}

/** Films coming out, with their cinemas and first date, soonest first. */
function comingCards(ctx, q) {
    return DATA.films
        .filter((f) => f.status === "in_uscita" && titleMatches(f, q))
        .map((f) => ({ f, releases: cinemaReleases(f, ctx) }))
        .filter((c) => c.releases.length)
        .map((c) => ({ ...c, first: c.releases.find((r) => r.date)?.date || null }))
        .sort((a, b) => (a.first === null) - (b.first === null) || (a.first || "").localeCompare(b.first || "") || a.f.title.localeCompare(b.f.title));
}

/** "In uscita" as a month calendar: each film on its first date (this month by default). */
function releaseCalendar(ctx, params, q) {
    const cards = comingCards(ctx, q);
    const thisMonth = ctx.day.slice(0, 7);
    const asked = /^\d{4}-\d{2}$/.test(params.get("mese") || "") ? params.get("mese") : thisMonth;
    const month = asked < thisMonth ? thisMonth : asked;
    const [y, m] = month.split("-").map(Number);
    const shift = (n) => isoDate(new Date(y, m - 1 + n, 1)).slice(0, 7);
    const lastRelease = cards.map((c) => c.first).filter(Boolean).sort().pop() || ctx.day;
    const byDay = new Map();
    cards.filter((c) => c.first).forEach((c) => push(byDay, c.first, c.f));

    // Monday to Sunday, with the days of nearby months that fill the first and last week
    const firstDay = new Date(y, m - 1, 1);
    const start = new Date(y, m - 1, 1 - ((firstDay.getDay() + 6) % 7));
    const days = [];
    for (let d = new Date(start); d.getMonth() === m - 1 || d < firstDay || days.length % 7; d.setDate(d.getDate() + 1)) {
        days.push(isoDate(d));
    }
    const nav = (target, label, symbol) => target
        ? `<a href="${filterHash("/uscita", params, { mese: target })}" class="btn" aria-label="${label}">${symbol}</a>`
        : `<span class="btn disabled" aria-hidden="true">${symbol}</span>`;
    const cells = days.map((d) => {
        const films = byDay.get(d) || [];
        const cls = ["cal-day", d.slice(0, 7) !== month ? "other-month" : "", d === ctx.day ? "today" : "", d < ctx.day ? "past" : ""].filter(Boolean).join(" ");
        return `<div class="${cls}"><span class="cal-num">${Number(d.slice(8))}</span>${films.map((f) =>
            `<a href="#/film/${f.id}" class="cal-film" title="${esc(f.title)}">${f.poster ? `<img src="${esc(f.poster)}" alt="" loading="lazy">` : `<span class="cal-placeholder">🎬</span>`}<span class="cal-title">${esc(f.title)}</span></a>`).join("")}</div>`;
    }).join("");
    const undated = cards.filter((c) => !c.first);
    return `<div class="month-nav">${nav(month > thisMonth ? shift(-1) : null, "Mese precedente", "‹")}
            <h2>${capitalize(MONTHS[m - 1])} ${y}</h2>${nav(shift(1) <= lastRelease.slice(0, 7) ? shift(1) : null, "Mese successivo", "›")}</div>
        <div class="release-calendar">${CALENDAR_DAYS.map((n) => `<div class="cal-head">${n}</div>`).join("")}${cells}</div>
        ${undated.length ? `<h3 class="section-title undated-title">Data da definire</h3>
            <ul class="undated-list">${undated.map((c) => `<li>${filmLink(c.f)}</li>`).join("")}</ul>` : ""}`;
}

function inUscitaResults(ctx, q) {
    const cards = comingCards(ctx, q);
    let html = q ? `<p class="small filter-info">${cards.length} film · <a href="#/uscita">Togli filtri</a></p>` : "";
    if (!cards.length) return html + `<p class="empty-state">${q ? "Nessun film in uscita con questo titolo." : "Nessun film in uscita al momento."}</p>`;
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
    let todayOver = false; // opened without choosing a day and nothing left today
    if (!byDay.has(selected)) {
        selected = days[0] || null;
        todayOver = selected !== null && selected !== ctx.day;
    }

    let html = `<header class="page-header"><h1>${esc(cinema.name)}</h1>
        <a href="${esc(cinema.url)}" target="_blank" rel="noopener" class="btn">Sito del cinema ↗</a>
        <p class="subtitle">Tocca un orario per aprire la pagina d'acquisto sul sito del cinema.</p></header>
        ${notUpdatedNotice(ctx, slug)}`;
    if (!selected) {
        return html + `<p class="empty-state">Il sito del cinema non ha spettacoli in programma.<br>
            <a href="${esc(cinema.url)}" target="_blank" rel="noopener">Controlla sul sito del cinema ↗</a></p>`;
    }
    html += `<nav class="calendar">${days.map((d) =>
        `<a href="#/cinema/${esc(slug)}?giorno=${d}" class="day-chip${d === selected ? " active" : ""}">${d === ctx.day ? "Oggi" : capitalize(formatDay(d, ctx.day))}</a>`).join("")}</nav>`;
    if (todayOver) {
        html += `<p class="notice next-day-notice">Oggi non ci sono altri spettacoli: ecco quelli di ${formatDay(selected, ctx.day)}.</p>`;
    }
    const films = [...byDay.get(selected).entries()]
        .map(([id, bySala]) => ({ film: FILMS.get(id), salas: salas(bySala) }))
        .filter((x) => x.film)
        .sort((a, b) => Math.min(...a.salas.map((s) => s.shows[0].start)) - Math.min(...b.salas.map((s) => s.shows[0].start)));
    return html + `<div class="day-films">${films.map(({ film, salas: list }) => `<article class="day-film">
        ${poster(film, "thumb")}
        <div class="day-film-info"><h3>${filmLink(film)}</h3>${meta(film)}
            ${list.map((s) => `<p class="day-sala">${salaShows(s)}</p>`).join("")}
            ${voteBox(film)}</div></article>`).join("")}</div>`;
}

/** One film: every show still to come, day by day, split by cinema. */
function pageFilm(ctx, id) {
    const film = FILMS.get(id);
    if (!film) return `<p class="empty-state">Film non trovato.</p>`;
    const cinemas = [];
    for (const [slug, byDay] of ctx.byCinemaDay) {
        const days = [...byDay.keys()].sort()
            .filter((d) => byDay.get(d).has(id))
            .map((d) => ({ day: d, salas: salas(byDay.get(d).get(id)) }));
        if (days.length) cinemas.push({ slug, days });
    }
    cinemas.sort((a, b) => a.days[0].salas[0].shows[0].start - b.days[0].salas[0].shows[0].start
        || cinemaName(a.slug).localeCompare(cinemaName(b.slug)));
    const releases = cinemaReleases(film, ctx);
    const firstRelease = releases.find((r) => r.date)?.date;
    const status = film.status === "in_sala" && film.since ? `In sala dal ${longDate(film.since, ctx.day)}`
        : film.status === "in_uscita" ? (firstRelease ? `In uscita dal ${longDate(firstRelease, ctx.day)}` : "In uscita, data da definire")
        : film.status === "uscito" && film.left ? `Uscito dalle sale il ${longDate(film.left, ctx.day)}` : "";

    let html = `<article class="film-page">${poster(film, "film-page-poster")}
        <div class="film-page-info"><h1>${esc(film.title)}</h1>${meta(film)}
            ${status ? `<p class="small">${status}</p>` : ""}${voteBox(film)}</div></article>`;
    if (cinemas.length) {
        html += `<h2 class="section-title">Spettacoli</h2>
            <p class="subtitle small">Tocca un orario per aprire la pagina d'acquisto sul sito del cinema.</p>
            <div class="film-cinemas">${cinemas.map((c) => `<section class="film-cinema">
                <h3><a href="#/cinema/${esc(c.slug)}">${esc(cinemaName(c.slug))}</a></h3>
                ${c.days.map((d) => `<div class="film-day">
                    <p class="film-day-label">${d.day === ctx.day ? "Oggi" : capitalize(formatDay(d.day, ctx.day))}</p>
                    <div class="film-day-salas">${d.salas.map((s) => `<p class="day-sala">${salaShows(s)}</p>`).join("")}</div>
                </div>`).join("")}</section>`).join("")}</div>`;
    } else {
        html += `<p class="empty-state">Nessuno spettacolo in programma.</p>`;
    }
    const elsewhere = releases.filter((r) => r.announced);
    if (elsewhere.length) {
        html += `<p class="small announced">In arrivo anche: ${elsewhere.map((r) => esc(cinemaName(r.slug)) + (r.date ? ` (dal ${longDate(r.date, ctx.day)})` : "")).join(", ")}</p>`;
    }
    return html;
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

/** Films marked ✓, latest first. */
const seenFilms = () => DATA.films.filter((f) => votes[f.id] === "S")
    .sort((a, b) => ((seen[b.id] || {}).date || "").localeCompare((seen[a.id] || {}).date || "") || a.title.localeCompare(b.title));
/** Seen films that go in the next diary file: without TMDB they cannot be imported. */
const toDiary = () => seenFilms().filter((f) => !diary[f.id] && f.tmdb);

function pageVisti() {
    const films = seenFilms();
    const ready = toDiary();
    const missing = films.filter((f) => !diary[f.id] && !f.tmdb);
    const today = isoDate(new Date());
    let html = `<header class="page-header"><h1>Visti</h1>
        <p class="subtitle">Film segnati ✓: giorno e cinema si possono correggere qui. Da qui vanno nel diario di Letterboxd.</p></header>`;
    if (ready.length) {
        html += `<section class="export-box"><h2>Da mettere nel diario <span class="count">${ready.length}</span></h2>
            <ol class="steps"><li>Scarica il file CSV.</li>
            <li>Su Letterboxd: Impostazioni → Importa ed esporta → Importa i tuoi dati. Ogni film diventa una voce del diario con la sua data.</li>
            <li>Torna qui e segnali come importati, così non finiscono nel prossimo file.</li></ol>
            <div class="export-actions">
                <button class="btn btn-export" data-action="export-diary">📥 Scarica CSV per il diario</button>
                <button class="btn" data-action="mark-diary">✓ Li ho importati su Letterboxd</button>
            </div></section>`;
    }
    if (missing.length) {
        html += `<section class="notice"><p><b>${missing.length} film senza abbinamento TMDB</b> non sono nel file:
            ${missing.map((f) => `<i>${esc(f.title)}</i>`).join(", ")}. Sistemali dalla versione di CNV sul PC.</p></section>`;
    }
    if (!films.length) {
        return html + `<p class="empty-state">Nessun film visto per ora.<br>Quando vedi un film al cinema, segnalo con <strong>✓</strong>.</p>`;
    }
    return html + seenStats(films) + `<h2 class="section-title">Elenco</h2><ul class="seen-list">${films.map((f) => {
        const info = seen[f.id] || {};
        const options = `<option value="">Cinema?</option>` + DATA.cinemas.map((c) =>
            `<option value="${esc(c.slug)}"${c.slug === info.cinema ? " selected" : ""}>${esc(c.name)}</option>`).join("");
        const state = diary[f.id]
            ? `Nel diario di Letterboxd <button class="btn btn-small" data-action="diary-again" data-film="${f.id}">Esporta di nuovo</button>`
            : f.tmdb ? "Da mettere nel diario" : "Senza abbinamento TMDB";
        return `<li class="seen-row">${poster(f, "thumb")}<div class="seen-row-info">
            <a href="#/film/${f.id}" class="film-title-link"><b>${esc(f.title)}</b></a>
            <div class="seen-edit">
                <input type="date" data-seen-date="${f.id}" value="${esc(info.date || "")}" max="${today}" aria-label="Giorno in cui l'hai visto">
                <select data-seen-where="${f.id}" aria-label="Cinema">${options}</select>
            </div>
            <span class="small">${state}</span></div></li>`;
    }).join("")}</ul>`;
}

/** Statistics of the films seen: summary numbers and bars by month, cinema and genre. */
function seenStats(films) {
    if (!films.length) return "";
    const count = (keys) => keys.reduce((m, k) => m.set(k, (m.get(k) || 0) + 1), new Map());
    const ranked = (map, last) => [...map].filter(([k]) => k !== last)
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).concat(map.has(last) ? [[last, map.get(last)]] : []);
    const today = isoDate(new Date());
    const months = count(films.map((f) => (seen[f.id] || {}).date).filter(Boolean).map((d) => d.slice(0, 7)));
    // From the first month with a film seen to this one, at most the last 12 (months counted from year 0)
    const index = (ym) => Number(ym.slice(0, 4)) * 12 + Number(ym.slice(5, 7)) - 1;
    const thisMonth = index(today);
    const firstMonth = Math.max(Math.min(thisMonth, ...[...months.keys()].map(index)), thisMonth - 11);
    const byMonth = [];
    for (let i = firstMonth; i <= thisMonth; i++) {
        const key = `${Math.floor(i / 12)}-${pad(i % 12 + 1)}`;
        byMonth.push([`${MONTHS[i % 12].slice(0, 3)} ${Math.floor(i / 12)}`, months.get(key) || 0]);
    }
    const byCinema = ranked(count(films.map((f) => (seen[f.id] || {}).cinema ? cinemaName(seen[f.id].cinema) : "Non indicato")), "Non indicato");
    const byGenre = ranked(count(films.map((f) => f.genre || "Non noto")), "Non noto");
    const top = (rows, last) => (rows.find(([k]) => k !== last) || [null])[0];
    const bars = (rows) => {
        const max = Math.max(1, ...rows.map(([, n]) => n));
        return rows.map(([label, n]) => `<div class="stat-bar" title="${esc(label)}: ${n} film">
            <span class="stat-label">${esc(label)}</span>
            <span class="stat-track"><span class="stat-fill" style="width: ${(n / max * 100).toFixed(1)}%"></span></span>
            <span class="stat-value">${n}</span></div>`).join("");
    };
    const tile = (value, caption, cls = "stat-number") => `<div class="stat-tile"><span class="${cls}">${esc(String(value))}</span><span class="stat-caption">${caption}</span></div>`;
    const topCinema = top(byCinema, "Non indicato"), topGenre = top(byGenre, "Non noto");
    return `<section class="stats" aria-label="Statistiche"><h2 class="section-title">Statistiche</h2>
        <div class="stat-tiles">${tile(films.length, "film visti")}${tile(months.get(today.slice(0, 7)) || 0, "questo mese")}
            ${topCinema ? tile(topCinema, "cinema più frequentato", "stat-text") : ""}${topGenre ? tile(topGenre, "genere più visto", "stat-text") : ""}</div>
        <div class="stat-groups">
            <div class="stat-group"><h3>Al mese</h3>${bars(byMonth)}</div>
            <div class="stat-group"><h3>Per cinema</h3>${bars(byCinema)}</div>
            <div class="stat-group"><h3>Per genere</h3>${bars(byGenre)}</div>
        </div></section>`;
}

function diaryCsv() {
    const quote = (s) => /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    const rows = toDiary().map((f) => [f.tmdb, quote(f.title), f.year || "", (seen[f.id] || {}).date || ""].join(","));
    return ["tmdbID,Title,Year,WatchedDate", ...rows].join("\n") + "\n";
}

/** The "Notifiche" box of the Voti page. */
function pushBox() {
    if (!pushState.supported) {
        return `<section class="notice"><p><b>Notifiche</b>: questo browser non le supporta. Su Android usa Chrome e aggiungi CNV alla schermata Home.</p></section>`;
    }
    if (!pushState.code) {
        return `<section class="export-box"><h2>Notifiche</h2>
            <p class="small">Ti avviso quando un film nuovo arriva in sala, con i tuoi V in evidenza. Gratis, anche ad app chiusa.</p>
            <div class="export-actions"><button class="btn btn-primary" data-action="push-enable">🔔 Attiva le notifiche</button></div></section>`;
    }
    return `<section class="export-box"><h2>Notifiche attive su questo telefono</h2>
        <ol class="steps">
            <li>Copia il codice qui sotto.</li>
            <li>Su GitHub: Settings → Secrets and variables → Actions → New repository secret, nome <b>PUSH_SUBSCRIPTION</b>, incolla il codice. Serve anche il segreto <b>VAPID_PRIVATE_KEY</b> (la chiave nel file .env del PC).</li>
            <li>Per provare: Actions → Aggiorna CNV per il telefono → Run workflow, con "Manda una notifica di prova".</li>
        </ol>
        <textarea class="push-code" readonly rows="4" aria-label="Codice per GitHub">${esc(pushState.code)}</textarea>
        <div class="export-actions">
            <button class="btn btn-primary" data-action="push-copy">📋 Copia il codice</button>
            <button class="btn" data-action="push-disable">Disattiva</button>
        </div></section>`;
}

/** Whether notifications can work here, and the code of the current subscription. */
async function refreshPush() {
    pushState.supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
    if (!pushState.supported) return;
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    pushState.code = subscription ? JSON.stringify(subscription) : null;
}

function base64UrlToBytes(text) {
    const base64 = (text + "=".repeat((4 - (text.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
    return Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
}

async function enablePush() {
    if (await Notification.requestPermission() !== "granted") {
        alert("Senza il permesso le notifiche non possono arrivare. Puoi darlo dalle impostazioni del sito in Chrome.");
        return;
    }
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription()
        || await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: base64UrlToBytes(PUSH_PUBLIC_KEY) });
    pushState.code = JSON.stringify(subscription);
}

async function disablePush() {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) await subscription.unsubscribe();
    pushState.code = null;
}

function pageVoti() {
    const count = Object.keys(votes).length;
    return `<header class="page-header"><h1>I tuoi voti</h1>
        <p class="subtitle">I voti sono salvati solo su questo telefono. Fai ogni tanto una copia: se cambi telefono o cancelli i dati del browser, la ripristini da qui.</p></header>
        <p>Hai votato <b>${count}</b> film${Object.keys(exported).length ? ` e ne hai esportati <b>${Object.keys(exported).length}</b> su Letterboxd` : ""}. La copia contiene anche i film visti.</p>
        <div class="backup-actions">
            <button class="btn btn-primary" data-action="export-votes">💾 Salva una copia dei voti</button>
            <label class="btn">📂 Ripristina da una copia<input type="file" accept="application/json,.json" data-action="import-votes"></label>
        </div>
        ${pushBox()}`;
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
    const now = new Date();
    const fullCtx = buildContext(now);
    const { path, params } = route();
    if (path in lastQuery) lastQuery[path] = params.toString();
    const cinemaFilter = path === "/" && CINEMAS.has(params.get("cinema")) ? params.get("cinema") : null;
    const ctx = cinemaFilter ? buildContext(now, cinemaFilter) : fullCtx;
    let page, active;
    if (path.startsWith("/cinema/")) {
        const slug = decodeURIComponent(path.slice("/cinema/".length));
        page = pageCinema(ctx, slug, params);
        active = "cinema:" + slug;
    } else if (path.startsWith("/film/")) {
        page = pageFilm(ctx, Number(path.slice("/film/".length)));
        active = "film";
    } else if (path === "/uscita") { page = pageInUscita(ctx, params); active = "uscita"; }
    else if (path === "/watchlist") { page = pageWatchlist(); active = "watchlist"; }
    else if (path === "/visti") { page = pageVisti(); active = "visti"; }
    else if (path === "/voti") { page = pageVoti(); active = "voti"; }
    else { page = pageInSala(ctx, params); active = "sala"; }
    page = arrivalsNotice(fullCtx) + page;

    const app = document.getElementById("app");
    const results = app.querySelector("#results");
    if (document.activeElement?.id === "search" && results) {
        // Typing a search: redraw only the results, so the box keeps the focus and the keyboard
        const fresh = Object.assign(document.createElement("template"), { innerHTML: page }).content.querySelector("#results");
        if (fresh) results.replaceWith(fresh);
    } else if (!periodic) {
        app.innerHTML = page;
        if (swipeDirection) {
            app.classList.remove("swipe-next", "swipe-prev");
            void app.offsetWidth; // restart the animation
            app.classList.add(`swipe-${swipeDirection}`);
            swipeDirection = "";
        }
    } else if (path !== "/voti" && page !== shownPage) {
        const open = [...app.querySelectorAll("details[data-key][open]")].map((d) => d.dataset.key);
        app.innerHTML = page;
        open.forEach((key) => app.querySelector(`details[data-key="${key}"]`)?.setAttribute("open", ""));
    }
    if (!periodic || path !== "/voti") shownPage = page;
    renderNav(fullCtx, active);
    renderMenu(fullCtx, active);
}

/** A menu page with the filters it had last time. */
const tabHash = (path) => `#${path}${lastQuery[path] ? `?${lastQuery[path]}` : ""}`;

function renderNav(ctx, active) {
    const inSala = DATA.films.filter((f) => f.status === "in_sala" && hasShows(f, ctx)).length;
    const inUscita = DATA.films.filter((f) => f.status === "in_uscita" && cinemaReleases(f, ctx).length).length;
    const watch = toExport().length;
    const links = [["sala", tabHash("/"), "In sala", inSala], ["uscita", tabHash("/uscita"), "In uscita", inUscita],
        ["watchlist", "#/watchlist", "Watchlist", watch], ["visti", "#/visti", "Visti", toDiary().length], ["voti", "#/voti", "Voti", 0]];
    const nav = document.getElementById("nav-links");
    nav.innerHTML = links.map(([key, href, label, n]) =>
        `<a href="${href}" class="${active === key ? "active" : ""}">${label}${n ? ` <span class="count">${n}</span>` : ""}</a>`).join("");
    // The menu scrolls sideways on narrow screens: keep the current page in view
    const current = nav.querySelector("a.active");
    if (current) nav.scrollLeft = Math.max(0, current.offsetLeft - nav.offsetLeft - (nav.clientWidth - current.offsetWidth) / 2);
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
        if (votes[id] === "S") {
            seen[id] = { date: programmeDay(new Date()), cinema: null }; // after midnight: last night
            askCinemaFor = id;
        } else {
            delete seen[id];
            delete diary[id];
            if (askCinemaFor === id) askCinemaFor = null;
        }
        save("cnv.seen", seen);
        save("cnv.diary", diary);
        if (votes[id] === "V" && FILMS.get(id).status === "in_sala") {
            inSalaSeen.add(id); // voted while in sala: no notice needed
            save("cnv.inSalaSeen", [...inSalaSeen]);
        }
        document.querySelectorAll(`#vote-${id}`).forEach((box) => { box.outerHTML = voteBox(FILMS.get(id)); });
        return;
    }
    const where = e.target.closest("[data-seen-cinema]");
    if (where) {
        const id = Number(where.dataset.film);
        if (seen[id]) seen[id].cinema = where.dataset.seenCinema || null;
        save("cnv.seen", seen);
        askCinemaFor = null;
        document.querySelectorAll(`#vote-${id}`).forEach((box) => { box.outerHTML = voteBox(FILMS.get(id)); });
        return;
    }
    const action = e.target.closest("[data-action]")?.dataset.action;
    const today = isoDate(new Date());
    if (action === "push-enable" || action === "push-disable") {
        (action === "push-enable" ? enablePush() : disablePush())
            .then(render)
            .catch((err) => alert(`Non riesco a ${action === "push-enable" ? "attivare" : "disattivare"} le notifiche (${err.message}).`));
    }
    if (action === "push-copy") {
        navigator.clipboard.writeText(pushState.code || "")
            .then(() => alert("Codice copiato: incollalo nel segreto PUSH_SUBSCRIPTION su GitHub."))
            .catch(() => { document.querySelector(".push-code")?.select(); });
    }
    if (action === "export-diary") download(`letterboxd_diario_${today}.csv`, "text/csv", diaryCsv());
    if (action === "mark-diary" && confirm("Hai importato il file su Letterboxd?")) {
        toDiary().forEach((f) => { diary[f.id] = today; });
        save("cnv.diary", diary);
        render();
    }
    if (action === "diary-again") {
        delete diary[Number(e.target.closest("[data-film]").dataset.film)];
        save("cnv.diary", diary);
        render();
    }
    if (action === "dismiss-arrivals") {
        vArrivals(buildContext(new Date())).forEach((f) => inSalaSeen.add(f.id));
        save("cnv.inSalaSeen", [...inSalaSeen]);
        render();
    }
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
        download(`cnv-voti-${today}.json`, "application/json", JSON.stringify({ votes, exported, seen, diary, saved_at: today }, null, 1));
    }
});

document.addEventListener("input", (e) => {
    if (e.target.id !== "search") return;
    const { path, params } = route();
    history.replaceState(null, "", filterHash(path, params, { q: e.target.value.trim() || null }));
    render();
});

document.addEventListener("change", (e) => {
    // "Visti" page: day and cinema of a seen film
    const dateOf = e.target.dataset.seenDate, whereOf = e.target.dataset.seenWhere;
    if (dateOf || whereOf) {
        const id = Number(dateOf || whereOf);
        seen[id] = seen[id] || { date: null, cinema: null };
        if (dateOf && e.target.value) seen[id].date = e.target.value;
        if (whereOf) seen[id].cinema = e.target.value || null;
        save("cnv.seen", seen);
        return;
    }
    if (e.target.matches("select[data-filter]")) {
        const { path, params } = route();
        location.hash = filterHash(path, params, { [e.target.dataset.filter]: e.target.value || null });
        return;
    }
    if (e.target.dataset.action !== "import-votes" || !e.target.files.length) return;
    e.target.files[0].text().then((text) => {
        const backup = JSON.parse(text);
        if (!backup || typeof backup.votes !== "object") throw new Error("file non valido");
        const restored = knownVotes(backup.votes);
        if (!confirm(`Ripristinare ${Object.keys(restored).length} voti? Quelli attuali verranno sostituiti.`)) return;
        votes = restored;
        exported = backup.exported || {};
        seen = backup.seen || {};
        diary = backup.diary || {};
        save("cnv.votes", votes);
        save("cnv.exported", exported);
        save("cnv.seen", seen);
        save("cnv.diary", diary);
        render();
    }).catch((err) => alert(`Copia dei voti non valida (${err.message}).`));
});

window.addEventListener("hashchange", () => { render(); window.scrollTo(0, 0); });

// ------------------------------------------------------------------ swipe between pages

const TABS = ["#/", "#/uscita", "#/watchlist", "#/visti", "#/voti"]; // same order as the menu
const SWIPE_MIN = 70;   // px sideways to change page
const SWIPE_EDGE = 24;  // touches starting this close to the screen edge are Android's "back" gesture
let swipe = null;       // the touch in progress: {x, y, horizontal}

/** Where a swipe leads (step +1 = next, -1 = previous): the next menu page, or the next day on a cinema page. */
function swipeTarget(step) {
    const { path, params } = route();
    if (path.startsWith("/cinema/")) {
        const slug = decodeURIComponent(path.slice("/cinema/".length));
        const days = [...(buildContext(new Date()).byCinemaDay.get(slug) || new Map()).keys()].sort();
        const current = days.includes(params.get("giorno")) ? params.get("giorno") : days[0];
        const day = days[days.indexOf(current) + step];
        return day ? `#/cinema/${slug}?giorno=${day}` : null;
    }
    const index = TABS.indexOf(`#${path}`);
    const target = index === -1 ? null : TABS[index + step] || null;
    return target && target.slice(1) in lastQuery ? tabHash(target.slice(1)) : target;
}

function endSwipe() {
    swipe = null;
    const app = document.getElementById("app");
    app.style.transition = "";
    app.style.transform = "";
}

document.addEventListener("touchstart", (e) => {
    swipe = null;
    if (!DATA || e.touches.length !== 1) return;
    const t = e.touches[0];
    if (t.clientX < SWIPE_EDGE || t.clientX > window.innerWidth - SWIPE_EDGE) return;
    if (e.target.closest(".calendar, .chips, .nav-links, .cinema-menu, .filters, input, select")) return; // they scroll or open by themselves
    swipe = { x: t.clientX, y: t.clientY, horizontal: null };
}, { passive: true });

document.addEventListener("touchmove", (e) => {
    if (!swipe) return;
    const dx = e.touches[0].clientX - swipe.x;
    const dy = e.touches[0].clientY - swipe.y;
    // Decide once, after a few px: sideways = swipe, otherwise the page is just scrolling
    if (swipe.horizontal === null && Math.hypot(dx, dy) > 12) swipe.horizontal = Math.abs(dx) > Math.abs(dy) * 1.5;
    if (swipe.horizontal) {
        const app = document.getElementById("app");
        app.style.transition = "none";
        app.style.transform = `translateX(${dx / 4}px)`; // the page follows the finger a little
    }
}, { passive: true });

document.addEventListener("touchend", (e) => {
    if (!swipe) return;
    const dx = e.changedTouches[0].clientX - swipe.x;
    const horizontal = swipe.horizontal;
    endSwipe();
    if (!horizontal || Math.abs(dx) < SWIPE_MIN) return;
    const step = dx < 0 ? 1 : -1; // finger to the left: next page
    const target = swipeTarget(step);
    if (!target) return;
    swipeDirection = step > 0 ? "next" : "prev";
    location.hash = target;
});
document.addEventListener("touchcancel", endSwipe);
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
        for (const map of [seen, diary]) {
            if (map[old]) {
                map[target] = map[target] || map[old];
                delete map[old];
                changed = true;
            }
        }
    }
    if (changed) {
        save("cnv.votes", votes);
        save("cnv.exported", exported);
        save("cnv.seen", seen);
        save("cnv.diary", diary);
    }
}

/** Saved posters of films no page shows any more are removed from the phone. */
function prunePosters() {
    if (!("caches" in window)) return;
    const shown = new Set(toExport());
    const keep = new Set(DATA.films.filter((f) => f.status !== "uscito" || shown.has(f) || votes[f.id] === "S").map((f) => f.poster));
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
    save("cnv.votes", votes); // without the old X votes (and a copy for the notifications)
    updateInSalaSeen();
    render();
    showUpdated(offline);
    if (!offline) prunePosters();
    refreshPush().then(() => { if (route().path === "/voti") render(); }).catch(() => { /* no notifications */ });
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
