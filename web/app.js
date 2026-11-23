"use strict";

// Kaderplaner – Oberfläche. Daten: /api/meta, /api/plan, /api/reload (scripts/webapp.py).

const SPEICHER = "fm27-kaderplaner";
const $ = (sel) => document.querySelector(sel);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

let META = null;
let PLAN = null;
let aktiverSlot = null;
let zustand = laden();
let planTimer = null;
let planNr = 0;

function laden() {
  try {
    return JSON.parse(localStorage.getItem(SPEICHER)) || {};
  } catch {
    return {};
  }
}
function speichern() {
  localStorage.setItem(SPEICHER, JSON.stringify(zustand));
}

async function api(pfad, body) {
  const r = await fetch(pfad, body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const daten = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof daten.detail === "string" ? daten.detail : JSON.stringify(daten.detail || daten));
  return daten;
}

function meldung(text, fehler = false) {
  const m = $("#meldung");
  m.hidden = !text;
  m.textContent = text || "";
  m.classList.toggle("fehler", fehler);
}

// ------------------------------------------------------------------ Formatierung

const zahl = (v, d = 0) => (v == null ? "–" : v.toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d }));
function geld(v) {
  if (v == null) return "–";
  if (Math.abs(v) >= 1e6) return zahl(v / 1e6, 1) + " Mio.";
  if (Math.abs(v) >= 1e3) return zahl(v / 1e3, 0) + " T";
  return zahl(v, 0);
}
function spanne(v, lo, hi) {
  if (lo != null && hi != null && lo !== hi) return `${geld(lo)} – ${geld(hi)}`;
  return geld(v);
}
function scoreKlasse(v) {
  if (v == null) return "";
  return v >= 66 ? "s-hoch" : v >= 40 ? "s-mittel" : "s-tief";
}
const score = (v) => `<span class="score ${scoreKlasse(v)}">${zahl(v)}</span>`;
const STATUS = { kader: "", leihe_ein: "Leihe", leihe_aus: "verliehen" };
const kurzName = (n) => (n || "").split(" ").slice(-1)[0];
const initialen = (n) => (n || "?").split(" ").filter(Boolean).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
// Spielerbild aus dem FM27-Faces-Ordner; fehlt es, bleiben die Initialen darunter sichtbar
// Größe in "px bei 14 px Grundschrift", wird in rem umgerechnet und wächst so mit der Schrift
const gesicht = (uid, name, px) =>
  `<span class="gesicht" style="--g:${(px / 14).toFixed(3)}rem"><span class="ini">${esc(initialen(name))}</span>` +
  `<img src="/api/face/${encodeURIComponent(uid)}" alt="" loading="lazy" onerror="this.remove()"></span>`;
// (i)-Symbol: Erklärtext erscheint beim Darüberfahren, Fokussieren oder Antippen (Popover #info_tip)
const info = (text) =>
  `<span class="info-i" tabindex="0" role="button" aria-label="Info: ${esc(text)}" data-info="${esc(text)}">i</span>`;

function infoVerdrahten() {
  const tip = document.createElement("div");
  tip.id = "info_tip";
  tip.className = "info-tip";
  tip.hidden = true;
  document.body.appendChild(tip);
  let offen = null;
  const zeigen = (el) => {
    offen?.classList.remove("offen");
    offen = el;
    el.classList.add("offen");
    tip.textContent = el.dataset.info;
    tip.hidden = false;
    const r = el.getBoundingClientRect();
    const rand = 8;
    let x = r.left + r.width / 2 - tip.offsetWidth / 2;
    x = Math.max(rand, Math.min(x, window.innerWidth - tip.offsetWidth - rand));
    let y = r.bottom + 6;
    if (y + tip.offsetHeight > window.innerHeight - rand) y = r.top - tip.offsetHeight - 6;
    tip.style.left = x + "px";
    tip.style.top = Math.max(rand, y) + "px";
  };
  const verbergen = () => {
    offen?.classList.remove("offen");
    offen = null;
    tip.hidden = true;
  };
  const ziel = (e) => e.target.closest?.(".info-i");
  document.addEventListener("mouseover", (e) => { const el = ziel(e); if (el) zeigen(el); });
  document.addEventListener("mouseout", (e) => { if (ziel(e) && !ziel(e).contains(e.relatedTarget)) verbergen(); });
  document.addEventListener("focusin", (e) => { const el = ziel(e); if (el) zeigen(el); });
  document.addEventListener("focusout", (e) => { if (ziel(e)) verbergen(); });
  document.addEventListener("click", (e) => {
    const el = ziel(e);
    if (el) { e.stopPropagation(); el === offen && !tip.hidden ? verbergen() : zeigen(el); }
  }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") verbergen(); }, true);
  window.addEventListener("scroll", verbergen, true);
}

// ------------------------------------------------------------------ Steuerung

function optionen(sel, werte, aktuell, leer) {
  sel.innerHTML = (leer ? `<option value="">${esc(leer)}</option>` : "") +
    werte.map((w) => `<option value="${esc(w)}"${w === aktuell ? " selected" : ""}>${esc(w)}</option>`).join("");
}

function filterWerte() {
  return { ...META.filter_standard, ...(zustand.filter || {}) };
}

function steuerungAufbauen() {
  const formen = Object.keys(META.formationen);
  if (!formen.includes(zustand.formation)) zustand.formation = META.standard || formen[0];
  optionen($("#formation"), formen, zustand.formation);
  $("#aufstellung").value = zustand.aufstellung === "score" ? "score" : "einsaetze";
  optionen($("#pool_min_stufe"), META.stufen, META.einstellungen.pool_min_stufe);
  $("#quelle").value = META.einstellungen.quelle;
  $("#anker_min_n").value = META.einstellungen.anker_min_n;

  const f = filterWerte();
  optionen(document.querySelector('[data-f="min_stufe"]'), META.stufen, f.min_stufe, "alle");
  optionen(document.querySelector('[data-f="gewichtung"]'), META.gewichtungen, f.gewichtung, "je Position");
  document.querySelectorAll("[data-f]").forEach((el) => {
    const v = f[el.dataset.f];
    if (el.type === "checkbox") el.checked = !!v;
    else el.value = v ?? "";
  });
  $("#nur_suche_box").hidden = META.stand.quelle !== "live";

  const s = META.stand;
  const teile = [
    `Save ${s.save ?? ""}`,
    s.quelle === "live" ? `Live, Stand ${s.datum ?? "?"}` : `DB: Kader ${s.kader_datum ?? "–"}, Suche ${s.suche_datum ?? "–"}`,
    `${zahl(s.n_eigene)} eigene, ${zahl(s.n_suche)} aus der Spielersuche`,
    `Pool ab ${s.pool_min_stufe}`,
  ];
  if (s.verein) teile.splice(1, 0, s.verein);
  const e = META.einsaetze;
  if (e) teile.push(e.spieler ? `Spiele erfasst: ${e.spieler} Spieler` : "Spiele nicht erfasst");
  $("#stand").textContent = teile.join(" · ");
  $("#erfassen").hidden = !META.erfassen_moeglich;
}

function filterLesen() {
  const f = {};
  document.querySelectorAll("[data-f]").forEach((el) => {
    const k = el.dataset.f;
    if (el.type === "checkbox") f[k] = el.checked;
    else if (el.type === "number") f[k] = el.value === "" ? null : Number(el.value);
    else f[k] = el.value === "" ? null : el.value;
  });
  for (const k of ["min_minuten", "min_minuten_eigene"]) if (f[k] == null) f[k] = META.filter_standard[k];
  return f;
}

function rollenWahl() {
  zustand.rollen = zustand.rollen || {};
  const form = META.formationen[zustand.formation];
  const wahl = (zustand.rollen[zustand.formation] = zustand.rollen[zustand.formation] || {});
  for (const [sn, s] of Object.entries(form.slots)) {
    const w = (wahl[sn] = wahl[sn] || {});
    if (!s.optionen.mit.includes(w.mit)) w.mit = s.mit;
    if (!s.optionen.ohne.includes(w.ohne)) w.ohne = s.ohne;
  }
  return wahl;
}

// ------------------------------------------------------------------ Spielfeld

function feldZeichnen() {
  const feld = $("#feld");
  feld.querySelectorAll(".slot").forEach((e) => e.remove());
  const form = META.formationen[zustand.formation];
  rollenWahl();
  for (const [sn, s] of Object.entries(form.slots)) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "slot" + (sn === aktiverSlot ? " aktiv" : "");
    el.style.setProperty("--x", s.x + "%");
    el.style.setProperty("--y", s.y + "%");
    el.dataset.slot = sn;
    el.innerHTML =
      `<div class="slot-kopf"><span class="pos" title="${esc(sn)}">${esc(s.label)}</span>` +
      `<span class="rechts"><span data-warn></span><span data-pill></span></span></div>` +
      `<div class="slot-spieler" data-spieler><span class="leer">…</span></div>` +
      `<div class="slot-ziel" data-ziel></div>`;
    el.addEventListener("click", () => slotWaehlen(sn));
    feld.appendChild(el);
  }
}

// Feldgröße aus der freien Bildschirmhöhe: alle Positionen ohne Scrollen sichtbar (Filterzeile darf umbrechen)
// Unter 440 px Breite überlappen die Karten (4 nebeneinander); bis 68:89 gestaucht bleiben alle Formationen frei.
// Alle Maße in rem-Vielfachen (Basis 14 px), damit Feld und Karten mit der Grundschrift wachsen.
function feldGroesse() {
  const em = parseFloat(getComputedStyle(document.documentElement).fontSize) / 14;
  const oben = $("main").getBoundingClientRect().top + window.scrollY;
  const frei = window.innerHeight - oben - 24 * em - $(".legende").offsetHeight;
  const w = Math.min(700 * em, Math.max(440 * em, frei * 0.68));
  const h = Math.min(w / 0.68, Math.max(frei, w / 0.76));
  document.documentElement.style.setProperty("--feld-w", Math.round(w) + "px");
  document.documentElement.style.setProperty("--feld-h-px", Math.round(h) + "px");
}

