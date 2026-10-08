# Power BI dashboard project

## Open the report

Open `HighwayAccidentAnalysis.pbip` in Power BI Desktop. Keep these three
items together: the `.pbip` file, `HighwayAccidentAnalysis.Report/`, and
`HighwayAccidentAnalysis.SemanticModel/`. A `.pbip` is a pointer to the report
project; it is not a standalone report file. The model contains embedded
Power Query data for the cleaned source and summary tables, so the project does not
need absolute CSV paths.

To transfer the report, use `HighwayAccidentAnalysis_PBIP_Project.zip` or
copy all three project items together. Unzip the package first, then open the
`.pbip` file in Power BI Desktop.

## Dashboard layout

- **National Overview:** four fixed 2022 KPI cards, a year slicer, and separate
  NH and all-road trend charts for 2018-2022.
- **State Hotspots:** Azure Maps bubble layer, a descending 2022 state ranking,
  and a five-year trend chart for the top ten states. State and year slicers
  filter this page.
- **Severity & Road Context:** annual all-road accidents, fatalities, and
  injuries; NH fatalities per 100 NH accidents for 2022; and donut comparisons
  of NH + Expressways against other roads for accidents and fatalities.
- All pages show MoRTH/PIB source and scope notes. Counts are not
  exposure-adjusted risk rates.

## Model

The semantic model keeps the original India NH, top-10 NH state, India
all-roads, and state/UT all-roads tables, plus a consolidated annual trend table
and a derived 2022 road-class table. The trend slicer filters its shared annual
table; state map/ranking visuals use only the top-ten NH state data. NH fatality
values from 2018-2021 remain blank because the cited source does not provide
them.

## If Power BI shows a prompt

The report definition includes report theme metadata and a bundled Power BI
base theme. Azure Maps requires internet access and can be disabled by an
organization; if the map tiles do not load, the state ranking and trend chart
remain available. If an older Power BI session is already open, close it
without saving and reopen `HighwayAccidentAnalysis.pbip` so Desktop reads the
latest project files. Capture each rendered page in the root `images/` folder.

The static `images/dashboard_preview.png` is a layout reference; it is not a
Power BI screenshot.
