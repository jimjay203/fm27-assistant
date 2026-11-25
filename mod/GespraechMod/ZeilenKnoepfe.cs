// Gesprächs-Spalte in Spielerlisten: je Zeile eine eigene Zelle neben der Spieler-Zelle mit
// Lob F L V T (grün) | Kritik F L V T (rot). Klick löst über ZeilenMenue das Gespräch für die Zeile aus, in der der
// Button gerade steckt (Tabellenzeilen werden beim Scrollen wiederverwendet, daher Ziel erst beim Klick bestimmen).
//
// Verfügbarkeit: im Hintergrund wird je sichtbarer Zeile unsichtbar das Kontextmenü gelesen; nicht angebotene
// Gespräche (Abklingzeit des Spiels) werden grau und deaktiviert. Cache je Spielername (TTL), nach einem Gespräch
// wird der Spieler neu geprüft.
//
// Platzierung: vom Namensfeld-Container ("player-name-button-template") aufwärts die Zelle suchen, deren Eltern-
// element mehrere gleich hohe Zellen nebeneinander hat (= Zeile); dahinter die eigene Zelle einfügen. Gelingt das
// nicht, kommt die Leiste wie in v0.8 hinter das Namensfeld. Taste SpalteKey blendet die Spalte ein/aus.
//
// Nur eigener Verein: eine Tabelle (StreamedTable) bleibt ohne Spalte, bis die erste geprüfte Zeile ein Menü mit
// Aktionen hat, die das Spiel nur eigenen Spielern anbietet (Training, Kader, Lob/Kritik; Erkennung.cs). Sonst gilt
// die Tabelle als fremd (Scouting, Spielerdatenbank usw.): Leisten werden entfernt, dort wird nicht mehr geprüft.

using System;
using System.Collections.Generic;
using Il2CppInterop.Runtime;
using UnityEngine;
using UnityEngine.UIElements;

namespace GespraechMod
{
    internal static class ZeilenKnoepfe
    {
        internal const string LEISTE = "gespraech-leiste";
        internal const string VORLAGE = "player-name-button-template";
        private const float TTL = 120f;

        // Kürzel, Gesprächstyp (Erkennung.cs); Tooltip = Menütext der Spielsprache
        private static readonly (string kurz, string typ)[] Typen =
        {
            ("F", "lob_form"), ("L", "lob_leistung"), ("V", "lob_verhalten"), ("T", "lob_training"),
            ("F", "kritik_form"), ("L", "kritik_leistung"), ("V", "kritik_verhalten"), ("T", "kritik_training"),
        };

        private static readonly Color Gruen = new(0.16f, 0.55f, 0.27f, 1f);
        private static readonly Color Rot = new(0.70f, 0.20f, 0.18f, 1f);
        private static readonly Color Grau = new(0.28f, 0.28f, 0.28f, 1f);
        private static readonly Color GrauText = new(0.55f, 0.55f, 0.55f, 1f);

        private sealed class Leiste
        {
            internal VisualElement Element;
            internal Button[] Knoepfe;
            internal string Spieler;       // zuletzt angezeigter Spieler (Zeilen werden recycelt)
            internal int NachSpieler = -1; // Index direkt nach der Spieler-Zelle (nur als eigene Zelle)
            internal IntPtr Tabelle;       // StreamedTable (oder Elternelement), für "nur eigener Verein"
            internal float RuheBis;        // nach einer Prüfung ohne Ergebnis erst später wieder
        }

        private static int s_prueflog;

        // Zeile wirklich auf dem Bildschirm: kein Vorfahr ausgeblendet, Fläche > 0
        private static bool ZeileSichtbar(VisualElement zeile)
        {
            if (zeile == null) return false;
            try
            {
                for (var x = zeile; x != null; x = x.parent)
                {
                    var rs = x.resolvedStyle;
                    if (rs.display == DisplayStyle.None || rs.visibility == Visibility.Hidden || rs.opacity <= 0.01f) return false;
                }
                var wb = zeile.worldBound;
                return !float.IsNaN(wb.width) && wb.width > 1f && wb.height > 1f;
            }
            catch { return false; }
        }