function slotWaehlen(sn) {
  aktiverSlot = sn;
  document.querySelectorAll(".slot").forEach((x) => x.classList.toggle("aktiv", x.dataset.slot === sn));
  panelZeichnen();
}

function stufe(v) {
  if (v == null) return "t-leer";
  return v >= 66 ? "t-hoch" : v >= 40 ? "t-mittel" : "t-tief";
}

// Warum ist der Spieler gesetzt? (Aufstellung nach Score oder wie gespielt)
function gesetztGrund(s) {
  const g = s.gesetzt_grund;
  if (!g || g.art === "keiner") return "niemand gesetzt";
  if (g.art === "einsaetze") return `wie gespielt: ${zahl(g.minuten)} Min. in ${g.spiele} Spielen auf ${g.position}`;
  return PLAN.aufstellung_nach === "einsaetze"
    ? "nach Score: niemand mit mindestens 270 erfassten Minuten auf dieser Position"
    : "nach Score (beste Elf ohne Doppelbesetzung)";
}

function slotsAktualisieren() {
  if (!PLAN) return;
  for (const [sn, s] of Object.entries(PLAN.slots)) {
    const el = document.querySelector(`.slot[data-slot="${CSS.escape(sn)}"]`);
    if (!el) continue;
    const g = s.eigene.find((z) => z.uid === s.gesetzt);
    el.classList.remove("t-hoch", "t-mittel", "t-tief", "t-leer");
    el.classList.add(stufe(g ? g.paar_gew : null));
    // "!" nur bei spürbaren Lücken: eine Rolle zu weniger als 80 % bewertbar (Details im Panel)
    const warn = s.luecken.some((l) => l.abdeckung != null && l.abdeckung < 0.8);
    el.querySelector("[data-warn]").innerHTML = warn
      ? '<span class="warn" title="Rolle nur teilweise bewertbar, Details im Panel">!</span>' : "";
    el.querySelector("[data-pill]").innerHTML = g ? `<span class="pill ${stufe(g.paar_gew)}">${zahl(g.paar_gew)}</span>` : "";
    const gr = gesetztGrund(s);
    el.classList.toggle("rueckfall", PLAN.aufstellung_nach === "einsaetze" && s.gesetzt_grund?.art === "score");
    el.querySelector("[data-spieler]").innerHTML = g
      ? `${gesicht(g.uid, g.name, 28)}<span class="name" title="${esc(g.name + " – " + gr)}">${esc(kurzName(g.name))}</span>`
      : `<span class="leer">niemand bewertbar</span>`;
    // Schattenteam: bester Kandidat, der den Gesetzten übertrifft
    const best = s.verbesserungen[0];
    const ziel = el.querySelector("[data-ziel]");
    if (best) {
      const zusatz = best.delta != null ? `+${zahl(best.delta)}` : zahl(best.paar_gew);
      ziel.innerHTML = `<span class="pfeil">▲</span>${gesicht(best.uid, best.name, 18)}` +
        `<span class="name">${esc(kurzName(best.name))}</span><b>${zusatz}</b>`;
      ziel.title = `${s.n_verbesserungen} Kandidaten besser als der Gesetzte. Bester: ${best.name} (${best.club}), Score ${zahl(best.paar_gew)}`;
      ziel.classList.remove("leer");
    } else {
      ziel.textContent = "kein besserer Kandidat";
      ziel.title = "Kein Kandidat übertrifft den gesetzten Spieler (mit diesen Filtern).";
      ziel.classList.add("leer");
    }
  }
}

// ------------------------------------------------------------------ Panel

function tabelle(spalten, zeilen, { gesetzt, sortierung, beiKlick } = {}) {
  const wrap = document.createElement("div");
  wrap.className = "tabelle-wrap";
  let sort = sortierung || null;
  const zeichnen = () => {
    const daten = [...zeilen];
    if (sort) {
      const sp = spalten.find((s) => s.k === sort.k);
      const wert = sp.sort || ((z) => z[sp.k]);
      daten.sort((a, b) => {
        const x = wert(a), y = wert(b);
        if (x == null && y == null) return 0;
        if (x == null) return 1;
        if (y == null) return -1;
        return (x < y ? -1 : x > y ? 1 : 0) * (sort.ab ? -1 : 1);
      });
    }
    const kopf = spalten.map((s) =>
      `<th class="${s.num ? "num" : ""}" data-k="${s.k}" title="${esc(s.titel || "")}">${esc(s.l)}` +
      (sort && sort.k === s.k ? ` <span class="pfeil">${sort.ab ? "▼" : "▲"}</span>` : "") + `</th>`).join("");
    const koerper = daten.map((z) => {
      const zellen = spalten.map((s) => `<td class="${s.num ? "num" : ""}">${s.f ? s.f(z) : esc(z[s.k] ?? "–")}</td>`).join("");
      return `<tr class="zeile${z.uid === gesetzt ? " gesetzt" : ""}" data-uid="${esc(z.uid)}">${zellen}</tr>`;
    }).join("");
    wrap.innerHTML = `<table><thead><tr>${kopf}</tr></thead><tbody>${koerper}</tbody></table>`;
    wrap.querySelectorAll("th").forEach((th) =>
      th.addEventListener("click", () => {
        const k = th.dataset.k;
        sort = sort && sort.k === k ? { k, ab: !sort.ab } : { k, ab: true };
        zeichnen();
      }),
    );
    wrap.querySelectorAll("tr.zeile").forEach((tr) =>
      tr.addEventListener("click", () => beiKlick && beiKlick(tr.dataset.uid)),
    );
  };
  zeichnen();
  return wrap;
}

const SP_NAME = {
  k: "name", l: "Name",
  f: (z) => `<span class="mit-gesicht">${gesicht(z.uid, z.name, 24)}${esc(z.name)}</span>` +
    (STATUS[z.eigen] ? `<span class="tag">${STATUS[z.eigen]}</span>` : ""),
};
const SP_SCORES = [
  { k: "mit", l: "mit", num: true, f: (z) => score(z.mit), titel: "Rolle mit Ball" },
  { k: "ohne", l: "ohne", num: true, f: (z) => score(z.ohne), titel: "Rolle ohne Ball" },
  { k: "paar_gew", l: "Score", num: true, f: (z) => score(z.paar_gew), titel: "Paar-Score × Liga-Gewicht" },
  { k: "vs_top", l: "vs Top", num: true, f: (z) => zahl(z.vs_top), titel: "50 = Median der Topclub-Spieler" },
];
function aufPosition(z) {
  if (z.pos_min == null) return '<span class="hinweis">–</span>';
  const anteil = z.erfasst_min ? z.pos_min / z.erfasst_min : 0;
  const kl = anteil < 0.25 ? "warn-text" : "";
  return `<span class="${kl}" title="${z.pos_spiele} von ${z.erfasst_spiele} erfassten Spielen auf dieser Position` +
    `${z.pos_note != null ? ", Ø Note " + zahl(z.pos_note, 2) : ""}">${zahl(z.pos_min)} Min. (${zahl(anteil * 100)} %)</span>`;
}
const SP_EIGENE = [
  SP_NAME,
  { k: "age", l: "Alter", num: true },
  { k: "minutes", l: "Min.", num: true, f: (z) => zahl(z.minutes) },
  { k: "pos_min", l: "auf Pos.", num: true, f: aufPosition,
    titel: "Minuten auf dieser Position in den erfassten Spielen (letzte 20 je Spieler, „Spiele erfassen“)" },
  ...SP_SCORES,
  { k: "contract_end", l: "Vertrag" },
];
const SP_KAND = [
  SP_NAME,
  { k: "club", l: "Verein", f: (z) => esc(z.club) },
  { k: "liga_stufe", l: "Liga", f: (z) => esc(z.liga_stufe ?? "–"), titel: "Ansehen der Liga", sort: (z) => (z.liga_stufe ? META.stufen.indexOf(z.liga_stufe) : null) },
  { k: "age", l: "Alter", num: true },
  { k: "minutes", l: "Min.", num: true, f: (z) => zahl(z.minutes) },
  ...SP_SCORES,
  { k: "delta", l: "Δ", num: true, f: (z) => `<b>${z.delta == null ? "–" : "+" + zahl(z.delta)}</b>` },
  { k: "value", l: "Marktwert", num: true, f: (z) => spanne(z.value, z.value_min, z.value_max), sort: (z) => z.value ?? z.value_max },
  { k: "wage", l: "Gehalt/J.", num: true, f: (z) => spanne(z.wage, z.wage_min, z.wage_max), sort: (z) => z.wage ?? z.wage_max },
  { k: "contract_end", l: "Vertrag" },
];

function lueckenHtml(s) {
  if (!s.luecken.length) return "";
  const weg = s.luecken.filter((l) => l.entfaellt).map((l) => l.baustein);
  const abd = s.luecken.filter((l) => l.abdeckung != null);
  const kurz = [
    weg.length ? `Baustein ${[...new Set(weg)].join(", ")} entfällt` : "",
    abd.length ? abd.map((l) => `${l.rolle} zu ${zahl(l.abdeckung * 100)} % bewertbar`).join(", ") : "",
  ].filter(Boolean).join(" · ") || "einzelne Statistiken fehlen";
  const zeilen = s.luecken.filter((l) => l.abdeckung == null).map((l) => {
    const stats = Object.entries(l.statistiken).map(([k, v]) => `${esc(k)} (${esc(v)})`).join(", ");
    return `<li>${esc(l.rolle)} · ${esc(l.baustein)}${l.entfaellt ? " entfällt" : " teilweise"}: ${stats}</li>`;
  });
  return `<details class="luecken"><summary><span class="warn">!</span> Datenlücken: ${esc(kurz)}</summary>` +
    `<ul>${zeilen.join("")}</ul></details>`;
}

