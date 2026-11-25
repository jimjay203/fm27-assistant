// Spike C: Gespräch für einen beliebigen Spieler auslösen.
//
// Vorlage = Handler-Closure eines Menüeintrags (<>c__DisplayClass47_0), gemerkt beim Lesen eines offenen Menüs.
// Der Spieler steckt in data/rowDataRecord als 'Ctid' › 'dref' = 0x01000000 | P_ID (P_ID = Personen-ID im Speicher,
// FMMT-Reader Offset 0x08; geprüft 25.11.2026: Ndiaye P_ID 6057 = dref 16783273, Pieper 29260 = 16806476).
// Austausch: alle 'dref' mit dem Wert des Vorlagenspielers vorübergehend auf den Zielspieler setzen, Handler
// aufrufen, Werte zurücksetzen.
//
// HTTP (nur 127.0.0.1, eigener kleiner TCP-Server, keine URL-ACL nötig):
//   GET  /status                       -> Vorlagen, letztes Ergebnis
//   POST /gespraech?pid=6057&text=...  -> in die Warteschlange; ausgeführt im nächsten Frame (Unity-Main-Thread)

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using FM.Game;
using SI.Core;
using SI.Bindable;

namespace GespraechMod
{
    internal static class Austausch
    {
        internal const uint DREF = 1685218662;  // 'dref'
        internal const uint CTID = 1131702628;  // 'Ctid'
        internal const int DREF_PERSON = 0x01000000;

        internal sealed class Vorlage
        {
            internal string Text;
            internal PluginContextMenuContributor.__c__DisplayClass47_0 Closure;
            internal int Dref;
        }

        internal static readonly Dictionary<string, Vorlage> Vorlagen = new();
        internal static readonly ConcurrentQueue<(int pid, string text)> Auftraege = new();
        internal static volatile string LetztesErgebnis = "noch nichts";

        internal static void Merken(string text, Il2CppSystem.Action h)
        {
            if (h == null) return;
            var ziel = h.Target;
            var c = ziel?.TryCast<PluginContextMenuContributor.__c__DisplayClass47_0>();
            if (c == null) return;
            int dref = SpielerDref(c.data);
            if (dref == 0) return;
            Vorlagen[text] = new Vorlage { Text = text, Closure = c, Dref = dref };
        }

        // data -> DynamicReference -> 'Ctid' -> DynamicReference -> 'dref'
        internal static int SpielerDref(TypedValue data)
        {
            var rec = data?.Get()?.TryCast<Record>();
            if (rec == null) return 0;
            if (!rec.TryGetValue(CTID, out var ctid) || ctid == null) return 0;
            var inner = ctid.Get()?.TryCast<Record>();
            if (inner == null || !inner.TryGetValue(DREF, out var d) || d == null) return 0;
            return Zahl(d);
        }

        internal static int Zahl(TypedValue v)
        {
            try { return int.Parse(v.AsString()); } catch { return 0; }
        }

        // Alle NumericTypedValue unter key 'dref' mit Wert `alt` sammeln (rekursiv, Zyklen abgefangen)
        internal static void Sammeln(Il2CppSystem.Object o, int alt, List<TypedValue> treffer, HashSet<IntPtr> besucht, int tiefe = 0)
        {
            if (o == null || tiefe > 8 || !besucht.Add(o.Pointer)) return;
            var tv = o.TryCast<TypedValue>();
            if (tv != null)
            {
                Il2CppSystem.Object inner = null;
                try { inner = tv.Get(); } catch { }
                if (inner != null) Sammeln(inner, alt, treffer, besucht, tiefe + 1);
                return;
            }
            var rec = o.TryCast<Record>();
            if (rec != null)
            {
                var e = rec.GetEnumerator();
                while (e.MoveNext())
                {
                    var kv = e.Current;
                    if (kv.Value == null) continue;
                    if (kv.Key == DREF && kv.Value.TryCast<NumericTypedValue>() != null)
                    {
                        if (Zahl(kv.Value) == alt) treffer.Add(kv.Value);
                        continue;
                    }
                    Sammeln(kv.Value, alt, treffer, besucht, tiefe + 1);
                }
                return;
            }
            var liste = o.TryCast<Il2CppSystem.Collections.Generic.List<TypedValue>>();
            if (liste != null)
                for (int i = 0; i < liste.Count; i++) Sammeln(liste[i], alt, treffer, besucht, tiefe + 1);
        }

        internal static unsafe void Setzen(TypedValue v, int wert)
        {
            var box = Il2CppInterop.Runtime.IL2CPP.il2cpp_value_box(
                Il2CppInterop.Runtime.Il2CppClassPointerStore<int>.NativeClassPtr, (IntPtr)(&wert));
            v.SetValue(new Il2CppSystem.Object(box));
        }

