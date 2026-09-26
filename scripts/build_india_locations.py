"""Build backend/data/india_locations.json: every Indian state / UT with its districts.

Run once (needs internet and shapely; the app itself needs neither):

    .\\.venv\\Scripts\\python.exe scripts\\build_india_locations.py

Source: geoBoundaries gbOpen IND (pinned to release commit 9469f09, built 12 Dec 2023)
  * ADM1 (36 states and union territories): DataMeet India community / Election Commission of India,
    licence CC BY 2.5 IN.
  * ADM2 (districts, 2021 list from lgdirectory.gov.in via Pathways Data Pvt. Ltd.): licence ODbL 1.0.
The simplified geometries are used; only names, centroids, bounding boxes and a zoom level are kept.

ADM2 carries no state, so every district is assigned to the ADM1 polygon it overlaps most. A small
table below fixes known issues in the source (typos, an enclave assigned by overlap, a placeholder
polygon) and renames districts to their current official names; every source name that changes is
kept as an alias so it still resolves. MAJOR_CITIES is a curated list (state capital first, then the
biggest cities) and each entry must point at a district in the generated list, or the build fails.
"""
import json
import math
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "backend" / "data" / "india_locations.json"
CACHE = REPO / "data" / "geoboundaries"  # git-ignored download cache

COMMIT = "9469f09"
URL = ("https://github.com/wmgeolab/geoBoundaries/raw/{commit}/releaseData/gbOpen/IND/{level}/"
       "geoBoundaries-IND-{level}_simplified.geojson")

SOURCE = {
    "dataset": "geoBoundaries gbOpen IND ADM1 + ADM2 (simplified geometries)",
    "release_commit": COMMIT,
    "build_date": "2023-12-12",
    "adm1": {"boundary_id": "IND-ADM1-1811400", "year_represented": "2011 (with 2019-2020 UT changes)",
             "source": "DataMeet India community, Election Commission of India",
             "licence": "CC BY 2.5 IN"},
    "adm2": {"boundary_id": "IND-ADM2-76128533", "year_represented": "2021",
             "source": "Pathways Data Pvt. Ltd., lgdirectory.gov.in", "licence": "ODbL 1.0"},
    "citation": "Runfola, D. et al. (2020) geoBoundaries: A global database of political administrative "
                "boundaries. PLoS ONE 15(4): e0231866. https://www.geoboundaries.org",
}

UNION_TERRITORIES = {"IN-AN", "IN-CH", "IN-DH", "IN-DL", "IN-JK", "IN-LA", "IN-LD", "IN-PY"}
STATE_NAME_FIX = {"IN-DH": "Dadra and Nagar Haveli and Daman and Diu"}

# Districts to drop, and districts whose state must be set explicitly (overlap picks the wrong one).
DROP = {"DATA NOT AVAILABLE"}
FORCE_STATE = {"Yanam": "IN-PY"}  # enclave of Puducherry inside Andhra Pradesh

