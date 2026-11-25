// Mitschnitt eines Spiels: eine JSONL-Datei, Feld "t" = Zeilentyp
// (kopf, setup, spieler, zaehler, ereignis, frame, ball_spur, bildschirm, fehler, ende).

using System;
using System.Collections.Generic;
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
        private static bool s_spielerDa, s_fertigDa;
        private static string s_periode;
        // Ballspur: bis wohin gesehen (Wiedergaben springen zurück), geschrieben und angefordert
        private static int s_maxTs, s_ballBis = -1, s_ballZiel = -1;
        private const int BallBlock = 1000;  // Zeitscheiben je Bild, damit nichts ruckelt
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
            try { s_maxTs = Math.Max(s_maxTs, match.CurrentTimeSlice); } catch (Exception e) { Fehler("zeit", e); }
            if (rueckblick) s_naechsteListe = 0;  // Taste: Zähler und Ereignisse sofort schreiben

            if (jetzt >= s_naechsteListe)
            {
                s_naechsteListe = jetzt + 2f;
                try { Zaehler(match, stufe); } catch (Exception e) { Fehler("zaehler", e); }
                if (stufe >= 2)
                {
                    if (!s_spielerDa) try { Spieler(setup); } catch (Exception e) { Fehler("spieler", e); }
                    try { Ereignisse(match); } catch (Exception e) { Fehler("ereignisse", e); }
                }
                s_datei?.Flush();
            }

            if (stufe >= 3 && jetzt >= s_naechsterFrame)
            {
                s_naechsterFrame = jetzt + 1f / Mathf.Clamp(Plugin.PositionenHz.Value, 0.2f, 30f);
                try { Frame(match); } catch (Exception e) { Fehler("frame", e); }
            }

            if (stufe >= 4)
            {
                // Ballspur anfordern: Periodenwechsel, Spielende oder Taste
                try
                {
                    var periode = match.MatchPeriod.ToString();
                    bool wechsel = s_periode != null && periode != s_periode;
                    s_periode = periode;
                    bool fertig = !s_fertigDa && s_ctrl.IsFinished;
                    s_fertigDa |= fertig;
                    if (wechsel || fertig || rueckblick) s_ballZiel = s_maxTs;
                    Ballspur();
                }
                catch (Exception e) { Fehler("ballspur", e); s_ballZiel = s_ballBis; }
            }
        }

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
        private static void Ereignisse(Match match)
        {
            var liste = match.m_commentaryEvents;
            if (liste == null) return;
            int n = liste.Count;
            for (int i = 0; i < n; i++)
            {
                var e = liste[i];
                int ts = e.TimeSlice, dauer = e.Duration, data1 = e.Data1;
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

        // Ballposition jeder bereits gesehenen Zeitscheibe, in Blöcken über mehrere Bilder
        private static void Ballspur()
        {
            if (s_ballZiel <= s_ballBis) return;
            var quelle = s_ctrl.PlaybackInterface;
            if (quelle == null) return;
            int von = s_ballBis + 1, bis = Math.Min(s_ballZiel, von + BallBlock - 1);
            var punkte = new List<float[]>(bis - von + 1);
            for (int ts = von; ts <= bis; ts++)
            {
                var p = quelle.GetBallPosition(ts);
                punkte.Add(new[] { R(p.x), R(p.y), R(p.z) });
            }
            Zeile(new { t = "ball_spur", von, punkte });
            s_ballBis = bis;
            if (bis < s_ballZiel) return;
            s_datei?.Flush();
            Plugin.L.LogInfo($"Ballspur bis Zeitscheibe {bis} geschrieben");
        }

        internal static void Schliessen(string grund)
        {
            if (s_datei != null)
            {
                Zeile(new { t = "ende", grund });
                try { s_datei.Dispose(); } catch (Exception e) { Plugin.L.LogWarning($"Schließen: {e.Message}"); }
                s_datei = null;
                Plugin.L.LogInfo($"Mitschnitt beendet ({grund})");
            }
            s_ctrl = null;
            s_spielerDa = s_fertigDa = false;
            s_periode = null;
            s_maxTs = 0;
            s_ballBis = s_ballZiel = -1;
            s_letzterZaehler = -1;
            s_letzteTs = int.MinValue;
            s_ereignisse.Clear();
            s_fehler.Clear();
        }
    }
}