function rollenWahlHtml(sn) {
  const opt = META.formationen[zustand.formation].slots[sn].optionen;
  const wahl = rollenWahl()[sn];
  const sel = (phase) => `<select data-phase="${phase}">` +
    opt[phase].map((r) => `<option${r === wahl[phase] ? " selected" : ""}>${esc(r)}</option>`).join("") + `</select>`;
  return `<div class="rollen-wahl"><label>mit Ball ${sel("mit")}</label><label>ohne Ball ${sel("ohne")}</label></div>`;
}

function panelZeichnen() {
  const p = $("#panel");
  if (!PLAN || !aktiverSlot || !PLAN.slots[aktiverSlot]) {
    p.innerHTML = '<p class="leer">Position auf dem Spielfeld anklicken: Rollen wählen, Preis-Leistung, Verbesserungen und eigene Spieler.</p>';
    return;
  }
  const s = PLAN.slots[aktiverSlot];
  const meta = META.formationen[zustand.formation].slots[aktiverSlot];
  const gw = s.gewertet_als;
  const alias = (n, z) => (n === z ? "" : ` (gewertet wie ${esc(z)})`);
  const g = s.eigene.find((z) => z.uid === s.gesetzt);
  const slotInfo = `Verlässlichkeit der Rollenbewertung: mit Ball ${s.verlaesslichkeit.mit}, ohne Ball ${s.verlaesslichkeit.ohne}.\n` +
    `Vergleichspool: ${s.n_pool.mit}${s.n_pool.ohne !== s.n_pool.mit ? " / " + s.n_pool.ohne : ""} Spieler.\n` +
    `Score = Paar-Score (mit und ohne Ball) × Liga-Gewicht; 0 = Schlecht, 50 = OK, 100 = Gut.\n` +
    `Rollen-Zuordnung ungeprüft (wissen/rollen-kpis.md).`;
  const aliasText = alias(s.mit, gw.mit) || alias(s.ohne, gw.ohne)
    ? `<div class="rollen">${s.mit !== gw.mit ? `mit Ball${alias(s.mit, gw.mit)}` : ""}` +
      `${s.mit !== gw.mit && s.ohne !== gw.ohne ? " · " : ""}${s.ohne !== gw.ohne ? `ohne Ball${alias(s.ohne, gw.ohne)}` : ""}</div>`
    : "";
  const ohneWertung = s.ohne_wertung.length
    ? `<h3>Eigene ohne Wertung ${info(s.ohne_wertung
        .map((o) => `${o.name} (${o.grund}${STATUS[o.eigen] ? ", " + STATUS[o.eigen] : ""})`).join("\n"))}</h3>` +
      `<p class="hinweis">${s.ohne_wertung.map((o) => esc(kurzName(o.name))).join(", ")}</p>`
    : "";
  p.innerHTML =
    `<div class="panel-kopf"><h2>${esc(meta.label)} ${info(slotInfo)}</h2>` +
    (g ? `<span class="gesetzt-info">${gesicht(g.uid, g.name, 32)}gesetzt: <b>${esc(g.name)}</b> ${score(g.paar_gew)}` +
      `<span class="hinweis">${esc(gesetztGrund(s))}</span></span>` : "") +
    `</div>` + rollenWahlHtml(aktiverSlot) + aliasText +
    s.hinweise.map((h) => `<p class="hinweis">Hinweis: ${esc(h)}</p>`).join("") +
    lueckenHtml(s) +
    `<div class="panel-raster">` +
    `<section class="pr-streu"><h3>Preis-Leistung ${info(streuInfo(s))}</h3>${streuHtml(s)}</section>` +
    `<section class="pr-kand"><h3>Verbesserungen (${s.n_verbesserungen} von ${s.n_kandidaten} Kandidaten` +
    `${s.basis != null ? ", besser als " + zahl(s.basis) : ""}) ${info("Kandidaten aus der Spielersuche, deren Score über dem " +
      "gesetzten eigenen Spieler liegt. Δ = Abstand zum Gesetzten. Zeile anklicken öffnet das Profil, Spaltenkopf sortiert.")}</h3>` +
    `<div id="t_kand"></div></section>` +
    `<section class="pr-eigene"><h3>Eigene Spieler (${s.n_eigene} bewertet) ${info("„auf Pos.“ = Minuten auf der " +
      "FM-Position dieses Slots in den erfassten Spielen (letzte 20 je Spieler); orange unter 25 % der erfassten Minuten.")}</h3>` +
    `<div id="t_eigene"></div>${ohneWertung}</section></div>`;
  p.querySelectorAll(".rollen-wahl select").forEach((se) =>
    se.addEventListener("change", () => {
      rollenWahl()[aktiverSlot][se.dataset.phase] = se.value;
      speichern();
      planAnfordern();
    }),
  );
  streuVerdrahten(s);
  $("#t_eigene").appendChild(s.eigene.length
    ? tabelle(SP_EIGENE, s.eigene, { gesetzt: s.gesetzt, beiKlick: (uid) => profilOeffnen(uid) })
    : Object.assign(document.createElement("p"), { className: "hinweis", textContent: "Kein eigener Spieler bewertbar." }));
  $("#t_kand").appendChild(s.verbesserungen.length
    ? tabelle(SP_KAND, s.verbesserungen, { beiKlick: (uid) => profilOeffnen(uid) })
    : Object.assign(document.createElement("p"), { className: "hinweis", textContent: "Kein Kandidat übertrifft den gesetzten Spieler (mit diesen Filtern)." }));
}

// ------------------------------------------------------------------ Preis-Leistung (Score × Marktwert)

const SW = 640, SH = 300, SL = 44, SR = 14, ST = 14, SB = 36;
const GELD_TICKS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500].map((m) => m * 1e6);
const mio = (v) => zahl(v / 1e6, v < 1e6 ? 1 : 0);
let streuCache = [];

function streuDaten(s) {
  const gueltig = (z) => z.value != null && z.value > 0 && z.paar_gew != null;
  const kand = s.punkte.kandidaten.filter(gueltig).map((z) => ({ ...z, art: "k" }));
  const eig = s.punkte.eigene.filter(gueltig).map((z) => ({ ...z, art: "e" }));
  const ohne = s.punkte.kandidaten.length - kand.length + s.punkte.eigene.length - eig.length;
  return { punkte: [...kand, ...eig], ohne };
}

function streuHtml(s) {
  const { punkte, ohne } = streuDaten(s);
  streuCache = [];
  if (!punkte.length) return '<p class="hinweis">Keine Spieler mit Marktwert und Score.</p>';
  const werte = punkte.map((z) => z.value);
  const lo = Math.log10(Math.min(...werte) / 1.25), hi = Math.log10(Math.max(...werte) * 1.25);
  const yMax = Math.max(100, ...punkte.map((z) => z.paar_gew));
  const x = (v) => SL + ((Math.log10(v) - lo) / (hi - lo)) * (SW - SL - SR);
  const y = (v) => ST + (1 - v / yMax) * (SH - ST - SB);
  let g = "";
  for (const t of [0, 25, 50, 75, 100]) {
    g += `<line class="gitter" x1="${SL}" x2="${SW - SR}" y1="${y(t).toFixed(1)}" y2="${y(t).toFixed(1)}"/>` +
      `<text x="${SL - 6}" y="${(y(t) + 3).toFixed(1)}" text-anchor="end">${t}</text>`;
  }
  for (const t of GELD_TICKS.filter((t) => Math.log10(t) > lo && Math.log10(t) < hi)) {
    g += `<line class="gitter" y1="${ST}" y2="${SH - SB}" x1="${x(t).toFixed(1)}" x2="${x(t).toFixed(1)}"/>` +
      `<text x="${x(t).toFixed(1)}" y="${SH - SB + 14}" text-anchor="middle">${mio(t)}</text>`;
  }
  g += `<text x="${(SL + SW - SR) / 2}" y="${SH - 4}" text-anchor="middle">Marktwert in Mio. € (logarithmisch)</text>` +
    `<text x="12" y="${(ST + SH - SB) / 2}" text-anchor="middle" transform="rotate(-90 12 ${(ST + SH - SB) / 2})">Score</text>`;
  if (s.basis != null) {
    const g0 = s.eigene.find((z) => z.uid === s.gesetzt);
    g += `<line class="basis" x1="${SL}" x2="${SW - SR}" y1="${y(s.basis).toFixed(1)}" y2="${y(s.basis).toFixed(1)}"/>` +
      `<text class="basis-label" x="${SL + 6}" y="${(y(s.basis) - 5).toFixed(1)}">gesetzt: ${esc(g0 ? kurzName(g0.name) : "")} ${zahl(s.basis)}</text>`;
  }
  // Kandidaten unter dem Gesetzten zurücknehmen; eigene Spieler zuletzt, damit sie oben liegen
  const reihenfolge = [...punkte].sort((a, b) => (a.art === b.art ? a.paar_gew - b.paar_gew : a.art === "k" ? -1 : 1));
  const marken = reihenfolge.map((z) => {
    const besser = s.basis == null || z.paar_gew > s.basis;
    const kl = z.art === "e" ? "p1" : "p2" + (besser ? "" : " blass");
    return `<circle class="${kl}" cx="${x(z.value).toFixed(1)}" cy="${y(z.paar_gew).toFixed(1)}" r="${z.art === "e" ? 5 : 4}"/>`;
  }).join("");
  const treffer = reihenfolge.map((z, i) =>
    `<circle class="treffer" data-i="${i}" cx="${x(z.value).toFixed(1)}" cy="${y(z.paar_gew).toFixed(1)}" r="9"/>`).join("");
  streuCache = reihenfolge;
  const n = punkte.filter((z) => z.art === "k").length;
  return `<div class="legende-chart"><span><span class="punkt s2"></span>Kandidaten (${n})</span>` +
    `<span><span class="punkt s1"></span>Eigene Spieler</span>` +
    (s.basis != null ? `<span class="hinweis">blass = schwächer als der Gesetzte</span>` : "") + `</div>` +
    `<div class="streu-wrap"><div class="chart"><svg viewBox="0 0 ${SW} ${SH}" role="img" aria-label="Score über Marktwert">` +
    g + marken + treffer + `</svg></div><div class="tooltip" id="streu_tip" hidden></div></div>`;
}

