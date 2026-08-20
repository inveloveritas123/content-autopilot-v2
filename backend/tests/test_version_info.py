"""Tests fuer services.version_info — Grundlage von /api/version (SSOT AP3, 21.08.).

Deckt den Kern der Deploy-Luecke aus §0 des SSOT ab: "alles deployed" war
fuenf Minuten spaeter falsch, niemand konnte es sehen. Der Endpoint muss den
tatsaechlichen Deploy-Zustand ehrlich zeigen — inklusive dem Fall, dass gar
kein Deploy-Skript-Build stattgefunden hat.
"""

from __future__ import annotations

from services.version_info import read_version


class TestReadVersion:
    def test_liest_commit_sha_und_build_time(self, tmp_path):
        version_file = tmp_path / "VERSION"
        version_file.write_text("d0be1c4abc123\n")

        ergebnis = read_version(tmp_path)

        assert ergebnis["commit_sha"] == "d0be1c4abc123"
        assert ergebnis["build_time"] is not None

    def test_fehlende_version_datei_taeuscht_keine_sha_vor(self, tmp_path):
        """Kern der Deploy-Luecke: lieber ehrlich 'unknown' als eine falsche
        SHA zeigen, wenn kein Deploy-Skript-Build stattgefunden hat."""
        ergebnis = read_version(tmp_path)

        assert ergebnis["commit_sha"].startswith("unknown")
        assert ergebnis["build_time"] is None

    def test_strippt_whitespace_aus_der_sha(self, tmp_path):
        version_file = tmp_path / "VERSION"
        version_file.write_text("  abc123  \n")

        ergebnis = read_version(tmp_path)

        assert ergebnis["commit_sha"] == "abc123"

    def test_build_time_folgt_der_dateimodifikationszeit(self, tmp_path):
        import os
        import time

        version_file = tmp_path / "VERSION"
        version_file.write_text("sha1")
        alte_zeit = time.time() - 3600
        os.utime(version_file, (alte_zeit, alte_zeit))

        ergebnis = read_version(tmp_path)

        assert ergebnis["build_time"] is not None
        # ISO-Format, muss sich parsen lassen
        from datetime import datetime

        parsed = datetime.fromisoformat(ergebnis["build_time"])
        assert abs(parsed.timestamp() - alte_zeit) < 1.0
