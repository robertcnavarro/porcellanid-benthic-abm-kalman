"""
Figure 0a - Official-style cartographic map of Colombia and the study area.

Projection : MAGNA-SIRGAS 2018 / Origen-Nacional (CTM12), EPSG:9377
Datum      : MAGNA-SIRGAS (GRS80 ellipsoid)
Base data  : Natural Earth 10m (boundaries, places, rivers), NOAA ETOPO 2022 relief
             (via ERDDAP), OpenStreetMap coastline for the Gulf inset (if available).

Panel A: Colombia (national), hypsometric relief + bathymetry, departments,
         capitals, rivers, projected graticule, CTM12 metric grid ticks,
         scale bar, north arrow, legend, San Andres & Providencia inset.
Panel B: Gulf of Morrosquillo detail with NOAA CoralTemp 0.05 deg grid cell.

Run download_gis_basedata.py first (cached files in 01_datos_raw/gis/).
"""
import os
import io
import numpy as np
import pandas as pd
import geopandas as gpd
import requests
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle, FancyArrow
from matplotlib_scalebar.scalebar import ScaleBar
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
from shapely.geometry import box, Point, LineString, Polygon
from shapely.ops import split, linemerge, unary_union, polygonize
from pyproj import Transformer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIS = os.path.join(BASE, "01_datos_raw", "gis")
FIG_DIR = os.path.join(BASE, "04_figuras")
CTM12 = "EPSG:9377"
WGS84 = "EPSG:4326"

# NOAA CoralTemp cell centre used for SST extraction (from the NOAA Excel file)
NOAA_LAT, NOAA_LON, NOAA_RES = 9.675, -75.725, 0.05
# Sampling station. >>> CONFIRM WITH FIELD RECORDS <<< (set to None to hide)
SITE_LAT, SITE_LON = None, None

GULF_BBOX = (-76.00, 9.25, -75.40, 9.95)  # lon_min, lat_min, lon_max, lat_max

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8,
                     "axes.linewidth": 0.8})

to_ctm = Transformer.from_crs(WGS84, CTM12, always_xy=True)
to_wgs = Transformer.from_crs(CTM12, WGS84, always_xy=True)


def shp(name):
    return gpd.read_file(os.path.join(GIS, name, name + ".shp"))


# ---------------------------------------------------------------------------
# Relief (ETOPO) helpers
# ---------------------------------------------------------------------------
def load_etopo(csv_name, url=None):
    path = os.path.join(GIS, csv_name)
    if not os.path.exists(path) and url:
        r = requests.get(url, timeout=300)
        r.raise_for_status()
        open(path, "wb").write(r.content)
    df = pd.read_csv(path, skiprows=[1])
    df.columns = ["lat", "lon", "z"]
    df["lon"] = np.where(df["lon"] > 180, df["lon"] - 360, df["lon"])
    lats = np.sort(df["lat"].unique())
    lons = np.sort(df["lon"].unique())
    grid = df.pivot(index="lat", columns="lon", values="z").reindex(index=lats, columns=lons).values
    return lons, lats, grid


def hillshade(z, dx, dy, az=315, alt=45):
    gy, gx = np.gradient(z, dy, dx)
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(az), np.radians(alt)
    hs = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    return np.clip(hs, 0, 1)


LAND_LEVELS = [0, 200, 500, 1000, 1500, 2000, 3000, 4000, 6000]
LAND_COLORS = ["#d8e8c4", "#c3dba5", "#e9e2a8", "#e2c98a", "#d2ab70",
               "#bb8b5a", "#a07052", "#f2efe9"]
SEA_LEVELS = [-8000, -4000, -3000, -2000, -1000, -200, 0]
SEA_COLORS = ["#8fb8d9", "#a2c5e1", "#b4d1e8", "#c6ddee", "#d6e7f4", "#e7f1f9"]


