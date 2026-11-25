// Mitschnitt eines Spiels: eine JSONL-Datei, Feld "t" = Zeilentyp
// (kopf, setup, spieler, zaehler, ereignis, frame, ball_spur, bildschirm, leistung, fehler, ende).
//
// Nichts darf das Spiel ruckeln lassen. Einzelne rückwirkende Ballabfragen (GetBallPosition) dauern bis über
// 100 ms – egal wie klein die Portionen sind. Automatisch während des Spiels hat das immer geruckelt (0.2–0.5).
// Deshalb nur noch auf Wunsch: nach F8, solange die Spielzeit stillsteht (Halbzeit, Abpfiff).

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text.Encodings.Web;
using System.Text.Json;
using FM.Match;
using UnityEngine;

namespace SpielLogger
{
    internal static class Mitschnitt
    {
        private static MatchPlaybackController s_ctrl;
        private static StreamWriter s_datei;
        private static float s_naechsteSuche, s_naechsteListe, s_naechsterFrame;
        private static int s_letzterZaehler = -1, s_letzteTs = int.MinValue;
        private static bool s_spielerDa;
        // Ballspur: bis wohin gesehen (Wiedergaben springen zurück) und geschrieben
        private static int s_maxTs, s_ballBis = -1;
        private static readonly List<float[]> s_ballPuffer = new();
        private const double BallBudgetMs = 15.0;     // Zeit je Bild für die Ballspur
        private static bool s_ballGewuenscht;         // durch F8, endet bei Rückstand 0 oder wenn das Spiel läuft
        private static string s_modus = "";
        private static readonly Dictionary<string, int> s_rucklerModus = new();
        private const float Stillstand = 2f;      // Sekunden ohne neue Zeitscheibe (Halbzeit, Pause, Abpfiff)
        private static int s_jetztTs = int.MinValue;
        private static float s_stehtSeit;
        // Ruckler: Bilder über 100 ms und wie viel davon eigene Arbeit war
        private static double s_arbeit;           // eigene Millisekunden im letzten Bild
        private static int s_ruckler, s_rucklerEigen;
        private static readonly Dictionary<string, int> s_haenger = new();  // Aufgabe: wie oft über 20 ms
        private const int BallZeile = 200;        // so viele Punkte je Zeile
        // Ereignisse: ab hier neu lesen (Gespieltes ändert sich nicht mehr)
        private static int s_ersterOffen;
        private const int Rueckschau = 400;       // Zeitscheiben (100 s) sicherheitshalber erneut prüfen
        // Längste Dauer je Aufgabe in Millisekunden (Zeile "leistung")
        private static readonly Dictionary<string, double> s_dauer = new();
        private static readonly HashSet<string> s_ereignisse = new();
        private static readonly Dictionary<string, int> s_fehler = new();
        private static readonly JsonSerializerOptions Json = new() { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };

        // Jede Fehlerstelle höchstens 3× melden
        internal static void Fehler(string wo, Exception e)
        {
            s_fehler.TryGetValue(wo, out int n);
            s_fehler[wo] = n + 1;
            if (n >= 3) return;
            Plugin.L.LogWarning($"{wo}: {e.GetType().Name}: {e.Message}");
            Zeile(new { t = "fehler", wo, text = $"{e.GetType().Name}: {e.Message}" });
        }

        private static void Zeile(object o)
        {
            if (s_datei == null) return;
            try { s_datei.WriteLine(JsonSerializer.Serialize(o, Json)); }
            catch (Exception e) { Plugin.L.LogWarning($"Schreiben: {e.Message}"); }
        }

        // Eigenständige JSON-Datei (Bildschirm-Export)
        internal static void Schreiben(string pfad, object o) => File.WriteAllText(pfad, JsonSerializer.Serialize(o, Json));

        // Im laufenden Mitschnitt vermerken, zu welchem Spiel ein Bildschirm-Export gehört
        internal static void BildschirmMerken(string name)
        {
            Zeile(new { t = "bildschirm", datei = name, gesehen = s_maxTs });
            s_datei?.Flush();
        }

