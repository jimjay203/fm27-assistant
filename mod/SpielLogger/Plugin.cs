// SpielLogger – Test-Plugin: schreibt während eines Spiels Ereignisse und Positionen als JSONL mit (BepInEx 6, IL2CPP).
//
// Nur lesend, KEINE Harmony-Haken. Nie aufgerufen werden Seek, PlayMatchEventAtTime, SkipDeadSimTime,
// Request…Update, Send… und Set… (können den Spielzustand ändern). Im Spiel wird nichts angezeigt.
//
// Stufen (Config "Stufe", im Spiel mit F7 weiterschalten): jede Stufe enthält die vorigen.
//   1 = nur Zähler (Ereignisliste, Zeitscheibe)   2 = Ereignisfelder und Spielerliste
//   3 = Positionen von Spielern und Ball          4 = Ballspur jeder Zeitscheibe (Periodenwechsel, Spielende, F8)
// F9 = sichtbare Bildschirmtexte exportieren (Bildschirm.cs), unabhängig von der Stufe.
// Config: BepInEx\config\fm27assistant.spiellogger.cfg   Ausgabe: BepInEx\SpielLogger\*.jsonl

using System;
using System.IO;
using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using UnityEngine;
using UnityEngine.InputSystem;

namespace SpielLogger
{
    [BepInPlugin(GUID, NAME, VERSION)]
    public class Plugin : BasePlugin
    {
        public const string GUID = "fm27assistant.spiellogger";
        public const string NAME = "SpielLogger";
        public const string VERSION = "0.2.0";

        internal static ManualLogSource L;
        internal static ConfigEntry<int> Stufe;
        internal static ConfigEntry<float> PositionenHz;
        internal static ConfigEntry<string> Ordner;
        internal static ConfigEntry<Key> StufeKey;
        internal static ConfigEntry<Key> RueckblickKey;
        internal static ConfigEntry<Key> BildschirmKey;

        public override void Load()
        {
            L = Log;
            Stufe = Config.Bind("Allgemein", "Stufe", 4,
                "0 = aus, 1 = Zähler, 2 = +Ereignisse, 3 = +Positionen, 4 = +Ballspur.");
            PositionenHz = Config.Bind("Allgemein", "PositionenHz", 30f, "Positionsmessungen je Sekunde (Echtzeit).");
            Ordner = Config.Bind("Allgemein", "Ordner", Path.Combine(Paths.BepInExRootPath, "SpielLogger"),
                "Ausgabeordner.");
            StufeKey = Config.Bind("Allgemein", "StufeKey", Key.F7, "Stufe weiterschalten (0–4).");
            RueckblickKey = Config.Bind("Allgemein", "RueckblickKey", Key.F8, "Alles bis jetzt schreiben (Halbzeit, Abpfiff).");
            BildschirmKey = Config.Bind("Allgemein", "BildschirmKey", Key.F9, "Sichtbare Bildschirmtexte exportieren.");
            AddComponent<Tick>();
            L.LogInfo($"{NAME} {VERSION} geladen, Stufe {Stufe.Value}. {StufeKey.Value} Stufe, {RueckblickKey.Value} Stand schreiben, {BildschirmKey.Value} Bildschirm.");
        }
    }

    public class Tick : MonoBehaviour
    {
        public Tick(IntPtr ptr) : base(ptr) { }

        private void Update()
        {
            try
            {
                var tasten = Keyboard.current;
                if (tasten != null && tasten[Plugin.StufeKey.Value].wasPressedThisFrame)
                {
                    Plugin.Stufe.Value = (Plugin.Stufe.Value + 1) % 5;
                    Plugin.L.LogInfo($"Stufe {Plugin.Stufe.Value}");
                }
                bool rueckblick = tasten != null && tasten[Plugin.RueckblickKey.Value].wasPressedThisFrame;
                Mitschnitt.Update(rueckblick);
                if (tasten != null && tasten[Plugin.BildschirmKey.Value].wasPressedThisFrame) Bildschirm.Exportieren();
            }
            catch (Exception e) { Mitschnitt.Fehler("Update", e); }
        }

        private void OnApplicationQuit() => Mitschnitt.Schliessen("spiel beendet");
    }
}
