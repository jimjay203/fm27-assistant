// Kontextmenü einer Spielerzeile selbst öffnen (wie ein Rechtsklick) und auswerten:
//  - Ausloesen(feld, text, fertig): Eintrag `text` auslösen (Gespräch öffnet mit dem Zeilenspieler)
//  - Pruefen(feld, fertig): nur lesen, welche Einträge das Spiel anbietet (Abklingzeit des Spiels)
// Das Spiel legt den Spieler selbst über die Zeile fest (Spike D, 25.11.2026). Spike C – Spieler in den Daten der
// Closure tauschen – öffnete das Gespräch mit dem Vorlagenspieler.
//
// Ziel ist das Namensfeld der Zeile ("primary-text"), wie beim echten Rechtsklick. Solange ein eigener Vorgang läuft,
// unterdrückt PopupPatch die Anzeige des Menüs (CascadingMenuPopup.Show*). Das Menü gilt als fertig aufgebaut, wenn
// sich die Zahl der Einträge einige Frames nicht mehr ändert (Timeout 3 s).
// Voraussetzung: ContextMenuSubsystem bekannt (ab dem ersten echten Rechtsklick nach dem Start).

using System;
using System.Collections.Generic;
using System.Text;
using HarmonyLib;
using SI.UI;
using UnityEngine;
using UnityEngine.UIElements;

namespace GespraechMod
{
    internal static class ZeilenMenue
    {
        internal const string NAMENSFELD = "primary-text";
        private const int STABIL_FRAMES = 6;
        internal const string ORDNER_INTERAKTION = "Interaktion";  // nur bei Spielern des eigenen Vereins
        internal const string MARKER_EIGEN = "#eigen";

        internal static MenuContext Muster;      // letzter echter Kontext (von OpenPatch)
        private static MenuContext s_eigener;
        private static string s_text;            // null = nur prüfen
        private static float s_bis;
        private static bool s_aktiv;
        private static int s_letzteAnzahl, s_stabil;
        private static Action<bool, HashSet<string>> s_fertig;
        internal static float PauseBis;          // nach einem ausgelösten Gespräch keine Prüfungen
        internal static float EchtesMenueSeit = -100f;  // Zeit des letzten echten Rechtsklick-Menüs (OpenPatch)

        internal static bool IstEigener(MenuContext c) => s_eigener != null && c != null && c.Pointer == s_eigener.Pointer;
        internal static bool Bereit => Info.Subsystem != null;
        internal static bool Laeuft => s_aktiv;

        internal static string Kette(VisualElement e, int max = 8)
        {
            var sb = new StringBuilder();
            for (int i = 0; e != null && i < max; i++, e = e.parent)
                sb.Append(i == 0 ? "" : " < ").Append(e.name).Append('{').Append(Info.Typ(e)).Append('}');
            return sb.ToString();
        }

        internal static VisualElement SucheNamen(VisualElement e, string name, int tiefe = 0)
        {
            if (e == null || tiefe > 14) return null;
            if (e.name == name) return e;
            int n = e.childCount;
            for (int i = 0; i < n; i++)
            {
                var r = SucheNamen(e[i], name, tiefe + 1);
                if (r != null) return r;
            }
            return null;
        }

        // In der Zeile des Elements das Namensfeld finden: aufwärts, bis ein Vorfahr eines enthält
        internal static VisualElement NamensFeld(VisualElement von)
        {
            for (var e = von; e != null; e = e.parent)
            {
                if (e.name == NAMENSFELD) return e;
                var f = SucheNamen(e, NAMENSFELD);
                if (f != null) return f;
            }
            return null;
        }

        internal static string ZeilenName(VisualElement namensfeld)
        {
            try
            {
                var t = namensfeld?.TryCast<TextElement>()?.text ?? "";
                var sb = new StringBuilder();
                bool tag = false;
                foreach (var ch in t) { if (ch == '<') tag = true; else if (ch == '>') tag = false; else if (!tag) sb.Append(ch); }
                return sb.ToString();
            }
            catch { return "?"; }
        }

        internal static bool Ausloesen(VisualElement feld, string text, Action<bool, HashSet<string>> fertig) =>
            Start(feld, text, fertig);

        internal static bool Pruefen(VisualElement feld, Action<bool, HashSet<string>> fertig) =>
            Start(feld, null, fertig);

        private static bool Start(VisualElement namensfeld, string text, Action<bool, HashSet<string>> fertig)
        {
            if (s_aktiv)
            {
                if (text == null || s_text != null) return false;  // Prüfung wartet; Auslösen läuft schon
                PruefungAbbrechen();                                // Klick hat Vorrang vor einer Prüfung
            }
            if (Info.Subsystem == null)
            {
                if (text != null)
                    Plugin.L.LogWarning("[Gespraech] Erst einmal einen echten Rechtsklick machen (Menü-System noch unbekannt).");
                return false;
            }
            var ctx = new MenuContext();
            ctx.Description = new MenuDescription(10);
            ctx.Target = namensfeld;
            ctx.TargetWasPicked = Muster?.TargetWasPicked ?? true;
            if (Muster != null)
            {
                ctx.PreferredFolderAnchor = Muster.PreferredFolderAnchor;
                ctx.CascadeDirection = Muster.CascadeDirection;
            }
            s_eigener = ctx;
            s_text = text;
            s_fertig = fertig;
            s_bis = Time.unscaledTime + 3f;
            s_letzteAnzahl = -1;
            s_stabil = 0;
            s_aktiv = true;
            if (text != null) Plugin.L.LogInfo($"[Gespraech] Öffne Menü für '{ZeilenName(namensfeld)}', suche '{text}'");
            Info.Subsystem.OpenContextMenu(ctx);
            return true;
        }

