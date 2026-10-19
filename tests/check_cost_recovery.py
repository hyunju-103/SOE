"""Cost recovery regression checks (invented figures; no uploaded SOE data stored)."""
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import calculations
import config
import data_loader
import report
import schema


def main():
    assert "cost_recovery" in config.KPI_CATEGORIES["profitability"]
    for header, mapped in [("Cost of Goods Sold", "Cost of Goods Sold"), ("cogs", "Cost of Goods Sold"),
                           ("cost_of_goods_sold", "Cost of Goods Sold"),
                           ("Other Operating Expenses", "Other Operating Expenses"),
                           ("other_operating_expenses", "Other Operating Expenses")]:
        assert schema.match_column(header)[0] == mapped, (header, schema.match_column(header))
    base = data_loader.demo_portfolio()
    # The metric cannot be computed from the demo, but remains in the UI
    # selector independently of this calculation-availability list.
    assert "cost_recovery" not in calculations.available_kpis(base, "profitability")
    ui = (ROOT / "templates" / "app.js").read_text(encoding="utf8")
    assert 'catKpis(cat) { return CFG.KPI_CATEGORIES[cat].slice(); }' in ui
    assert "Data unavailable — ${SPEC[k].label} requires" in ui

    # Invented examples, including missing pieces, a zero denominator and negative grants.
    df = base.iloc[:5].copy()
    df["Revenues"] = [120, 200, 100, 50, 130]
    df["Government Grants"] = [20, 30, 10, 2, -2]
    df["Cost of Goods Sold"] = [60, 90, 70, 0, np.nan]
    df["Other Operating Expenses"] = [20, 70, np.nan, 0, 22]
    expected = [1.25, 1.0625, None, None, None]
    results = calculations.compute_kpis(df)["cost_recovery"].tolist()
    for actual, reference in zip(results, expected):
        if reference is None: assert math.isnan(actual), (actual, reference)
        else: assert math.isclose(actual, reference, rel_tol=1e-12), (actual, reference)
    assert "cost_recovery" in calculations.available_kpis(df, "profitability")
    print("Python formula, mapping and missing-input tests: OK")

    node = shutil.which("node")
    if node:
        script = """
        const fs = require('fs');
        const engine = require(process.argv[1]).create(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
        const r = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
        process.stdout.write(JSON.stringify(engine.enrich(r).map(x => Number.isFinite(x.cost_recovery)?x.cost_recovery:null)));
        """
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "config.json").write_text(json.dumps(report.config_payload(), ensure_ascii=False), encoding="utf8")
            (td / "rows.json").write_text(df.to_json(orient="records"), encoding="utf8")
            result = subprocess.run([node, "-e", script, str(ROOT / "templates" / "engine.js"), str(td / "config.json"), str(td / "rows.json")], capture_output=True, text=True, check=True)
            js = json.loads(result.stdout)
        for n, expected_value in zip(js, expected):
            assert n is None if expected_value is None else math.isclose(n, expected_value, rel_tol=1e-12)
        print("JavaScript/Python formula parity for valid, invalid and missing input: OK")
    print("PASS: cost recovery KPI checks")


if __name__ == "__main__":
    main()