# (state ISO, source name) -> current official name. Source names become aliases.
RENAMES = {
    # typos / formatting in the source
    ("IN-TG", "Hydrabad"): "Hyderabad",
    ("IN-GJ", "Batod"): "Botad",
    ("IN-MH", "Raigarh"): "Raigad",
    ("IN-LA", "Leh(Ladakh)"): "Leh",
    ("IN-AP", "Kadapa(YSR)"): "YSR Kadapa",
    ("IN-AN", "North  & Middle Andaman"): "North and Middle Andaman",
    ("IN-DH", "Dadra & Nagar Haveli"): "Dadra and Nagar Haveli",
    ("IN-HP", "Lahul & Spiti"): "Lahaul and Spiti",
    ("IN-TG", "Warangal (R)"): "Warangal Rural",
    ("IN-TG", "Warangal (U)"): "Warangal Urban",
    ("IN-TG", "Bhadradri"): "Bhadradri Kothagudem",
    ("IN-TG", "Jayashankar"): "Jayashankar Bhupalpally",
    ("IN-TG", "Jogulamba"): "Jogulamba Gadwal",
    ("IN-TG", "Komaram Bheem"): "Komaram Bheem Asifabad",
    ("IN-TG", "Medchal"): "Medchal-Malkajgiri",
    # official renames
    ("IN-KA", "Bangalore"): "Bengaluru Urban",
    ("IN-KA", "Bangalore Rural"): "Bengaluru Rural",
    ("IN-KA", "Belgaum"): "Belagavi",
    ("IN-KA", "Bellary"): "Ballari",
    ("IN-KA", "Bijapur"): "Vijayapura",
    ("IN-KA", "Chikmagalur"): "Chikkamagaluru",
    ("IN-KA", "Gulbarga"): "Kalaburagi",
    ("IN-KA", "Mysore"): "Mysuru",
    ("IN-KA", "Shimoga"): "Shivamogga",
    ("IN-KA", "Tumkur"): "Tumakuru",
    ("IN-UP", "Allahabad"): "Prayagraj",
    ("IN-UP", "Faizabad"): "Ayodhya",
    ("IN-UP", "Jyotiba Phule Nagar"): "Amroha",
    ("IN-UP", "Mahamaya Nagar"): "Hathras",
    ("IN-UP", "Kanshiram Nagar"): "Kasganj",
    ("IN-UP", "Samli"): "Shamli",
    ("IN-UP", "Bara Banki"): "Barabanki",
    ("IN-UP", "Sant Ravidas Nagar (Bhadohi)"): "Bhadohi",
    ("IN-UP", "Kheri"): "Lakhimpur Kheri",
    ("IN-HR", "Gurgaon"): "Gurugram",
    ("IN-HR", "Mewat"): "Nuh",
    ("IN-MP", "Hoshangabad"): "Narmadapuram",
    ("IN-MH", "Aurangabad"): "Chhatrapati Sambhajinagar",
    ("IN-MH", "Osmanabad"): "Dharashiv",
    ("IN-UT", "Hardwar"): "Haridwar",
    ("IN-UT", "Garhwal"): "Pauri Garhwal",
    ("IN-SK", "East District"): "Gangtok",
    ("IN-SK", "North District"): "Mangan",
    ("IN-SK", "South District"): "Namchi",
    ("IN-SK", "West District"): "Gyalshing",
    ("IN-WB", "Barddhaman"): "Purba Bardhaman",
    # common English spellings (the source uses Census transliterations)
    ("IN-WB", "Haora"): "Howrah",
    ("IN-WB", "Hugli"): "Hooghly",
    ("IN-WB", "Darjiling"): "Darjeeling",
    ("IN-WB", "Koch Bihar"): "Cooch Behar",
    ("IN-WB", "Puruliya"): "Purulia",
    ("IN-WB", "Maldah"): "Malda",
    ("IN-WB", "Paschim Barddhaman"): "Paschim Bardhaman",
    ("IN-WB", "North Twenty Four Parganas"): "North 24 Parganas",
    ("IN-WB", "South Twenty Four Parganas"): "South 24 Parganas",
    ("IN-MH", "Ahmadnagar"): "Ahmednagar",
    ("IN-MH", "Bid"): "Beed",
    ("IN-MH", "Buldana"): "Buldhana",
    ("IN-MH", "Gondiya"): "Gondia",
    ("IN-GJ", "Ahmadabad"): "Ahmedabad",
    ("IN-GJ", "Dohad"): "Dahod",
    ("IN-GJ", "Banas Kantha"): "Banaskantha",
    ("IN-GJ", "Sabar Kantha"): "Sabarkantha",
    ("IN-GJ", "Panch Mahals"): "Panchmahal",
    ("IN-TN", "Chengalputtu"): "Chengalpattu",
    ("IN-BR", "Pashchim Champaran"): "West Champaran",
    ("IN-BR", "Purba Champaran"): "East Champaran",
    ("IN-JH", "Pashchimi Singhbhum"): "West Singhbhum",
    ("IN-JH", "Purbi Singhbhum"): "East Singhbhum",
    ("IN-JH", "Kodarma"): "Koderma",
    ("IN-JK", "Baramula"): "Baramulla",
    ("IN-JK", "Badgam"): "Budgam",
    ("IN-JK", "Punch"): "Poonch",
    ("IN-JK", "Shupiyan"): "Shopian",
    ("IN-PB", "Muktsar"): "Sri Muktsar Sahib",
    ("IN-MP", "Narsimhapur"): "Narsinghpur",
}

# Names the app used before this file existed: (state, old name) -> district.
LEGACY_ALIASES = {("Karnataka", "Mangaluru"): "Dakshina Kannada"}