def draw_relief(ax, lons, lats, z, land_mask_geom=None, alpha_hs=0.35):
    lon2, lat2 = np.meshgrid(lons, lats)
    X, Y = to_ctm.transform(lon2, lat2)
    sea = np.ma.masked_where(z > 0, z)
    land = np.ma.masked_where(z <= 0, z)
    ax.pcolormesh(X, Y, sea, cmap=LinearSegmentedColormap.from_list("s", SEA_COLORS, N=len(SEA_COLORS)),
                  norm=BoundaryNorm(SEA_LEVELS, len(SEA_COLORS)), shading="auto", zorder=1, rasterized=True)
    ax.pcolormesh(X, Y, land, cmap=LinearSegmentedColormap.from_list("l", LAND_COLORS, N=len(LAND_COLORS)),
                  norm=BoundaryNorm(LAND_LEVELS, len(LAND_COLORS)), shading="auto", zorder=2, rasterized=True)
    dx = np.abs(np.diff(lons).mean()) * 111e3
    dy = np.abs(np.diff(lats).mean()) * 111e3
    hs = np.ma.masked_where(z <= 0, hillshade(z.astype(float), dx, dy))
    ax.pcolormesh(X, Y, hs, cmap="Greys_r", alpha=alpha_hs, shading="auto", zorder=3, rasterized=True)


# ---------------------------------------------------------------------------
# Graticule in a projected CRS
# ---------------------------------------------------------------------------
def graticule(ax, lon_ticks, lat_ticks, lon_rng, lat_rng, label=True, fs=6.5):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    for lo in lon_ticks:
        la = np.linspace(lat_rng[0], lat_rng[1], 200)
        X, Y = to_ctm.transform(np.full_like(la, lo), la)
        ax.plot(X, Y, color="#5d6d7e", lw=0.35, ls=(0, (4, 3)), zorder=8)
        if label:
            # bottom intersection
            idx = np.argmin(np.abs(Y - y0))
            if x0 < X[idx] < x1:
                ax.text(X[idx], y0, f"{abs(lo):g}°W", ha="center", va="top", fontsize=fs,
                        transform=ax.transData, clip_on=False, color="#2c3e50")
                ax.annotate("", xy=(X[idx], y0), xytext=(X[idx], y0 - (y1 - y0) * 0.0), zorder=9)
    for la in lat_ticks:
        lo = np.linspace(lon_rng[0], lon_rng[1], 200)
        X, Y = to_ctm.transform(lo, np.full_like(lo, la))
        ax.plot(X, Y, color="#5d6d7e", lw=0.35, ls=(0, (4, 3)), zorder=8)
        if label:
            idx = np.argmin(np.abs(X - x0))
            if y0 < Y[idx] < y1:
                hemi = "N" if la >= 0 else "S"
                ax.text(x0, Y[idx], f"{abs(la):g}°{hemi} ", ha="right", va="center", fontsize=fs,
                        clip_on=False, color="#2c3e50")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)