        internal static string Ausfuehren(int pid, string text)
        {
            if (!Vorlagen.TryGetValue(text, out var vl))
                return $"keine Vorlage für '{text}' (vorhanden: {string.Join(", ", Vorlagen.Keys)}); einmal ein Spielermenü mit diesem Eintrag öffnen";
            int neu = DREF_PERSON | (pid & 0xFFFFFF);
            var c = vl.Closure;
            var treffer = new List<TypedValue>();
            var besucht = new HashSet<IntPtr>();
            Sammeln(c.data, vl.Dref, treffer, besucht);
            Sammeln(c.rowDataRecord, vl.Dref, treffer, besucht);
            if (treffer.Count == 0) return $"Vorlage '{text}': Spieler-dref {vl.Dref} nicht gefunden";
            foreach (var t in treffer) Setzen(t, neu);
            int pruef = SpielerDref(c.data);
            Info.Wiederholung = true;
            try
            {
                if (pruef != neu) return $"Austausch fehlgeschlagen (Ctid {pruef} statt {neu})";
                c._RegisterItem_b__4();
                return $"ausgelöst: '{text}' für pid {pid} (dref {neu}, {treffer.Count} Felder getauscht)";
            }
            finally
            {
                Info.Wiederholung = false;
                foreach (var t in treffer) Setzen(t, vl.Dref);
            }
        }

        // ------------------------------------------------------------------ HTTP

        private static Thread s_thread;

        internal static void ServerStarten(int port)
        {
            if (s_thread != null) return;
            s_thread = new Thread(() => Server(port)) { IsBackground = true, Name = "GespraechHttp" };
            s_thread.Start();
        }

        private static void Server(int port)
        {
            TcpListener l;
            try
            {
                l = new TcpListener(IPAddress.Loopback, port);
                l.Start();
                Plugin.L.LogInfo($"[Gespraech] HTTP auf 127.0.0.1:{port}");
            }
            catch (Exception e) { Plugin.L.LogError($"[Gespraech] HTTP-Start: {e.Message}"); return; }
            while (true)
            {
                try
                {
                    using var client = l.AcceptTcpClient();
                    client.ReceiveTimeout = 2000;
                    var s = client.GetStream();
                    var buf = new byte[4096];
                    int n = s.Read(buf, 0, buf.Length);
                    var anfrage = Encoding.UTF8.GetString(buf, 0, n);
                    var zeile = anfrage.Split('\n')[0].Trim();
                    var teile = zeile.Split(' ');
                    string methode = teile.Length > 0 ? teile[0] : "", pfad = teile.Length > 1 ? teile[1] : "/";
                    var (status, json) = Behandeln(methode, pfad);
                    var body = Encoding.UTF8.GetBytes(json);
                    var kopf = $"HTTP/1.1 {status}\r\nContent-Type: application/json; charset=utf-8\r\n" +
                               $"Access-Control-Allow-Origin: http://127.0.0.1:8700\r\nContent-Length: {body.Length}\r\nConnection: close\r\n\r\n";
                    var k = Encoding.ASCII.GetBytes(kopf);
                    s.Write(k, 0, k.Length);
                    s.Write(body, 0, body.Length);
                }
                catch (Exception e) { Plugin.L.LogWarning($"[Gespraech] HTTP: {e.Message}"); }
            }
        }

        private static string J(string s) => "\"" + (s ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";

        private static (string, string) Behandeln(string methode, string pfad)
        {
            var qi = pfad.IndexOf('?');
            var weg = qi < 0 ? pfad : pfad.Substring(0, qi);
            var q = new Dictionary<string, string>();
            if (qi >= 0)
                foreach (var p in pfad.Substring(qi + 1).Split('&'))
                {
                    var kv = p.Split('=', 2);
                    if (kv.Length == 2) q[Uri.UnescapeDataString(kv[0])] = Uri.UnescapeDataString(kv[1].Replace('+', ' '));
                }
            if (weg == "/status")
            {
                var v = new StringBuilder("[");
                int i = 0;
                foreach (var t in Vorlagen.Keys) v.Append(i++ == 0 ? "" : ",").Append(J(t));
                v.Append(']');
                return ("200 OK", $"{{\"ok\":true,\"version\":{J(Plugin.VERSION)},\"vorlagen\":{v},\"letztes\":{J(LetztesErgebnis)}}}");
            }
            if (weg == "/gespraech" && methode == "POST")
            {
                if (!q.TryGetValue("pid", out var ps) || !int.TryParse(ps, out var pid) || pid <= 0)
                    return ("400 Bad Request", "{\"ok\":false,\"fehler\":\"pid fehlt\"}");
                if (!q.TryGetValue("text", out var text) || string.IsNullOrEmpty(text))
                    return ("400 Bad Request", "{\"ok\":false,\"fehler\":\"text fehlt\"}");
                Auftraege.Enqueue((pid, text));
                return ("202 Accepted", $"{{\"ok\":true,\"eingereiht\":{{\"pid\":{pid},\"text\":{J(text)}}}}}");
            }
            return ("404 Not Found", "{\"ok\":false,\"fehler\":\"unbekannt\"}");
        }
    }
}
