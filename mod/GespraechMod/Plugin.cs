// GespraechMod – Spike A/B: Kontextmenü-Einträge mitschneiden und ihren Klick-Handler selbst auslösen.
//
// v0.1/v0.2: Haken in FM.Game.PluginContextMenuContributor griffen beim Spielermenü nicht (25.11.2026).
// v0.3:
//  - ContextMenuSubsystem.OpenContextMenu: loggt, welche IMenuContributor das Menü füllen.
//  - MenuDescription.AddItem(..., Il2CppSystem.Action): loggt Name des Eintrags, Klasse/Methode des Handlers und
//    die eingefangenen Felder des Handler-Ziels (z. B. Spieler-Referenz, Aktion); merkt sich den Handler je Name.
//  - Taste F9: ruft den gemerkten Handler des Eintrags ReplayText (Standard "Leistung im letzten Spiel loben") auf,
//    auch wenn das Menü schon geschlossen ist.
// v0.4: AddItem(…, Action) wird für das Spielermenü nicht benutzt (Log 25.11.). Stattdessen liest Tick den fertigen
//       Menübaum (ContextMenuSubsystem.m_popupContext.Description.m_entries) alle 0,3 s, solange ein Menü offen ist.
// v0.5: Inhalt von data/rowDataRecord (SI.Bindable.DynamicReference = Record = Dictionary<uint, TypedValue>) ausgeben,
//       um die Spieler-Kennung zu finden. Felder der Closure nur noch einmal je Menütext ausführlich.
// v0.6: Spike C (Austausch.cs): Vorlage je Menütext, Spieler per P_ID tauschen; HTTP 127.0.0.1:8701; F10 = Test mit
//       TestPid/TestText aus der Config. Feld-Dump nur mit Ausfuehrlich=true.
// v0.7: Spike D (ZeilenMenue.cs): Taste F7 über einer Kaderzeile öffnet deren Kontextmenü selbst und löst ZeilenText
//       aus. Spike C (Austausch) öffnete das Gespräch weiter mit dem Vorlagenspieler.
// v0.8: Buttons je Spielerzeile (ZeilenKnoepfe.cs), Menü beim Auslösen unsichtbar und danach geschlossen;
//       F6 = Struktur der Zeile unter der Maus loggen.
// v0.9: Menü wird beim eigenen Öffnen gar nicht angezeigt (PopupPatch), Verfügbarkeit je Zeile im Hintergrund
//       geprüft (graue Buttons), Buttons als eigene Zelle neben "Spieler"; F5 = Spalte ein/aus.
// v0.10: Kopfzelle "Gespräche" (Kopfzeile per x-Positionen gesucht). Haken auf Initialise/Sichtbarkeitswechsel
//        ließen FM27 beim Laden abstürzen (IL2CPP-Methodenfaltung) -> v0.11 ohne diese Haken; echte Menüs über OpenPatch.
// v0.12: echter Rechtsklick bricht eine laufende Prüfung ab (Menü wird angezeigt); nach einem Klick bleibt der
//        bekannte Stand stehen (geklickter Typ sofort grau); ungeprüfte Buttons halbtransparent.
// v0.13: F4 wechselt die Stellung der Spalte (nach Spieler / ganz vorne / ganz hinten); nach echtem Rechtsklick
//        2 s feste Prüfpause (erster Rechtsklick nach dem Start wurde von der ersten Prüfung überholt).
// v0.14: rechte Maustaste/Button-Klick brechen eine laufende Prüfung ab (Rechtsklick schloss sonst nur das
//        unsichtbare Prüfmenü); gestörte Prüfung (kein auslösbarer Eintrag) = unbekannt statt alles grau;
//        Kopfzelle wird wieder eingesetzt, wenn FM die Kopfzeile neu aufbaut.
// v0.15: Spalte nur in Tabellen mit Spielern des eigenen Vereins (Menü hat Ordner "Interaktion"); Scouting,
//        Spielerdatenbank usw. bleiben ohne Spalte.
// Nur mit einer Kopie des Spielstands testen.

using System;
using System.Collections.Generic;
using System.Text;
using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using HarmonyLib;
using Il2CppInterop.Runtime;
using SI.Interop;
using SI.UI;
using UnityEngine;
using UnityEngine.InputSystem;
using BF = Il2CppSystem.Reflection.BindingFlags;