        private const int EIGEN = 1, FREMD = 2;
        private static readonly Dictionary<IntPtr, int> s_tabellen = new();

        private static int TabellenStand(IntPtr t) => s_tabellen.TryGetValue(t, out var v) ? v : 0;

        private static IntPtr TabelleVon(VisualElement e) => TabellenElement(e)?.Pointer ?? e?.Pointer ?? IntPtr.Zero;

        private static VisualElement TabellenElement(VisualElement e)
        {
            for (var x = e; x != null; x = x.parent)
                if (Info.Typ(x) == "SI.Bindable.StreamedTable") return x;
            return null;
        }

        // Whitelist (Config NurTabellen): nur Tabellen mit diesen Elementnamen bekommen die Spalte.
        // Nicht passende Tabellen gelten sofort als fremd. Jede neue Tabelle wird einmal mit Namen geloggt.
        private static bool TabelleErlaubt(VisualElement zeile, IntPtr tab)
        {
            var t = TabellenElement(zeile);
            string name = t?.name ?? "";
            var liste = (Plugin.NurTabellen.Value ?? "").Split(new[] { ',', '|' }, StringSplitOptions.RemoveEmptyEntries);
            bool ok = liste.Length == 0;
            foreach (var n in liste) if (n.Trim() == name) ok = true;
            if (s_geloggt.Add("tabelle:" + tab))
                Plugin.L.LogInfo($"[Gespraech] Tabelle '{name}' {(ok ? "erlaubt" : "nicht in NurTabellen")}: {ZeilenMenue.Kette(t ?? zeile, 10)}");
            return ok;
        }

        private static void Sichtbarkeit(Leiste l)
        {
            bool an = Plugin.Knoepfe.Value && !s_imSpiel && TabellenStand(l.Tabelle) == EIGEN;
            try { l.Element.style.display = new StyleEnum<DisplayStyle>(an ? DisplayStyle.Flex : DisplayStyle.None); } catch { }
        }

        // Ergebnis einer Prüfung: Tabelle einstufen (erste Prüfung entscheidet)
        private static void Einstufen(IntPtr tab, bool eigen)
        {
            if (TabellenStand(tab) != 0) return;
            s_tabellen[tab] = eigen ? EIGEN : FREMD;
            var betroffen = new List<KeyValuePair<IntPtr, Leiste>>();
            foreach (var kv in s_leisten) if (kv.Value.Tabelle == tab) betroffen.Add(kv);
            foreach (var kv in betroffen)
            {
                var l = kv.Value;
                if (eigen)
                {
                    Sichtbarkeit(l);
                    if (l.NachSpieler >= 0 && l.Element.parent != null) KopfEinfuegen(l.Element.parent, l.NachSpieler);
                }
                else
                {
                    try { l.Element.parent?.Remove(l.Element); } catch { }
                    s_leisten.Remove(kv.Key);
                }
            }
            Plugin.L.LogInfo($"[Gespraech] Tabelle {(eigen ? "eigener Verein: Spalte an" : "fremd: keine Spalte")} ({betroffen.Count} Zeilen)");
        }

        private sealed class Kopf
        {
            internal VisualElement Element;
            internal int NachSpieler;
        }

        private sealed class Stand
        {
            internal HashSet<string> Angebote;  // null = noch nicht geprüft
            internal float Zeit;
        }

        private static float s_naechsteSuche;
        private static readonly Dictionary<IntPtr, Leiste> s_leisten = new();
        private static readonly Dictionary<string, Stand> s_stand = new();
        private static readonly HashSet<string> s_geloggt = new();
        private static readonly Dictionary<IntPtr, Kopf> s_koepfe = new();  // Kopfzeile -> eingefügte Kopfzelle

        // Stellung der Spalte: 0 = nach "Spieler", 1 = ganz vorne, 2 = ganz hinten
        private static readonly string[] Stellungen = { "nach Spieler", "ganz vorne", "ganz hinten" };