        // Öffentliche Felder/Eigenschaften eines Spiel-Structs als Text (Zeile "setup")
        private static Dictionary<string, string> Felder(object o)
        {
            var d = new Dictionary<string, string>();
            if (o == null) return d;
            const BindingFlags f = BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly;
            void Setze(string name, Func<object> lesen)
            {
                try
                {
                    var w = lesen();
                    if (w is System.Collections.IEnumerable liste && w is not string)
                    {
                        var teile = new List<string>();
                        foreach (var x in liste) teile.Add(x?.ToString());
                        d[name] = string.Join(",", teile);
                    }
                    else d[name] = w?.ToString();
                }
                catch (Exception e) { d[name] = $"?{e.GetType().Name}"; }
            }
            foreach (var x in o.GetType().GetFields(f)) Setze(x.Name, () => x.GetValue(o));
            foreach (var x in o.GetType().GetProperties(f))
                if (x.GetIndexParameters().Length == 0) Setze(x.Name, () => x.GetValue(o));
            return d;
        }

        private static float R(float v) => float.IsFinite(v) ? MathF.Round(v, 3) : 0f;

        internal static void Update(bool rueckblick)
        {
            int stufe = Plugin.Stufe.Value;
            if (stufe <= 0) { Schliessen("ausgeschaltet"); return; }

            float jetzt = Time.unscaledTime;
            if (s_ctrl == null)  // Unity-Vergleich: auch zerstörte Objekte sind null
            {
                if (s_datei != null) Schliessen("controller weg");
                if (jetzt < s_naechsteSuche) return;
                s_naechsteSuche = jetzt + 1f;
                s_ctrl = UnityEngine.Object.FindObjectOfType<MatchPlaybackController>();
                if (s_ctrl == null) return;
            }

            var match = s_ctrl.Match;
            var setup = s_ctrl.Setup;
            if (match == null || setup == null) return;
            if (s_datei == null) Oeffnen(setup, stufe);
            else if (Time.unscaledDeltaTime > 0.1f)
            {
                s_ruckler++;
                if (s_arbeit > 20) s_rucklerEigen++;
                s_rucklerModus.TryGetValue(s_modus, out int r);
                s_rucklerModus[s_modus] = r + 1;
            }
            s_arbeit = 0;
            try
            {
                int ts = match.CurrentTimeSlice;
                s_maxTs = Math.Max(s_maxTs, ts);
                if (ts != s_jetztTs)
                {
                    if (jetzt - s_stehtSeit >= Stillstand) s_ballGewuenscht = false;  // Spiel läuft wieder
                    s_jetztTs = ts;
                    s_stehtSeit = jetzt;
                }
                s_modus = match.CurrentMatchPlaybackMode.ToString();
            }
            catch (Exception e) { Fehler("zeit", e); }
            if (rueckblick) s_naechsteListe = 0;  // Taste: Zähler und Ereignisse sofort schreiben

            if (jetzt >= s_naechsteListe)
            {
                s_naechsteListe = jetzt + 2f;
                try { Zaehler(match, stufe); } catch (Exception e) { Fehler("zaehler", e); }
                if (stufe >= 2)
                {
                    if (!s_spielerDa) try { Spieler(setup); } catch (Exception e) { Fehler("spieler", e); }
                    try { Messen("ereignisse", () => Ereignisse(match, rueckblick)); }
                    catch (Exception e) { Fehler("ereignisse", e); }
                }
                s_datei?.Flush();
            }

            if (stufe >= 3 && jetzt >= s_naechsterFrame)
            {
                s_naechsterFrame = jetzt + 1f / Mathf.Clamp(Plugin.PositionenHz.Value, 0.2f, 30f);
                try { Messen("frame", () => Frame(match)); } catch (Exception e) { Fehler("frame", e); }
            }

            if (stufe >= 4)
            {
                if (rueckblick) s_ballGewuenscht = true;
                bool steht = jetzt - s_stehtSeit >= Stillstand && !s_modus.StartsWith("Replay") && s_modus != "Highlight";
                try
                {
                    if (s_ballGewuenscht && steht) Messen("ballspur", () => Ballspur(rueckblick));
                    else if (rueckblick) BallZeileSchreiben();
                }
                catch (Exception e) { Fehler("ballspur", e); s_ballBis = s_maxTs; }
            }
            if (rueckblick)
            {
                Leistung();
                s_datei?.Flush();
                Plugin.L.LogInfo($"Stand geschrieben bis Zeitscheibe {s_maxTs}, Ballspur bis {s_ballBis}");
            }
        }