# State capital first (when it is a district of that state), then the biggest cities.
# Each entry is (label, district); the district must exist in that state's list.
MAJOR_CITIES = {
    "Andaman and Nicobar Islands": [("Port Blair (South Andaman)", "South Andaman"),
                                    ("North and Middle Andaman", "North and Middle Andaman"),
                                    ("Nicobars", "Nicobars")],
    "Andhra Pradesh": [("Amaravati & Guntur (Guntur)", "Guntur"), ("Visakhapatnam", "Visakhapatnam"),
                       ("Vijayawada (Krishna)", "Krishna"), ("Nellore (Sri Potti Sriramulu Nellore)",
                                                             "Sri Potti Sriramulu Nellore"),
                       ("Tirupati (Chittoor)", "Chittoor")],
    "Arunachal Pradesh": [("Itanagar (Papum Pare)", "Papum Pare"), ("Pasighat (East Siang)", "East Siang"),
                          ("Namsai", "Namsai"), ("Tezu (Lohit)", "Lohit"), ("Tawang", "Tawang")],
    "Assam": [("Guwahati / Dispur (Kamrup Metropolitan)", "Kamrup Metropolitan"), ("Silchar (Cachar)", "Cachar"),
              ("Dibrugarh", "Dibrugarh"), ("Jorhat", "Jorhat"), ("Nagaon", "Nagaon")],
    "Bihar": [("Patna", "Patna"), ("Gaya", "Gaya"), ("Bhagalpur", "Bhagalpur"), ("Muzaffarpur", "Muzaffarpur"),
              ("Darbhanga", "Darbhanga"), ("Purnia", "Purnia")],
    "Chandigarh": [("Chandigarh", "Chandigarh")],
    "Chhattisgarh": [("Raipur", "Raipur"), ("Bhilai (Durg)", "Durg"), ("Bilaspur", "Bilaspur"),
                     ("Korba", "Korba"), ("Rajnandgaon", "Rajnandgaon")],
    "Dadra and Nagar Haveli and Daman and Diu": [("Daman", "Daman"), ("Silvassa (Dadra and Nagar Haveli)",
                                                                      "Dadra and Nagar Haveli"), ("Diu", "Diu")],
    "Delhi": [("New Delhi", "New Delhi"), ("Central Delhi", "Central"), ("South Delhi", "South"),
              ("North West Delhi", "North West"), ("East Delhi", "East")],
    "Goa": [("Panaji (North Goa)", "North Goa"), ("Margao (South Goa)", "South Goa")],
    "Gujarat": [("Gandhinagar", "Gandhinagar"), ("Ahmedabad", "Ahmedabad"), ("Surat", "Surat"),
                ("Vadodara", "Vadodara"), ("Rajkot", "Rajkot"), ("Bhavnagar", "Bhavnagar")],
    "Haryana": [("Faridabad", "Faridabad"), ("Gurugram", "Gurugram"), ("Panipat", "Panipat"),
                ("Ambala", "Ambala"), ("Hisar", "Hisar")],
    "Himachal Pradesh": [("Shimla", "Shimla"), ("Dharamshala (Kangra)", "Kangra"), ("Mandi", "Mandi"),
                         ("Solan", "Solan"), ("Kullu", "Kullu")],
    "Jammu and Kashmir": [("Srinagar", "Srinagar"), ("Jammu", "Jammu"), ("Anantnag", "Anantnag"),
                          ("Baramulla", "Baramulla"), ("Udhampur", "Udhampur")],
    "Jharkhand": [("Ranchi", "Ranchi"), ("Jamshedpur (East Singhbhum)", "East Singhbhum"), ("Dhanbad", "Dhanbad"),
                  ("Bokaro", "Bokaro"), ("Deoghar", "Deoghar")],
    "Karnataka": [("Bengaluru (Bengaluru Urban)", "Bengaluru Urban"), ("Mysuru", "Mysuru"),
                  ("Hubballi-Dharwad (Dharwad)", "Dharwad"), ("Mangaluru (Dakshina Kannada)", "Dakshina Kannada"),
                  ("Belagavi", "Belagavi"), ("Kalaburagi", "Kalaburagi")],
    "Kerala": [("Thiruvananthapuram", "Thiruvananthapuram"), ("Kochi (Ernakulam)", "Ernakulam"),
               ("Kozhikode", "Kozhikode"), ("Thrissur", "Thrissur"), ("Kollam", "Kollam")],
    "Ladakh": [("Leh", "Leh"), ("Kargil", "Kargil")],
    "Lakshadweep": [("Kavaratti (Lakshadweep)", "Lakshadweep")],
    "Madhya Pradesh": [("Bhopal", "Bhopal"), ("Indore", "Indore"), ("Jabalpur", "Jabalpur"),
                       ("Gwalior", "Gwalior"), ("Ujjain", "Ujjain")],
    "Maharashtra": [("Mumbai", "Mumbai"), ("Pune", "Pune"), ("Nagpur", "Nagpur"), ("Nashik", "Nashik"),
                    ("Thane", "Thane")],
    "Manipur": [("Imphal (Imphal West)", "Imphal West"), ("Imphal East", "Imphal East"), ("Thoubal", "Thoubal"),
                ("Bishnupur", "Bishnupur"), ("Churachandpur", "Churachandpur")],
    "Meghalaya": [("Shillong (East Khasi Hills)", "East Khasi Hills"), ("Tura (West Garo Hills)", "West Garo Hills"),
                  ("Jowai (West Jaintia Hills)", "West Jaintia Hills"), ("Nongpoh (Ribhoi)", "Ribhoi")],
    "Mizoram": [("Aizawl", "Aizawl"), ("Lunglei", "Lunglei"), ("Champhai", "Champhai"), ("Kolasib", "Kolasib"),
                ("Serchhip", "Serchhip")],
    "Nagaland": [("Kohima", "Kohima"), ("Dimapur", "Dimapur"), ("Mokokchung", "Mokokchung"),
                 ("Tuensang", "Tuensang"), ("Wokha", "Wokha")],
    "Odisha": [("Bhubaneswar (Khordha)", "Khordha"), ("Cuttack", "Cuttack"), ("Berhampur (Ganjam)", "Ganjam"),
               ("Rourkela (Sundargarh)", "Sundargarh"), ("Sambalpur", "Sambalpur"), ("Puri", "Puri")],
    "Puducherry": [("Puducherry", "Puducherry"), ("Karaikal", "Karaikal"), ("Mahe", "Mahe"), ("Yanam", "Yanam")],
    "Punjab": [("Ludhiana", "Ludhiana"), ("Amritsar", "Amritsar"), ("Jalandhar", "Jalandhar"),
               ("Patiala", "Patiala"), ("Bathinda", "Bathinda"), ("Mohali (Sahibzada Ajit Singh Nagar)",
                                                                  "Sahibzada Ajit Singh Nagar")],
    "Rajasthan": [("Jaipur", "Jaipur"), ("Jodhpur", "Jodhpur"), ("Kota", "Kota"), ("Bikaner", "Bikaner"),
                  ("Ajmer", "Ajmer"), ("Udaipur", "Udaipur")],
    "Sikkim": [("Gangtok", "Gangtok"), ("Namchi", "Namchi"), ("Mangan", "Mangan"), ("Gyalshing", "Gyalshing")],
    "Tamil Nadu": [("Chennai", "Chennai"), ("Coimbatore", "Coimbatore"), ("Madurai", "Madurai"),
                   ("Tiruchirappalli", "Tiruchirappalli"), ("Salem", "Salem"), ("Tiruppur", "Tiruppur")],
    "Telangana": [("Hyderabad", "Hyderabad"), ("Warangal (Warangal Urban)", "Warangal Urban"),
                  ("Nizamabad", "Nizamabad"), ("Karimnagar", "Karimnagar"), ("Khammam", "Khammam")],
    "Tripura": [("Agartala (West Tripura)", "West Tripura"), ("Udaipur (Gomati)", "Gomati"),
                ("Dharmanagar (North Tripura)", "North Tripura"), ("Kailashahar (Unokoti)", "Unokoti")],
    "Uttar Pradesh": [("Lucknow", "Lucknow"), ("Kanpur (Kanpur Nagar)", "Kanpur Nagar"), ("Ghaziabad", "Ghaziabad"),
                      ("Agra", "Agra"), ("Varanasi", "Varanasi"), ("Prayagraj", "Prayagraj")],
    "Uttarakhand": [("Dehradun", "Dehradun"), ("Haridwar", "Haridwar"), ("Haldwani (Nainital)", "Nainital"),
                    ("Rudrapur (Udham Singh Nagar)", "Udham Singh Nagar")],
    "West Bengal": [("Kolkata", "Kolkata"), ("Howrah", "Howrah"), ("Siliguri area (Darjeeling)", "Darjeeling"),
                    ("Asansol area (Paschim Bardhaman)", "Paschim Bardhaman"),
                    ("North 24 Parganas", "North 24 Parganas")],
}