        private static int Ziel(VisualElement eltern, int nachSpieler)
        {
            int n = eltern.childCount;  // ohne die eigene Zelle (vorher entfernt)
            return Plugin.SpaltenStellung.Value switch
            {
                1 => 0,
                2 => n,
                _ => Math.Min(Math.Max(nachSpieler, 0), n),
            };
        }

        private static void Setzen(VisualElement el, int nachSpieler)
        {
            var e = el.parent;
            if (e == null) return;
            e.Remove(el);
            e.Insert(Ziel(e, nachSpieler), el);
        }

        internal static void StellungWechseln()
        {
            Plugin.SpaltenStellung.Value = (Plugin.SpaltenStellung.Value + 1) % Stellungen.Length;
            foreach (var l in s_leisten.Values)
                if (l.NachSpieler >= 0) try { Setzen(l.Element, l.NachSpieler); } catch { }
            foreach (var k in s_koepfe.Values)
                try { Setzen(k.Element, k.NachSpieler); } catch { }
            Plugin.L.LogInfo($"[Gespraech] Spalte {Stellungen[Plugin.SpaltenStellung.Value]}");
        }
        internal const string KOPF = "gespraech-kopf";

        private static IEnumerable<VisualElement> Wurzeln()
        {
            var docs = UnityEngine.Object.FindObjectsOfType(Il2CppType.Of<UIDocument>());
            foreach (var o in docs)
            {
                var r = o.TryCast<UIDocument>()?.rootVisualElement;
                if (r != null) yield return r;
            }
        }

        private static void Sammeln(VisualElement e, List<VisualElement> treffer, int tiefe = 0)
        {
            if (e == null || tiefe > 80) return;
            if (e.name == VORLAGE) { treffer.Add(e); return; }
            int n = e.childCount;
            for (int i = 0; i < n; i++) Sammeln(e[i], treffer, tiefe + 1);
        }

        // Zelle + Zeile finden: Vorfahr, dessen Eltern mehrere Kinder nebeneinander in gleicher Höhe haben
        private static (VisualElement zelle, VisualElement zeile) ZelleUndZeile(VisualElement v)
        {
            var c = v;
            for (int i = 0; c != null && i < 10; i++, c = c.parent)
            {
                var p = c.parent;
                if (p == null) break;
                var lc = c.layout;
                var lp = p.layout;
                if (float.IsNaN(lc.height) || lc.height < 4) continue;
                if (p.childCount >= 4 && Math.Abs(lp.height - lc.height) < 3 && lp.width > lc.width * 2.5f)
                    return (c, p);
            }
            return (null, null);
        }

        internal static void Umschalten()
        {
            Plugin.Knoepfe.Value = !Plugin.Knoepfe.Value;
            AlleSichtbarkeiten();
            Plugin.L.LogInfo($"[Gespraech] Spalte {(Plugin.Knoepfe.Value ? "an" : "aus")}");
        }

        private static void AlleSichtbarkeiten()
        {
            var d = new StyleEnum<DisplayStyle>(Plugin.Knoepfe.Value && !s_imSpiel ? DisplayStyle.Flex : DisplayStyle.None);
            foreach (var l in s_leisten.Values) Sichtbarkeit(l);
            foreach (var k in s_koepfe.Values)
                try { k.Element.style.display = d; } catch { }
        }

        // Während eines Spiels (aktives FM.Match.Match-Objekt, wie bei DugoutQuiet) Spalte aus, keine Prüfungen
        private static bool s_imSpiel;
        private static float s_naechsterSpielCheck;

        private static void SpielPruefen()
        {
            if (Time.unscaledTime < s_naechsterSpielCheck) return;
            s_naechsterSpielCheck = Time.unscaledTime + 1f;
            bool spiel = false;
            if (Plugin.ImSpielAusblenden.Value)
                try
                {
                    var o = UnityEngine.Object.FindObjectOfType(Il2CppType.Of<FM.Match.Match>());
                    spiel = o != null && o.TryCast<Behaviour>()?.isActiveAndEnabled == true;
                }
                catch { }
            if (spiel == s_imSpiel) return;
            s_imSpiel = spiel;
            if (spiel) ZeilenMenue.PruefungAbbrechen();
            AlleSichtbarkeiten();
            Plugin.L.LogInfo($"[Gespraech] {(spiel ? "Spiel läuft: Spalte aus" : "Kein Spiel: Spalte wieder an")}");
        }

