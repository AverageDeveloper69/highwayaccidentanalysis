"""Create the Power BI Project (PBIP) package for this workspace."""
from pathlib import Path
import json, uuid, base64, shutil, csv

ROOT = Path(__file__).resolve().parents[2]
PBI = ROOT / "Project files" / "powerbi"
NAME = "HighwayAccidentAnalysis"
REPORT = PBI / f"{NAME}.Report"
MODEL = PBI / f"{NAME}.SemanticModel"
DATA = ROOT / "Dataset" / "Cleaned"
THEME_SOURCE = REPORT / "StaticResources" / "SharedResources" / "BaseThemes" / "CY26SU09.json"
PAGE_OVERVIEW = "ReportSectionHighwayOverview"
PAGE_STATES = "ReportSectionStateExplorer"
PAGE_TRENDS = "ReportSectionSafetyTrends"
PAGE_NAMES = {
    PAGE_OVERVIEW: "National Overview",
    PAGE_STATES: "State Hotspots",
    PAGE_TRENDS: "Severity & Road Context",
}
for page_id in PAGE_NAMES:
    visual_dir = REPORT / "definition" / "pages" / page_id / "visuals"
    if visual_dir.exists():
        shutil.rmtree(visual_dir)

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def uid():
    return str(uuid.uuid4())