function streuInfo(s) {
  const { ohne } = streuDaten(s);
  return "Score über Marktwert (logarithmisch). Oben links = besser und günstiger. Gestrichelte Linie = gesetzter " +
    "Spieler. Punkt anklicken öffnet das Profil." + (ohne ? `\n${ohne} Spieler ohne Marktwert sind nicht eingezeichnet.` : "");
}

function streuVerdrahten(s) {
  const tip = $("#streu_tip");
  const wrap = document.querySelector(".streu-wrap");
  if (!tip || !wrap) return;
  wrap.querySelectorAll(".treffer").forEach((el) => {
    const z = streuCache[Number(el.dataset.i)];
    el.addEventListener("mousemove", (ev) => {
      const d = s.basis != null && z.art === "k" ? z.paar_gew - s.basis : null;
      tip.innerHTML = `<div class="tip-kopf">${gesicht(z.uid, z.name, 36)}<div><b>${esc(z.name)}</b>` +
        `<div class="hinweis">${esc(z.club ?? "")}${z.age != null ? " · " + zahl(z.age) + " J." : ""}` +
        `${z.liga_stufe ? " · " + esc(z.liga_stufe) : ""}</div></div></div>` +
        `<div>Score <b>${zahl(z.paar_gew)}</b>${d != null ? ` (${d > 0 ? "+" : ""}${zahl(d)} zum Gesetzten)` : ""}</div>` +
        `<div>Marktwert ${spanne(z.value, z.value_min, z.value_max)}</div>`;
      tip.hidden = false;
      const box = wrap.getBoundingClientRect();
      let px = ev.clientX - box.left + 14, py = ev.clientY - box.top + 14;
      if (px + tip.offsetWidth > box.width) px = ev.clientX - box.left - tip.offsetWidth - 14;
      tip.style.left = px + "px";
      tip.style.top = py + "px";
    });
    el.addEventListener("mouseleave", () => { tip.hidden = true; });
    el.addEventListener("click", () => profilOeffnen(z.uid));
  });
}

// ------------------------------------------------------------------ Spielerprofil

let profilNr = 0;
let profilAktuell = null; // { p, uid, vergleich }

function standardVergleich(s, uid) {
  // Eigener Spieler ansehen -> mit dem besten Kandidaten vergleichen, sonst mit dem gesetzten Spieler
  if (s.gesetzt && s.gesetzt !== uid) return s.gesetzt;
  return s.verbesserungen.find((z) => z.uid !== uid)?.uid || s.eigene.find((z) => z.uid !== uid)?.uid || "";
}

async function profilOeffnen(uid, vergleich, slot = aktiverSlot) {
  const s = PLAN && PLAN.slots[slot];
  if (!s) return;
  const nr = ++profilNr;
  if (vergleich === undefined) vergleich = standardVergleich(s, uid);
  const q = new URLSearchParams({ mit: s.mit, ohne: s.ohne });
  if (vergleich) q.set("vergleich", vergleich);
  if (zustand.filter && zustand.filter.gewichtung) q.set("gewichtung", zustand.filter.gewichtung);
  if ($("#profil").hidden) $("#profil_inhalt").innerHTML = '<p class="leer">Profil lädt …</p>';
  $("#profil").hidden = false;
  try {
    const p = await api(`/api/spieler/${encodeURIComponent(uid)}?${q}`);
    if (nr !== profilNr) return;
    profilAktuell = { p, uid, vergleich, slot };
    $("#profil_inhalt").innerHTML = profilHtml(p, slot);
    profilVerdrahten();
  } catch (e) {
    if (nr === profilNr) $("#profil_inhalt").innerHTML = `<p class="meldung fehler">${esc(e.message)}</p>`;
  }
}

function profilVerdrahten() {
  const sel = $("#vergleich_wahl");
  if (sel) sel.addEventListener("change", () => profilOeffnen(profilAktuell.uid, sel.value, profilAktuell.slot));
  chartVerdrahten();
}

function profilSchliessen() {
  profilNr++;
  $("#profil").hidden = true;
}

const statWert = (v, art) => (v == null ? "–" : zahl(v, art === "p90" ? 2 : 1));
// Stufen wie im FM-Farbschema: ab 15, 12, 10, 7, 4, darunter (Spannen nach ihrer Mitte)
const ATTR_STUFEN = [15, 12, 10, 7, 4, 1];
function attrKlasse(v) {
  if (v == null) return "";
  return "a-" + (ATTR_STUFEN.find((s) => v >= s) ?? 1);
}
// Perzentil als farbige Pille (gleiche Schwellen wie der Score)
const badge = (v) => (v == null ? '<span class="hinweis">–</span>' : `<span class="badge ${stufe(v)}">${zahl(v)}</span>`);
const perz = badge;

// Statistik-Bezeichnung und Wert lesbar machen: "Tacklingquote %" -> "Tacklingquote" / "55,6 %",
// "Sprints pro 90" -> "Sprints" / "10,8 /90"
function statAnzeige(label, wert, pro90) {
  let name = label;
  const pct = /\s*%$/.test(name);
  const p90 = pro90 || /\s+pro 90$/.test(name);
  name = name.replace(/\s*%$/, "").replace(/\s+pro 90$/, "");
  if (wert == null) return { name, text: "–" };
  if (pct) return { name, text: `${zahl(wert, 1)}<span class="einheit"> %</span>` };
  if (p90) return { name, text: `${zahl(wert, 2)}<span class="einheit"> /90</span>` };
  return { name, text: zahl(wert, Number.isInteger(wert) ? 0 : 2) };
}

// ------------------------------------------------------------------ Profil: linke Spalte

const FUSS = ["Sehr schwach", "Schwach", "Durchschnitt", "Gut", "Stark", "Sehr stark"];
// Ampel für Textwerte aus dem Spiel (nur die Wörter, die das Spiel anzeigt; nichts geschätzt)
const AMPEL = {
  gut: ["Begeistert", "Sehr glücklich", "Glücklich", "Zufrieden", "Sehr gering", "Gering", "Unterdurchschnittlich", "0 Tage"],
  ok: ["Eher zufrieden", "Normal", "Durchschnittlich"],
  warn: ["Leicht unzufrieden", "Beunruhigt", "Erhöht", "Überdurchschnittlich"],
  schlecht: ["Unzufrieden", "Sehr unzufrieden", "Tief bestürzt", "Sehr verstimmt", "Hoch", "Sehr hoch"],
};
function ampel(text) {
  const stufe = Object.keys(AMPEL).find((k) => AMPEL[k].includes(text));
  return stufe ? `<span class="ampel a-${stufe}"></span>${esc(text)}` : esc(text);
}
function fussSkala(text) {
  const n = FUSS.indexOf(text) + 1;
  if (!n) return esc(text ?? "–");
  return `<span class="fuss" title="${esc(text)}">` +
    FUSS.map((_, i) => `<i class="${i < n ? "an" : ""}"></i>`).join("") + `</span>`;
}

function kv(label, wert, titel = "") {
  return wert == null || wert === "" ? "" :
    `<div class="kv"${titel ? ` title="${esc(titel)}"` : ""}><span class="k">${esc(label)}</span><span class="v">${wert}</span></div>`;
}
function block(titel, inhalt) {
  return inhalt ? `<section class="p-block"><h4>${esc(titel)}</h4>${inhalt}</section>` : "";
}