def ctm_ticks(ax, step, fs=5.5):
    """CTM12 metric coordinates on top/right axes (official grid annotation)."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    xt = np.arange(np.ceil(x0 / step) * step, x1, step)
    yt = np.arange(np.ceil(y0 / step) * step, y1, step)
    ax.xaxis.tick_top()
    ax.yaxis.tick_right()
    ax.set_xticks(xt)
    ax.set_yticks(yt)
    ax.set_xticklabels([f"{v/1e3:,.0f} km E" for v in xt], fontsize=fs, color="#7b241c")
    ax.set_yticklabels([f"{v/1e3:,.0f} km N" for v in yt], fontsize=fs, color="#7b241c", rotation=90, va="center")
    ax.tick_params(length=2.5, width=0.6, color="#7b241c", pad=1.5)


def north_arrow(ax, x=0.93, y=0.88, size=0.07):
    ax.annotate("", xy=(x, y + size), xytext=(x, y), xycoords="axes fraction",
                arrowprops=dict(facecolor="black", edgecolor="black", width=3.2, headwidth=9, headlength=8),
                zorder=20)
    ax.text(x, y + size + 0.012, "N", transform=ax.transAxes, ha="center", va="bottom",
            fontsize=10, fontweight="bold", zorder=20)


def neat_frame(ax):
    for s in ax.spines.values():
        s.set_linewidth(1.1)
        s.set_color("#1b2631")


# ---------------------------------------------------------------------------
# OSM coastline for the Gulf inset (falls back to Natural Earth)
# ---------------------------------------------------------------------------
def gulf_land_polygons(ne_land_ctm):
    cache = os.path.join(GIS, "osm_coast_morrosquillo.geojson")
    lon0, lat0, lon1, lat1 = GULF_BBOX
    if not os.path.exists(cache):
        q = f"""[out:json][timeout:120];way["natural"="coastline"]({lat0},{lon0},{lat1},{lon1});(._;>;);out body;"""
        try:
            js = None
            for ep in ["https://overpass.kumi.systems/api/interpreter",
                       "https://overpass-api.de/api/interpreter",
                       "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]:
                try:
                    r = requests.post(ep, data={"data": q}, timeout=90,
                                      headers={"User-Agent": "porcellanid-study-map/1.0 (academic)", "Accept": "*/*"})
                    r.raise_for_status()
                    js = r.json()
                    break
                except Exception as ex_ep:
                    print("[WARN] Overpass endpoint failed:", ep, type(ex_ep).__name__)
            if js is None:
                raise RuntimeError("all Overpass endpoints failed")
            nodes = {e["id"]: (e["lon"], e["lat"]) for e in js["elements"] if e["type"] == "node"}
            lines = [LineString([nodes[n] for n in e["nodes"] if n in nodes])
                     for e in js["elements"] if e["type"] == "way" and len(e["nodes"]) > 1]
            gpd.GeoDataFrame(geometry=lines, crs=WGS84).to_file(cache, driver="GeoJSON")
        except Exception as ex:
            print("[WARN] OSM coastline unavailable, using Natural Earth:", ex)
            return ne_land_ctm, "Natural Earth 10m"
    coast = gpd.read_file(cache)
    frame = box(lon0 - 0.05, lat0 - 0.05, lon1 + 0.05, lat1 + 0.05)
    merged = linemerge(unary_union(list(coast.geometry)))
    geoms = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
    # closed rings -> islands; open lines -> mainland split
    islands = [Polygon(g.coords) for g in geoms if g.is_ring]
    open_lines = unary_union([g for g in geoms if not g.is_ring] + [frame.exterior])
    pieces = list(polygonize(open_lines))
    # OSM convention: land lies to the LEFT of coastline direction. Classify with a known inland point.
    inland = Point(-75.45, 9.55)  # Sucre lowlands, east of the gulf
    sea = Point(-75.85, 9.55)     # open water of the gulf
    mainland = [p for p in pieces if p.contains(inland) and not p.contains(sea)]
    land = unary_union(mainland + islands) if mainland else None
    if land is None or land.is_empty or land.contains(sea) or not land.contains(inland):
        print("[WARN] OSM land polygon implausible, using Natural Earth")
        return ne_land_ctm, "Natural Earth 10m"
    g = gpd.GeoDataFrame(geometry=[land], crs=WGS84).to_crs(CTM12)
    return g, "OpenStreetMap coastline"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    REG = box(-86, -9, -60, 17)  # regional window in WGS84

    def prep(g):
        g = g[g.geometry.intersects(REG)].copy()
        g["geometry"] = g.geometry.intersection(REG)
        return g.to_crs(CTM12)

    countries = prep(shp("ne_10m_admin_0_countries"))
    admin1 = shp("ne_10m_admin_1_states_provinces")
    deps = prep(admin1[admin1["adm0_a3"] == "COL"])
    places = shp("ne_10m_populated_places_simple")
    places = places[places["adm0name"] == "Colombia"].to_crs(CTM12)
    rivers = prep(shp("ne_10m_rivers_lake_centerlines"))
    col = countries[countries["ADM0_A3"] == "COL"]
    others = countries[countries["ADM0_A3"] != "COL"]

    lons, lats, z = load_etopo("etopo_colombia.csv")

    fig = plt.figure(figsize=(12.5, 8.6), dpi=300, facecolor="white")
    axA = fig.add_axes([0.035, 0.06, 0.50, 0.86])
    axB = fig.add_axes([0.585, 0.30, 0.385, 0.62])
    axL = fig.add_axes([0.585, 0.06, 0.385, 0.20])
    axL.axis("off")

    # ---------------- Panel A: Colombia ----------------
    xmin, ymin = to_ctm.transform(-79.6, -4.4)
    xmax, ymax = to_ctm.transform(-66.6, 12.7)
    axA.set_xlim(xmin, xmax)
    axA.set_ylim(ymin, ymax)
    draw_relief(axA, lons, lats, z)
    others.plot(ax=axA, facecolor="#f4f4f2", edgecolor="#7f8c8d", lw=0.5, zorder=4)
    col_clip = col.copy()
    deps.boundary.plot(ax=axA, color="#566573", lw=0.35, ls="-", zorder=6)
    col.boundary.plot(ax=axA, color="#1b2631", lw=1.1, zorder=7)
    rv = gpd.clip(rivers, box(xmin, ymin, xmax, ymax))
    rv[rv["scalerank"] <= 6].plot(ax=axA, color="#3c7fb1", lw=0.45, zorder=5)

    # Department capitals (Natural Earth flags) + national capital
    caps = places[(places["adm0cap"] == 1) | (places["featurecla"].str.contains("Admin-1 capital", na=False))]
    caps_dep = caps[caps["adm0cap"] != 1]
    axA.scatter(caps_dep.geometry.x, caps_dep.geometry.y, s=7, facecolor="white", edgecolor="black",
                lw=0.6, zorder=10)
    bog = places[places["adm0cap"] == 1]
    axA.scatter(bog.geometry.x, bog.geometry.y, s=60, marker="*", color="#c0392b", edgecolor="black",
                lw=0.5, zorder=11)
    for _, r in bog.iterrows():
        axA.text(r.geometry.x + 25e3, r.geometry.y, "BOGOTÁ D.C.", fontsize=6.5, fontweight="bold",
                 zorder=12, path_effects=[pe.withStroke(linewidth=2, foreground="white")])

    # Labels for seas and neighbours
    halo = [pe.withStroke(linewidth=2.2, foreground="white")]
    def lbl(lon, lat, t, **kw):
        x, y = to_ctm.transform(lon, lat)
        axA.text(x, y, t, ha="center", va="center", zorder=12, path_effects=halo, **kw)
    lbl(-76.2, 12.0, "MAR CARIBE\n(Caribbean Sea)", fontsize=7.5, style="italic", color="#1f618d")
    lbl(-78.9, 3.3, "OCÉANO\nPACÍFICO", fontsize=7.5, style="italic", color="#1f618d")
    lbl(-71.3, 2.9, "COLOMBIA", fontsize=13, fontweight="bold", color="#17202a", alpha=0.85)
    lbl(-67.6, 7.6, "VENEZUELA", fontsize=6.5, color="#566573")
    lbl(-78.3, 0.2, "ECUADOR", fontsize=6.5, color="#566573")
    lbl(-72.6, -3.6, "PERÚ", fontsize=6.5, color="#566573")
    lbl(-67.6, -0.4, "BRASIL", fontsize=6.5, color="#566573")
    lbl(-79.0, 8.6, "PANAMÁ", fontsize=6.5, color="#566573")

    # Study-area box (Panel B extent)
    gx0, gy0 = to_ctm.transform(GULF_BBOX[0], GULF_BBOX[1])
    gx1, gy1 = to_ctm.transform(GULF_BBOX[2], GULF_BBOX[3])
    axA.add_patch(Rectangle((gx0, gy0), gx1 - gx0, gy1 - gy0, fill=False, ec="#c0392b", lw=1.4, zorder=13))
    axA.text(gx1 + 20e3, gy1 + 10e3, "Fig. B", color="#c0392b", fontsize=7, fontweight="bold", zorder=13,
             path_effects=halo)

    graticule(axA, np.arange(-80, -64, 2), np.arange(-4, 14, 2), (-82, -64), (-6, 15))
    ctm_ticks(axA, 400e3)
    axA.add_artist(ScaleBar(1, units="m", location="lower left", length_fraction=0.22, box_alpha=0.85,
                            font_properties={"size": 7}, scale_loc="top", border_pad=1.0))
    north_arrow(axA, x=0.93, y=0.84)
    neat_frame(axA)
    axA.text(0.012, 0.988, "A", transform=axA.transAxes, fontsize=13, fontweight="bold", va="top",
             bbox=dict(fc="white", ec="black", lw=0.8, pad=2.5), zorder=30)

    # San Andrés y Providencia inset (official cartographic convention)
    axI = axA.inset_axes([0.78, 0.045, 0.20, 0.16])
    sx0, sy0 = to_ctm.transform(-81.85, 12.42)
    sx1, sy1 = to_ctm.transform(-81.25, 13.45)
    axI.set_xlim(sx0, sx1)
    axI.set_ylim(sy0, sy1)
    axI.set_facecolor("#e7f1f9")
    col.plot(ax=axI, facecolor="#c3dba5", edgecolor="#1b2631", lw=0.6)
    try:
        isl = shp("ne_10m_minor_islands").to_crs(CTM12)
        isl.plot(ax=axI, facecolor="#c3dba5", edgecolor="#1b2631", lw=0.6)
    except Exception:
        pass
    axI.set_xticks([]); axI.set_yticks([])
    axI.set_title("Archipiélago de San Andrés,\nProvidencia y Santa Catalina", fontsize=5.2, pad=1.5)
    for s in axI.spines.values():
        s.set_linewidth(0.8)

    # ---------------- Panel B: Gulf of Morrosquillo ----------------
    bx0, by0 = to_ctm.transform(GULF_BBOX[0], GULF_BBOX[1])
    bx1, by1 = to_ctm.transform(GULF_BBOX[2], GULF_BBOX[3])
    axB.set_xlim(bx0, bx1)
    axB.set_ylim(by0, by1)
    url_fine = ("https://oceanwatch.pifsc.noaa.gov/erddap/griddap/ETOPO_2022_v1_15s.csv?"
                "z[(9.15):1:(10.05)][(283.9):1:(284.7)]")
    try:
        flon, flat, fz = load_etopo("etopo_morrosquillo.csv", url_fine)
        lon2, lat2 = np.meshgrid(flon, flat)
        X, Y = to_ctm.transform(lon2, lat2)
        sea = np.ma.masked_where(fz > 0, fz)
        axB.set_facecolor("#e7f1f9")
        axB.contourf(X, Y, sea, levels=[-500, -200, -100, -50, -20, -10, 0],
                     colors=["#a2c5e1", "#b4d1e8", "#c6ddee", "#d0e3f1", "#dceaf5", "#e7f1f9"], zorder=1)
        cs = axB.contour(X, Y, sea, levels=[-50, -20, -10], colors="#5499c7", linewidths=0.4, zorder=2)
        axB.clabel(cs, fmt="%d m", fontsize=5, inline=True)
    except Exception as ex:
        print("[WARN] fine bathymetry unavailable:", ex)
        axB.set_facecolor("#e7f1f9")

    ne_land = countries[countries["ADM0_A3"] == "COL"]
    land, coast_src = gulf_land_polygons(ne_land)
    land.plot(ax=axB, facecolor="#e9e2c8", edgecolor="#1b2631", lw=0.7, zorder=4)
    gb = box(bx0, by0, bx1, by1)
    deps_b = gpd.clip(deps, gb)
    deps_b.boundary.plot(ax=axB, color="#566573", lw=0.8, linestyle="-.", zorder=5)
    for _, r in deps_b.iterrows():
        c = r.geometry.representative_point()
        axB.text(c.x, c.y, r["name"].upper(), fontsize=7, color="#566573", fontweight="bold",
                 ha="center", zorder=6, path_effects=halo)

    # Reference towns (WGS84 coordinates, approximate municipal centroids)
    towns = {"Santiago de Tolú": (-75.582, 9.524), "Coveñas": (-75.680, 9.402),
             "San Onofre": (-75.526, 9.737), "Rincón del Mar": (-75.646, 9.786)}
    for name, (lo, la) in towns.items():
        x, y = to_ctm.transform(lo, la)
        axB.scatter(x, y, s=12, marker="s", color="#2c3e50", zorder=9)
        axB.text(x + 1200, y + 600, name, fontsize=6.5, zorder=9, path_effects=halo)

    # NOAA CoralTemp 0.05° cell
    h = NOAA_RES / 2
    cell = gpd.GeoSeries([box(NOAA_LON - h, NOAA_LAT - h, NOAA_LON + h, NOAA_LAT + h)], crs=WGS84).to_crs(CTM12)
    cell.plot(ax=axB, facecolor="#2e86c1", alpha=0.25, edgecolor="#1b4f72", lw=1.2, ls="--", zorder=7)
    cx, cy = to_ctm.transform(NOAA_LON, NOAA_LAT)
    axB.scatter(cx, cy, s=14, marker="+", color="#1b4f72", lw=1.2, zorder=8)
    axB.annotate("NOAA CoralTemp cell\n9.675° N, 75.725° W", xy=(cx, cy), xytext=(cx - 24e3, cy + 9e3),
                 fontsize=6.5, color="#1b4f72", fontweight="bold", zorder=10, path_effects=halo,
                 arrowprops=dict(arrowstyle="-", color="#1b4f72", lw=0.6))
    if SITE_LAT is not None:
        sx, sy = to_ctm.transform(SITE_LON, SITE_LAT)
        axB.scatter(sx, sy, s=90, marker="*", color="#e74c3c", edgecolor="black", lw=0.6, zorder=11)

    xb, yb = to_ctm.transform(-75.78, 9.55)
    axB.text(xb, yb, "Golfo de\nMorrosquillo", fontsize=8.5, style="italic", color="#1f618d",
             ha="center", zorder=6, path_effects=halo)

    graticule(axB, np.arange(-76.0, -75.35, 0.2), np.arange(9.3, 10.0, 0.2), (-76.2, -75.2), (9.1, 10.1), fs=6)
    ctm_ticks(axB, 20e3)
    axB.add_artist(ScaleBar(1, units="m", location="lower right", length_fraction=0.3, box_alpha=0.85,
                            font_properties={"size": 6.5}, scale_loc="top"))
    north_arrow(axB, x=0.07, y=0.83, size=0.08)
    neat_frame(axB)
    axB.text(0.015, 0.015, "B", transform=axB.transAxes, fontsize=13, fontweight="bold", va="bottom", ha="left",
             bbox=dict(fc="white", ec="black", lw=0.8, pad=2.5), zorder=30)

    # ---------------- Legend & cartographic metadata ----------------
    handles = [
        Line2D([], [], color="#1b2631", lw=1.1, label="International boundary"),
        Line2D([], [], color="#566573", lw=0.6, label="Departmental boundary"),
        Line2D([], [], color="#3c7fb1", lw=0.8, label="Main rivers"),
        Line2D([], [], marker="*", ls="", color="#c0392b", markeredgecolor="k", ms=8, label="National capital"),
        Line2D([], [], marker="o", ls="", mfc="white", mec="k", ms=4, label="Departmental capital"),
        Line2D([], [], marker="s", ls="", color="#2c3e50", ms=4, label="Town / locality"),
        Patch(facecolor="#2e86c1", alpha=0.35, edgecolor="#1b4f72", ls="--", label="NOAA CoralTemp 0.05° cell"),
        Rectangle((0, 0), 1, 1, fill=False, ec="#c0392b", lw=1.4, label="Study area (panel B)"),
        Line2D([], [], color="#5d6d7e", lw=0.6, ls=(0, (4, 3)), label="Geographic graticule"),
    ]
    leg = axL.legend(handles=handles, loc="upper left", ncol=2, fontsize=6.6, frameon=True,
                     title="LEGEND", title_fontsize=7.5, borderpad=0.7, handlelength=2.2, columnspacing=1.4)
    leg.get_frame().set_edgecolor("#1b2631")
    leg.get_frame().set_linewidth(0.8)
    # Elevation / depth colour key
    keyx = axL.inset_axes([0.0, 0.0, 0.48, 0.10])
    keyx.imshow([np.arange(len(LAND_COLORS))], cmap=LinearSegmentedColormap.from_list("l", LAND_COLORS, N=len(LAND_COLORS)),
                aspect="auto")
    keyx.set_yticks([])
    keyx.set_xticks(np.arange(len(LAND_COLORS)) - 0.5)
    keyx.set_xticklabels([str(v) for v in LAND_LEVELS[:-1]], fontsize=5)
    keyx.set_title("Elevation (m a.s.l.)", fontsize=5.8, pad=1)
    keys = axL.inset_axes([0.52, 0.0, 0.48, 0.10])
    keys.imshow([np.arange(len(SEA_COLORS))], cmap=LinearSegmentedColormap.from_list("s", SEA_COLORS, N=len(SEA_COLORS)),
                aspect="auto")
    keys.set_yticks([])
    keys.set_xticks(np.arange(len(SEA_COLORS)) - 0.5)
    keys.set_xticklabels([str(v) for v in SEA_LEVELS[:-1]], fontsize=5)
    keys.set_title("Depth (m)", fontsize=5.8, pad=1)

    meta = ("Projection: MAGNA-SIRGAS 2018 / Origen-Nacional (CTM12), EPSG:9377 — Transverse Mercator, "
            "λ₀ = 73° W, φ₀ = 4° N, k₀ = 0.9992, FE = 5 000 000 m, FN = 2 000 000 m. Datum: MAGNA-SIRGAS (GRS80). "
            "Red ticks: CTM12 plane coordinates. Sources: Natural Earth 10m (boundaries, places, rivers); "
            f"NOAA ETOPO 2022 relief/bathymetry; {coast_src} (panel B); NOAA Coral Reef Watch CoralTemp v3.1 grid.")
    axL.text(0.0, 0.40, meta, transform=axL.transAxes, fontsize=5.4, wrap=True, va="top", color="#2c3e50")

    out = os.path.join(FIG_DIR, "Fig0a_Colombia_CTM12_Map.png")
    fig.savefig(out, dpi=300, facecolor="white")
    fig.savefig(out.replace(".png", ".pdf"), facecolor="white")
    plt.close(fig)
    print("Saved", out, "and PDF (vector)")


if __name__ == "__main__":
    main()