namespace GespraechMod
{
    [BepInPlugin(GUID, NAME, VERSION)]
    public class Plugin : BasePlugin
    {
        public const string GUID = "fm27assistant.gespraech";
        public const string NAME = "Gespraech";
        public const string VERSION = "0.16.0";

        internal static ManualLogSource L;
        internal static ConfigEntry<bool> Enabled;
        internal static ConfigEntry<Key> ReplayKey;
        internal static ConfigEntry<string> ReplayText;
        internal static ConfigEntry<string> LogFilter;
        internal static ConfigEntry<bool> Ausfuehrlich;
        internal static ConfigEntry<Key> TestKey;
        internal static ConfigEntry<int> TestPid;
        internal static ConfigEntry<string> TestText;
        internal static ConfigEntry<int> Port;
        internal static ConfigEntry<Key> ZeilenKey;
        internal static ConfigEntry<string> ZeilenText;
        internal static ConfigEntry<bool> Knoepfe;
        internal static ConfigEntry<Key> DumpKey;
        internal static ConfigEntry<Key> SpalteKey;
        internal static ConfigEntry<Key> StellungKey;
        internal static ConfigEntry<int> SpaltenStellung;
        internal static ConfigEntry<bool> AlsSpalte;
        internal static ConfigEntry<float> SpaltenBreite;
        internal static ConfigEntry<float> KnopfGroesse;
        internal static ConfigEntry<bool> VerfuegbarkeitPruefen;
        internal static ConfigEntry<bool> MenueUnterdruecken;

        public override void Load()
        {
            L = Log;
            Enabled = Config.Bind("Allgemein", "Enabled", true, "Mitschnitt und Wiederholung an/aus.");
            ReplayKey = Config.Bind("Spike", "ReplayKey", Key.F9, "Gemerkten Handler auslösen.");
            ReplayText = Config.Bind("Spike", "ReplayText", "Leistung im letzten Spiel loben",
                "Menütext des Eintrags, dessen Handler F9 auslöst.");
            LogFilter = Config.Bind("Spike", "LogFilter", "loben|kritisieren|Loben|Warnung|Interaktion",
                "Nur Einträge, deren Text eines dieser Wörter enthält, ausführlich loggen (| getrennt; leer = alle).");
            Ausfuehrlich = Config.Bind("Spike", "Ausfuehrlich", false, "Felder der Handler-Closure vollständig loggen.");
            TestKey = Config.Bind("Spike", "TestKey", Key.F10, "Vorlage TestText für TestPid auslösen.");
            TestPid = Config.Bind("Spike", "TestPid", 0, "P_ID des Zielspielers (FMMT-Reader, Offset 0x08).");
            TestText = Config.Bind("Spike", "TestText", "Verhalten loben", "Menütext der Vorlage für F10.");
            Port = Config.Bind("Allgemein", "Port", 8701, "HTTP-Port (nur 127.0.0.1).");
            ZeilenKey = Config.Bind("SpikeD", "ZeilenKey", Key.F7, "Maus über Spielerzeile: Menü öffnen und ZeilenText auslösen.");
            ZeilenText = Config.Bind("SpikeD", "ZeilenText", "Verhalten loben", "Menütext, den F7 auslöst.");
            Knoepfe = Config.Bind("Allgemein", "Knoepfe", true, "Gesprächs-Buttons in Spielerzeilen einblenden.");
            DumpKey = Config.Bind("SpikeD", "DumpKey", Key.F6, "Struktur der Zeile unter der Maus loggen.");
            SpalteKey = Config.Bind("Allgemein", "SpalteKey", Key.F5, "Gesprächs-Spalte ein-/ausblenden.");
            StellungKey = Config.Bind("Allgemein", "StellungKey", Key.F4, "Stellung der Gesprächs-Spalte wechseln.");
            SpaltenStellung = Config.Bind("Darstellung", "SpaltenStellung", 0, "0 = nach Spieler, 1 = ganz vorne, 2 = ganz hinten.");
            AlsSpalte = Config.Bind("Darstellung", "AlsSpalte", true, "Eigene Zelle neben 'Spieler' (sonst hinter dem Namen).");
            SpaltenBreite = Config.Bind("Darstellung", "SpaltenBreite", 150f, "Breite der Gesprächs-Spalte in px.");
            KnopfGroesse = Config.Bind("Darstellung", "KnopfGroesse", 16f, "Kantenlänge der Buttons in px.");
            VerfuegbarkeitPruefen = Config.Bind("Allgemein", "VerfuegbarkeitPruefen", true, "Nicht angebotene Gespräche grau anzeigen (liest je Zeile unsichtbar das Menü).");
            MenueUnterdruecken = Config.Bind("Allgemein", "MenueUnterdruecken", true, "Menü beim eigenen Öffnen nicht anzeigen.");
            Austausch.ServerStarten(Port.Value);
            var h = new Harmony(GUID);
            h.PatchAll(typeof(OpenPatch));
            h.PatchAll(typeof(AddItemPatch));
            h.PatchAll(typeof(AddItemEnabledPatch));
            h.PatchAll(typeof(PopupPatch));
            foreach (var m in h.GetPatchedMethods())
                L.LogInfo($"[Gespraech] gepatcht: {m.DeclaringType?.FullName}.{m.Name}");
            AddComponent<Tick>();
            L.LogInfo($"[Gespraech] {NAME} {VERSION} geladen. Replay={ReplayKey.Value} '{ReplayText.Value}'");
        }
    }

