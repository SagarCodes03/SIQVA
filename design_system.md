# FloatChat — Design System

## 1. Brand Identity
- **Product Name:** FloatChat
- **Tagline:** Ask the Ocean
- **Personality:** Scientific, clean, trustworthy, accessible

---

## 2. Color Palette

### Primary Colors
| Name | Hex | Usage |
|---|---|---|
| Ocean Deep | #0A1628 | Main background |
| Ocean Blue | #1E3A5F | Card backgrounds |
| Teal Active | #00B4D8 | Primary buttons, links, highlights |
| Wave Light | #90E0EF | Hover states, accents |

### Secondary Colors
| Name | Hex | Usage |
|---|---|---|
| Success Green | #2D9B5A | QC good data indicator (flag 1,2) |
| Warning Amber | #F4A261 | QC probably good (flag 2) |
| Error Red | #E63946 | QC bad data indicator (flag 3,4) |
| Neutral Gray | #ADB5BD | Secondary text, borders |

---

## 3. Typography
| Element | Font | Size | Weight |
|---|---|---|---|
| App Title | Inter | 28px | Bold |
| Section Header | Inter | 20px | SemiBold |
| Body Text | Inter | 14px | Regular |
| Chat Message | Inter | 14px | Regular |
| Code / WMO IDs | JetBrains Mono | 13px | Regular |
| Metadata / QC | Inter | 11px | Regular |

---

## 4. UI Components

### Chat Bubbles
- User message: Right-aligned, Teal Active (#00B4D8) background
- Bot message: Left-aligned, Ocean Blue (#1E3A5F) background
- Border radius: 12px
- Padding: 12px 16px

### QC Status Badge
- Flag 1 → Green badge → "Good Data"
- Flag 2 → Amber badge → "Probably Good"
- Flag 3/4 → Red badge → "Filtered Out"

### Provenance Card (shown below EVERY answer)
- Float WMO number
- Latitude and Longitude
- Date UTC
- QC Status
- Data source (Argovis / ERDDAP)

---

## 5. Chart Styling (Plotly)

```python
CHART_THEME = {
    "paper_bgcolor": "#0A1628",
    "plot_bgcolor": "#1E3A5F",
    "font": {"color": "#F8F9FA", "family": "Inter"},
    "gridcolor": "#2A4A7F",
    "linecolor": "#00B4D8"
}
```

### Chart Types by Query Intent
| Intent | Chart Type | X-axis | Y-axis |
|---|---|---|---|
| Depth profile | Line chart | Temperature/Salinity | Depth (inverted) |
| Float positions | Folium map | Longitude | Latitude |
| Time series | Line chart | Date | Parameter value |
| T-S diagram | Scatter plot | Salinity | Temperature |
| Trajectory | Map animation | Lon | Lat over time |

---

## 6. Layout
```
Header: FloatChat logo + ARGO Global Live badge
Chat area: 65% of screen height
Chart area: 25% of screen height
Input bar: fixed at bottom
Sidebar: quick query buttons + export options
```

---

## 7. Streamlit Config (config.toml)
```toml
[theme]
primaryColor = "#00B4D8"
backgroundColor = "#0A1628"
secondaryBackgroundColor = "#1E3A5F"
textColor = "#F8F9FA"
font = "sans serif"
```

---

## 8. Icons Used
| Context | Icon |
|---|---|
| App logo | 🌊 |
| Temperature | 🌡️ |
| Salinity | 🧂 |
| Location | 📍 |
| Date | 📅 |
| QC Good | ✅ |
| QC Bad | ❌ |
| Chart | 📊 |
| Map | 🗺️ |
| Export | ⬇️ |