        // Echter Rechtsklick während eines eigenen Vorgangs: eigenen Vorgang verwerfen, damit das Menü des Spielers
        // angezeigt wird (PopupPatch unterdrückt sonst jedes Popup, solange Laeuft).
        internal static void Abbrechen()
        {
            if (!s_aktiv) return;
            s_eigener = null;
            Ende(false, null);
        }

        // Laufende Hintergrundprüfung abbrechen und ihr Menü schließen (Klick oder rechte Maustaste hat Vorrang)
        internal static void PruefungAbbrechen()
        {
            if (!s_aktiv || s_text != null) return;
            s_eigener = null;
            Schliessen();
            Ende(false, null);
        }

        private static void Schliessen()
        {
            try { Info.Subsystem?.m_cascadingMenuPopup?.Hide(); } catch { }
            try { Info.Subsystem?.CloseContextMenu(); }
            catch (Exception e) { Plugin.L.LogWarning($"[Gespraech] Schließen: {e.Message}"); }
        }

        private static void Ende(bool ok, HashSet<string> angebote)
        {
            s_aktiv = false;
            var f = s_fertig;
            s_fertig = null;
            try { f?.Invoke(ok, angebote); } catch (Exception e) { Plugin.L.LogWarning($"[Gespraech] Rückmeldung: {e.Message}"); }
        }

        internal static void Update()
        {
            if (!s_aktiv) return;
            var es = s_eigener?.Description?.m_entries;
            int n = es?.Count ?? 0;
            if (s_text != null && es != null)
                for (int i = 0; i < n; i++)
                {
                    var e = es[i];
                    if (e == null) continue;
                    string name = null;
                    try { name = e._Name_k__BackingField; } catch { }
                    if (name != s_text) continue;
                    var h = e._HandleInteraction_k__BackingField;
                    if (h == null) continue;
                    Plugin.L.LogInfo($"[Gespraech] '{s_text}' gefunden, löse aus");
                    Schliessen();
                    h.Invoke();
                    PauseBis = Time.unscaledTime + 3f;
                    Ende(true, null);
                    return;
                }
            if (n == s_letzteAnzahl && n > 1) s_stabil++; else s_stabil = 0;
            s_letzteAnzahl = n;
            // leeres Menü (nur Wurzel) nach 0,5 s aufgeben, sonst warten bis stabil oder Timeout
            bool leer = n <= 1 && Time.unscaledTime > s_bis - 2.5f;
            if (!leer && s_stabil < STABIL_FRAMES && Time.unscaledTime <= s_bis) return;
            var angebote = new HashSet<string>();
            for (int i = 0; i < n; i++)
                try
                {
                    var e = es[i];
                    if (e?._HandleInteraction_k__BackingField != null) angebote.Add(e._Name_k__BackingField);
                    else if (e?._Name_k__BackingField == ORDNER_INTERAKTION) angebote.Add(MARKER_EIGEN);
                }
                catch { }
            if (angebote.Count == 0)
            {
                // kein einziger auslösbarer Eintrag: Menü gestört/leer, nicht "nichts angeboten"
                if (s_text != null) Plugin.L.LogInfo($"[Gespraech] '{s_text}': Menü leer ({n} Einträge), bitte erneut klicken.");
                Schliessen();
                Ende(false, null);
                return;
            }
            if (s_text != null) Plugin.L.LogInfo($"[Gespraech] '{s_text}' wird nicht angeboten ({n} Einträge).");
            Schliessen();
            Ende(false, angebote);
        }

        internal static string Struktur(VisualElement e, int max)
        {
            var sb = new StringBuilder();
            for (int i = 0; e != null && i < max; i++, e = e.parent)
                sb.Append($"\n   {i,2} '{e.name}' {Info.Typ(e)} kinder={e.childCount} rect={e.layout}");
            return sb.ToString();
        }
    }

    // KEINE Haken auf ContextMenuSubsystem.Initialise / OnContextMenuBeforeVisibilityChanged: IL2CPP faltet Methoden
    // mit gleichem Maschinencode zusammen, der Haken lief dann für fremde Objekte in Dauerschleife und FM27 stürzte
    // beim Laden ab (v0.10, 25.11.2026). Echte Menüs werden über OpenPatch verfolgt (ZeilenMenue.EchtesMenueSeit).

    // Menü nicht anzeigen, solange ein eigener Vorgang läuft
    [HarmonyPatch(typeof(CascadingMenuPopup))]
    internal static class PopupPatch
    {
        [HarmonyPrefix]
        [HarmonyPatch(nameof(CascadingMenuPopup.Show))]
        private static bool Show() => !(Plugin.MenueUnterdruecken.Value && ZeilenMenue.Laeuft);

        [HarmonyPrefix]
        [HarmonyPatch(nameof(CascadingMenuPopup.ShowOrWaitForEntries))]
        private static bool ShowOrWait() => !(Plugin.MenueUnterdruecken.Value && ZeilenMenue.Laeuft);

        [HarmonyPrefix]
        [HarmonyPatch(nameof(CascadingMenuPopup.ShowInternal))]
        private static bool ShowInternal() => !(Plugin.MenueUnterdruecken.Value && ZeilenMenue.Laeuft);
    }
}