        private static void Messen(string aufgabe, Action tun)
        {
            var uhr = Stopwatch.StartNew();
            tun();
            double ms = uhr.Elapsed.TotalMilliseconds;
            s_arbeit += ms;
            if (ms > 20 && aufgabe != "ballspur")
            {
                s_haenger.TryGetValue(aufgabe, out int h);
                s_haenger[aufgabe] = h + 1;
            }
            s_dauer.TryGetValue(aufgabe, out double bisher);
            if (ms <= bisher) return;
            s_dauer[aufgabe] = ms;
            if (ms > 50 && aufgabe != "ballspur") Plugin.L.LogWarning($"{aufgabe} brauchte {ms:0} ms");
        }

        private static void Leistung() =>
            Zeile(new
            {
                t = "leistung", max_ms = s_dauer, ueber_20ms = s_haenger, ruckler = s_ruckler,
                ruckler_eigen = s_rucklerEigen, ruckler_modus = s_rucklerModus,
                ball_rueckstand = s_maxTs - s_ballBis,
            });

        private static void Oeffnen(MatchSetup setup, int stufe)
        {
            int spielId = 0;
            try { spielId = (int)setup.UniqueIds.matchUniqueId; } catch (Exception e) { Fehler("spielid", e); }
            Directory.CreateDirectory(Plugin.Ordner.Value);
            var pfad = Path.Combine(Plugin.Ordner.Value, $"{DateTime.Now:yyyyMMdd_HHmmss}_{spielId}.jsonl");
            s_datei = new StreamWriter(pfad);
            float laenge = 0, breite = 0;
            try
            {
                var feld = setup.Stadium.pitchSetupInfo;
                laenge = R(feld.pitchLength);
                breite = R(feld.pitchWidth);
            }
            catch (Exception e) { Fehler("feld", e); }
            Zeile(new
            {
                t = "kopf", version = Plugin.VERSION, zeit = DateTime.Now.ToString("s"), spiel_id = spielId, stufe,
                hz = Plugin.PositionenHz.Value, feld_laenge = laenge, feld_breite = breite,
            });
            Dictionary<string, string> info = null, ids = null, wetter = null;
            try { info = Felder(setup.MatchInfo); } catch (Exception e) { Fehler("matchinfo", e); }
            try { ids = Felder(setup.UniqueIds); } catch (Exception e) { Fehler("ids", e); }
            try { wetter = Felder(setup.MatchLightingAndWeatherSetup); } catch (Exception e) { Fehler("wetter", e); }
            Zeile(new { t = "setup", info, ids, wetter });
            s_datei.Flush();
            Plugin.L.LogInfo($"Spiel erkannt, schreibe {pfad}");
        }

        private static void Zaehler(Match match, int stufe)
        {
            var liste = match.m_commentaryEvents;
            int n = liste?.Count ?? -1;
            int ts = match.CurrentTimeSlice;
            Zeile(new
            {
                t = "zaehler", stufe, ereignisse = n, ts, gesehen = s_maxTs, max_ts = match.m_maxMatchTimeSlice,
                periode = match.MatchPeriod.ToString(), modus = match.CurrentMatchPlaybackMode.ToString(),
                wir = (int)match.UserTeamId,
            });
            if (n != s_letzterZaehler) Plugin.L.LogInfo($"Ereignisse {n}, Zeitscheibe {ts}");
            s_letzterZaehler = n;
        }

        private static void Spieler(MatchSetup setup)
        {
            var alle = setup.Entities;
            if (alle == null || alle.Length == 0) return;
            for (int i = 0; i < alle.Length; i++)
            {
                var e = alle[i];
                Zeile(new
                {
                    t = "spieler", index = i, art = e.kind.ToString(), team = (int)e.teamIndex, uid = (long)e.uniqueID,
                    name = e.shirtName.ToString(), nr = (int)e.shirtNumber,
                });
            }
            s_spielerDa = true;
        }

        // Neue oder geänderte Einträge anhängen, auch verschobene: je Index gilt beim Auswerten der letzte Stand
        private static void Ereignisse(Match match, bool alles)
        {
            var liste = match.m_commentaryEvents;
            if (liste == null) return;
            int n = liste.Count;
            // Nur den offenen Teil lesen: die ganze Liste wächst auf rund 1900 Einträge und kostet spürbar Zeit
            int ab = alles || s_ersterOffen > n ? 0 : s_ersterOffen;
            int offen = -1;
            for (int i = ab; i < n; i++)
            {
                var e = liste[i];
                int ts = e.TimeSlice;
                if (offen < 0 && ts >= s_maxTs - Rueckschau) offen = i;
                int dauer = e.Duration, data1 = e.Data1;
                var id = e.CommentaryEventID;
                var ids = e.PlayerUniqueIDs;
                var spieler = new int[ids?.Length ?? 0];
                for (int k = 0; k < spieler.Length; k++) spieler[k] = ids[k];
                if (!s_ereignisse.Add($"{i}|{ts}|{(int)id}|{dauer}|{data1}|{string.Join(",", spieler)}")) continue;

                var texte = e.TextPast;
                var text = new List<string>();
                for (int k = 0; k < (texte?.Length ?? 0); k++) text.Add(texte[k]);
                Zeile(new
                {
                    t = "ereignis", i, id = (int)id, name = id.ToString(), ts, dauer, data1, spieler,
                    teams = e.PlayerTeams.ToString(), team = e.Team.ToString(), flags = e.Flags.ToString(),
                    wichtig = e.CommentaryImportance.ToString(), vorfall = e.IncidentImportance.ToString(), text,
                });
            }
            s_ersterOffen = offen < 0 ? n : offen;
        }