    internal static class Info
    {
        internal static readonly Dictionary<string, Il2CppSystem.Action> Handler = new();
        internal static bool Wiederholung;
        internal static ContextMenuSubsystem Subsystem;
        internal static readonly HashSet<string> Gesehen = new();

        internal static bool Interessant(string name)
        {
            var f = Plugin.LogFilter.Value;
            if (string.IsNullOrEmpty(f)) return true;
            if (string.IsNullOrEmpty(name)) return false;
            foreach (var w in f.Split('|'))
                if (w.Length > 0 && name.Contains(w)) return true;
            return false;
        }

        internal static string Typ(Il2CppSystem.Object o)
        {
            if (o == null) return "null";
            try { return o.GetIl2CppType().FullName; } catch { return "?"; }
        }

        internal static string Referenz(InteropReference r)
        {
            if (r == null) return "null";
            var sb = new StringBuilder(Typ(r));
            try { sb.Append(" id=").Append(r.GetPersistentIdentity()); } catch { }
            try
            {
                var ids = r.m_id;
                sb.Append(" pairs=[");
                for (int i = 0; ids != null && i < ids.Count; i++)
                    sb.Append(i == 0 ? "" : ", ").Append(FourCC(ids[i].ID)).Append('=').Append(ids[i].Value);
                sb.Append(']');
            }
            catch (Exception e) { sb.Append(" pairs?").Append(e.GetType().Name); }
            return sb.ToString();
        }

        // Felder eines Objekts (Closure des Handlers) über Il2Cpp-Reflection, eine Ebene tief
        internal static string Felder(Il2CppSystem.Object o, int tiefe = 0)
        {
            if (o == null) return "null";
            var sb = new StringBuilder();
            try
            {
                var t = o.GetIl2CppType();
                foreach (var f in t.GetFields(BF.Instance | BF.Public | BF.NonPublic))
                {
                    Il2CppSystem.Object v = null;
                    try { v = f.GetValue(o); } catch { }
                    sb.Append("\n      ").Append(new string(' ', tiefe * 4)).Append(f.Name).Append(" : ")
                      .Append(f.FieldType?.FullName).Append(" = ");
                    if (v == null) { sb.Append("null"); continue; }
                    var r = v.TryCast<InteropReference>();
                    if (r != null) { sb.Append(Referenz(r)); continue; }
                    var rec = v.TryCast<SI.Core.Record>();
                    if (rec != null) { sb.Append(Datensatz(rec, tiefe + 1)); continue; }
                    var tv = v.TryCast<SI.Core.TypedValue>();
                    if (tv != null) { sb.Append(Wert(tv, tiefe + 1)); continue; }
                    string s;
                    try { s = v.ToString(); } catch { s = "?"; }
                    sb.Append(s);
                    if (tiefe == 0 && !f.FieldType.IsPrimitive && !f.FieldType.IsEnum && f.FieldType.FullName != "System.String"
                        && (f.FieldType.FullName ?? "").Contains("DisplayClass"))
                        sb.Append(Felder(v, tiefe + 1));
                }
            }
            catch (Exception e) { sb.Append(" felder?").Append(e.GetType().Name).Append(' ').Append(e.Message); }
            return sb.ToString();
        }