function profilSeite(p, slot) {
  const z = p.spieler, v = p.vergleich;
  const inf = Object.fromEntries((p.attribute.info || []).map((i) => [i.feld, i.text]));
  const t = (f) => (inf[f] == null ? null : esc(inf[f]));
  const tags = [
    STATUS[z.eigen] ? `<span class="tag">${STATUS[z.eigen]}</span>` : "",
    z.eigen ? '<span class="tag">eigener Spieler</span>' : z.in_suche ? '<span class="tag">Spielersuche</span>' : "",
  ].join("");
  const delta = v && z.paar_gew != null && v.paar_gew != null ? z.paar_gew - v.paar_gew : null;
  const kopf = `<div class="p-kopf">${gesicht(z.uid, z.name, 84)}<div class="p-name"><h2>${esc(z.name)}</h2>${tags}` +
    `<div class="p-meta">${esc(z.club ?? "–")}</div>` +
    `<div class="p-meta">${esc(z.league ?? "–")}${z.liga_stufe ? ` · ${esc(z.liga_stufe)}` : ""}</div>` +
    `<div class="p-meta">${zahl(z.age)} J. · ${esc(z.position ?? "–")}</div></div></div>`;
  const scoreInfo = `Score = Paar-Score ${zahl(z.paar)} (Mittel aus mit und ohne Ball) × Liga-Gewicht ${zahl(z.liga_gewicht, 2)}.\n` +
    `0 = Schlecht, 50 = OK, 100 = Gut. vs Top: 50 = Median der Topclub-Spieler.\n` +
    `${zahl(z.minutes)} Min., Datenbasis ${z.datenbasis ?? "–"}.`;
  const scores = `<div class="p-scores">` +
    `<div class="p-score-gross"><span class="pill ${stufe(z.paar_gew)}">${zahl(z.paar_gew)}</span>` +
    `<span class="k">Score ${info(scoreInfo)}</span></div>` +
    `<div class="p-score"><span class="k">mit Ball</span>${score(z.mit)}</div>` +
    `<div class="p-score"><span class="k">ohne Ball</span>${score(z.ohne)}</div>` +
    `<div class="p-score"><span class="k">vs Top</span><span class="score">${zahl(z.vs_top)}</span></div></div>` +
    (v ? `<div class="p-delta" title="${esc(`${slot}: ${v.name} Score ${zahl(v.paar_gew)}`)}">Δ zu ${esc(kurzName(v.name))} ` +
      `<b class="${delta == null ? "" : delta >= 0 ? "s-hoch" : "s-tief"}">${delta == null ? "–" : (delta > 0 ? "+" : "") + zahl(delta)}</b></div>` : "");

  const einsatz = inf.rolle && inf.rolle_tatsaechlich && inf.rolle !== inf.rolle_tatsaechlich
    ? `${t("rolle")} <span class="hinweis">→ tatsächlich</span> ${t("rolle_tatsaechlich")}` : t("rolle") ?? t("rolle_tatsaechlich");
  const nation = inf.geburtsland && inf.geburtsland !== inf.nation
    ? `${t("nation") ?? "–"} <span class="hinweis">(geb. ${t("geburtsland")})</span>` : t("nation");
  const fuesse = inf.fuss_links || inf.fuss_rechts
    ? `<span class="fuesse"><span>L ${fussSkala(inf.fuss_links)}</span><span>R ${fussSkala(inf.fuss_rechts)}</span></span>` : null;
  const vertrag = block("Vertrag",
    kv("Marktwert", spanne(z.value, z.value_min, z.value_max)) + kv("Gehalt/J.", spanne(z.wage, z.wage_min, z.wage_max)) +
    kv("Vertrag bis", esc(z.contract_end ?? "–")) + kv("Leihe bis", z.loan_end ? esc(z.loan_end) : null) +
    kv("Ausgeliehen von", t("ausgeliehen_von")) + kv("Seit", t("vertragsbeginn")) + kv("Status", t("vertragsstatus")) +
    kv("Ablöse", t("abloeseforderung")));
  const person = block("Person",
    kv("Nation", nation) + kv("Größe", t("groesse")) +
    kv("Füße", fuesse, `Links: ${inf.fuss_links ?? "–"}, rechts: ${inf.fuss_rechts ?? "–"}`) +
    kv("Idealposition", t("idealpos")) + kv("Persönlichkeit", t("persoenlichkeit")) + kv("Medien", t("medienumgang")) +
    kv("Eigengewächs", t("eigengewaechs")));
  const kader = block("Kader und Stimmung",
    kv("Einsatzzeit", einsatz, "zugesagt → tatsächlich") + kv("Hierarchie", t("hierarchie")) +
    kv("Zufriedenheit", inf.zufriedenheit ? ampel(inf.zufriedenheit) : null) +
    kv("Gesamt", inf.gesamtzufriedenheit ? ampel(inf.gesamtzufriedenheit) : null, "Gesamtzufriedenheit") +
    kv("Mit Einsätzen", inf.zufriedenheit_einsaetze ? ampel(inf.zufriedenheit_einsaetze) : null));
  const fitness = block("Fitness",
    kv("Verletzung", inf.verletzung ? `<span class="warn-text">${t("verletzung")}</span>` : null) +
    kv("Ausfallzeit", inf.ausfallszeit ? ampel(inf.ausfallszeit) : null) +
    kv("Risiko", inf.verletzungsrisiko ? ampel(inf.verletzungsrisiko) : null, "Verletzungsrisiko") +
    kv("Anfälligkeit", inf.verletzungsanfaelligkeit ? ampel(inf.verletzungsanfaelligkeit) : null, "Verletzungsanfälligkeit") +
    kv("Belastung", inf.spielbelastung || inf.trainingsbelastung
      ? `Spiel ${t("spielbelastung") ?? "–"} · Training ${t("trainingsbelastung") ?? "–"}` : null));
  return `<aside class="p-seite karte">${kopf}${scores}${vertrag}${person}${kader}${fitness}</aside>`;
}

// ------------------------------------------------------------------ Profil: Attribute und Kennzahlen der Rolle

function profilAttribute(a) {
  if (!a.gruppen.length) return `<h3>Attribute</h3><p class="hinweis">${esc(a.grund || "Keine Attribute vorhanden.")}</p>`;
  const quelle = `Export „${a.quelle.ansicht}“ vom ${a.quelle.datum}: ${a.n_exakt} exakt, ${a.n_spanne} als Spanne ` +
    `(Scouting-Kenntnisstand im Spiel, kein geschätzter Wert; gestrichelt, Farbe nach der Mitte der Spanne).\n` +
    `Farben wie im FM-Farbschema: ab 15, ab 12, ab 10, ab 7, ab 4, darunter.`;
  const legende = `<span class="attr-legende">${ATTR_STUFEN.map((st) => `<span class="a-${st}">${st}</span>`).join("")}</span>`;
  const spalten = a.gruppen.map((g) =>
    `<div class="attr-gruppe"><h4>${esc(g.gruppe)}</h4>` + g.attribute.map((x) => {
      const exakt = x.wert != null;
      const lo = x.lo, hi = x.hi;
      const anzeige = exakt ? zahl(x.wert) : lo != null ? (lo === hi ? zahl(lo) : `${zahl(lo)}–${zahl(hi)}`) : "?";
      const klasse = attrKlasse(exakt ? x.wert : lo != null ? (lo + hi) / 2 : null) + (exakt ? "" : " spanne");
      return `<div class="attr"><span>${esc(x.name)}</span><span class="a-wert ${klasse}">${anzeige}</span></div>`;
    }).join("") + `</div>`).join("");
  return `<h3>Attribute ${info(quelle)} ${legende}</h3><div class="attr-raster">${spalten}</div>`;
}

// Die Statistiken der beiden gewählten Rollen, nach Baustein gruppiert: Wert, Perzentil, ggf. Vergleich
function profilKennzahlen(p) {
  const v = p.vergleich;
  const chart = Object.fromEntries((p.chart || []).map((d) => [d.stat, d]));
  const vName = v ? esc(kurzName(v.name)) : "";
  const spalten = p.rollen.map((r) => {
    const zeilen = r.bausteine.map((bs) => {
      const kopf = `<tr class="baustein"><td>${esc(bs.label)}${bs.gewicht !== 1 ? ` <span class="tag">×${zahl(bs.gewicht)}</span>` : ""}</td>` +
        `<td></td><td class="num">${badge(bs.score[0])}</td>${v ? `<td class="num vgl-z">${badge(bs.score[1])}</td>` : ""}</tr>`;
      const stats = bs.stats.map((st) => {
        if (st.fehlt) {
          return `<tr><td class="hinweis" title="${esc(st.fehlt)}">${esc(st.label)}</td><td colspan="${v ? 3 : 2}" class="hinweis">nicht bewertet</td></tr>`;
        }
        const d = chart[st.stat];
        const a0 = statAnzeige(st.label, st.wert[0], st.art === "p90");
        const a1 = v ? statAnzeige(st.label, st.wert[1], st.art === "p90") : null;
        return `<tr><td>${esc(a0.name)}${st.niedrig ? ' <span class="tag" title="weniger ist besser">↓</span>' : ""}</td>` +
          `<td class="num">${a0.text}</td><td class="num">${perz(d ? d.perzentil[0] : null)}</td>` +
          (v ? `<td class="num vgl-z"><span class="vgl-wert">${a1.text}</span> ${perz(d ? d.perzentil[1] : null)}</td>` : "") + `</tr>`;
      }).join("");
      return kopf + stats;
    }).join("");
    return `<div class="kz"><h4>${r.phase === "mit" ? "Mit Ball" : "Ohne Ball"}: ${esc(r.rolle)} ${badge(r.score[0])}` +
      `${v ? ` <span class="vgl">${vName} ${zahl(r.score[1])}</span>` : ""}</h4>` +
      `<table class="kz-t"><thead><tr><th></th><th class="num">Wert</th><th class="num">Perz.</th>${v ? `<th class="num">${vName}</th>` : ""}</tr></thead>` +
      `<tbody>${zeilen}</tbody></table></div>`;
  }).join("");
  const erkl = "Statistiken der gewählten Rollen, nach Baustein. Fettgedruckte Zeile = Score des Bausteins (0 = Schlecht, " +
    "50 = OK, 100 = Gut). Perz. = Perzentil im Pool der Positionsgruppe (wie im Radar); ↓ = weniger ist besser, " +
    "Perzentil schon gespiegelt. Anker und vs Top: Score-Aufschlüsselung weiter unten.";
  return `<h3>Kennzahlen der Rolle ${info(erkl)}</h3><div class="kz-raster">${spalten}</div>`;
}

// Score-Aufschlüsselung mit Ankern (aufklappbar, für die Herleitung)
function profilScores(p) {
  const v = p.vergleich;
  const vk = v ? `<th class="num" title="${esc(v.name)}">${esc(kurzName(v.name))}</th>` : "";
  const teile = p.rollen.map((r) => {
    const kopf = `<h4>${r.phase === "mit" ? "Mit Ball" : "Ohne Ball"}: ${esc(r.rolle)}` +
      (r.rolle !== r.gewertet_als ? ` <span class="tag">gewertet wie ${esc(r.gewertet_als)}</span>` : "") +
      ` ${badge(r.score[0])}${v ? ` <span class="vgl">${esc(kurzName(v.name))} ${zahl(r.score[1])}</span>` : ""} ` +
      info(`Verlässlichkeit der Rollenbewertung: ${r.verlaesslichkeit ?? "–"}.` + (r.luecken ? `\nNicht erfasst: ${r.luecken}` : "")) +
      `</h4>`;
    const zeilen = r.bausteine.map((bs) => {
      const bz = `<tr class="baustein"><td>${esc(bs.label)} <span class="tag">×${zahl(bs.gewicht)}</span></td>` +
        `<td></td><td></td><td class="num">${badge(bs.score[0])}</td><td></td>${v ? `<td class="num vgl-z">${badge(bs.score[1])}</td>` : ""}</tr>`;
      const sz = bs.stats.map((st) => {
        if (st.fehlt) {
          return `<tr class="stat"><td>${esc(st.label)}</td><td colspan="${v ? 5 : 4}" class="fehlt">nicht bewertet: ${esc(st.fehlt)}</td></tr>`;
        }
        const anker = `${statWert(st.schlecht, st.art)} / ${statWert(st.ok, st.art)} / ${statWert(st.gut, st.art)}`;
        return `<tr class="stat"><td>${esc(st.label)}${st.niedrig ? ' <span class="tag">weniger ist besser</span>' : ""}</td>` +
          `<td class="num">${statWert(st.wert[0], st.art)}</td><td class="num anker">${anker}</td>` +
          `<td class="num">${badge(st.score[0])}</td><td class="num">${zahl(st.vs_top[0])}</td>` +
          (v ? `<td class="num vgl-z"><span class="vgl-wert">${statWert(st.wert[1], st.art)}</span> ${badge(st.score[1])}</td>` : "") + `</tr>`;
      }).join("");
      return bz + sz;
    }).join("");
    return kopf + `<div class="tabelle-wrap"><table class="aufschl"><thead><tr><th></th>` +
      `<th class="num">Wert</th><th class="num">Schlecht / OK / Gut</th>` +
      `<th class="num">Score</th><th class="num">vs Top</th>${vk}</tr></thead>` +
      `<tbody>${zeilen}</tbody></table></div>`;
  }).join("");
  return `<h3>Score-Aufschlüsselung ${info("Anker Schlecht / OK / Gut = Perzentile 25 / 55 / 90 des Pools; daraus der Score 0 / 50 / 100 je Statistik. " +
      "Baustein-Score = Mittel seiner Statistiken, Rollen-Score = gewichtetes Mittel der Bausteine. " +
      "vs Top = Anteil der Topclub-Spieler, den er übertrifft.")}</h3>${teile}`;
}

