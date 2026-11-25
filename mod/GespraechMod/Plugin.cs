// GespraechMod – Gesprächs-Spalte in der FM27-Kadertabelle (BepInEx 6, IL2CPP).
//
// Je Zeile der eigenen Kadertabelle: Lob F L V T (grün) | Kritik F L V T (rot) = Form, Leistung im letzten Spiel,
// Verhalten, Training/Entwicklung. Ein Klick öffnet unsichtbar das Kontextmenü der Zeile und löst den Eintrag aus;
// das Spiel legt den Spieler selbst über die Zeile fest (ZeilenMenue.cs). Nicht angebotene Gespräche (Abklingzeit des
// Spiels) werden per Hintergrundprüfung grau (ZeilenKnoepfe.cs). Die Spalte erscheint nur in Tabellen mit Spielern
// des eigenen Vereins (Menü hat Ordner "Interaktion").
//
// Bedienung: nach dem Start einmal einen Spieler rechtsklicken (macht das Menüsystem bekannt);
//            F5 = Spalte ein/aus, F4 = Stellung (nach Spieler / ganz vorne / ganz hinten).
// Config:    BepInEx\config\fm27assistant.gespraech.cfg
// Bauen:     dotnet build -c Release -p:Installieren=true  (siehe GespraechMod.csproj)
//
// Erkenntnisse aus den Spikes (25.11.2026, Details im Git-Verlauf bis beda82e):
//  - Harmony-Haken auf PluginContextMenuContributor (PerformAction, RegisterItem, Klick-Lambda) feuerten nicht;
//    zuverlässig ist, den fertigen Menübaum zu lesen (MenuDescription.m_entries).
//  - Spieler in den Daten einer gemerkten Menü-Closure tauschen öffnete das Gespräch weiter mit dem alten Spieler;
//    nur das Menü der Zeile selbst öffnen legt den richtigen Spieler fest.
//  - KEINE Haken auf kleine, generische Methoden (z. B. ContextMenuSubsystem.Initialise): IL2CPP faltet Methoden
//    mit gleichem Maschinencode zusammen, der Haken lief für fremde Objekte in Dauerschleife und FM27 stürzte ab.

using System;
using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using HarmonyLib;
using SI.UI;
using UnityEngine;
using UnityEngine.InputSystem;

namespace GespraechMod
{
    [BepInPlugin(GUID, NAME, VERSION)]
    public class Plugin : BasePlugin
    {
        public const string GUID = "fm27assistant.gespraech";
        public const string NAME = "Gespraech";
        public const string VERSION = "1.0.0";

        internal static ManualLogSource L;
        internal static ConfigEntry<bool> Enabled;
        internal static ConfigEntry<bool> Knoepfe;
        internal static ConfigEntry<Key> SpalteKey;
        internal static ConfigEntry<Key> StellungKey;
        internal static ConfigEntry<int> SpaltenStellung;
        internal static ConfigEntry<float> SpaltenBreite;
        internal static ConfigEntry<float> KnopfGroesse;
        internal static ConfigEntry<bool> VerfuegbarkeitPruefen;
        internal static ConfigEntry<bool> MenueUnterdruecken;

        public override void Load()
        {
            L = Log;
            Enabled = Config.Bind("Allgemein", "Enabled", true, "Mod an/aus.");
            Knoepfe = Config.Bind("Allgemein", "Knoepfe", true, "Gesprächs-Spalte einblenden (F5 schaltet um).");
            SpalteKey = Config.Bind("Allgemein", "SpalteKey", Key.F5, "Gesprächs-Spalte ein-/ausblenden.");
            StellungKey = Config.Bind("Allgemein", "StellungKey", Key.F4, "Stellung der Gesprächs-Spalte wechseln.");
            VerfuegbarkeitPruefen = Config.Bind("Allgemein", "VerfuegbarkeitPruefen", true,
                "Nicht angebotene Gespräche grau anzeigen (liest je Zeile unsichtbar das Menü).");
            MenueUnterdruecken = Config.Bind("Allgemein", "MenueUnterdruecken", true, "Menü beim eigenen Öffnen nicht anzeigen.");
            SpaltenStellung = Config.Bind("Darstellung", "SpaltenStellung", 0, "0 = nach Spieler, 1 = ganz vorne, 2 = ganz hinten.");
            SpaltenBreite = Config.Bind("Darstellung", "SpaltenBreite", 150f, "Breite der Gesprächs-Spalte in px.");
            KnopfGroesse = Config.Bind("Darstellung", "KnopfGroesse", 16f, "Kantenlänge der Buttons in px.");

            var h = new Harmony(GUID);
            h.PatchAll(typeof(OpenPatch));
            h.PatchAll(typeof(PopupPatch));
            AddComponent<Tick>();
            L.LogInfo($"[Gespraech] {NAME} {VERSION} geladen. F5 Spalte, F4 Stellung; einmal rechtsklicken zum Start.");
        }
    }