        internal static string Wert(SI.Core.TypedValue v, int tiefe)
        {
            if (v == null) return "null";
            var sb = new StringBuilder(Typ(v));
            Il2CppSystem.Object o = null;
            try { o = v.Get(); } catch { }
            if (o == null)
            {
                try { sb.Append(" '").Append(v.AsString()).Append("'"); } catch { }
                return sb.ToString();
            }
            sb.Append(" -> ").Append(Typ(o));
            var r = o.TryCast<InteropReference>();
            if (r != null) return sb.Append(' ').Append(Referenz(r)).ToString();
            var rec = o.TryCast<SI.Core.Record>();
            if (rec != null) return sb.Append(Datensatz(rec, tiefe)).ToString();
            try { sb.Append(" '").Append(v.AsString()).Append("'"); } catch { }
            return sb.ToString();
        }

        internal static string Datensatz(SI.Core.Record rec, int tiefe)
        {
            if (rec == null) return "null";
            var sb = new StringBuilder($" [{Typ(rec)} n={rec.Count}]");
            if (tiefe > 3) return sb.Append(" …").ToString();
            var e = rec.GetEnumerator();
            while (e.MoveNext())
            {
                var kv = e.Current;
                sb.Append("\n      ").Append(new string(' ', tiefe * 4)).Append(FourCC(kv.Key)).Append(" = ")
                  .Append(Wert(kv.Value, tiefe + 1));
            }
            return sb.ToString();
        }

        internal static string Delegat(Il2CppSystem.Delegate d)
        {
            if (d == null) return "null";
            var sb = new StringBuilder();
            try
            {
                var m = d.Method;
                sb.Append(m?.DeclaringType?.FullName).Append("::").Append(m?.Name);
            }
            catch (Exception e) { sb.Append("method?").Append(e.GetType().Name); }
            try
            {
                var t = d.Target;
                sb.Append(" ziel=").Append(Typ(t));
                if (t != null) sb.Append(Felder(t));
            }
            catch (Exception e) { sb.Append(" target?").Append(e.GetType().Name); }
            return sb.ToString();
        }

        internal static string FourCC(uint id)
        {
            var b = BitConverter.GetBytes(id);
            foreach (var c in b) if (c < 32 || c > 126) return id.ToString();
            Array.Reverse(b);
            return $"{id}('{Encoding.ASCII.GetString(b)}')";
        }

        // Fertigen Menübaum lesen (Felder, keine Methoden-Hooks)
        internal static void Scannen()
        {
            if (ZeilenMenue.Laeuft) return;  // eigene Menüs nicht als Vorlage/Log erfassen
            var ctx = Subsystem?.m_popupContext;
            var desc = ctx?.Description;
            var es = desc?.m_entries;
            if (es == null) return;
            for (int i = 0; i < es.Count; i++)
            {
                var e = es[i];
                if (e == null) continue;
                string name = null;
                try { name = e._Name_k__BackingField; } catch { }
                if (string.IsNullOrEmpty(name) || !Interessant(name)) continue;
                Il2CppSystem.Action h = null;
                try { h = e._HandleInteraction_k__BackingField; } catch { }
                string schluessel = $"{name}|{(h == null ? 0 : h.Pointer.ToInt64())}";
                if (!Gesehen.Add(schluessel)) continue;
                string eltern = null;
                try { eltern = e._Parent_k__BackingField?._Name_k__BackingField; } catch { }
                if (h != null) Handler[name] = h;
                try { Austausch.Merken(name, h); } catch (Exception ex) { Plugin.L.LogWarning($"[Gespraech] Vorlage '{name}': {ex.Message}"); }
                if (Plugin.Ausfuehrlich.Value)
                    Plugin.L.LogInfo($"[Gespraech] Eintrag '{name}' (in '{eltern}') kind={e._Kind_k__BackingField} handler={Delegat(h)}");
            }
        }

