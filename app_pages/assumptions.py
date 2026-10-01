"""
Assumptions & sources — every number the tool uses, with its value, where it
comes from and its status: backed by literature / data, set by the user, a
working proxy, a model design choice, or a placeholder that still needs a
source. Driven by config.PARAMETER_REGISTER, so it stays next to the values.
"""

import pandas as pd
import streamlit as st

import config
from utils import theme

theme.header(
    "MODEL GOVERNANCE",
    "Assumptions & sources",
    "Every coefficient, threshold and default in the tool, with its source and status. Placeholders are "
    "numbers the tool needs to run but that still need a literature or data source before results are "
    "used in policy advice.",
)

reg = pd.DataFrame(config.PARAMETER_REGISTER)
labels = config.PARAMETER_STATUS_LABELS
chip = {"literature": "green", "user": "muted", "proxy": "amber", "placeholder": "red", "design": "amber"}

counts = reg["status"].value_counts()
_status = {"literature": ("ok", "● Sourced"), "user": (None, "Set by you"), "proxy": ("watch", "▲ Proxy"),
           "placeholder": ("alert", "■ Needs source"), "design": ("watch", "▲ Justify")}
_tiles = []
for key, label in labels.items():
    head, _, rest = label.partition(" — ")
    stt, txt = _status.get(key, (None, ""))
    _tiles.append(theme.tile(head, str(int(counts.get(key, 0))), f"of {len(reg)}", rest[:1].upper() + rest[1:] if rest else "",
                             status=stt, status_text=txt))
theme.stat_strip(_tiles)

sel = st.multiselect("Show", list(labels), default=list(labels), format_func=lambda k: labels[k], key="reg_status")
groups = st.multiselect("Groups", list(dict.fromkeys(reg["group"])), default=list(dict.fromkeys(reg["group"])), key="reg_groups")
view = reg[reg["status"].isin(sel) & reg["group"].isin(groups)]

rows = "".join(
    f"<tr><td style='white-space:nowrap'>{r.group}</td><td><b>{r.parameter}</b></td><td>{r.value}</td>"
    f"<td>{theme.status_chip(chip[r.status], labels[r.status])}</td><td>{r.source}</td><td>{r.used_in}</td></tr>"
    for r in view.itertuples()
)
st.markdown(
    "<table class='sfp-table sfp-table-wrap'><thead><tr><th>Group</th><th>Parameter</th><th>Value</th><th>Status</th>"
    f"<th>Source</th><th>Used in</th></tr></thead><tbody>{rows}</tbody></table>",
    unsafe_allow_html=True,
)
st.download_button("⬇ Download register (CSV)", view.assign(status=view["status"].map(labels)).to_csv(index=False),
                   file_name="soe_tool_parameter_register.csv")

st.markdown(
    """
    <div class="sfp-footnote">
    <p><b>How to use this page.</b> Before results go into a policy note, each placeholder should either get a
    source (literature, a rating framework, an industry benchmark, or the empirical distribution of the SOE panel)
    or be set explicitly by the user for the country. Edit values and sources together in config.py
    (PARAMETER_REGISTER sits at the end of the file).</p>
    </div>
    """,
    unsafe_allow_html=True,
)
