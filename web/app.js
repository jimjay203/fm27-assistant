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
  $("#stand").textContent = teile.join(" · ");
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
  const wahl = rollenWahl();
  for (const [sn, s] of Object.entries(form.slots)) {
    const el = document.createElement("div");
    el.className = "slot" + (sn === aktiverSlot ? " aktiv" : "");
    el.style.left = s.x + "%";
    el.style.top = s.y + "%";
    el.dataset.slot = sn;
    const sel = (phase) =>
      `<select data-phase="${phase}" title="Rolle ${phase} Ball">` +
      s.optionen[phase].map((r) => `<option${r === wahl[sn][phase] ? " selected" : ""}>${esc(r)}</option>`).join("") +
      `</select>`;
    el.innerHTML =
      `<div class="kopf"><span>${esc(sn)}</span><span class="badge null" data-badge>…</span></div>` +
      sel("mit") + sel("ohne") +
      `<div class="spieler" data-spieler><span class="leer">…</span></div>`;
    el.addEventListener("click", (ev) => {
      if (ev.target.tagName === "SELECT" || ev.target.tagName === "OPTION") return;
      aktiverSlot = sn;
      document.querySelectorAll(".slot").forEach((x) => x.classList.toggle("aktiv", x.dataset.slot === sn));
      panelZeichnen();
    });
    el.querySelectorAll("select").forEach((se) =>
      se.addEventListener("change", () => {
        wahl[sn][se.dataset.phase] = se.value;
        speichern();
        planAnfordern();
      }),
    );
    feld.appendChild(el);
  }
}

function slotsAktualisieren() {
  if (!PLAN) return;
  for (const [sn, s] of Object.entries(PLAN.slots)) {
    const el = document.querySelector(`.slot[data-slot="${CSS.escape(sn)}"]`);
    if (!el) continue;
    const g = s.eigene.find((z) => z.uid === s.gesetzt);
    const warn = s.luecken.some((l) => l.entfaellt) || s.luecken.some((l) => l.abdeckung != null);
    el.querySelector("[data-spieler]").innerHTML = g
      ? `<span class="name" title="${esc(g.name)}">${esc(g.name)}</span>${score(g.paar_gew)}`
      : `<span class="leer">kein eigener Spieler bewertbar</span>`;
    const b = el.querySelector("[data-badge]");
    const n = s.n_verbesserungen;
    const best = s.verbesserungen[0];
    b.className = "badge" + (n ? "" : " null");
    b.textContent = n ? `+${n}${best && best.delta != null ? " · Δ " + zahl(best.delta) : ""}` : "0";
    b.title = n ? `${n} Kandidaten besser als der gesetzte Spieler` : "keine Verbesserung in den Kandidaten";
    el.querySelector(".kopf span").innerHTML = esc(sn) + (warn ? ' <span class="warn" title="Datenlücken, siehe Panel">!</span>' : "");
  }
}

// ------------------------------------------------------------------ Panel

function tabelle(spalten, zeilen, { gesetzt, sortierung } = {}) {
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
      tr.addEventListener("click", () => {
        const next = tr.nextElementSibling;
        if (next && next.classList.contains("detail")) return next.remove();
        const z = zeilen.find((x) => x.uid === tr.dataset.uid);
        tr.insertAdjacentHTML("afterend", `<tr class="detail"><td colspan="${spalten.length}">${bausteinText(z)}</td></tr>`);
      }),
    );
  };
  zeichnen();
  return wrap;
}

function bausteinText(z) {
  const teil = (phase) => {
    const b = z.bausteine?.[phase] || {};
    const e = Object.entries(b);
    return e.length ? e.map(([k, v]) => `${esc(k)} ${score(v)}`).join(", ") : "keine Bausteine bewertbar";
  };
  return `<b>mit Ball</b> (${zahl(z.mit)}): ${teil("mit")}<br><b>ohne Ball</b> (${zahl(z.ohne)}): ${teil("ohne")}` +
    `<br>${esc(z.position || "")} · ${esc(z.league || "")} · Datenbasis ${esc(z.datenbasis || "–")}` +
    (z.liga_gewicht != null ? ` · Liga-Gewicht ${zahl(z.liga_gewicht, 2)}` : "");
}

