import os
import tempfile
from pathlib import Path

from pmc.memory import PMCMemory


FIXTURE_FILES = {
    "main.py": (
        "import utils\n"
        "import config\n"
        "def main():\n"
        "    return utils.helper()\n"
        "def helper_main():\n"
        "    return 1\n"
    ),
    "utils.py": (
        "def helper():\n"
        "    return 42\n"
        "def other():\n"
        "    return 'x'\n"
    ),
    "config.py": (
        "VALUE = 1\n"
        "def get_value():\n"
        "    return VALUE\n"
    ),
    "README.md": "# Project\nThis project is a fixture for PMC tests.\n",
    "settings.json": '{"name": "fixture", "version": "0.1"}\n',
}


def _make_fixture(root: Path):
    for name, content in FIXTURE_FILES.items():
        (root / name).write_text(content)


def test_ingest_then_query_offline(monkeypatch):
    # Disable network model + API key — exercise full offline path.
    monkeypatch.setenv("PMC_EMBED_MODE", "fallback")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "src"
        root.mkdir()
        _make_fixture(root)
        db = str(Path(d) / "m.db")
        m = PMCMemory.create(db, schema="default")
        rep = m.ingest(str(root))
        assert rep.nodes_created >= 5
        assert m.stats()["node_counts_by_type"]["CODE_FILE"] == 3
        assert m.stats()["node_counts_by_type"]["DOC"] == 1
        assert m.stats()["node_counts_by_type"]["CONFIG"] == 1

        res = m.query("what is in main.py?")
        assert res.status in ("COMPLETE", "PARTIAL")
        # Offline synthesizer returns formatted assertions or [UNKNOWN: ...]
        assert isinstance(res.text, str) and len(res.text) > 0
        m.close()
