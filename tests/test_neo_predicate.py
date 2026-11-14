"""Every NEO selection from mpc_orbits uses the one project predicate.

lib/orbit_classes.NEO_SQL_PREDICATE (q <= 1.30) is authoritative. Pure-SQL
files can't import it, so this test scans the SQL the repo runs -- sql/,
scripts/, lib/ and app/ -- for `mo.q <op> <number>` and fails on any other
threshold or operator. sandbox/ and docs/ are exploratory and not scanned.
"""
import re
from pathlib import Path

from lib.orbit_classes import NEO_Q_MAX, NEO_SQL_PREDICATE

ROOT = Path(__file__).resolve().parent.parent
SCANNED = ["sql/**/*.sql", "scripts/**/*.py", "lib/**/*.py", "app/*.py"]
# Deliberately wider selections that are not "the NEOs" -- (file, threshold).
NOT_NEO_SELECTIONS = {
    ("sql/orbit_watch/capture_snapshot.sql", 1.5),  # watch set: NEOs + margin
}
PRED_RE = re.compile(r"\bmo\.q\s*(<=|<|>=|>)\s*([0-9]+(?:\.[0-9]+)?)")


def _hits():
    for pattern in SCANNED:
        for path in ROOT.glob(pattern):
            for n, line in enumerate(path.read_text().splitlines(), 1):
                for m in PRED_RE.finditer(line):
                    yield path.relative_to(ROOT), n, m.group(1), float(m.group(2))


def test_predicate_constant():
    assert NEO_SQL_PREDICATE == f"mo.q <= {NEO_Q_MAX:.2f}"


def test_every_neo_selection_matches():
    hits = list(_hits())
    assert hits, "scan found no NEO predicates -- has the layout changed?"
    bad = [h for h in hits if (h[2], h[3]) != ("<=", NEO_Q_MAX)
           and (str(h[0]), h[3]) not in NOT_NEO_SELECTIONS]
    assert not bad, "NEO predicate differs from NEO_SQL_PREDICATE:\n" + \
        "\n".join(f"  {p}:{n}  mo.q {op} {v}" for p, n, op, v in bad)


def test_no_orbit_type_fallback():
    # orbit_type_int 20 is Jupiter-coupled, not an NEO class.
    for pattern in SCANNED:
        for path in ROOT.glob(pattern):
            assert "orbit_type_int IN (0, 1, 2, 3, 20)" not in path.read_text(), path