const SP_NAME = { k: "name", l: "Name", f: (z) => esc(z.name) + (STATUS[z.eigen] ? `<span class="tag">${STATUS[z.eigen]}</span>` : "") };
const SP_SCORES = [
  { k: "mit", l: "mit", num: true, f: (z) => score(z.mit), titel: "Rolle mit Ball" },
  { k: "ohne", l: "ohne", num: true, f: (z) => score(z.ohne), titel: "Rolle ohne Ball" },
  { k: "paar_gew", l: "Score", num: true, f: (z) => score(z.paar_gew), titel: "Paar-Score × Liga-Gewicht" },
  { k: "vs_top", l: "vs Top", num: true, f: (z) => zahl(z.vs_top), titel: "50 = Median der Topclub-Spieler" },
];
const SP_EIGENE = [
  SP_NAME,
  { k: "age", l: "Alter", num: true },
  { k: "minutes", l: "Min.", num: true, f: (z) => zahl(z.minutes) },
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
  const zeilen = s.luecken.map((l) => {
    if (l.abdeckung != null) return `<li>${esc(l.rolle)}: nur ${zahl(l.abdeckung * 100)} % des Baustein-Gewichts bewertbar</li>`;
    const stats = Object.entries(l.statistiken).map(([k, v]) => `${esc(k)} (${esc(v)})`).join(", ");
    return `<li>${esc(l.rolle)} · ${esc(l.baustein)}${l.entfaellt ? " entfällt" : " teilweise"}: ${stats}</li>`;
  });
  return zeilen.length ? `<h3>Datenlücken</h3><ul class="luecken">${zeilen.join("")}</ul>` : "";
}

function panelZeichnen() {
  const p = $("#panel");
  if (!PLAN || !aktiverSlot || !PLAN.slots[aktiverSlot]) {
    p.innerHTML = '<p class="leer">Slot anklicken, um Ranglisten und Verbesserungen zu sehen.</p>';
    return;
  }
  const s = PLAN.slots[aktiverSlot];
  const gw = s.gewertet_als;
  const alias = (n, z) => (n === z ? esc(n) : `${esc(n)} <span class="tag">gewertet wie ${esc(z)}</span>`);
  p.innerHTML =
    `<h2>${esc(aktiverSlot)}</h2>` +
    `<div class="rollen">mit Ball: ${alias(s.mit, gw.mit)} (Verlässlichkeit ${esc(s.verlaesslichkeit.mit)}) · ` +
    `ohne Ball: ${alias(s.ohne, gw.ohne)} (Verlässlichkeit ${esc(s.verlaesslichkeit.ohne)}) · ` +
    `Pool n = ${s.n_pool.mit}${s.n_pool.ohne !== s.n_pool.mit ? " / " + s.n_pool.ohne : ""}</div>` +
    s.hinweise.map((h) => `<p class="hinweis">Hinweis: ${esc(h)}</p>`).join("") +
    lueckenHtml(s) +
    `<h3>Eigene Spieler (${s.n_eigene} bewertet)</h3><div id="t_eigene"></div>` +
    `<h3>Verbesserungen (${s.n_verbesserungen} von ${s.n_kandidaten} Kandidaten${s.basis != null ? ", besser als " + zahl(s.basis) : ""})</h3>` +
    `<div id="t_kand"></div>` +
    (s.ohne_wertung.length
      ? `<h3>Eigene ohne Wertung</h3><p class="hinweis">${s.ohne_wertung
          .map((o) => `${esc(o.name)} (${esc(o.grund)}${STATUS[o.eigen] ? ", " + STATUS[o.eigen] : ""})`).join(" · ")}</p>`
      : "");
  $("#t_eigene").appendChild(s.eigene.length
    ? tabelle(SP_EIGENE, s.eigene, { gesetzt: s.gesetzt })
    : Object.assign(document.createElement("p"), { className: "hinweis", textContent: "Kein eigener Spieler bewertbar." }));
  $("#t_kand").appendChild(s.verbesserungen.length
    ? tabelle(SP_KAND, s.verbesserungen)
    : Object.assign(document.createElement("p"), { className: "hinweis", textContent: "Kein Kandidat übertrifft den gesetzten Spieler (mit diesen Filtern)." }));
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
    const plan = await api("/api/plan", { formation: zustand.formation, slots: rollenWahl(), filter: zustand.filter });
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
  feldZeichnen();
  await planHolen();
}

function init() {
  $("#formation").addEventListener("change", (e) => {
    zustand.formation = e.target.value;
    aktiverSlot = null;
    speichern();
    feldZeichnen();
    panelZeichnen();
    planAnfordern();
  });
  document.querySelectorAll("[data-f]").forEach((el) => el.addEventListener("change", planAnfordern));
  $("#filter_reset").addEventListener("click", () => {
    zustand.filter = {};
    speichern();
    steuerungAufbauen();
    planAnfordern();
  });
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
  metaHolen().catch((e) => meldung(e.message, true));
}

init();
