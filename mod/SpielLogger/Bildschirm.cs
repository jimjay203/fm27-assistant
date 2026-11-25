// Bildschirmtext-Export (Taste BildschirmKey): alle sichtbaren Texte aller UI-Panels mit Position und Elementnamen
// als JSON – ersetzt Screenshots. Nur lesend; erfasst wird nur, was gerade auf dem Bildschirm steht.

using System;
using System.Collections.Generic;
using System.IO;
using Il2CppInterop.Runtime;
using UnityEngine;
using UnityEngine.UIElements;

namespace SpielLogger
{
    internal static class Bildschirm
    {
        private const int MaxTiefe = 120, MaxElemente = 200000;

        internal static void Exportieren()
        {
            var texte = new List<object>();
            int elemente = 0, fehler = 0, panel = 0;
            foreach (var o in UnityEngine.Object.FindObjectsOfType(Il2CppType.Of<UIDocument>()))
            {
                var wurzel = o.TryCast<UIDocument>()?.rootVisualElement;
                if (wurzel == null) continue;
                Sammeln(wurzel, panel++, new List<string>(), texte, ref elemente, ref fehler, 0);
            }
            var ordner = Path.Combine(Plugin.Ordner.Value, "bildschirm");
            Directory.CreateDirectory(ordner);
            var jetzt = DateTime.Now;
            var name = $"{jetzt:yyyyMMdd_HHmmss_fff}.json";
            Mitschnitt.Schreiben(Path.Combine(ordner, name), new
            {
                t = "bildschirm", version = Plugin.VERSION, zeit = jetzt.ToString("s"),
                breite = Screen.width, hoehe = Screen.height, panels = panel, elemente, fehler, texte,
            });
            Mitschnitt.BildschirmMerken(name);
            Plugin.L.LogInfo($"Bildschirm: {texte.Count} Texte aus {elemente} Elementen -> {name} (Fehler {fehler})");
        }

        // namen = benannte Vorfahren (für die spätere Zuordnung: Tabelle, Kachel, Panel)
        private static void Sammeln(VisualElement e, int panel, List<string> namen, List<object> texte,
            ref int elemente, ref int fehler, int tiefe)
        {
            if (e == null || tiefe > MaxTiefe || elemente >= MaxElemente) return;
            elemente++;
            bool benannt = false;
            try
            {
                var stil = e.resolvedStyle;
                if (stil.display == DisplayStyle.None || stil.opacity <= 0.01f) return;
                var name = e.name;
                if (!string.IsNullOrEmpty(name)) { namen.Add(name); benannt = true; }
                var text = stil.visibility == Visibility.Hidden ? null : e.TryCast<TextElement>()?.text;
                if (!string.IsNullOrWhiteSpace(text))
                {
                    var r = e.worldBound;
                    if (float.IsFinite(r.x) && float.IsFinite(r.y) && r.width > 0.5f && r.height > 0.5f)
                        texte.Add(new
                        {
                            p = panel, text, x = (int)r.x, y = (int)r.y, b = (int)r.width, h = (int)r.height,
                            pfad = namen.GetRange(Math.Max(0, namen.Count - 6), Math.Min(6, namen.Count)),
                        });
                }
                int n = e.childCount;
                for (int i = 0; i < n; i++)
                    Sammeln(e[i], panel, namen, texte, ref elemente, ref fehler, tiefe + 1);
            }
            catch (Exception ex)
            {
                fehler++;
                if (fehler <= 3) Plugin.L.LogWarning($"Bildschirm: {ex.GetType().Name}: {ex.Message}");
            }
            finally
            {
                if (benannt) namen.RemoveAt(namen.Count - 1);
            }
        }
    }
}