// Alle Statistiken: je Gruppe eine schmale Tabelle; Hauptwert pro 90 (sonst Gesamt bzw. Quote), Perzentil als Pille
function profilStatistiken(p) {
  const pool = `Perz. = Perzentil: Anteil der ${zahl(p.pool.n)} Spieler der Positionsgruppe „${p.pool.gruppe}“ ` +
    `(ab 900 Min., Ligen ab ${p.pool.min_stufe}), die er übertrifft. Hoch = gut, auch bei „weniger ist besser“ ` +
    `(Fouls, Ballverluste …). Wert = pro 90 Minuten, wo es den gibt, sonst Quote oder Gesamtwert; Gesamt = Saisonsumme.`;
  const gruppen = p.statistiken.map((g) =>
    `<div class="stat-gruppe"><h4>${esc(g.gruppe)}</h4><table class="stat-t"><thead><tr><th></th>` +
    `<th class="num">Wert</th><th class="num">Gesamt</th><th class="num">Perz.</th></tr></thead><tbody>` +
    g.stats.map((st) => {
      const mit90 = st.pro90 != null;
      const a = statAnzeige(st.label, mit90 ? st.pro90 : st.gesamt, mit90);
      return `<tr><td>${esc(a.name)}</td><td class="num">${a.text}</td>` +
        `<td class="num hinweis">${mit90 ? zahl(st.gesamt, Number.isInteger(st.gesamt) ? 0 : 1) : ""}</td>` +
        `<td class="num">${perz(st.perzentil)}</td></tr>`;
    }).join("") + `</tbody></table></div>`).join("");
  return `<h3>Statistiken ${info(pool)}</h3><div class="stat-raster">${gruppen}</div>`;
}

// ------------------------------------------------------------------ Vergleichschart (Radar)

function profilVergleich(p, slot) {
  const s = PLAN.slots[slot];
  const uid = p.spieler.uid;
  const akt = p.vergleich ? p.vergleich.uid : "";
  const opt = (z, zusatz = "") =>
    `<option value="${esc(z.uid)}"${z.uid === akt ? " selected" : ""}>${esc(z.name)}${zusatz} · ${zahl(z.paar_gew)}</option>`;
  const eigene = s.eigene.filter((z) => z.uid !== uid).map((z) => opt(z, z.uid === s.gesetzt ? " (gesetzt)" : "")).join("");
  const kand = s.verbesserungen.filter((z) => z.uid !== uid).map((z) => opt(z)).join("");
  const erkl = p.chart && p.chart.length
    ? `Perzentil je Statistik der beiden Rollen im Pool der Positionsgruppe (${zahl(p.chart[0].n_pool)} Spieler, ` +
      `ab 900 Min., Ligen ab ${p.pool.min_stufe}). 100 = besser als alle, 50 = Median; bei „weniger ist besser“ ` +
      `gespiegelt, also immer: weiter außen = besser.`
    : "";
  return `<div class="vergleich-kopf"><h3>Radar ${erkl ? info(erkl) : ""}</h3>` +
    `<label>Vergleich <select id="vergleich_wahl"><option value=""${akt ? "" : " selected"}>– kein Vergleich –</option>` +
    (eigene ? `<optgroup label="Eigene Spieler (${esc(slot)})">${eigene}</optgroup>` : "") +
    (kand ? `<optgroup label="Kandidaten">${kand}</optgroup>` : "") + `</select></label></div>` +
    `<div id="chart_bereich">${chartHtml(p)}</div>`;
}

function chartHtml(p) {
  const daten = p.chart || [];
  if (!daten.length) return '<p class="hinweis">Keine bewertbaren Statistiken für diese Rollen.</p>';
  const zwei = !!p.vergleich;
  const legende = `<div class="legende-chart"><span><span class="punkt s1"></span>${esc(p.spieler.name)}</span>` +
    (zwei ? `<span><span class="punkt s2"></span>${esc(p.vergleich.name)}</span>` : "") + `</div>`;
  return legende + `<div class="chart-wrap"><div class="chart">${radarSvg(daten, zwei)}</div>` +
    `<div class="tooltip" id="chart_tip" hidden></div></div>`;
}

// Geometrie: Mittelpunkt C, innerer Ring R0, 100. Perzentil bei R1, Beschriftung außerhalb
const C = 280, R0 = 26, R1 = 178, RL = 196;
const winkel = (i, n) => -Math.PI / 2 + (i * 2 * Math.PI) / n;
const punkt = (a, r) => [C + r * Math.cos(a), C + r * Math.sin(a)];
const radius = (pz) => R0 + ((R1 - R0) * Math.max(0, Math.min(100, pz))) / 100;

function sektor(a0, a1, r0, r1) {
  const [x0, y0] = punkt(a0, r1), [x1, y1] = punkt(a1, r1), [x2, y2] = punkt(a1, r0), [x3, y3] = punkt(a0, r0);
  const gross = a1 - a0 > Math.PI ? 1 : 0;
  return `M${x0.toFixed(1)},${y0.toFixed(1)} A${r1},${r1} 0 ${gross} 1 ${x1.toFixed(1)},${y1.toFixed(1)} ` +
    `L${x2.toFixed(1)},${y2.toFixed(1)} A${r0},${r0} 0 ${gross} 0 ${x3.toFixed(1)},${y3.toFixed(1)} Z`;
}

function umbrechen(text, max = 17) {
  const woerter = text.split(" "), zeilen = [""];
  for (const w of woerter) {
    const z = zeilen[zeilen.length - 1];
    if ((z + " " + w).trim().length > max && z) zeilen.push(w);
    else zeilen[zeilen.length - 1] = (z + " " + w).trim();
  }
  return zeilen.length > 2 ? [zeilen[0], zeilen[1] + " …"] : zeilen;
}

function beschriftung(daten, n) {
  return daten.map((d, i) => {
    const a = winkel(i + 0.5, n);
    const [x, y] = punkt(a, RL);
    const cos = Math.cos(a);
    const anker = Math.abs(cos) < 0.08 ? "middle" : cos > 0 ? "start" : "end";
    const zeilen = umbrechen(d.label);
    const dy0 = Math.sin(a) < -0.5 ? -(zeilen.length - 1) * 15 : Math.sin(a) > 0.5 ? 9 : -((zeilen.length - 1) * 7.5) + 4;
    return `<text x="${x.toFixed(1)}" y="${(y + dy0).toFixed(1)}" text-anchor="${anker}">` +
      zeilen.map((z, k) => `<tspan x="${x.toFixed(1)}" dy="${k ? 15 : 0}">${esc(z)}</tspan>`).join("") + `</text>`;
  }).join("");
}

function gitter(n) {
  return [25, 50, 75, 100].map((pz) => {
    const pts = Array.from({ length: n }, (_, i) => punkt(winkel(i + 0.5, n), radius(pz)).map((v) => v.toFixed(1)).join(",")).join(" ");
    return `<polygon class="gitter" points="${pts}"${pz === 100 ? "" : ' stroke-dasharray="2 3"'}/>`;
  }).join("") + `<text x="${C + 3}" y="${(C - radius(50) + 11).toFixed(1)}">50</text>` +
    `<text x="${C + 3}" y="${(C - radius(100) + 11).toFixed(1)}">100</text>`;
}

function treffer(daten, n) {
  return daten.map((d, i) =>
    `<path class="treffer" data-i="${i}" d="${sektor(winkel(i, n), winkel(i + 1, n), 0, R1 + 12)}"/>`).join("");
}

function radarSvg(daten, zwei) {
  const n = daten.length;
  let speichen = "";
  for (let i = 0; i < n; i++) {
    const [x, y] = punkt(winkel(i + 0.5, n), R1);
    const [x0, y0] = punkt(winkel(i + 0.5, n), R0);
    speichen += `<line class="achse" x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/>`;
  }
  const flaeche = (k) => {
    const pts = daten.map((d, i) => punkt(winkel(i + 0.5, n), radius(d.perzentil[k] ?? 0)));
    const poly = `<polygon class="f${k + 1}" points="${pts.map((q) => q.map((v) => v.toFixed(1)).join(",")).join(" ")}"/>`;
    const dots = pts.map((q, i) => (daten[i].perzentil[k] == null ? "" :
      `<circle class="p${k + 1}" cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="4.5"/>`)).join("");
    return poly + dots;
  };
  return `<svg viewBox="-60 -10 680 580" role="img" aria-label="Radar-Chart der Perzentile">` +
    gitter(n) + speichen + (zwei ? flaeche(1) : "") + flaeche(0) + beschriftung(daten, n) + treffer(daten, n) + `</svg>`;
}

