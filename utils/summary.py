"""
Automated, rules-based summaries for charts across the tool. These read
already-computed numbers and fill in a sentence template — no model call,
no cost, and every figure quoted matches the chart it sits under.
"""

import pandas as pd


def summarize_z_trend(df_entity: pd.DataFrame, entity_name: str) -> str:
    d = df_entity.dropna(subset=["Z_EM"]).sort_values("Year")
    if len(d) < 2:
        return f"Not enough time points to describe a trend for {entity_name}."
    first, last = d["Z_EM"].iloc[0], d["Z_EM"].iloc[-1]
    change = last - first
    direction = "improved" if change > 0 else "declined" if change < 0 else "held steady"
    return (
        f"{entity_name}'s Z-EM score {direction} from {first:.2f} in {d['Year'].iloc[0]:.0f} "
        f"to {last:.2f} in {d['Year'].iloc[-1]:.0f}, ending in the {d['Zone'].iloc[-1].lower()} zone."
    )


def summarize_zone_distribution(df: pd.DataFrame) -> str:
    if df.empty:
        return "No data available for this selection."
    counts = df["Zone"].value_counts()
    n = len(df)
    distress = counts.get("Distress", 0)
    grey = counts.get("Grey", 0)
    safe = counts.get("Safe", 0)

    parts = [f"{distress} of {n} SOEs are in the distress zone (Z-EM ≤ 1.1)"]
    if grey:
        parts.append(f"{grey} in the grey zone")
    if safe:
        parts.append(f"{safe} in the safe zone")
    sentence = ", ".join(parts) + "."

    if distress > 0 and "Sector" in df.columns:
        worst_sectors = df.loc[df["Zone"] == "Distress", "Sector"].value_counts().head(2).index.tolist()
        if worst_sectors:
            sentence += f" Distress is concentrated in {', '.join(worst_sectors)}."
    return sentence


def summarize_kpi_flags(flags: pd.Series, kpi_label: str) -> str:
    n = len(flags)
    if n == 0:
        return f"No data available to assess {kpi_label}."
    red = int((flags == "Red").sum())
    green = int((flags == "Green").sum())
    return f"{red} of {n} SOEs are flagged red on {kpi_label}, {green} are green."


def summarize_shock_scenario(base_efc, scenario_efc, n_soes, shock_active, unit_label="EFC") -> str:
    if not shock_active:
        return f"Baseline: average {unit_label} of {base_efc:,.0f} across {n_soes} SOE(s)."
    delta = scenario_efc - base_efc
    direction = "increases" if delta > 0 else "decreases"
    return (
        f"Under the selected scenario, average {unit_label} {direction} from "
        f"{base_efc:,.0f} to {scenario_efc:,.0f} ({delta:+,.0f}) across {n_soes} SOE(s)."
    )