        internal static void Update()
        {
            if (!Plugin.Knoepfe.Value) return;
            SpielPruefen();
            if (s_imSpiel) return;
            if (Time.unscaledTime >= s_naechsteSuche)
            {
                s_naechsteSuche = Time.unscaledTime + 1f;
                Einfuegen();
            }
            Aktualisieren();
            Pruefen();
        }

        private static void Einfuegen()
        {
            var vorlagen = new List<VisualElement>();
            foreach (var w in Wurzeln())
            {
                Sammeln(w, vorlagen);
            }
            // tote Leisten (Element nicht mehr im Baum) vergessen
            var weg = new List<IntPtr>();
            foreach (var kv in s_leisten)
                try { if (kv.Value.Element.panel == null) weg.Add(kv.Key); } catch { weg.Add(kv.Key); }
            foreach (var k in weg) s_leisten.Remove(k);

            bool kopfGeprueft = false;
            foreach (var v in vorlagen)
            {
                try
                {
                    var (zelle, zeile) = ZelleUndZeile(v);
                    if (zeile == null) continue;  // nur echte Tabellenzeilen (keine Leiste hinter Namen in anderen Widgets)
                    VisualElement ziel = zeile;
                    VisualElement nach = zelle ?? v;
                    if (ziel == null || float.IsNaN(v.layout.height)) continue;
                    var tab = TabelleVon(ziel);
                    if (TabellenStand(tab) == FREMD) continue;
                    if (TabellenStand(tab) == 0 && !TabelleErlaubt(ziel, tab)) { s_tabellen[tab] = FREMD; continue; }
                    VisualElement vorhanden = null;
                    for (int i = 0; i < ziel.childCount; i++)
                        if (ziel[i].name == LEISTE) { vorhanden = ziel[i]; break; }
                    if (vorhanden != null)
                    {
                        // Kopfzelle je Durchlauf einmal nachprüfen (FM baut die Kopfzeile teils neu)
                        if (zeile != null && !kopfGeprueft && TabellenStand(tab) == EIGEN && s_leisten.TryGetValue(vorhanden.Pointer, out var lv) && lv.NachSpieler >= 0)
                        {
                            kopfGeprueft = true;
                            KopfEinfuegen(zeile, lv.NachSpieler);
                        }
                        continue;
                    }
                    if (s_geloggt.Add(zeile != null ? "zelle" : "name"))
                    {
                        Plugin.L.LogInfo($"[Gespraech] Platzierung: {(zeile != null ? "eigene Zelle" : "hinter Namensfeld")}; " +
                            $"Struktur ab Namensfeld:{ZeilenMenue.Struktur(v, 14)}");
                    }
                    int index = ziel.IndexOf(nach) + 1;
                    var l = Bauen(zeile != null, zelle?.layout.height ?? 0);
                    l.Tabelle = tab;
                    Sichtbarkeit(l);
                    if (zeile != null)
                    {
                        l.NachSpieler = index;
                        if (TabellenStand(tab) == EIGEN) KopfEinfuegen(zeile, index);
                        ziel.Insert(Ziel(ziel, index), l.Element);
                    }
                    else ziel.Insert(index, l.Element);
                    s_leisten[l.Element.Pointer] = l;
                }
                catch (Exception e) { Plugin.L.LogWarning($"[Gespraech] Leiste: {e.Message}"); }
            }
        }

