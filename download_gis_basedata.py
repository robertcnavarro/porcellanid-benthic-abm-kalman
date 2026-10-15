"""
Download real geographic base data for the Colombia CTM12 study-area map.
- Natural Earth 10m: countries, admin-1 (departments), land, coastline, rivers, populated places
- NOAA ETOPO (1 arc-min) relief/bathymetry via ERDDAP (subsampled)
All files are cached in 01_datos_raw/gis/ so the map is reproducible offline.
"""
import os
import zipfile
import io
import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIS_DIR = os.path.join(BASE, "01_datos_raw", "gis")
os.makedirs(GIS_DIR, exist_ok=True)

NE = {
    "ne_10m_admin_0_countries": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip",
    "ne_10m_admin_1_states_provinces": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_1_states_provinces.zip",
    "ne_10m_populated_places_simple": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_populated_places_simple.zip",
    "ne_10m_rivers_lake_centerlines": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_rivers_lake_centerlines.zip",
    "ne_10m_minor_islands": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_minor_islands.zip",
}

def fetch_ne():
    for name, url in NE.items():
        target = os.path.join(GIS_DIR, name, name + ".shp")
        if os.path.exists(target):
            print("cached:", name)
            continue
        print("downloading:", name)
        r = requests.get(url, timeout=180, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(os.path.join(GIS_DIR, name))

def fetch_etopo():
    target = os.path.join(GIS_DIR, "etopo_colombia.csv")
    if os.path.exists(target):
        print("cached: etopo")
        return
    # NOAA ETOPO 2022 (60 arc-sec) on PIFSC OceanWatch ERDDAP; stride 4 -> ~4 arc-min (~7.4 km)
    url = ("https://oceanwatch.pifsc.noaa.gov/erddap/griddap/ETOPO_2022_v1_60s.csv?"
           "z[(-5.0):4:(14.0)][(278.0):4:(294.0)]")
    print("downloading: ETOPO 2022 relief")
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    with open(target, "wb") as f:
        f.write(r.content)

if __name__ == "__main__":
    fetch_ne()
    fetch_etopo()
    print("Done. Files in", GIS_DIR)
