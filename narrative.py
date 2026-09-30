"""
Rule-based (non-generative) narrative engine for Z''-EM results.
Every sentence is assembled from templates and computed values only —
no free-text generation — so figures in the narrative are always
traceable to the underlying calculation.
"""

import pandas as pd

import config


def _bucket_component(comp: str, value: float) -> str:
    """Bucket a raw component ratio (X1-X4) into strong_positive /
    weak_positive / negative for the descriptor lookup."""
    if pd.isna(value):
        return "weak_positive"
    threshold = config.ZEM_COMPONENT_STRONG_THRESHOLD[comp]
    if value < 0:
        return "negative"
    elif value >= threshold:
        return "strong_positive"
    else:
        return "weak_positive"


def _describe_component(comp: str, value: float) -> str:
    bucket = _bucket_component(comp, value)
    return config.ZEM_DESCRIPTORS[comp][bucket]


def single_soe_narrative(row: pd.Series) -> str:
    """Generate the component-attribution summary for one SOE-year.
    Expects row to already have X1-X4, *_contrib, Z_EM, Zone from
    calculations.compute_zem_components."""
    entity = row.get("Entity", "This SOE")
    zone = row["Zone"]
    z = row["Z_EM"]

    contribs = {c: row[f"{c}_contrib"] for c in config.ZEM_COEFFICIENTS}
    total_abs = sum(abs(v) for v in contribs.values())

    ranked = sorted(contribs.items(), key=lambda kv: kv[1])
    most_negative_comp, most_negative_val = ranked[0]
    most_positive_comp, most_positive_val = ranked[-1]

    lead = f"**{entity} sits in the {zone} zone (Z-EM = {z:.2f}).**"

    sentences = [lead]

    # Positive driver sentence
    if most_positive_val > 0:
        share = abs(most_positive_val) / total_abs if total_abs else 0
        descriptor = _describe_component(most_positive_comp, row[most_positive_comp])
        if share >= config.SINGLE_DRIVER_SHARE_THRESHOLD:
            sentences.append(
                f"The classification is driven almost entirely by {descriptor} "
                f"({config.ZEM_LABELS[most_positive_comp]} = {row[most_positive_comp]:.2f})."
            )
        else:
            sentences.append(
                f"{descriptor.capitalize()} ({config.ZEM_LABELS[most_positive_comp]} = "
                f"{row[most_positive_comp]:.2f}) is the largest positive contributor."
            )

    # Negative driver sentence
    if most_negative_val < 0:
        descriptor = _describe_component(most_negative_comp, row[most_negative_comp])
        sentences.append(
            f"The main drag is {descriptor} "
            f"({config.ZEM_LABELS[most_negative_comp]} = {row[most_negative_comp]:.2f})."
        )

    # Divergence flag: are most components negative but zone is not Distress,
    # or vice versa?
    n_negative = sum(1 for c in config.ZEM_COEFFICIENTS if row[c] < 0)
    if n_negative >= 3 and zone != "Distress":
        sentences.append(
            f"Three or more components are negative even though the headline "
            f"classification is {zone} — worth flagging as a fragile score "
            f"carried by a narrow base."
        )
    elif n_negative <= 1 and zone == "Distress":
        sentences.append(
            f"Most components are positive despite the Distress classification — "
            f"the score is being pulled down by a concentrated weakness rather than "
            f"broad-based deterioration."
        )
    elif n_negative == 4:
        sentences.append("This is broad-based distress, not a single-metric problem.")

    return " ".join(sentences)


def cross_soe_narrative(df: pd.DataFrame) -> dict:
    """Generate the portfolio-level summary across all SOE-years in df
    (typically pre-filtered to a single year). Returns a dict with:
      - 'paragraph': the summary text
      - 'table': a DataFrame with Entity, Sector, Z_EM, Zone, primary driver, flag
    """
    if df.empty:
        return {"paragraph": "No data available for this selection.", "table": pd.DataFrame()}

    rows = []
    for _, row in df.iterrows():
        contribs = {c: row[f"{c}_contrib"] for c in config.ZEM_COEFFICIENTS}
        total_abs = sum(abs(v) for v in contribs.values())
        ranked = sorted(contribs.items(), key=lambda kv: kv[1])
        most_negative_comp, most_negative_val = ranked[0]
        most_positive_comp, most_positive_val = ranked[-1]

        share = abs(most_positive_val) / total_abs if total_abs else 0
        primary_driver = config.ZEM_LABELS[most_positive_comp]

        flag = ""
        if share >= config.SINGLE_DRIVER_SHARE_THRESHOLD:
            n_negative = sum(1 for c in config.ZEM_COEFFICIENTS if row[c] < 0)
            if n_negative >= 2:
                flag = f"Single-driver classification — weak on {n_negative} of 4 components"
            else:
                flag = "Single-driver classification"

        rows.append({
            "Entity": row.get("Entity", ""),
            "Sector": row.get("Sector", ""),
            "Z_EM": row["Z_EM"],
            "Zone": row["Zone"],
            "Primary driver": primary_driver,
            "Flag": flag,
        })

    table = pd.DataFrame(rows).sort_values("Z_EM", ascending=False).reset_index(drop=True)

    n_total = len(table)
    zone_counts = table["Zone"].value_counts().to_dict()
    n_safe = zone_counts.get("Safe", 0)
    n_grey = zone_counts.get("Grey", 0)
    n_distress = zone_counts.get("Distress", 0)
    n_single_driver = (table["Flag"] != "").sum()

    paragraph_parts = [
        f"Of {n_total} SOEs assessed, {n_safe} sit in Safe, {n_grey} in Grey, "
        f"and {n_distress} in Distress."
    ]

    if n_single_driver > 0:
        paragraph_parts.append(
            f"{n_single_driver} SOE{'s' if n_single_driver != 1 else ''} "
            f"{'have' if n_single_driver != 1 else 'has'} a classification driven "
            f"primarily by a single component rather than a broad financial "
            f"position — worth monitoring for fragility."
        )

    # Sector comparison, if Sector column has more than one distinct value
    if "Sector" in table.columns and table["Sector"].nunique() > 1:
        sector_means = table.groupby("Sector")["Z_EM"].mean().sort_values()
        weakest_sector = sector_means.index[0]
        strongest_sector = sector_means.index[-1]
        if len(sector_means) >= 2 and sector_means.iloc[0] < sector_means.iloc[-1]:
            paragraph_parts.append(
                f"{weakest_sector} SOEs show systematically weaker Z-EM scores "
                f"(mean {sector_means.iloc[0]:.2f}) than {strongest_sector} SOEs "
                f"(mean {sector_means.iloc[-1]:.2f}) in this sample — flagged as a "
                f"sector-level pattern rather than a firm-specific one, though the "
                f"sample size here is small."
            )

    return {"paragraph": " ".join(paragraph_parts), "table": table}