function chartVerdrahten() {
  const tip = $("#chart_tip");
  const svg = document.querySelector("#chart_bereich svg");
  if (!tip || !svg || !profilAktuell) return;
  const p = profilAktuell.p, daten = p.chart;
  const wrap = document.querySelector("#chart_bereich .chart-wrap");
  svg.querySelectorAll(".treffer").forEach((el) => {
    el.addEventListener("mousemove", (ev) => {
      const d = daten[Number(el.dataset.i)];
      const zeile = (k, z) => `<div><span class="punkt s${k + 1}"></span>${esc(kurzName(z.name))}: ` +
        `<b>${d.perzentil[k] == null ? "keine Daten" : zahl(d.perzentil[k]) + ". Perzentil"}</b> ` +
        `(${statWert(d.wert[k], d.art)}${d.art === "p90" ? " pro 90" : ""})</div>`;
      tip.innerHTML = `<div><b>${esc(d.label)}</b></div><div class="hinweis">${esc(d.baustein)} · ${d.phase === "mit" ? "mit Ball" : "ohne Ball"}` +
        `${d.niedrig ? " · weniger ist besser" : ""}</div>` + zeile(0, p.spieler) + (p.vergleich ? zeile(1, p.vergleich) : "");
      tip.hidden = false;
      const box = wrap.getBoundingClientRect();
      let x = ev.clientX - box.left + 14, y = ev.clientY - box.top + 14;
      if (x + tip.offsetWidth > box.width) x = ev.clientX - box.left - tip.offsetWidth - 14;
      tip.style.left = x + "px";
      tip.style.top = y + "px";
    });
    el.addEventListener("mouseleave", () => { tip.hidden = true; });
  });
}

function profilEinsaetze(p, slot) {
  const e = p.einsaetze;
  if (!e) {
    return '<h3>Einsätze je Position</h3><p class="hinweis">Noch nicht erfasst. In FM27 „Leistung → Spiele“ des Spielers ' +
      'öffnen und oben „Spiele erfassen“ klicken.</p>';
  }
  const ziel = PLAN && PLAN.slots[slot] ? PLAN.slots[slot].fm_position : null;
  const zeilen = e.je_position.map((r) =>
    `<tr${r.position === ziel ? ' class="gesetzt"' : ""}><td>${esc(r.position ?? "–")}</td><td>${esc(r.rolle ?? "–")}</td>` +
    `<td class="num">${r.spiele}</td><td class="num">${zahl(r.minuten)}</td><td class="num">${r.note == null ? "–" : zahl(r.note, 2)}</td>` +
    `<td class="num">${r.tore}</td><td class="num">${r.vorlagen}</td><td class="num">${zahl(r.xg, 2)}</td></tr>`).join("");
  const spiele = e.spiele.map((g) =>
    `<tr><td>${esc(g.datum.split("-").reverse().join("."))}</td><td>${esc(g.wettbewerb ?? "")}</td>` +
    (g.eingesetzt
      ? `<td>${esc(g.position ?? "–")}</td><td>${esc(g.rolle_kurz ?? "–")}</td><td class="num">${zahl(g.minuten)}` +
        `${g.einwechslung ? ` <span class="tag">Einw ${g.einwechslung}</span>` : ""}${g.auswechslung ? ` <span class="tag">Ausw ${g.auswechslung}</span>` : ""}</td>` +
        `<td class="num">${g.note == null ? "–" : zahl(g.note, 1)}</td><td class="num">${g.tore}</td><td class="num">${g.vorlagen}</td><td class="num">${zahl(g.xg, 2)}</td>`
      : `<td colspan="7" class="hinweis">nicht eingesetzt</td>`) + `</tr>`).join("");
  const erkl = `Aus den erfassten Spielen (letzte 20, Stand ${e.erfasst_am.replace("T", " ")}).` +
    (ziel ? `\nHervorgehoben: Position dieses Slots (${ziel}).` : "");
  return `<h3>Einsätze je Position ${info(erkl)}</h3>` +
    `<div class="tabelle-wrap"><table><thead><tr><th>Position</th><th>Rolle</th><th class="num">Spiele</th><th class="num">Min.</th>` +
    `<th class="num">Ø Note</th><th class="num">Tore</th><th class="num">Vorl.</th><th class="num">xG</th></tr></thead><tbody>${zeilen}</tbody></table></div>` +
    `<details class="spiele"><summary>Einzelne Spiele (${e.spiele.length})</summary><div class="tabelle-wrap"><table><thead><tr><th>Datum</th><th>Wettb.</th><th>Pos.</th><th>Rolle</th>` +
    `<th class="num">Min.</th><th class="num">Note</th><th class="num">Tore</th><th class="num">Vorl.</th><th class="num">xG</th></tr></thead><tbody>${spiele}</tbody></table></div></details>`;
}

// Auf einen Blick: links Steckbrief, Mitte Attribute und Kennzahlen der Rolle, rechts Radar.
// Darunter: Einsätze, Score-Herleitung, alle Statistiken.
function profilHtml(p, slot) {
  // Jeder Bereich eine Karte (.karte), damit sich die Bereiche klar voneinander abheben
  return `<div class="profil-oben">${profilSeite(p, slot)}` +
    `<div class="p-stapel"><section class="karte">${profilAttribute(p.attribute)}</section>` +
    `<section class="karte">${profilKennzahlen(p)}</section></div>` +
    `<section class="p-radar karte">${profilVergleich(p, slot)}</section></div>` +
    `<div class="profil-unten"><section class="karte">${profilStatistiken(p)}</section>` +
    `<div class="p-stapel"><section class="karte">${profilEinsaetze(p, slot)}</section>` +
    `<section class="karte">${profilScores(p)}</section></div></div>`;
}

// ------------------------------------------------------------------ Spiele erfassen

let erfassung = null; // { bis, timer, bekannt }

async function erfassenSchritt(schnell) {
  const r = await api(`/api/spiele/erfassen?schnell=${schnell ? "true" : "false"}`, {});
  const neu = r.gespeichert.filter((g) => !erfassung.bekannt.has(g.uid));
  r.gespeichert.forEach((g) => erfassung.bekannt.add(g.uid));
  const offen = r.offen.length ? ` · ${r.offen.length} Listen nicht eindeutig zuordenbar` : "";
  meldung(`Erfassung läuft (${r.modus === "quick" ? "schnell" : "voller Durchlauf"}, ${zahl(r.sekunden, 1)} s): ` +
    `${r.stand.spieler} Spieler erfasst${neu.length ? ", neu: " + neu.map((g) => kurzName(g.name)).join(", ") : ""}${offen}. ` +
    `In FM27 durch die Leistungsbildschirme blättern; „Erfassung stoppen“ beendet.`);
  if (META) META.einsaetze = r.stand;
  if (neu.length) planAnfordern();
}

function erfassungStoppen(text) {
  if (!erfassung) return;
  clearTimeout(erfassung.timer);
  erfassung = null;
  $("#erfassen").textContent = "Spiele erfassen";
  meldung(text || "");
  metaHolen().catch((e) => meldung(e.message, true));
}

async function erfassungStarten() {
  erfassung = { bis: Date.now() + 15 * 60 * 1000, timer: null, bekannt: new Set() };
  $("#erfassen").textContent = "Erfassung stoppen";
  meldung("Lese alle Spiellisten aus FM27 (voller Durchlauf, etwa eine Minute) …");
  try {
    await erfassenSchritt(false);
  } catch (e) {
    return erfassungStoppen(`Erfassen fehlgeschlagen: ${e.message}`);
  }
  const weiter = async () => {
    if (!erfassung) return;
    if (Date.now() > erfassung.bis) return erfassungStoppen("Erfassung nach 15 Minuten beendet.");
    try {
      await erfassenSchritt(true);
    } catch (e) {
      meldung(`Erfassen: ${e.message}`, true);
    }
    if (erfassung) erfassung.timer = setTimeout(weiter, 4000);
  };
  erfassung.timer = setTimeout(weiter, 4000);
}

// ------------------------------------------------------------------ Spielersuche

const SUCHE_STANDARD = { text: "", min_minuten: 900, eigene: true, nur_suche: false, nur_volle_daten: false };
let sucheTimer = null;
let sucheNr = 0;

function sucheZustand() {
  zustand.suche = { ...SUCHE_STANDARD, ...(zustand.suche || {}) };
  return zustand.suche;
}

function sucheSlot() {
  const slots = Object.keys(META.formationen[zustand.formation].slots);
  const w = sucheZustand().slot;
  return slots.includes(w) ? w : aktiverSlot && slots.includes(aktiverSlot) ? aktiverSlot : slots[0];
}

function sucheOeffnen() {
  if (!META) return;
  const z = sucheZustand();
  const form = META.formationen[zustand.formation].slots;
  const wahl = rollenWahl();
  if (aktiverSlot && form[aktiverSlot]) z.slot = aktiverSlot; // aktiver Slot gibt die Rolle vor
  const slot = sucheSlot();
  $("#s_slot").innerHTML = Object.entries(form).map(([sn, m]) =>
    `<option value="${esc(sn)}"${sn === slot ? " selected" : ""}>${esc(m.label)} – ${esc(wahl[sn].mit)} / ${esc(wahl[sn].ohne)}</option>`).join("");
  optionen(document.querySelector('[data-s="min_stufe"]'), META.stufen, z.min_stufe, "alle");
  $("#s_text").value = z.text || "";
  document.querySelectorAll("[data-s]").forEach((el) => {
    const v = z[el.dataset.s];
    if (el.type === "checkbox") el.checked = !!v;
    else el.value = v ?? "";
  });
  $("#s_nur_suche_box").hidden = META.stand.quelle !== "live";
  $("#suche").hidden = false;
  $("#s_text").focus();
  $("#s_text").select();
  sucheHolen();
}

function sucheSchliessen() {
  sucheNr++;
  $("#suche").hidden = true;
}

