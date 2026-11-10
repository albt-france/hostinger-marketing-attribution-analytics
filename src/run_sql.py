"""Run every query in sql/ with DuckDB and export the results to data/output/.

Each simulated table in data/clean/sim_<name>.parquet becomes a view called <name>.
Files run in name order (00, 01, ... 07). Inside a file, a statement ends with ';' at the end of a line.
A statement preceded by a comment line '-- output: <name>' is exported to data/output/<name>.csv.

Usage:  python src/run_sql.py
"""
import re
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
CLEAN, OUT, SQL = ROOT / "data" / "clean", ROOT / "data" / "output", ROOT / "sql"
OUT.mkdir(parents=True, exist_ok=True)

con = duckdb.connect()
for f in sorted(CLEAN.glob("sim_*.parquet")):
    name = f.stem.removeprefix("sim_")
    con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{f.as_posix()}')")

for sql_file in sorted(SQL.glob("*.sql")):
    t0 = time.time()
    text = sql_file.read_text(encoding="utf-8")
    for statement in re.split(r";\s*$", text, flags=re.MULTILINE):
        if not re.search(r"^\s*[A-Za-z(]", statement, flags=re.MULTILINE):
            continue                                  # only comments / blank
        match = re.search(r"--\s*output:\s*(\w+)", statement)
        if match:
            df = con.execute(statement).df()
            df.to_csv(OUT / f"{match.group(1)}.csv", index=False)
            print(f"  {sql_file.name:32s} -> {match.group(1)}.csv ({len(df):,} rows)")
        else:
            con.execute(statement)
    print(f"{sql_file.name} done in {time.time() - t0:.1f}s")