def csv_rows(filename):
    with (DATA / filename).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def write_dashboard_data():
    nh = {r["year"]: r for r in csv_rows("india_nh_annual_clean.csv")}
    roads = {r["year"]: r for r in csv_rows("india_all_roads_annual_clean.csv")}
    top10 = {r["year"]: r for r in csv_rows("annual_nh_summary.csv")}
    fields = ["year", "nh_accidents", "nh_fatalities", "top10_state_accidents",
              "top10_share_of_nh_accidents_pct", "all_road_accidents",
              "all_road_fatalities", "all_road_injured", "source"]
    with (DATA / "annual_dashboard_summary.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for year in sorted(nh):
            writer.writerow({
                "year": year,
                "nh_accidents": nh[year]["nh_accidents"],
                "nh_fatalities": nh[year]["nh_fatalities"],
                "top10_state_accidents": top10[year]["top10_state_accidents"],
                "top10_share_of_nh_accidents_pct": top10[year]["top10_share_of_nh_accidents_pct"],
                "all_road_accidents": roads[year]["accidents"],
                "all_road_fatalities": roads[year]["fatalities"],
                "all_road_injured": roads[year]["injured"],
                "source": nh[year]["source"],
            })
    with (DATA / "road_class_2022.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["road_class", "accidents", "fatalities", "source"])
        writer.writeheader()
        writer.writerow({"road_class": "National Highways + Expressways", "accidents": 151997,
                         "fatalities": 61038, "source": "MoRTH/PIB, 2022"})
        writer.writerow({"road_class": "Other roads (derived)", "accidents": 309315,
                         "fatalities": 107453, "source": "All roads minus NH + Expressways, 2022"})

write_dashboard_data()

def m_partition(table, filename, type_pairs):
    encoded_csv = base64.b64encode((DATA / filename).read_bytes()).decode("ascii")
    typing = ",\n            ".join("{\"%s\", %s}" % pair for pair in type_pairs)
    expr = (
        'let\n'
        f'    Source = Csv.Document(Binary.FromText("{encoded_csv}", BinaryEncoding.Base64), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n'
        '    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),\n'
        f'    ChangedTypes = Table.TransformColumnTypes(PromotedHeaders, {{{typing}}})\n'
        'in\n    ChangedTypes'
    )
    return {"name": table, "mode": "import", "source": {"type": "m", "expression": expr}}

def table_def(name, columns, partition, measures=None):
    cols=[]
    for col, dtype in columns:
        cols.append({"name": col, "dataType": dtype, "sourceColumn": col,
                     "summarizeBy": "none" if col.lower() in {"state", "location", "road_class", "source", "source_table", "year"} else "sum",
                     "lineageTag": uid()})
        if col.lower() == "location":
            cols[-1]["dataCategory"] = "Address"
    return {"name": name, "lineageTag": uid(), "columns": cols,
            "measures": measures or [], "partitions": [partition]}

def measure(name, expression, fmt):
    return {"name": name, "expression": expression, "formatString": fmt,
            "lineageTag": uid()}

def col(table, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": prop}}

def meas(table, prop):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": prop}}

def projection(field, query_ref, native_ref=None):
    p={"field": field, "queryRef": query_ref, "active": True}
    if native_ref: p["nativeQueryRef"]=native_ref
    return p

def title_object(label):
    return {"title": [{"properties": {
        "show": {"expr": {"Literal": {"Value": "true"}}},
        "text": {"expr": {"Literal": {"Value": "'" + label.replace("'", "''") + "'"}}}
    }}]}

def visual(name, visual_type, position, query_state=None, title=None, objects=None, sort_definition=None):
    v={"visualType": visual_type}
    if query_state is not None:
        v["query"]={"queryState": query_state}
        if sort_definition is not None:
            v["query"]["sortDefinition"] = sort_definition
    if objects: v["objects"]=objects
    if title: v["visualContainerObjects"]=title_object(title)
    return {"$schema":"https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.9.0/schema.json",
            "name":name,"position":position,"visual":v}

def write_visual(label, visual_type, pos, query_state=None, title=None, objects=None, page=PAGE_OVERVIEW, sort_definition=None):
    vid=uuid.uuid4().hex[:20]
    vis_dir = REPORT / "definition" / "pages" / page / "visuals"
    dump(vis_dir / vid / "visual.json", visual(vid,visual_type,pos,query_state,title,objects,sort_definition))

# Semantic model: the four fact tables remain separate so the top-10 state
# highway counts can never be mistaken for the India-wide totals.
tables=[]
tables.append(table_def("FactNHIndiaYear",
    [("year","int64"),("nh_accidents","int64"),("nh_fatalities","int64"),("source","string")],
    m_partition("FactNHIndiaYear","india_nh_annual_clean.csv",[("year","Int64.Type"),("nh_accidents","Int64.Type"),("nh_fatalities","Int64.Type"),("source","type text")])) )

tables.append(table_def("FactNHStateYear",
    [("state","string"),("year","int64"),("nh_accidents","int64"),("rank_2022","int64"),("source_table","string"),("location","string")],
    {"name":"FactNHStateYear","mode":"import","source":{"type":"m","expression":
        'let\n    Source = Csv.Document(Binary.FromText("'+base64.b64encode((DATA / "nh_accidents_top10_clean.csv").read_bytes()).decode("ascii")+'", BinaryEncoding.Base64), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n'
        '    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),\n'
        '    ChangedTypes = Table.TransformColumnTypes(PromotedHeaders, {{"state", type text}, {"year", Int64.Type}, {"nh_accidents", Int64.Type}, {"rank_2022", Int64.Type}, {"source_table", type text}}),\n'
        '    AddedLocation = Table.AddColumn(ChangedTypes, "location", each [state] & ", India", type text)\nin\n    AddedLocation'}},
    [measure("NH State Accidents","SUM('FactNHStateYear'[nh_accidents])","#,0"),
     measure("NH State Accidents 2022","CALCULATE(SUM('FactNHStateYear'[nh_accidents]), REMOVEFILTERS('FactNHStateYear'[year]), 'FactNHStateYear'[year] = 2022)","#,0")]))

tables.append(table_def("FactAllRoadsIndiaYear",
    [("year","int64"),("accidents","int64"),("fatalities","int64"),("injured","int64"),("source","string")],
    m_partition("FactAllRoadsIndiaYear","india_all_roads_annual_clean.csv",[("year","Int64.Type"),("accidents","Int64.Type"),("fatalities","Int64.Type"),("injured","Int64.Type"),("source","type text")])))

tables.append(table_def("FactAllRoadsStateYear",
    [("state","string"),("year","int64"),("all_road_accidents","int64"),("all_road_fatalities","int64"),("all_road_injured","int64"),("source","string")],
    m_partition("FactAllRoadsStateYear","state_allroads_annual_clean.csv",[("state","type text"),("year","Int64.Type"),("all_road_accidents","Int64.Type"),("all_road_fatalities","Int64.Type"),("all_road_injured","Int64.Type"),("source","type text")]),
    [measure("State All Road Accidents","SUM('FactAllRoadsStateYear'[all_road_accidents])","#,0"),
     measure("State All Road Fatalities","SUM('FactAllRoadsStateYear'[all_road_fatalities])","#,0")]))

annual_measures = [
    measure("NH Accidents", "SUM('FactAnnualSummary'[nh_accidents])", "#,0"),
    measure("NH Fatalities", "SUM('FactAnnualSummary'[nh_fatalities])", "#,0"),
    measure("Top 10 State Accidents", "SUM('FactAnnualSummary'[top10_state_accidents])", "#,0"),
    measure("All Road Accidents", "SUM('FactAnnualSummary'[all_road_accidents])", "#,0"),
    measure("All Road Fatalities", "SUM('FactAnnualSummary'[all_road_fatalities])", "#,0"),
    measure("All Road Injuries", "SUM('FactAnnualSummary'[all_road_injured])", "#,0"),
    measure("NH Accidents 2022", "CALCULATE([NH Accidents], REMOVEFILTERS('FactAnnualSummary'[year]), 'FactAnnualSummary'[year] = 2022)", "#,0"),
    measure("NH Fatalities 2022", "CALCULATE([NH Fatalities], REMOVEFILTERS('FactAnnualSummary'[year]), 'FactAnnualSummary'[year] = 2022)", "#,0"),
    measure("NH Accident Share 2022", "DIVIDE([NH Accidents 2022], CALCULATE([All Road Accidents], REMOVEFILTERS('FactAnnualSummary'[year]), 'FactAnnualSummary'[year] = 2022))", "0.0%"),
    measure("NH Fatality Share 2022", "DIVIDE([NH Fatalities 2022], CALCULATE([All Road Fatalities], REMOVEFILTERS('FactAnnualSummary'[year]), 'FactAnnualSummary'[year] = 2022))", "0.0%"),
    measure("All Road Accidents 2022", "CALCULATE([All Road Accidents], REMOVEFILTERS('FactAnnualSummary'[year]), 'FactAnnualSummary'[year] = 2022)", "#,0"),
    measure("All Road Fatalities 2022", "CALCULATE([All Road Fatalities], REMOVEFILTERS('FactAnnualSummary'[year]), 'FactAnnualSummary'[year] = 2022)", "#,0"),
    measure("All Road Injuries 2022", "CALCULATE([All Road Injuries], REMOVEFILTERS('FactAnnualSummary'[year]), 'FactAnnualSummary'[year] = 2022)", "#,0"),
    measure("NH Accidents YoY 2022", "VAR CurrentYear = CALCULATE([NH Accidents], REMOVEFILTERS('FactAnnualSummary'[year]), 'FactAnnualSummary'[year] = 2022) VAR PriorYear = CALCULATE([NH Accidents], REMOVEFILTERS('FactAnnualSummary'[year]), 'FactAnnualSummary'[year] = 2021) RETURN DIVIDE(CurrentYear - PriorYear, PriorYear)", "0.0%;-0.0%;0.0%"),
    measure("NH Fatalities per 100 Accidents 2022", "DIVIDE([NH Fatalities 2022], [NH Accidents 2022]) * 100", "0.0"),
]
tables.append(table_def("FactAnnualSummary",
    [("year","int64"),("nh_accidents","int64"),("nh_fatalities","int64"),("top10_state_accidents","int64"),
     ("top10_share_of_nh_accidents_pct","double"),("all_road_accidents","int64"),("all_road_fatalities","int64"),
     ("all_road_injured","int64"),("source","string")],
    m_partition("FactAnnualSummary","annual_dashboard_summary.csv",[("year","Int64.Type"),("nh_accidents","Int64.Type"),
     ("nh_fatalities","Int64.Type"),("top10_state_accidents","Int64.Type"),("top10_share_of_nh_accidents_pct","type number"),
     ("all_road_accidents","Int64.Type"),("all_road_fatalities","Int64.Type"),("all_road_injured","Int64.Type"),("source","type text")]),
    annual_measures))
tables.append(table_def("FactRoadClass2022",
    [("road_class","string"),("accidents","int64"),("fatalities","int64"),("source","string")],
    m_partition("FactRoadClass2022","road_class_2022.csv",[("road_class","type text"),("accidents","Int64.Type"),("fatalities","Int64.Type"),("source","type text")]),
    [measure("Road Class Accidents", "SUM('FactRoadClass2022'[accidents])", "#,0"),
     measure("Road Class Fatalities", "SUM('FactRoadClass2022'[fatalities])", "#,0")]))

# Keep the model relationship-free for reliable loading from TMSL/PBIP. The
# overview page's trend slicer uses the NH annual fact table directly.
relationships=[]

MODEL.mkdir(parents=True,exist_ok=True)
dump(MODEL/"definition.pbism",{"$schema":"https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json","version":"4.2","settings":{"qnaEnabled":False}})
dump(MODEL/"model.bim",{"name":NAME,"compatibilityLevel":1604,"model":{"culture":"en-US","defaultPowerBIDataSourceVersion":"powerBI_V3","sourceQueryCulture":"en-US","dataAccessOptions":{"legacyRedirects":True,"returnErrorValuesAsNull":True},"tables":tables,"relationships":relationships}})
dump(MODEL/".platform",{"$schema":"https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json","metadata":{"type":"SemanticModel","displayName":"Highway Accident Analysis"},"config":{"version":"2.0","logicalId":uid()}})

# PBIR report scaffold with three interactive analysis pages.
dump(PBI/f"{NAME}.pbip",{"$schema":"https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json","version":"1.0","artifacts":[{"report":{"path":f"{NAME}.Report"}}],"settings":{"enableAutoRecovery":True}})
dump(REPORT/"definition.pbir",{"$schema":"https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json","version":"4.0","datasetReference":{"byPath":{"path":f"../{NAME}.SemanticModel"}}})
dump(REPORT/".platform",{"$schema":"https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json","metadata":{"type":"Report","displayName":"Highway Accident Analysis"},"config":{"version":"2.0","logicalId":uid()}})
theme_name = "CY26SU09"
theme_dir = REPORT / "StaticResources" / "SharedResources" / "BaseThemes"
theme_dir.mkdir(parents=True, exist_ok=True)
if not THEME_SOURCE.exists():
    raise FileNotFoundError(f"Bundled Power BI base theme is missing: {THEME_SOURCE}")
dump(REPORT/"definition"/"report.json",{
    "$schema":"https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.0.0/schema.json",
    "themeCollection":{"baseTheme":{"name":theme_name,"reportVersionAtImport":{"visual":"2.9.0","report":"3.0.0","page":"2.1.0"},"type":"SharedResources"}},
    "resourcePackages":[{"name":"SharedResources","type":"SharedResources","items":[{"name":theme_name,"path":f"BaseThemes/{theme_name}.json","type":"BaseTheme"}]}],
    "filterConfig":{"filters":[]},
    "settings":{"useEnhancedTooltips":True,"defaultDrillFilterOtherVisuals":True,"useDefaultAggregateDisplayName":True}
})
dump(REPORT/"definition"/"version.json",{"$schema":"https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json","version":"2.0.0"})
page_order = list(PAGE_NAMES)
dump(REPORT/"definition"/"pages"/"pages.json",{"$schema":"https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json","pageOrder":page_order,"activePageName":PAGE_OVERVIEW})
for page_id, display_name in PAGE_NAMES.items():
    dump(REPORT/"definition"/"pages"/page_id/"page.json",{"$schema":"https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json","name":page_id,"displayName":display_name,"displayOption":"FitToPage","height":900,"width":1600})

def textbox(label, text, x, y, width, height, page, size=14, color="#334B62", weight="normal"):
    runs=[{"value":text,"textStyle":{"fontFamily":"Segoe UI","fontSize":f"{size}px","fontWeight":weight,"color":color}}]
    obj={"general":[{"properties":{"paragraphs":[{"textRuns":runs}]}}]}
    write_visual(label,"textbox",{"x":x,"y":y,"z":9000+int(y),"width":width,"height":height,"tabOrder":int(y)},objects=obj,page=page)

def page_header(page, title, subtitle):
    textbox("Page title",title,28,18,1120,54,page,30,"#10263D","bold")
    textbox("Page subtitle",subtitle,32,69,1180,28,page,14,"#60778D")
    textbox("Source note","SOURCE  MoRTH · PIB  |  India · 2018–2022  |  Counts are not exposure-adjusted risk rates",28,865,1540,22,page,11,"#60778D")

def card(label, measure_name, x, page=PAGE_OVERVIEW):
    q={"Data":{"projections":[projection(meas("FactAnnualSummary",measure_name),f"FactAnnualSummary.{measure_name}",measure_name)]}}
    write_visual(label,"cardVisual",{"x":x,"y":112,"z":2000+x,"width":364,"height":112,"tabOrder":2+x//380},q,title=label,page=page)

# PAGE 1 — executive overview: headline metrics and two complementary trends.
page_header(PAGE_OVERVIEW,"HIGHWAY SAFETY  /  INDIA","National Highway accident patterns · annual reported counts · 2018–2022")
year_slicer={"Values":{"projections":[projection(col("FactAnnualSummary","year"),"FactAnnualSummary.year","year")]}}
write_visual("Overview year filter","slicer",{"x":1320,"y":25,"z":5000,"width":240,"height":72,"tabOrder":1},year_slicer,title="Trend year",objects={"data":[{"properties":{"mode":{"expr":{"Literal":{"Value":"'Dropdown'"}}}}}]},page=PAGE_OVERVIEW)
for x,label,metric in [
    (24,"NH ACCIDENTS · 2022","NH Accidents 2022"),
    (412,"NH FATALITIES · 2022","NH Fatalities 2022"),
    (800,"NH SHARE OF ACCIDENTS","NH Accident Share 2022"),
    (1188,"NH SHARE OF FATALITIES","NH Fatality Share 2022"),
]:
    card(label,metric,x)

year_field=col("FactAnnualSummary","year")
nh_trend={"Category":{"projections":[projection(year_field,"FactAnnualSummary.year","Year")]},
          "Y":{"projections":[projection(meas("FactAnnualSummary","NH Accidents"),"FactAnnualSummary.NH Accidents","NH Accidents")]}}
write_visual("National highway trend","lineChart",{"x":24,"y":248,"z":3000,"width":752,"height":570,"tabOrder":10},nh_trend,title="National Highway accidents  |  +18.0% vs 2021",page=PAGE_OVERVIEW)
road_trend={"Category":{"projections":[projection(year_field,"FactAnnualSummary.year","Year")]},
            "Y":{"projections":[projection(meas("FactAnnualSummary","All Road Accidents"),"FactAnnualSummary.All Road Accidents","All-road accidents")]}}
write_visual("All road trend","lineChart",{"x":800,"y":248,"z":3100,"width":776,"height":570,"tabOrder":11},road_trend,title="All-road accidents  |  India",page=PAGE_OVERVIEW)
textbox("Overview insight","2022 NH accidents reached 151,997 — 7.9% above 2018. These are reported counts, not road-risk rates.",34,825,1500,28,PAGE_OVERVIEW,13,"#D38C15","bold")

# PAGE 2 — geospatial state hotspots with ranked and year-over-year views.
page_header(PAGE_STATES,"STATE HOTSPOTS  /  TOP 10","Bubble size and bars show NH accident counts · ranking fixed to 2022")
state_slicer={"Values":{"projections":[projection(col("FactNHStateYear","state"),"FactNHStateYear.state","State")]}}
write_visual("State filter","slicer",{"x":1240,"y":22,"z":5100,"width":310,"height":74,"tabOrder":1},state_slicer,title="State filter",objects={"data":[{"properties":{"mode":{"expr":{"Literal":{"Value":"'Dropdown'"}}}}}]},page=PAGE_STATES)
state_year_slicer={"Values":{"projections":[projection(col("FactNHStateYear","year"),"FactNHStateYear.year","Year")]}}
write_visual("State trend year filter","slicer",{"x":1050,"y":22,"z":5000,"width":170,"height":74,"tabOrder":2},state_year_slicer,title="Trend year",objects={"data":[{"properties":{"mode":{"expr":{"Literal":{"Value":"'Dropdown'"}}}}}]},page=PAGE_STATES)
map_query={"Category":{"projections":[projection(col("FactNHStateYear","location"),"FactNHStateYear.location","State · India")]},
           "Size":{"projections":[projection(meas("FactNHStateYear","NH State Accidents 2022"),"FactNHStateYear.NH State Accidents 2022","NH accidents 2022")]}}
write_visual("India NH hotspot map","map",{"x":24,"y":126,"z":3000,"width":752,"height":470,"tabOrder":10},map_query,title="NH accident hotspots  |  State-level locations",page=PAGE_STATES)
rank_query={"Category":{"projections":[projection(col("FactNHStateYear","state"),"FactNHStateYear.state","State")]},
            "Y":{"projections":[projection(meas("FactNHStateYear","NH State Accidents 2022"),"FactNHStateYear.NH State Accidents 2022","NH accidents 2022")]}}
rank_sort={"sort":[{"field":meas("FactNHStateYear","NH State Accidents 2022"),"direction":"Descending"}],"isDefaultSort":False}
write_visual("Top ten state ranking","clusteredBarChart",{"x":800,"y":126,"z":3100,"width":776,"height":470,"tabOrder":11},rank_query,title="Top 10 states by NH accidents  |  2022",page=PAGE_STATES,sort_definition=rank_sort)
state_trend={"Category":{"projections":[projection(col("FactNHStateYear","year"),"FactNHStateYear.year","Year")]},
             "Series":{"projections":[projection(col("FactNHStateYear","state"),"FactNHStateYear.state","State")]},
             "Y":{"projections":[projection(meas("FactNHStateYear","NH State Accidents"),"FactNHStateYear.NH State Accidents","NH accidents")]}}
write_visual("State trend by year","lineChart",{"x":24,"y":618,"z":3200,"width":1552,"height":220,"tabOrder":12},state_trend,title="Five-year NH accident trend  |  Top 10 states only",page=PAGE_STATES)
textbox("State scope note","State-level NH reporting here covers the 10 states ranked highest in 2022; it is not an all-state comparison.",32,845,1530,18,PAGE_STATES,11,"#60778D")

# PAGE 3 — road-safety context and severity indicators, with clearly labeled denominators.
page_header(PAGE_TRENDS,"SEVERITY & ROAD CONTEXT","National all-road annual totals · NH vs other-road split shown for 2022")
for x,label,metric in [
    (24,"ALL-ROAD ACCIDENTS · 2022","All Road Accidents 2022"),
    (412,"ALL-ROAD FATALITIES · 2022","All Road Fatalities 2022"),
    (800,"ALL-ROAD INJURIES · 2022","All Road Injuries 2022"),
    (1188,"NH FATALITIES / 100 ACCIDENTS","NH Fatalities per 100 Accidents 2022"),
]:
    card(label,metric,x,PAGE_TRENDS)

accident_line={"Category":{"projections":[projection(year_field,"FactAnnualSummary.year","Year")]},
               "Y":{"projections":[projection(meas("FactAnnualSummary","All Road Accidents"),"FactAnnualSummary.All Road Accidents","All-road accidents")]}}
write_visual("All road accident count trend","lineChart",{"x":24,"y":244,"z":3000,"width":500,"height":330,"tabOrder":10},accident_line,title="All-road accidents",page=PAGE_TRENDS)
fatality_line={"Category":{"projections":[projection(year_field,"FactAnnualSummary.year","Year")]},
               "Y":{"projections":[projection(meas("FactAnnualSummary","All Road Fatalities"),"FactAnnualSummary.All Road Fatalities","Fatalities")]}}
write_visual("All road fatality trend","lineChart",{"x":550,"y":244,"z":3100,"width":500,"height":330,"tabOrder":11},fatality_line,title="All-road fatalities",page=PAGE_TRENDS)
injury_line={"Category":{"projections":[projection(year_field,"FactAnnualSummary.year","Year")]},
             "Y":{"projections":[projection(meas("FactAnnualSummary","All Road Injuries"),"FactAnnualSummary.All Road Injuries","Injuries")]}}
write_visual("All road injury trend","lineChart",{"x":1076,"y":244,"z":3200,"width":500,"height":330,"tabOrder":12},injury_line,title="All-road injuries",page=PAGE_TRENDS)
roadclass_acc={"Category":{"projections":[projection(col("FactRoadClass2022","road_class"),"FactRoadClass2022.road_class","Road class")]},
               "Y":{"projections":[projection(meas("FactRoadClass2022","Road Class Accidents"),"FactRoadClass2022.Road Class Accidents","Accidents")]}}
write_visual("Road class accident composition","donutChart",{"x":24,"y":590,"z":3300,"width":740,"height":250,"tabOrder":13},roadclass_acc,title="2022 accidents  |  NH + Expressways vs other roads",page=PAGE_TRENDS)
roadclass_fatal={"Category":{"projections":[projection(col("FactRoadClass2022","road_class"),"FactRoadClass2022.road_class","Road class")]},
                 "Y":{"projections":[projection(meas("FactRoadClass2022","Road Class Fatalities"),"FactRoadClass2022.Road Class Fatalities","Fatalities")]}}
write_visual("Road class fatality composition","donutChart",{"x":800,"y":590,"z":3300,"width":776,"height":250,"tabOrder":14},roadclass_fatal,title="2022 fatalities  |  NH + Expressways vs other roads",page=PAGE_TRENDS)
textbox("NH severity note","NH fatality data is available here for 2022 only. “Fatalities per 100 accidents” is a count ratio, not an exposure-adjusted risk rate.",32,845,1530,18,PAGE_TRENDS,11,"#60778D")

(PBI/".gitignore").write_text("**/.pbi/localSettings.json\n**/.pbi/cache.abf\n",encoding="utf-8")
print(PBI/f"{NAME}.pbip")