function sucheLesen() {
  const z = sucheZustand();
  z.text = $("#s_text").value;
  z.slot = $("#s_slot").value;
  document.querySelectorAll("[data-s]").forEach((el) => {
    const k = el.dataset.s;
    if (el.type === "checkbox") z[k] = el.checked;
    else if (el.type === "number") z[k] = el.value === "" ? null : Number(el.value);
    else z[k] = el.value === "" ? null : el.value;
  });
  if (z.min_minuten == null) z.min_minuten = SUCHE_STANDARD.min_minuten;
  speichern();
  return z;
}

function sucheAnfordern(ms = 250) {
  clearTimeout(sucheTimer);
  sucheTimer = setTimeout(sucheHolen, ms);
}

async function sucheHolen() {
  const nr = ++sucheNr;
  const z = sucheLesen();
  const slot = z.slot;
  const wahl = rollenWahl()[slot];
  $("#suche_info").textContent = "sucht …";
  try {
    const r = await api("/api/suche", {
      mit: wahl.mit, ohne: wahl.ohne, text: z.text, min_alter: z.min_alter, max_alter: z.max_alter,
      max_wert_mio: z.max_wert_mio, min_stufe: z.min_stufe, min_minuten: z.min_minuten, eigene: z.eigene,
      nur_suche: META.stand.quelle === "live" && z.nur_suche, nur_volle_daten: z.nur_volle_daten,
      gewichtung: (zustand.filter && zustand.filter.gewichtung) || null,
    });
    if (nr !== sucheNr) return;
    sucheZeichnen(r, slot);
  } catch (e) {
    if (nr === sucheNr) {
      $("#suche_info").textContent = "";
      $("#suche_ergebnis").innerHTML = `<p class="meldung fehler">${esc(e.message)}</p>`;
    }
  }
}

function sucheZeichnen(r, slot) {
  const ps = PLAN && PLAN.slots[slot];
  const basis = ps ? ps.basis : null;
  const gesetzt = ps ? ps.gesetzt : null;
  const zeilen = r.treffer.map((z) => ({ ...z, delta: basis == null || z.paar_gew == null ? null : z.paar_gew - basis }));
  const gw = r.gewertet_als;
  const alias = [r.mit !== gw.mit ? `mit Ball gewertet wie ${gw.mit}` : "", r.ohne !== gw.ohne ? `ohne Ball gewertet wie ${gw.ohne}` : ""];
  $("#s_rollen").textContent = alias.filter(Boolean).join(" · ");
  $("#suche_info").textContent = `${zahl(r.n_treffer)} mit Score` + (r.n_treffer > r.limit ? `, die besten ${r.limit} gezeigt` : "") +
    (basis != null ? ` · Δ gegenüber dem Gesetzten (${zahl(basis)})` : "");
  const spalten = [
    SP_NAME,
    { k: "club", l: "Verein", f: (z) => esc(z.club ?? "–") },
    { k: "liga_stufe", l: "Liga", f: (z) => esc(z.liga_stufe ?? "–"), titel: "Ansehen der Liga", sort: (z) => (z.liga_stufe ? META.stufen.indexOf(z.liga_stufe) : null) },
    { k: "position", l: "Pos.", f: (z) => esc(z.position ?? "–") },
    { k: "age", l: "Alter", num: true },
    { k: "minutes", l: "Min.", num: true, f: (z) => zahl(z.minutes) },
    ...SP_SCORES,
    { k: "delta", l: "Δ", num: true, titel: "Abstand zum gesetzten Spieler dieses Slots",
      f: (z) => { if (z.delta == null) return "–"; const d = Math.round(z.delta) || 0; return `<b>${d > 0 ? "+" : ""}${zahl(d)}</b>`; } },
    { k: "value", l: "Marktwert", num: true, f: (z) => spanne(z.value, z.value_min, z.value_max), sort: (z) => z.value ?? z.value_max },
    { k: "wage", l: "Gehalt/J.", num: true, f: (z) => spanne(z.wage, z.wage_min, z.wage_max), sort: (z) => z.wage ?? z.wage_max },
    { k: "contract_end", l: "Vertrag" },
  ];
  const erkl = "Score = Paar-Score des Rollenpaars × Liga-Gewicht (0 = Schlecht, 50 = OK, 100 = Gut), Rollen wie im gewählten Slot. " +
    "Fremde Marktwerte und Gehälter sind Scouting-Spannen. Zeile anklicken öffnet das Profil (Vergleich: gesetzter Spieler), Spaltenkopf sortiert.";
  const el = $("#suche_ergebnis");
  el.innerHTML = `<section class="karte"><h3>Treffer ${info(erkl)}</h3><div id="s_treffer"></div></section>` +
    (r.ohne_score.length
      ? `<section class="karte"><h3>Gefunden, aber ohne Score (${r.ohne_score.length}) ${info("Passen zum Suchtext, " +
        "sind für diese Rollen aber nicht bewertbar; Grund in der letzten Spalte.")}</h3><div id="s_ohne"></div></section>`
      : "");
  $("#s_treffer").appendChild(zeilen.length
    ? tabelle(spalten, zeilen, { gesetzt, beiKlick: (uid) => profilOeffnen(uid, undefined, slot) })
    : Object.assign(document.createElement("p"), { className: "hinweis", textContent: "Keine Spieler mit Score für diese Kriterien." }));
  if (r.ohne_score.length) {
    $("#s_ohne").appendChild(tabelle([
      SP_NAME,
      { k: "club", l: "Verein", f: (z) => esc(z.club ?? "–") },
      { k: "position", l: "Pos.", f: (z) => esc(z.position ?? "–") },
      { k: "age", l: "Alter", num: true },
      { k: "minutes", l: "Min.", num: true, f: (z) => zahl(z.minutes) },
      { k: "grund", l: "Grund", f: (z) => `<span class="hinweis">${esc(z.grund)}</span>` },
    ], r.ohne_score, {}));
  }
}

function sucheVerdrahten() {
  $("#suche_auf").addEventListener("click", sucheOeffnen);
  $("#suche_zu").addEventListener("click", sucheSchliessen);
  $("#suche").addEventListener("click", (e) => { if (e.target.id === "suche") sucheSchliessen(); });
  $("#s_text").addEventListener("input", () => sucheAnfordern(300));
  $("#s_slot").addEventListener("change", () => sucheAnfordern(0));
  document.querySelectorAll("[data-s]").forEach((el) => el.addEventListener("change", () => sucheAnfordern(0)));
  $("#s_reset").addEventListener("click", () => {
    zustand.suche = { ...SUCHE_STANDARD, slot: $("#s_slot").value };
    speichern();
    sucheOeffnen();
  });
  // Taste "/" öffnet die Suche (nicht beim Tippen in Feldern)
  document.addEventListener("keydown", (e) => {
    const tippt = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement?.tagName || "");
    if (e.key === "/" && !tippt && $("#suche").hidden && $("#profil").hidden) {
      e.preventDefault();
      sucheOeffnen();
    }
  });
}

// ------------------------------------------------------------------ Ablauf

function planAnfordern() {
  clearTimeout(planTimer);
  planTimer = setTimeout(planHolen, 200);
}

async function planHolen() {
  const nr = ++planNr;
  zustand.filter = filterLesen();
  speichern();
  try {
    const plan = await api("/api/plan", {
      formation: zustand.formation, slots: rollenWahl(), filter: zustand.filter,
      aufstellung: zustand.aufstellung === "score" ? "score" : "einsaetze",
    });
    if (nr !== planNr) return; // überholt
    PLAN = plan;
    meldung("");
    slotsAktualisieren();
    panelZeichnen();
  } catch (e) {
    meldung(e.message, true);
  }
}

async function metaHolen() {
  META = await api("/api/meta");
  steuerungAufbauen();
  feldGroesse();
  feldZeichnen();
  await planHolen();
}

const THEMES = { auto: "Auto", light: "Hell", dark: "Dunkel" };
function themeSetzen(t) {
  zustand.theme = t;
  speichern();
  if (t === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  $("#theme").textContent = `Design: ${THEMES[t]}`;
}

function init() {
  infoVerdrahten();
  sucheVerdrahten();
  themeSetzen(THEMES[zustand.theme] ? zustand.theme : "auto");
  $("#theme").addEventListener("click", () => {
    const folge = Object.keys(THEMES);
    themeSetzen(folge[(folge.indexOf(zustand.theme) + 1) % folge.length]);
  });
  $("#formation").addEventListener("change", (e) => {
    zustand.formation = e.target.value;
    aktiverSlot = null;
    speichern();
    feldZeichnen();
    panelZeichnen();
    planAnfordern();
  });
  document.querySelectorAll("[data-f]").forEach((el) => el.addEventListener("change", planAnfordern));
  $("#aufstellung").addEventListener("change", (e) => {
    zustand.aufstellung = e.target.value;
    speichern();
    planAnfordern();
  });
  $("#filter_reset").addEventListener("click", () => {
    zustand.filter = {};
    speichern();
    steuerungAufbauen();
    planAnfordern();
  });
  $("#erfassen").addEventListener("click", () => (erfassung ? erfassungStoppen() : erfassungStarten()));
  $("#neu_laden").addEventListener("click", async () => {
    const knopf = $("#neu_laden");
    knopf.disabled = true;
    meldung("Lade Daten neu …");
    try {
      await api("/api/reload", {
        quelle: $("#quelle").value,
        pool_min_stufe: $("#pool_min_stufe").value,
        anker_min_n: Number($("#anker_min_n").value) || 100,
      });
      await metaHolen();
    } catch (e) {
      meldung(e.message, true);
      $("#quelle").value = META.einstellungen.quelle;
    } finally {
      knopf.disabled = false;
    }
  });
  window.addEventListener("resize", feldGroesse);
  $("#profil_zu").addEventListener("click", profilSchliessen);
  $("#profil").addEventListener("click", (e) => {
    if (e.target.id === "profil") profilSchliessen();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("#profil").hidden) profilSchliessen();
    else if (!$("#suche").hidden) sucheSchliessen();
  });
  metaHolen().catch((e) => meldung(e.message, true));
}

init();