        internal static void Eintrag(string name, Il2CppSystem.Action handler)
        {
            if (!Plugin.Enabled.Value || Wiederholung) return;
            try
            {
                if (!Interessant(name))
                {
                    Plugin.L.LogDebug($"[Gespraech] AddItem '{name}'");
                    return;
                }
                if (handler != null && !string.IsNullOrEmpty(name)) Handler[name] = handler;
                Plugin.L.LogInfo($"[Gespraech] AddItem '{name}' handler={Delegat(handler)}");
            }
            catch (Exception e) { Plugin.L.LogError($"[Gespraech] AddItem: {e}"); }
        }
    }

    [HarmonyPatch(typeof(ContextMenuSubsystem), nameof(ContextMenuSubsystem.OpenContextMenu))]
    internal static class OpenPatch
    {
        [HarmonyPrefix]
        private static void Prefix(ContextMenuSubsystem __instance, MenuContext context)
        {
            if (!Plugin.Enabled.Value) return;
            if (Info.Subsystem == null) Plugin.L.LogInfo("[Gespraech] Menüsystem bekannt (erster Rechtsklick), Prüfungen starten.");
            Info.Subsystem = __instance;
            Info.Gesehen.Clear();
            try
            {
                bool eigen = ZeilenMenue.IstEigener(context);
                if (!eigen && context?.Target != null) ZeilenMenue.Muster = context;
                if (!eigen)
                {
                    ZeilenMenue.EchtesMenueSeit = UnityEngine.Time.unscaledTime;
                    ZeilenMenue.Abbrechen();
                }
                if (eigen || !Plugin.Ausfuehrlich.Value) return;
                Plugin.L.LogInfo($"[Gespraech] Kontext{(eigen ? " (eigener)" : "")}: picked={context?.TargetWasPicked} " +
                    $"anchor={context?.PreferredFolderAnchor} cascade={context?.CascadeDirection} " +
                    $"desc={(context?.Description == null ? "null" : "da")} ziel={ZeilenMenue.Kette(context?.Target, 6)}");
            }
            catch (Exception e) { Plugin.L.LogWarning($"[Gespraech] Kontext: {e.Message}"); }
            try
            {
                var g = __instance.m_globalContributors;
                var gs = new StringBuilder();
                for (int i = 0; g != null && i < g.Count; i++)
                    gs.Append(i == 0 ? "" : ", ").Append(g[i] == null ? "null" : Info.Typ(new Il2CppSystem.Object(g[i].Pointer)));
                Plugin.L.LogInfo($"[Gespraech] global contributors=[{gs}]");
                var sb = new StringBuilder("[Gespraech] OpenContextMenu contributors=[");
                var cs = context?.m_contributors;
                for (int i = 0; cs != null && i < cs.Count; i++)
                {
                    var c = cs[i];
                    sb.Append(i == 0 ? "" : ", ")
                      .Append(c == null ? "null" : Info.Typ(new Il2CppSystem.Object(c.Pointer)));
                }
                sb.Append("] target=").Append(context?.Target?.name);
                Plugin.L.LogInfo(sb.ToString());
            }
            catch (Exception e) { Plugin.L.LogError($"[Gespraech] Open: {e}"); }
        }
    }

    [HarmonyPatch(typeof(MenuDescription), nameof(MenuDescription.AddItem),
        new[] { typeof(MenuDescription.EntryID), typeof(string), typeof(Il2CppSystem.Action) })]
    internal static class AddItemPatch
    {
        [HarmonyPrefix]
        private static void Prefix(string name, Il2CppSystem.Action handleInteraction) =>
            Info.Eintrag(name, handleInteraction);
    }

    [HarmonyPatch(typeof(MenuDescription), nameof(MenuDescription.AddItem),
        new[] { typeof(MenuDescription.EntryID), typeof(string), typeof(bool), typeof(Il2CppSystem.Action) })]
    internal static class AddItemEnabledPatch
    {
        [HarmonyPrefix]
        private static void Prefix(string name, Il2CppSystem.Action handleInteraction) =>
            Info.Eintrag(name, handleInteraction);
    }

    public class Tick : MonoBehaviour
    {
        public Tick(IntPtr ptr) : base(ptr) { }

        private float naechsterScan;

