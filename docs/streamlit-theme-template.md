# Streamlit Theme Template

Reusable pattern for a branded Streamlit app: custom color, custom font, forced
light background, and consistently-styled Plotly charts. Copy both files below
into a new project and change the marked values.

## 1. `.streamlit/config.toml`

Controls the theme of Streamlit's own widgets/chrome (sidebar, tabs, buttons,
metrics). Requires a full server restart to pick up changes — it does not
hot-reload like `.py` files.

```toml
[theme]
base = "light"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F2F2F2"
textColor = "#1E1E1E"
primaryColor = "#06C755"
font = "Prompt:https://fonts.googleapis.com/css2?family=Prompt:wght@400;500;600;700&display=swap, sans-serif"
```

- `base = "light"` + an explicit `backgroundColor` is what forces a white
  background regardless of the viewer's OS/browser dark-mode setting. Verified
  by loading the app with the browser forced to `prefers-color-scheme: dark`.
- `font = "<name>:<google-fonts-css-url>, <fallback>"` is Streamlit's
  externally-hosted-font syntax. Swap `family=Prompt` for any Google Font.
- To rebrand: change `primaryColor` and the font family/URL. That's it for
  the widget-level theme.

## 2. Python side (top of `app.py`)

Plotly renders inside its own `<canvas>`/SVG and does **not** inherit
`config.toml` — it needs to be styled separately.

```python
import plotly.express as px
import streamlit as st

BRAND_COLOR = "#06C755"       # primary brand color
NEUTRAL_GREY = "#C4C4C4"      # baseline / de-emphasized comparison color
CHART_FONT = "Prompt, sans-serif"
COLOR_RAMP = ["#06C755", "#00893D", "#7ED9A8", "#003A1F", "#B6EFCB", "#00B14F"]

st.set_page_config(page_title="...", layout="wide")
px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = COLOR_RAMP


def style_fig(fig):
    fig.update_layout(template="plotly_white", font_family=CHART_FONT)
    return fig
```

### Usage per chart type

```python
# Single-series chart -> pass the brand color directly
fig = px.bar(df, x="...", y="...", color_discrete_sequence=[BRAND_COLOR])
st.plotly_chart(style_fig(fig), width="stretch")

# Two categories being compared (baseline vs. highlighted) -> grey vs. brand color
fig = px.bar(
    df, x="...", y="...", color="category",
    color_discrete_map={"baseline_label": NEUTRAL_GREY, "highlight_label": BRAND_COLOR},
)
st.plotly_chart(style_fig(fig), width="stretch")

# Pie chart -> MUST pass color_discrete_sequence directly in the call.
# px.defaults.color_discrete_sequence is silently overridden if style_fig()
# (i.e. fig.update_layout(template=...)) runs afterward - a real bug hit
# during development. Bar/line/area charts don't have this problem because
# px bakes their colors into the trace at creation time; pie relies on
# layout.colorway unless told otherwise.
fig = px.pie(df, names="...", values="...", color_discrete_sequence=COLOR_RAMP)
st.plotly_chart(style_fig(fig), width="stretch")
```

## Lessons learned (save yourself the debugging time)

1. **Pie charts ignore `px.defaults.color_discrete_sequence`** once
   `style_fig()`/`update_layout(template=...)` runs after creation — always
   pass `color_discrete_sequence` explicitly to `px.pie()`.
2. **Verify the "forced light theme" claim by testing with the browser set to
   dark mode**, not just by eyeballing it locally (a light OS theme can make a
   broken override look correct).
3. **`st.metric` truncates long values to "..." when columns are narrow** (5+
   metrics in one row). Format big numbers compactly (e.g. `฿123.8M` instead
   of `฿123,833,012`) rather than fighting column width.
4. **Local dev screenshots include Streamlit's own "Deploy" toolbar strip** at
   the top — crop it out before using screenshots anywhere external:
   ```python
   from PIL import Image
   img = Image.open("screenshot.png")
   img.crop((0, 46, img.width, img.height)).save("screenshot.png")
   ```
5. **Streamlit Community Cloud runs whatever its current default Python is**
   and does **not** honor a `runtime.txt` pin — pin dependency *versions*
   (`requirements.txt`) that have prebuilt wheels for a recent Python instead
   of trying to pin the Python version itself.