        // Kopfzeile der Tabelle: Element in der Nähe der Zeile (ohne Spielername), dessen Kinder an denselben
        // x-Positionen liegen wie die Zellen der Zeile. Dort an gleicher Stelle eine Kopfzelle "Gespräche" einfügen.
        private static void KopfEinfuegen(VisualElement zeile, int index)
        {
            var xs = new List<float>();
            for (int i = 0; i < zeile.childCount; i++)
                if (zeile[i].name != LEISTE) xs.Add(zeile[i].layout.x);
            if (xs.Count < 4) return;
            var a = zeile.parent;
            for (int ebene = 0; a != null && ebene < 8; ebene++, a = a.parent)
            {
                var kopf = SucheKopf(a, zeile, xs, 0);
                if (kopf == null) continue;
                if (s_koepfe.TryGetValue(kopf.Pointer, out var alt))
                {
                    // FM baut die Kopfzeile teils neu: Kopfzelle wieder einsetzen, wenn sie fehlt
                    try { if (alt.Element.parent != null && alt.Element.parent.Pointer == kopf.Pointer) return; } catch { }
                    s_koepfe.Remove(kopf.Pointer);
                }
                for (int i = 0; i < kopf.childCount; i++) if (kopf[i].name == KOPF) return;
                var k = new VisualElement { name = KOPF };
                k.style.width = new StyleLength(Plugin.SpaltenBreite.Value);
                k.style.flexShrink = new StyleFloat(0f);
                k.style.justifyContent = new StyleEnum<Justify>(Justify.Center);
                k.style.alignItems = new StyleEnum<Align>(Align.Center);
                var t = new Label("Gespräche");
                t.style.fontSize = new StyleLength(Plugin.KnopfGroesse.Value * 0.75f);
                t.style.color = new StyleColor(new Color(0.75f, 0.75f, 0.75f, 1f));
                k.Add(t);
                kopf.Insert(Ziel(kopf, index), k);
                s_koepfe[kopf.Pointer] = new Kopf { Element = k, NachSpieler = index };
                if (s_geloggt.Add("kopf")) Plugin.L.LogInfo($"[Gespraech] Kopfzeile gefunden: {ZeilenMenue.Kette(kopf, 5)}");
                return;
            }
            if (s_geloggt.Add("kopf-fehlt"))
                Plugin.L.LogInfo($"[Gespraech] Keine Kopfzeile gefunden. Zeile:{ZeilenMenue.Struktur(zeile, 8)}");
        }

        private static VisualElement SucheKopf(VisualElement e, VisualElement zeile, List<float> xs, int tiefe)
        {
            if (e == null || tiefe > 5 || e.Pointer == zeile.Pointer) return null;
            if (tiefe > 0 && Passt(e, xs) && ZeilenMenue.SucheNamen(e, VORLAGE) == null) return e;
            for (int i = 0; i < e.childCount; i++)
            {
                var c = e[i];
                if (c.Pointer == zeile.Pointer) continue;
                var r = SucheKopf(c, zeile, xs, tiefe + 1);
                if (r != null) return r;
            }
            return null;
        }

        private static bool Passt(VisualElement h, List<float> xs)
        {
            var hx = new List<float>();
            for (int i = 0; i < h.childCount; i++) if (h[i].name != KOPF) hx.Add(h[i].layout.x);
            if (Math.Abs(hx.Count - xs.Count) > 1) return false;
            int n = Math.Min(hx.Count, xs.Count), treffer = 0;
            for (int i = 0; i < n; i++) if (Math.Abs(hx[i] - xs[i]) < 3f) treffer++;
            return treffer >= Math.Max(3, n - 1);
        }

        private static Leiste Bauen(bool alsZelle, float hoehe)
        {
            var el = new VisualElement { name = LEISTE };
            var s = el.style;
            s.flexDirection = new StyleEnum<FlexDirection>(FlexDirection.Row);
            s.flexShrink = new StyleFloat(0f);
            s.flexGrow = new StyleFloat(0f);
            s.alignItems = new StyleEnum<Align>(Align.Center);
            s.justifyContent = new StyleEnum<Justify>(Justify.Center);
            if (alsZelle)
            {
                s.width = new StyleLength(Plugin.SpaltenBreite.Value);
                if (hoehe > 0) s.height = new StyleLength(hoehe);
            }
            else s.marginLeft = new StyleLength(4f);
            var l = new Leiste { Element = el, Knoepfe = new Button[Typen.Length] };
            for (int i = 0; i < Typen.Length; i++)
            {
                if (i == 4)
                {
                    var luecke = new VisualElement();
                    luecke.style.width = new StyleLength(5f);
                    el.Add(luecke);
                }
                var b = Knopf(Typen[i].kurz, Typen[i].typ, i < 4 ? Gruen : Rot);
                l.Knoepfe[i] = b;
                el.Add(b);
            }
            return l;
        }