        private void Update()
        {
            if (Plugin.Enabled.Value && Info.Subsystem != null && Time.unscaledTime >= naechsterScan)
            {
                naechsterScan = Time.unscaledTime + 0.3f;
                try { Info.Scannen(); }
                catch (Exception e) { Plugin.L.LogError($"[Gespraech] Scan: {e}"); naechsterScan = Time.unscaledTime + 5f; }
            }
            try
            {
                var maus = UnityEngine.InputSystem.Mouse.current;
                var rm = maus?.rightButton;
                if (rm != null && rm.isPressed)
                {
                    ZeilenMenue.EchtesMenueSeit = Time.unscaledTime;  // Prüfungen pausieren
                    ZeilenMenue.PruefungAbbrechen();
                }
                // Esc oder Linksklick schließen ein echtes Menü: Pause auf 0,3 s verkürzen
                bool zu = (maus?.leftButton?.wasPressedThisFrame ?? false)
                          || (UnityEngine.InputSystem.Keyboard.current?.escapeKey?.wasPressedThisFrame ?? false);
                if (zu && Time.unscaledTime - ZeilenMenue.EchtesMenueSeit < 10f)
                    ZeilenMenue.EchtesMenueSeit = Time.unscaledTime - 9.7f;
            }
            catch (Exception e) { Plugin.L.LogWarning($"[Gespraech] Maus: {e.Message}"); }
            try { ZeilenKnoepfe.Update(); }
            catch (Exception e) { Plugin.L.LogError($"[Gespraech] Knöpfe: {e}"); }
            try { ZeilenMenue.Update(); }
            catch (Exception e) { Plugin.L.LogError($"[Gespraech] Spike D: {e}"); }
            while (Plugin.Enabled.Value && Austausch.Auftraege.TryDequeue(out var a))
            {
                string erg;
                try { erg = Austausch.Ausfuehren(a.pid, a.text); }
                catch (Exception e) { erg = "Fehler: " + e.Message; Plugin.L.LogError($"[Gespraech] Auftrag: {e}"); }
                Austausch.LetztesErgebnis = erg;
                Plugin.L.LogInfo($"[Gespraech] Auftrag pid={a.pid} '{a.text}': {erg}");
            }
            try
            {
                var kb = Keyboard.current;
                if (kb == null || !Plugin.Enabled.Value) return;
                var t7 = kb[Plugin.ZeilenKey.Value];
                var t5 = kb[Plugin.SpalteKey.Value];
                if (t5 != null && t5.wasPressedThisFrame) ZeilenKnoepfe.Umschalten();
                var t4 = kb[Plugin.StellungKey.Value];
                if (t4 != null && t4.wasPressedThisFrame) ZeilenKnoepfe.StellungWechseln();
                var t6 = kb[Plugin.DumpKey.Value];
                if (t6 != null && t6.wasPressedThisFrame)
                {
                    try { ZeilenMenue.Dump(); } catch (Exception e) { Plugin.L.LogError($"[Gespraech] Dump: {e}"); }
                }
                if (t7 != null && t7.wasPressedThisFrame)
                {
                    try { ZeilenMenue.StartMaus(Plugin.ZeilenText.Value); }
                    catch (Exception e) { Plugin.L.LogError($"[Gespraech] Spike D Start: {e}"); }
                }
                var t10 = kb[Plugin.TestKey.Value];
                if (t10 != null && t10.wasPressedThisFrame)
                    Austausch.Auftraege.Enqueue((Plugin.TestPid.Value, Plugin.TestText.Value));
                var k = kb[Plugin.ReplayKey.Value];
                if (k == null || !k.wasPressedThisFrame) return;
                var text = Plugin.ReplayText.Value;
                if (!Info.Handler.TryGetValue(text, out var h) || h == null)
                {
                    Plugin.L.LogWarning($"[Gespraech] Kein Handler für '{text}' gemerkt. Gemerkt: " +
                        string.Join(", ", Info.Handler.Keys));
                    return;
                }
                Plugin.L.LogInfo($"[Gespraech] Löse '{text}' aus …");
                Info.Wiederholung = true;
                try { h.Invoke(); }
                finally { Info.Wiederholung = false; }
                Plugin.L.LogInfo("[Gespraech] Handler ohne Ausnahme zurückgekehrt.");
            }
            catch (Exception e) { Plugin.L.LogError($"[Gespraech] Tick: {e}"); }
        }
    }
}
