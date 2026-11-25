// Sprachunabhängige Erkennung der Gesprächs-Einträge im Kontextmenü eines Spielers.
//
// Jeder Menüeintrag des Spielers hat als Klick-Handler eine Closure (PluginContextMenuContributor+<>c__DisplayClass47_0)
// mit der ActionID des Spiels. Daraus der Typ:
//   PraisePlayerConduct -> lob_verhalten, PraisePlayerTrainingDevelopment -> lob_training, analog Warn* -> kritik_*.
//   PraisePlayerPerformance / WarnPlayerPerformance gibt es ZWEIMAL ("Form …" und "Leistung im letzten Spiel …",
//   gleiche ActionID, gleiche Daten; nur der Text unterscheidet sie). Stehen beide im Menü, ist der erste in der
//   Geschwister-Reihenfolge "Form", der zweite "Leistung"; dabei werden die Texte der aktuellen Spielsprache gelernt
//   (Config "Gelernt"). Steht nur einer da (der andere hat Abklingzeit), entscheidet der gelernte Text, sonst die
//   Stichwortliste "LeistungStichworte" (de/en vorbelegt), sonst "Form".
// Eigener Verein: Aktionen, die das Spiel nur bei eigenen Spielern anbietet (Training, Kader, Lob/Kritik).

using System;
using System.Collections.Generic;
using FM.Game;
using FM.GamePlugin;
using SI.UI;

namespace GespraechMod
{
    internal static class Erkennung
    {
        internal const string MARKER_EIGEN = "#eigen";

        internal static readonly string[] Typen =
        {
            "lob_form", "lob_leistung", "lob_verhalten", "lob_training",
            "kritik_form", "kritik_leistung", "kritik_verhalten", "kritik_training",
        };

        // Anzeige, solange die Spielsprache noch nicht gelernt ist
        internal static readonly Dictionary<string, string> StandardTexte = new()
        {
            ["lob_form"] = "Form loben", ["lob_leistung"] = "Leistung im letzten Spiel loben",
            ["lob_verhalten"] = "Verhalten loben", ["lob_training"] = "Training/Entwicklung loben",
            ["kritik_form"] = "Form kritisieren", ["kritik_leistung"] = "Leistung im letzten Spiel kritisieren",
            ["kritik_verhalten"] = "Verhalten kritisieren", ["kritik_training"] = "Training/Entwicklung kritisieren",
        };

        // Menütexte der laufenden Spielsprache je Typ (für Tooltips), aus den Menüs gelesen
        internal static readonly Dictionary<string, string> Texte = new();

        private static readonly HashSet<ActionID> EigenIds = new()
        {
            ActionID.PersonTrainingFocus, ActionID.PersonRestTrainingSchedule, ActionID.PersonTrainingNewPosition,
            ActionID.PersonChangePlayersClubSquad, ActionID.PersonTrainingIntensityRest,
            ActionID.PraisePlayerPerformance, ActionID.PraisePlayerConduct, ActionID.PraisePlayerTrainingDevelopment,
            ActionID.WarnPlayerPerformance, ActionID.WarnPlayerConduct, ActionID.WarnPlayerTrainingDevelopment,
        };

        private static Dictionary<string, string> s_gelernt;  // Menütext -> Typ (nur die Performance-Paare)

        internal sealed class Ergebnis
        {
            internal readonly Dictionary<string, Il2CppSystem.Action> Handler = new();  // Typ -> Klick-Handler
            internal int MitHandler;  // Einträge mit Handler überhaupt (0 = Menü leer/gestört)
            internal bool Eigen;

            internal HashSet<string> Angebote()
            {
                var s = new HashSet<string>(Handler.Keys);
                if (Eigen) s.Add(MARKER_EIGEN);
                return s;
            }
        }

        internal static string Text(string typ) =>
            Texte.TryGetValue(typ, out var t) ? t : StandardTexte.TryGetValue(typ, out var s) ? s : typ;

        private static Dictionary<string, string> Gelernt()
        {
            if (s_gelernt != null) return s_gelernt;
            s_gelernt = new Dictionary<string, string>();
            foreach (var paar in (Plugin.Gelernt.Value ?? "").Split('|'))
            {
                var kv = paar.Split('=', 2);
                if (kv.Length == 2 && kv[0].Length > 0) s_gelernt[kv[0]] = kv[1];
            }
            return s_gelernt;
        }