        private static Button Knopf(string kurz, string typ, Color farbe)
        {
            var b = new Button { text = kurz, tooltip = Erkennung.Text(typ) };
            var s = b.style;
            float g = Plugin.KnopfGroesse.Value;
            s.width = new StyleLength(g);
            s.height = new StyleLength(g);
            s.fontSize = new StyleLength(g * 0.6f);
            s.paddingLeft = new StyleLength(0f); s.paddingRight = new StyleLength(0f);
            s.paddingTop = new StyleLength(0f); s.paddingBottom = new StyleLength(0f);
            s.marginLeft = new StyleLength(1f); s.marginRight = new StyleLength(1f);
            s.marginTop = new StyleLength(0f); s.marginBottom = new StyleLength(0f);
            s.color = new StyleColor(Color.white);
            s.backgroundColor = new StyleColor(farbe);
            s.unityTextAlign = new StyleEnum<TextAnchor>(TextAnchor.MiddleCenter);
            System.Action klick = () => Geklickt(b, typ);
            b.add_clicked(klick);
            return b;
        }

        private static string SpielerDerLeiste(Leiste l)
        {
            var feld = ZeilenMenue.NamensFeld(l.Element);
            return feld == null ? null : ZeilenMenue.ZeilenName(feld);
        }

        // Darstellung an den aktuellen Spieler der (evtl. recycelten) Zeile anpassen
        private static void Aktualisieren()
        {
            // neue Tabelle (FM baut sie z. B. beim Zurückwechseln neu auf) mit gespeichertem Ergebnis sofort einstufen
            var einstufen = new Dictionary<IntPtr, bool>();
            foreach (var l in s_leisten.Values)
            {
                string sp;
                try { sp = SpielerDerLeiste(l); } catch { continue; }
                if (sp == null) continue;
                s_stand.TryGetValue(sp, out var st);
                if (st?.Angebote != null && TabellenStand(l.Tabelle) == 0 && !einstufen.ContainsKey(l.Tabelle))
                    einstufen[l.Tabelle] = st.Angebote.Contains(Erkennung.MARKER_EIGEN);
                if (sp == l.Spieler && st != null && st.Angebote != null && l.Knoepfe[0].userData != null) continue;
                if (sp != l.Spieler) l.RuheBis = 0f;  // recycelte Zeile, neuer Spieler: sofort prüfbar
                l.Spieler = sp;
                Anzeigen(l, st?.Angebote);
            }
            foreach (var kv in einstufen) Einstufen(kv.Key, kv.Value);
        }

        private static void Anzeigen(Leiste l, HashSet<string> angebote)
        {
            if (angebote != null)
                try
                {
                    l.Element.style.visibility = new StyleEnum<Visibility>(
                        angebote.Contains(Erkennung.MARKER_EIGEN) ? Visibility.Visible : Visibility.Hidden);
                }
                catch { }
            for (int i = 0; i < Typen.Length; i++)
            {
                var b = l.Knoepfe[i];
                bool an = angebote == null || angebote.Contains(Typen[i].typ);
                try
                {
                    b.style.backgroundColor = new StyleColor(an ? (i < 4 ? Gruen : Rot) : Grau);
                    b.style.opacity = new StyleFloat(angebote == null ? 0.45f : 1f);
                    b.style.color = new StyleColor(an ? Color.white : GrauText);
                    b.SetEnabled(an);
                    b.tooltip = Erkennung.Text(Typen[i].typ) + (angebote == null ? " (wird geprüft)" : an ? "" : " (gerade nicht angeboten)");
                    b.userData = angebote == null ? null : b;  // Marker: Stand angezeigt
                }
                catch { }
            }
        }