    internal static class Info
    {
        internal static ContextMenuSubsystem Subsystem;

        internal static string Typ(Il2CppSystem.Object o)
        {
            if (o == null) return "null";
            try { return o.GetIl2CppType().FullName; } catch { return "?"; }
        }
    }

    // Jedes Kontextmenü läuft hierdurch: Menüsystem merken, echte Rechtsklicks von eigenen Menüs unterscheiden
    [HarmonyPatch(typeof(ContextMenuSubsystem), nameof(ContextMenuSubsystem.OpenContextMenu))]
    internal static class OpenPatch
    {
        [HarmonyPrefix]
        private static void Prefix(ContextMenuSubsystem __instance, MenuContext context)
        {
            if (!Plugin.Enabled.Value) return;
            if (Info.Subsystem == null) Plugin.L.LogInfo("[Gespraech] Menüsystem bekannt (erster Rechtsklick), Prüfungen starten.");
            Info.Subsystem = __instance;
            try
            {
                if (ZeilenMenue.IstEigener(context)) return;
                if (context?.Target != null) ZeilenMenue.Muster = context;
                ZeilenMenue.EchtesMenueSeit = Time.unscaledTime;
                ZeilenMenue.Abbrechen();  // echter Rechtsklick hat Vorrang vor einem eigenen Vorgang
            }
            catch (Exception e) { Plugin.L.LogWarning($"[Gespraech] Kontext: {e.Message}"); }
        }
    }

    public class Tick : MonoBehaviour
    {
        public Tick(IntPtr ptr) : base(ptr) { }

        private void Update()
        {
            if (!Plugin.Enabled.Value) return;
            try
            {
                var maus = Mouse.current;
                var rm = maus?.rightButton;
                if (rm != null && rm.isPressed)
                {
                    ZeilenMenue.EchtesMenueSeit = Time.unscaledTime;  // Prüfungen pausieren
                    ZeilenMenue.PruefungAbbrechen();
                }
                // Esc oder Linksklick schließen ein echtes Menü: Pause auf 0,3 s verkürzen
                bool zu = (maus?.leftButton?.wasPressedThisFrame ?? false)
                          || (Keyboard.current?.escapeKey?.wasPressedThisFrame ?? false);
                if (zu && Time.unscaledTime - ZeilenMenue.EchtesMenueSeit < 10f)
                    ZeilenMenue.EchtesMenueSeit = Time.unscaledTime - 9.7f;
            }
            catch (Exception e) { Plugin.L.LogWarning($"[Gespraech] Maus: {e.Message}"); }
            try { ZeilenKnoepfe.Update(); }
            catch (Exception e) { Plugin.L.LogError($"[Gespraech] Knöpfe: {e}"); }
            try { ZeilenMenue.Update(); }
            catch (Exception e) { Plugin.L.LogError($"[Gespraech] Menü: {e}"); }
            try
            {
                var kb = Keyboard.current;
                if (kb == null) return;
                var t5 = kb[Plugin.SpalteKey.Value];
                if (t5 != null && t5.wasPressedThisFrame) ZeilenKnoepfe.Umschalten();
                var t4 = kb[Plugin.StellungKey.Value];
                if (t4 != null && t4.wasPressedThisFrame) ZeilenKnoepfe.StellungWechseln();
            }
            catch (Exception e) { Plugin.L.LogError($"[Gespraech] Tasten: {e}"); }
        }
    }
}