# Zoom so the district's bounding box fits a ~500 px map, clamped to a sensible range.
MAP_PX, MIN_ZOOM, MAX_ZOOM = 500, 5, 12


def plain_name(name):
    """Strip diacritics and tidy whitespace: 'Karnātaka' -> 'Karnataka'."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def zoom_for(bbox):
    west, south, east, north = bbox
    lat = math.radians((south + north) / 2)
    extent = max((east - west) * math.cos(lat), north - south, 1e-6)  # degrees, roughly isotropic
    return int(max(MIN_ZOOM, min(MAX_ZOOM, math.floor(math.log2(MAP_PX * 360 / (256 * extent))))))


def load(level):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"IND_{level}_{COMMIT}.geojson"
    if not path.exists():
        print(f"downloading {level} ...")
        urllib.request.urlretrieve(URL.format(commit=COMMIT, level=level), path)
    return json.loads(path.read_text(encoding="utf-8"))["features"]


def place(geom):
    """(centroid lat/lon inside the shape, bbox rounded) for a shapely geometry."""
    point = geom.centroid
    if not geom.contains(point):
        point = geom.representative_point()
    w, s, e, n = geom.bounds
    return (round(point.y, 4), round(point.x, 4)), [round(w, 4), round(s, 4), round(e, 4), round(n, 4)]


def build():
    from shapely.geometry import shape
    from shapely.strtree import STRtree

    adm1, adm2 = load("ADM1"), load("ADM2")
    state_geoms = [shape(f["geometry"]).buffer(0) for f in adm1]
    tree = STRtree(state_geoms)
    iso_index = {f["properties"]["shapeISO"]: i for i, f in enumerate(adm1)}

    states = {}
    for i, f in enumerate(adm1):
        iso = f["properties"]["shapeISO"]
        name = STATE_NAME_FIX.get(iso) or plain_name(f["properties"]["shapeName"])
        (lat, lon), bbox = place(state_geoms[i])
        states[iso] = {"name": name, "iso": iso, "type": "union_territory" if iso in UNION_TERRITORIES else "state",
                       "lat": lat, "lon": lon, "bbox": bbox, "zoom": zoom_for(bbox), "districts": {},
                       "aliases": {}}

    for f in adm2:
        source = re.sub(r"\s+", " ", f["properties"]["shapeName"]).strip()
        raw = f["properties"]["shapeName"]
        if source in DROP:
            continue
        geom = shape(f["geometry"]).buffer(0)
        if source in FORCE_STATE:
            iso = FORCE_STATE[source]
        else:
            best = max(tree.query(geom), key=lambda k: state_geoms[k].intersection(geom).area)
            iso = adm1[best]["properties"]["shapeISO"]
        name = RENAMES.get((iso, raw)) or RENAMES.get((iso, source)) or source
        state = states[iso]
        if name in state["districts"]:
            sys.exit(f"duplicate district {name!r} in {state['name']}")
        (lat, lon), bbox = place(geom)
        state["districts"][name] = {"lat": lat, "lon": lon, "bbox": bbox, "zoom": zoom_for(bbox)}
        if name != source:
            state["aliases"][source] = name

    by_name = {s["name"]: s for s in states.values()}
    for (state_name, old), district in LEGACY_ALIASES.items():
        by_name[state_name]["aliases"][old] = district

    out_states = []
    for s in sorted(states.values(), key=lambda s: s["name"]):
        districts = dict(sorted(s["districts"].items()))
        majors = MAJOR_CITIES.get(s["name"])
        if not majors:
            sys.exit(f"no MAJOR_CITIES entry for {s['name']}")
        for label, district in majors:
            if district not in districts:
                sys.exit(f"major city {label!r}: district {district!r} is not in {s['name']}")
        if len({d for _, d in majors}) != len(majors):
            sys.exit(f"major cities of {s['name']} repeat a district")
        for alias, target in s["aliases"].items():
            if target not in districts:
                sys.exit(f"alias {alias!r} -> {target!r} missing in {s['name']}")
        out_states.append({
            "name": s["name"], "iso": s["iso"], "type": s["type"], "lat": s["lat"], "lon": s["lon"],
            "bbox": s["bbox"], "zoom": s["zoom"],
            "major_cities": [{"label": label, "district": district} for label, district in majors],
            "districts": [{"name": n, **v} for n, v in districts.items()],
            "aliases": dict(sorted(s["aliases"].items())),
        })

    unused = [k for k in RENAMES if k[1] not in {a for s in states.values() for a in s["aliases"]}
              and RENAMES[k] not in {d for s in states.values() for d in s["districts"]}]
    if unused:
        sys.exit(f"RENAMES entries that matched nothing: {unused}")

    data = {"source": SOURCE, "notes": [
        "District list as of 2021 (geoBoundaries). Districts created later (e.g. Andhra Pradesh's 2022 "
        "reorganisation into 26 districts, Rajasthan's 2023 new districts) are not included.",
        "lat/lon is the district centroid (a point inside the district for odd shapes); bbox is "
        "[west, south, east, north] in degrees from the simplified boundary; zoom fits the bbox in ~500 px.",
        "Some source spellings were replaced by current official names; the source names are kept as aliases.",
    ], "states": out_states}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = sum(len(s["districts"]) for s in out_states)
    print(f"wrote {OUT.relative_to(REPO)}: {len(out_states)} states/UTs, {n} districts, "
          f"{OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    build()