        // Nächste Zeile ohne frischen Stand im Hintergrund prüfen
        private static void Pruefen()
        {
            if (!ZeilenMenue.Bereit && s_leisten.Count > 0 && s_geloggt.Add("warte"))
                Plugin.L.LogInfo("[Gespraech] Spalte wartet auf den ersten Rechtsklick (Menüsystem noch unbekannt).");
            if (!Plugin.VerfuegbarkeitPruefen.Value || !ZeilenMenue.Bereit || ZeilenMenue.Laeuft) return;
            if (Time.unscaledTime < ZeilenMenue.PauseBis) return;
            // echtes Menü offen: Pause bis Esc/Linksklick (Plugin.cs setzt EchtesMenueSeit zurück), höchstens 10 s
            if (Time.unscaledTime - ZeilenMenue.EchtesMenueSeit < 10f) return;
            foreach (var l in s_leisten.Values)
            {
                if (l.Spieler == null || TabellenStand(l.Tabelle) == FREMD) continue;
                if (Time.unscaledTime < l.RuheBis) continue;
                if (!ZeileSichtbar(l.Element.parent)) continue;  // versteckte Bildschirme (z. B. Spielerdatenbank im Hintergrund)
                if (s_stand.TryGetValue(l.Spieler, out var st) && st.Angebote != null && Time.unscaledTime - st.Zeit < TTL) continue;
                var feld = ZeilenMenue.NamensFeld(l.Element);
                if (feld == null) continue;
                var sp = l.Spieler;
                var tab = l.Tabelle;
                l.RuheBis = Time.unscaledTime + 15f;  // ohne Ergebnis nicht sofort wieder dieselbe Leiste
                if (ZeilenMenue.Pruefen(feld, (ok, angebote) =>
                    {
                        if (++s_prueflog <= 15)
                            Plugin.L.LogInfo($"[Gespraech] Prüfung '{sp}': {(angebote == null ? "kein Ergebnis" : $"{angebote.Count} Einträge, eigen={angebote.Contains(Erkennung.MARKER_EIGEN)}")}");
                        if (angebote == null) return;  // abgebrochen (echter Rechtsklick): alten Stand behalten
                        Einstufen(tab, angebote.Contains(Erkennung.MARKER_EIGEN));
                        if (TabellenStand(tab) == FREMD) return;
                        s_stand[sp] = new Stand { Angebote = angebote, Zeit = Time.unscaledTime };
                        foreach (var x in s_leisten.Values) if (x.Spieler == sp) Anzeigen(x, s_stand[sp].Angebote);
                    }))
                    return;  // eine Prüfung zur Zeit
            }
        }

        private static void Geklickt(Button b, string typ)
        {
            try
            {
                var feld = ZeilenMenue.NamensFeld(b);
                if (feld == null) { Plugin.L.LogWarning("[Gespraech] Button: kein Namensfeld in der Zeile."); return; }
                var sp = ZeilenMenue.ZeilenName(feld);
                Plugin.L.LogInfo($"[Gespraech] Button {typ} für '{sp}'");
                ZeilenMenue.Ausloesen(feld, typ, (ok, angebote) =>
                {
                    if (!ok && angebote == null) return;  // abgebrochen: nichts ändern
                    // geführtes Gespräch sperrt das Spiel: sofort grau, Rest wie eben gelesen; Neuprüfung in ~5 s
                    var neu = angebote == null ? null : new HashSet<string>(angebote);
                    if (ok) neu?.Remove(typ);
                    if (neu != null) s_stand[sp] = new Stand { Angebote = neu, Zeit = Time.unscaledTime - TTL + 5f };
                    else s_stand.Remove(sp);
                    foreach (var x in s_leisten.Values)
                        if (x.Spieler == sp) Anzeigen(x, neu);
                });
            }
            catch (Exception e) { Plugin.L.LogError($"[Gespraech] Button: {e}"); }
        }
    }
}