        private static void Lernen(string text, string typ)
        {
            var g = Gelernt();
            if (string.IsNullOrEmpty(text) || g.TryGetValue(text, out var alt) && alt == typ) return;
            g[text] = typ;
            var teile = new List<string>();
            foreach (var kv in g) teile.Add($"{kv.Key.Replace("|", "").Replace("=", "")}={kv.Value}");
            Plugin.Gelernt.Value = string.Join("|", teile);
            Plugin.L.LogInfo($"[Gespraech] Gelernt: '{text}' = {typ}");
        }

        private static bool IstLeistungNachStichwort(string text)
        {
            foreach (var w in (Plugin.LeistungStichworte.Value ?? "").Split('|'))
                if (w.Length > 0 && text != null && text.IndexOf(w, StringComparison.OrdinalIgnoreCase) >= 0) return true;
            return false;
        }

        // Position eines Eintrags unter seinen Geschwistern (Reihenfolge im Menü)
        private static int Position(MenuDescription.Entry e)
        {
            try
            {
                var p = e._Parent_k__BackingField;
                int i = 0;
                for (var c = p?._FirstChild_k__BackingField; c != null && i < 200; c = c._Next_k__BackingField, i++)
                    if (c.Pointer == e.Pointer) return i;
            }
            catch { }
            return int.MaxValue;
        }

        internal static Ergebnis Lesen(Il2CppSystem.Collections.Generic.List<MenuDescription.Entry> es)
        {
            var r = new Ergebnis();
            if (es == null) return r;
            var performance = new Dictionary<string, List<(MenuDescription.Entry e, string text, Il2CppSystem.Action h)>>
            {
                ["lob"] = new(), ["kritik"] = new(),
            };
            for (int i = 0; i < es.Count; i++)
            {
                var e = es[i];
                if (e == null) continue;
                Il2CppSystem.Action h = null;
                string text = null;
                try { h = e._HandleInteraction_k__BackingField; text = e._Name_k__BackingField; } catch { }
                if (h == null) continue;
                r.MitHandler++;
                PluginContextMenuContributor.__c__DisplayClass47_0 c = null;
                try { c = h.Target?.TryCast<PluginContextMenuContributor.__c__DisplayClass47_0>(); } catch { }
                if (c == null) continue;
                var aid = c.actionID;
                if (EigenIds.Contains(aid)) r.Eigen = true;
                string typ = aid switch
                {
                    ActionID.PraisePlayerConduct => "lob_verhalten",
                    ActionID.PraisePlayerTrainingDevelopment => "lob_training",
                    ActionID.WarnPlayerConduct => "kritik_verhalten",
                    ActionID.WarnPlayerTrainingDevelopment => "kritik_training",
                    _ => null,
                };
                if (typ != null) { r.Handler[typ] = h; Texte[typ] = text; continue; }
                if (aid == ActionID.PraisePlayerPerformance) performance["lob"].Add((e, text, h));
                else if (aid == ActionID.WarnPlayerPerformance) performance["kritik"].Add((e, text, h));
            }
            foreach (var (art, liste) in performance)
            {
                if (liste.Count == 0) continue;
                if (liste.Count >= 2)
                {
                    liste.Sort((a, b) => Position(a.e).CompareTo(Position(b.e)));
                    Zuordnen(r, $"{art}_form", liste[0], lernen: true);
                    Zuordnen(r, $"{art}_leistung", liste[1], lernen: true);
                    continue;
                }
                var x = liste[0];
                string t = Gelernt().TryGetValue(x.text ?? "", out var g) ? g
                    : IstLeistungNachStichwort(x.text) ? $"{art}_leistung" : $"{art}_form";
                Zuordnen(r, t, x, lernen: false);
            }
            return r;
        }

        private static void Zuordnen(Ergebnis r, string typ, (MenuDescription.Entry e, string text, Il2CppSystem.Action h) x, bool lernen)
        {
            r.Handler[typ] = x.h;
            if (x.text != null) Texte[typ] = x.text;
            if (lernen) Lernen(x.text, typ);
        }
    }
}
