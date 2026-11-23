"""FMMT-27-Reader (github.com/fmoreoo/FMMT-27, GPL-3.0) bei Bedarf im Hintergrund mitstarten.

Der Reader ist ein eigenes Programm (`reader/server.py`, nur Python-Standardbibliothek); hier wird er nur als Prozess
gestartet und über HTTP gefragt, kein GPL-Code in diesem Repo. Ordner: Argument, sonst $FM27_FMMT, sonst
~/Developer/fmmt-27-fork.

- Läuft der Reader schon (z. B. per "Start FMMT 27.bat"), wird er genutzt und beim Beenden nicht angefasst.
- Sonst startet ihn `Reader.sicherstellen()` ohne Konsolenfenster und ohne Browser, Ausgabe in logs/fmmt.log,
  und `Reader.stoppen()` beendet ihn wieder.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

FMMT_STANDARD = Path.home() / "Developer" / "fmmt-27-fork"
LOG = common.ROOT / "logs" / "fmmt.log"


def ordner(arg: str | None = None) -> Path | None:
    """FMMT-Ordner mit reader/server.py: Argument, sonst $FM27_FMMT, sonst der Standardpfad; None, wenn nicht da."""
    pfad = Path(arg or os.environ.get("FM27_FMMT") or FMMT_STANDARD)
    return pfad if (pfad / "reader" / "server.py").is_file() else None


def status(url: str, timeout: float = 2) -> dict | None:
    """Antwort von /api/status (ok = FM27 läuft und ist lesbar), None = Reader nicht erreichbar."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/status", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError, OSError):
        return None


def spiel_bereit(url: str) -> bool:
    """True, wenn der Reader läuft und FM27 lesen kann (Spiel offen)."""
    s = status(url)
    return bool(s and s.get("ok"))


class Reader:
    """Verwaltet einen selbst gestarteten Reader-Prozess; ein fremder, schon laufender bleibt unberührt."""

    def __init__(self, url: str, ordner_fmmt: Path | None, log: Path = LOG):
        self.url, self.ordner, self.log = url, ordner_fmmt, log
        self.proc: subprocess.Popen | None = None

    def sicherstellen(self, warten: float = 20) -> str:
        """-> 'läuft' | 'gestartet' | 'kein Ordner' | 'Start fehlgeschlagen: …'."""
        if status(self.url) is not None:
            return "läuft"
        if self.proc and self.proc.poll() is None:  # selbst gestartet, antwortet aber (noch) nicht
            return self._warten(warten)
        if not self.ordner:
            return "kein Ordner"
        port = urlparse(self.url).port or 8627
        self.log.parent.mkdir(parents=True, exist_ok=True)
        logdatei = open(self.log, "a", encoding="utf-8")  # noqa: SIM115 - bleibt offen, solange der Prozess läuft
        logdatei.write(f"\n--- Start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        logdatei.flush()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: kein Konsolenfenster
        self.proc = subprocess.Popen(
            [sys.executable, "server.py", "--no-browser", "--port", str(port)],
            cwd=self.ordner / "reader", stdout=logdatei, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=flags,
        )  # fmt: skip
        return self._warten(warten)

    def _warten(self, warten: float) -> str:
        ende = time.monotonic() + warten
        while time.monotonic() < ende:
            if status(self.url) is not None:
                return "gestartet"
            if self.proc and self.proc.poll() is not None:
                return f"Start fehlgeschlagen: Reader beendet mit Code {self.proc.returncode}, siehe {self.log}"
            time.sleep(0.3)
        return f"Start fehlgeschlagen: keine Antwort nach {warten:.0f} s, siehe {self.log}"

    def stoppen(self) -> None:
        """Beendet nur einen selbst gestarteten Reader."""
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