        private static void Frame(Match match)
        {
            var bild = match.m_matchFrame;
            int ts = bild.CurrentTimeSlice;
            if (ts == s_letzteTs) return;  // Pause oder Stillstand
            s_letzteTs = ts;

            bool aktiv = bild.MatchEntitiesEnabled;
            float[] ball = null;
            var spieler = new List<float[]>();
            var quelle = s_ctrl.PlaybackInterface;
            if (aktiv && quelle != null)
            {
                var b = quelle.GetBallWorldTransform(1f).pos;
                ball = new[] { R(b.x), R(b.y), R(b.z) };
                int n = s_ctrl.EntityCount;
                for (int i = 0; i < n; i++)
                {
                    var p = quelle.GetEntityWorldTransform(i).pos;
                    spieler.Add(new[] { i, R(p.x), R(p.y), R(p.z) });
                }
            }
            Zeile(new
            {
                t = "frame", ts, zeit = R(bild.CurrentTime), min = bild.ClockMinutes, sek = bild.ClockSeconds,
                periode = match.MatchPeriod.ToString(), modus = bild.CurrentPlaybackMode.ToString(), aktiv,
                tore = new[] { (int)bild.HomeGoals, (int)bild.AwayGoals }, ball, spieler,
            });
        }

        // Ballposition jeder gesehenen Zeitscheibe, je Bild nur so viele, wie ins Zeitbudget passen
        private static void Ballspur(bool sofort)
        {
            var quelle = s_ctrl.PlaybackInterface;
            if (quelle == null) return;
            var uhr = Stopwatch.StartNew();
            while (s_ballBis < s_maxTs && uhr.Elapsed.TotalMilliseconds < BallBudgetMs)
            {
                var p = quelle.GetBallPosition(s_ballBis + 1);
                s_ballPuffer.Add(new[] { R(p.x), R(p.y), R(p.z) });
                s_ballBis++;
            }
            if (s_ballBis >= s_maxTs && s_ballGewuenscht)
            {
                s_ballGewuenscht = false;
                sofort = true;
                Plugin.L.LogInfo($"Ballspur vollständig bis Zeitscheibe {s_ballBis}");
            }
            if (s_ballPuffer.Count >= BallZeile || sofort) BallZeileSchreiben();
        }

        private static void BallZeileSchreiben()
        {
            if (s_ballPuffer.Count == 0) return;
            Zeile(new { t = "ball_spur", von = s_ballBis - s_ballPuffer.Count + 1, punkte = s_ballPuffer });
            s_ballPuffer.Clear();
        }

        internal static void Schliessen(string grund)
        {
            if (s_datei != null)
            {
                BallZeileSchreiben();
                Leistung();
                Zeile(new { t = "ende", grund });
                try { s_datei.Dispose(); } catch (Exception e) { Plugin.L.LogWarning($"Schließen: {e.Message}"); }
                s_datei = null;
                Plugin.L.LogInfo($"Mitschnitt beendet ({grund})");
            }
            s_ctrl = null;
            s_spielerDa = false;
            s_maxTs = s_ersterOffen = 0;
            s_ballBis = -1;
            s_ballPuffer.Clear();
            s_jetztTs = int.MinValue;
            s_arbeit = 0;
            s_ruckler = s_rucklerEigen = 0;
            s_haenger.Clear();
            s_rucklerModus.Clear();
            s_ballGewuenscht = false;
            s_modus = "";
            s_dauer.Clear();
            s_letzterZaehler = -1;
            s_letzteTs = int.MinValue;
            s_ereignisse.Clear();
            s_fehler.Clear();
        }
    }
}
