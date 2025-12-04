from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List, Tuple

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from math import radians, sin, cos, sqrt, atan2

from tqdm.auto import tqdm
import folium
import os


# -------------------------------------------------------------------
# CONFIG DE BASE (chemins)
# -------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
INPUTS_DIR = ROOT / "inputs"   # dossier où tu as iris_shapes.gpkg, iris_joint.xlsx, relais_colis.xlsx
OUTPUTS_DIR = ROOT
OUTPUTS_DIR.mkdir(exist_ok=True)


# -------------------------------------------------------------------
# DISTANCE HAVERSINE
# -------------------------------------------------------------------
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Distance en km entre deux points (lat/lon en degrés) – vol d’oiseau.
    """
    R = 6371.0  # rayon Terre en km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


# -------------------------------------------------------------------
# CHARGEMENT DES IRIS (geometries + socio)
# -------------------------------------------------------------------
def load_iris_data(
    iris_geom_path: Path | str = INPUTS_DIR / "iris_shapes.gpkg",
    iris_joint_path: Path | str = INPUTS_DIR / "iris_joint.xlsx",
    iris_code_col: str = "CODE_IRIS",
) -> gpd.GeoDataFrame:
    """
    Charge les polygones IRIS (GeoPackage) + les données socio (iris_joint.xlsx)
    et fusionne le tout dans un GeoDataFrame unique.
    """

    iris_geom_path = Path(iris_geom_path)
    iris_joint_path = Path(iris_joint_path)

    print(f"📂 Chargement des géométries IRIS depuis {iris_geom_path}...")
    gdf_geom = gpd.read_file(iris_geom_path)
    if iris_code_col not in gdf_geom.columns:
        raise ValueError(f"{iris_code_col} manquant dans le GeoPackage.")

    print(f"📂 Chargement des données socio IRIS depuis {iris_joint_path}...")
    df_joint = pd.read_excel(iris_joint_path)

    if iris_code_col not in df_joint.columns:
        raise ValueError(f"{iris_code_col} manquant dans iris_joint.xlsx.")

    # Fusion
    iris_socio_gdf = gdf_geom.merge(df_joint, on=iris_code_col, how="left")

    # S’assurer du CRS
    if iris_socio_gdf.crs is None:
        iris_socio_gdf.set_crs(epsg=4326, inplace=True)
    else:
        iris_socio_gdf = iris_socio_gdf.to_crs(4326)

    print(f"✅ IRIS chargés : {len(iris_socio_gdf)} lignes.")
    return iris_socio_gdf


# -------------------------------------------------------------------
# CHARGEMENT DES RELAIS
# -------------------------------------------------------------------
def load_relais_excel(
    path: Path | str,
    col_code: str = "Code agence",
    col_nom: str = "Nom d'enseigne",
    col_lat: str = "Latitude",
    col_lon: str = "Longitude",
    col_statut: str = "Statut",
) -> gpd.GeoDataFrame:
    """
    Charge un fichier de relais (points) au format Excel et renvoie un GeoDataFrame.
    Attend au minimum : Code agence, Nom d'enseigne, Latitude, Longitude, Statut.
    """

    path = Path(path)
    print(f"📂 Chargement des relais depuis {path}...")
    df = pd.read_excel(path)

    # Normalisation des noms de colonnes si besoin
    for col in [col_code, col_nom, col_lat, col_lon, col_statut]:
        if col not in df.columns:
            raise ValueError(f"Colonne '{col}' manquante dans {path.name}")

    df["Statut"] = df[col_statut].astype(str).str.lower()
    df["id_point"] = df[col_code].astype(str)
    df["nom_point"] = df[col_nom].astype(str)

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df[col_lon], df[col_lat]),
        crs="EPSG:4326",
    )
    print(f"✅ Relais chargés : {len(gdf)} lignes.")
    return gdf


# -------------------------------------------------------------------
# INDEX SPATIAL + CENTROÏDES IRIS (pour zones par rayon en km)
# -------------------------------------------------------------------
_IRIS_GDF_3857 = None
_IRIS_SINDEX = None
_IRIS_CENTROIDS_4326 = None


def _prepare_iris_index(iris_socio_gdf: gpd.GeoDataFrame, iris_code_col: str = "CODE_IRIS") -> None:
    """
    Prépare :
      - une version en EPSG:3857 (mètres) pour les buffers
      - un sindex (R-tree) pour requêtes spatiales rapides
      - les centroids en EPSG:4326 pour calcul de distances (haversine)
    """
    global _IRIS_GDF_3857, _IRIS_SINDEX, _IRIS_CENTROIDS_4326

    if _IRIS_GDF_3857 is not None:
        return

    iris_3857 = iris_socio_gdf.to_crs(3857).copy()
    _IRIS_GDF_3857 = iris_3857
    _IRIS_SINDEX = iris_3857.sindex

    centroids_4326 = iris_socio_gdf.to_crs(4326).geometry.centroid
    _IRIS_CENTROIDS_4326 = pd.DataFrame(
        {
            iris_code_col: iris_socio_gdf[iris_code_col].values,
            "lat_centroid": centroids_4326.y,
            "lon_centroid": centroids_4326.x,
        }
    ).set_index(iris_code_col)


# -------------------------------------------------------------------
# STATISTIQUES SOCIO POUR UNE ZONE (liste d’IRIS)
# -------------------------------------------------------------------
def calculer_stats_zone_complet(df_zone: gpd.GeoDataFrame) -> Dict[str, Any]:
    """
    Calcule les stats socio-démographiques complètes pour une zone IRIS.
    df_zone doit contenir les colonnes :
      - POP_TOTAL
      - REVENU_MEDIAN (peut contenir des NaN)
      - AGE_0_17, ETUDIANTS_18_24, ACTIFS_25_39, AGE_40_64, AGE_65_PLUS
      - HOMMES, FEMMES
      - AGRICULTEURS, COMMERCANTS, CADRES, INTERMEDIAIRES,
        EMPLOYES, OUVRIERS, RETRAITES, AUTRES_INACTIFS
    """

    if df_zone.empty:
        return {"Population totale": 0}

    resultats: Dict[str, Any] = {}

    # Population totale
    pop_totale = df_zone["POP_TOTAL"].sum(skipna=True)
    resultats["Population totale"] = int(round(pop_totale))

    # Revenu médian pondéré par la population (en ignorant les NaN)
    if "REVENU_MEDIAN" in df_zone.columns:
        df_revenu = df_zone[["POP_TOTAL", "REVENU_MEDIAN"]].dropna(subset=["REVENU_MEDIAN"])
        if not df_revenu.empty:
            poids = df_revenu["POP_TOTAL"]
            revenus = df_revenu["REVENU_MEDIAN"]
            revenu_pond = (poids * revenus).sum() / poids.sum()
            resultats["Revenu médian pondéré (€)"] = round(float(revenu_pond), 2)
        else:
            resultats["Revenu médian pondéré (€)"] = None

    # Répartition par âge
    age_cols = ["AGE_0_17", "ETUDIANTS_18_24", "ACTIFS_25_39", "AGE_40_64", "AGE_65_PLUS"]
    if all(col in df_zone.columns for col in age_cols):
        age_totaux = df_zone[age_cols].sum(skipna=True)
        if age_totaux.sum() > 0:
            age_dist = (age_totaux / age_totaux.sum()) * 100
            resultats["Répartition par âge (%)"] = age_dist.round(1).to_dict()

    # Répartition par sexe
    if "HOMMES" in df_zone.columns and "FEMMES" in df_zone.columns:
        hommes = df_zone["HOMMES"].sum(skipna=True)
        femmes = df_zone["FEMMES"].sum(skipna=True)
        total_sexe = hommes + femmes
        if total_sexe > 0:
            resultats["Répartition par sexe (%)"] = {
                "Hommes (%)": round(hommes / total_sexe * 100, 1),
                "Femmes (%)": round(femmes / total_sexe * 100, 1),
            }

    # Répartition CSP
    csp_cols = [
        "AGRICULTEURS",
        "COMMERCANTS",
        "CADRES",
        "INTERMEDIAIRES",
        "EMPLOYES",
        "OUVRIERS",
        "RETRAITES",
        "AUTRES_INACTIFS",
    ]
    if all(col in df_zone.columns for col in csp_cols):
        csp_totaux = df_zone[csp_cols].sum(skipna=True)
        if csp_totaux.sum() > 0:
            csp_dist = (csp_totaux / csp_totaux.sum()) * 100
            resultats["Répartition par CSP (%)"] = csp_dist.round(1).to_dict()

    return resultats


# -------------------------------------------------------------------
# CALCUL D’UNE ZONE POUR UN GROUPE (IRIS centre + env) – MODE DISTANCE
# -------------------------------------------------------------------
_ZONE_CACHE_KM: Dict[Tuple[str, str, float], Tuple[List[str], Dict[str, Any]]] = {}


def _get_zone_for_group_distance(
    code_iris_centre: str,
    env_val: str,
    iris_socio_gdf: gpd.GeoDataFrame,
    env_params: Dict[str, Dict[str, Any]],
    iris_code_col: str = "CODE_IRIS",
) -> Tuple[gpd.GeoDataFrame, Dict[str, Any]]:
    """
    Calcule la zone de chalandise d'un groupe (IRIS centre + statut env)
    en utilisant un rayon en km (distance vol d'oiseau).
    Aucun appel à ORS.
    """

    _prepare_iris_index(iris_socio_gdf, iris_code_col=iris_code_col)
    global _IRIS_GDF_3857, _IRIS_SINDEX, _IRIS_CENTROIDS_4326, _ZONE_CACHE_KM

    env_val_norm = str(env_val).strip().lower()
    if env_val_norm not in env_params:
        raise ValueError(f"Env '{env_val}' non trouvé dans env_params.")

    rayon_km = float(env_params[env_val_norm].get("rayon_km", 0))
    if rayon_km <= 0:
        raise ValueError(
            f"env_params['{env_val_norm}'] doit contenir un 'rayon_km' (> 0)."
        )

    cache_key = (code_iris_centre, env_val_norm, rayon_km)
    if cache_key in _ZONE_CACHE_KM:
        codes_iris_zone, stats_zone = _ZONE_CACHE_KM[cache_key]
        iris_zone = iris_socio_gdf[iris_socio_gdf[iris_code_col].isin(codes_iris_zone)].copy()
        return iris_zone, stats_zone

    # IRIS centre en 3857 (pour buffer)
    centre_3857 = _IRIS_GDF_3857[_IRIS_GDF_3857[iris_code_col] == code_iris_centre]
    if centre_3857.empty:
        raise ValueError(f"CODE_IRIS centre '{code_iris_centre}' introuvable dans IRIS.")

    centre_geom_3857 = centre_3857.geometry.values[0]

    # Centroid centre en WGS84 (pour distances)
    centre_centroid = _IRIS_CENTROIDS_4326.loc[code_iris_centre]
    lat0 = centre_centroid["lat_centroid"]
    lon0 = centre_centroid["lon_centroid"]

    # Buffer en mètres autour de l'IRIS centre
    buffer_m = centre_geom_3857.buffer(rayon_km * 1000.0)

    # Candidats via index spatial
    idx = list(_IRIS_SINDEX.query(buffer_m))
    candidats = _IRIS_GDF_3857.iloc[idx]

    # Calcul des distances centre ↔ centroids
    candidats_codes = candidats[iris_code_col].tolist()
    centroids_sub = _IRIS_CENTROIDS_4326.loc[candidats_codes]

    distances = []
    keep_codes = []
    for code, row in centroids_sub.iterrows():
        d_km = haversine_km(lat0, lon0, row["lat_centroid"], row["lon_centroid"])
        if d_km <= rayon_km * 1.05:  # léger slack
            keep_codes.append(code)
            distances.append(d_km)

    iris_zone = iris_socio_gdf[iris_socio_gdf[iris_code_col].isin(keep_codes)].copy()
    stats_zone = calculer_stats_zone_complet(iris_zone)

    if distances:
        stats_zone["rayon_max_km"] = round(max(distances), 2)
        stats_zone["rayon_moy_km"] = round(sum(distances) / len(distances), 2)
    else:
        stats_zone["rayon_max_km"] = 0.0
        stats_zone["rayon_moy_km"] = 0.0

    stats_zone["rayon_theorique_km"] = float(rayon_km)

    # Cache
    _ZONE_CACHE_KM[cache_key] = (keep_codes, stats_zone)

    return iris_zone, stats_zone

def flatten_stats(stats: dict, prefix="") -> dict:
    """
    Aplati un dictionnaire potentiellement imbriqué :
    {'a':1, 'b':{'x':10,'y':20}} devient
    {'a':1, 'b_x':10, 'b_y':20}
    """

    out = {}
    for k, v in stats.items():
        col = f"{prefix}{k}".replace(" ", "_").replace("(", "").replace(")", "")
        if isinstance(v, dict):
            for kk, vv in v.items():
                col2 = f"{col}_{kk}".replace(" ", "_").replace("(", "").replace(")", "")
                out[col2] = vv
        else:
            out[col] = v
    return out


# -------------------------------------------------------------------
# CALCUL GLOBAL POUR TOUS LES RELAIS
# -------------------------------------------------------------------
def compute_zones_for_relais(
    points_gdf: gpd.GeoDataFrame,
    iris_socio_gdf: gpd.GeoDataFrame,
    env_params: Dict[str, Dict[str, Any]],
    col_env: str = "Statut",
    iris_code_col: str = "CODE_IRIS",
    use_tqdm: bool = True,
) -> Dict[str, Any]:
    """
    Calcule les zones de chalandise pour un ensemble de relais,
    en définissant chaque zone comme un rayon en km autour de l'IRIS centre.
    """

    # S'assurer du CRS
    if points_gdf.crs is None:
        points_gdf.set_crs(epsg=4326, inplace=True)
    else:
        points_gdf = points_gdf.to_crs(4326)

    # Spatial join pour récupérer l’IRIS de chaque relais
    print("🧩 Attribution des IRIS aux relais (spatial join)...")
    iris_geom = iris_socio_gdf[[iris_code_col, "geometry"]].copy()

    # S'assurer aussi que les IRIS sont dans le même CRS que les points
    if iris_geom.crs != points_gdf.crs:
        iris_geom = iris_geom.to_crs(points_gdf.crs)

    points_with_iris = gpd.sjoin(
        points_gdf,
        iris_geom,
        how="left",
        predicate="within",
    )

    points_with_iris = points_with_iris.rename(columns={iris_code_col: "code_iris_point"})

    # --- Diagnostic des points sans IRIS ---
    mask_na = points_with_iris["code_iris_point"].isna()
    n_na = mask_na.sum()
    if n_na > 0:
        print(f"⚠️ {n_na} relais n'ont pas d'IRIS associé (en dehors des polygones).")

        sans_iris = points_with_iris[mask_na].copy()
        cols_diag = [c for c in [
            "Code agence", "Nom d'enseigne", "Adresse", "Commune",
            "Code postal", "Latitude", "Longitude"
        ] if c in sans_iris.columns]

        print("=== Aperçu des points sans IRIS ===")
        print(sans_iris[cols_diag].head(20))

        os.makedirs("output", exist_ok=True)
        sans_iris[cols_diag].to_excel("output/relais_sans_iris.xlsx", index=False)
        print("📁 Exporté dans output/relais_sans_iris.xlsx")

    # On supprime ensuite les points sans IRIS
    points_with_iris = points_with_iris.dropna(subset=["code_iris_point"])

    # Groupes (IRIS centre + statut)
    groups = list(points_with_iris.groupby(["code_iris_point", col_env]))

    zones_summary_rows: List[Dict[str, Any]] = []
    iris_zone_rows: List[gpd.GeoDataFrame] = []

    iterator = tqdm(groups, desc="Calcul des zones", total=len(groups)) if use_tqdm else groups

    for (code_iris_centre, env_val), group in iterator:
        iris_zone, stats_zone = _get_zone_for_group_distance(
            code_iris_centre=code_iris_centre,
            env_val=env_val,
            iris_socio_gdf=iris_socio_gdf,
            env_params=env_params,
            iris_code_col=iris_code_col,
        )

        iris_zone = iris_zone.copy()
        iris_zone["code_iris_centre"] = code_iris_centre
        iris_zone["env"] = env_val
        iris_zone_rows.append(iris_zone)

        # Une ligne par point relais, avec les stats de la zone
        for _, row in group.iterrows():
            d = {
                "id_point": row.get("id_point"),
                "nom_point": row.get("nom_point"),
                "adresse_point": row.get("Adresse", None),
                "commune_point": row.get("Commune", None),
                "latitude": row.geometry.y,
                "longitude": row.geometry.x,
                "statut_point": row.get(col_env),
                "code_iris_centre": code_iris_centre,
            }
            # flatten stats_zone
            flat_stats = flatten_stats(stats_zone)
            for k, v in flat_stats.items():
                d[k] = v
            zones_summary_rows.append(d)

    zones_df = pd.DataFrame(zones_summary_rows)

    # IRIS couverts : une ligne par IRIS, avec stats socio + nb zones
    print("📊 Agrégation par IRIS couvert...")
    iris_zone_all = pd.concat(iris_zone_rows, ignore_index=True)

    # Nb de zones (tous statuts confondus)
    counts_total = (
        iris_zone_all.groupby(iris_code_col)["code_iris_centre"]
        .nunique()
        .rename("nb_zones_total")
    )

    # Nb de zones par type d'environnement (tes libellés)
    env_counts = (
        iris_zone_all
        .groupby([iris_code_col, "env"])["code_iris_centre"]
        .nunique()
        .unstack(fill_value=0)
    )
    # Colonnes du type nb_zones_Com > 200 m habts, etc.
    env_counts.columns = [f"nb_zones_{str(c)}" for c in env_counts.columns]

    # Base IRIS : toutes les colonnes socio
    base_iris = (
        iris_socio_gdf
        .drop(columns=["geometry"])
        .drop_duplicates(subset=[iris_code_col])
        .set_index(iris_code_col)
    )

    iris_agg_df = base_iris.join(counts_total, how="left")
    iris_agg_df = iris_agg_df.join(env_counts, how="left")

    iris_agg_df["nb_zones_total"] = iris_agg_df["nb_zones_total"].fillna(0).astype(int)
    for c in env_counts.columns:
        iris_agg_df[c] = iris_agg_df[c].fillna(0).astype(int)

    # Type_env_iris = catégorie dominante (celle avec le plus de zones)
    def _type_env(row):
        if row["nb_zones_total"] == 0:
            return "Non couverte"
        env_cols = [c for c in row.index if c.startswith("nb_zones_") and c != "nb_zones_total"]
        if not env_cols:
            return "Non couverte"
        sub = row[env_cols]
        col_max = sub.idxmax()           # ex: "nb_zones_Com > 200 m habts"
        return col_max.replace("nb_zones_", "")

    iris_agg_df["type_env_iris"] = iris_agg_df.apply(_type_env, axis=1)

    # Ne garder que les IRIS effectivement couverts
    iris_agg_df = iris_agg_df[iris_agg_df["nb_zones_total"] > 0].reset_index()


    # Stats globales sur tous les IRIS couverts
    iris_couverts = iris_agg_df[iris_code_col].unique()
    iris_sub = iris_socio_gdf[iris_socio_gdf[iris_code_col].isin(iris_couverts)].copy()
    stats_globales = calculer_stats_zone_complet(iris_sub)

    return {
        "zones_df": zones_df,
        "iris_agg_df": iris_agg_df,
        "stats_globales": stats_globales,
    }


# -------------------------------------------------------------------
# MAIN POUR TESTER EN LOCAL
# -------------------------------------------------------------------
if __name__ == "__main__":
    iris_gdf = load_iris_data()

    relais_file = INPUTS_DIR / "relais_colis.xlsx"
    points_gdf = load_relais_excel(relais_file)

    # Paramètres de rayon par type de zone (en km)
    env_params = {
    "com > 200 m habts":      {"rayon_km": 1.0},
    "com < 200 m habts":      {"rayon_km": 2.0},
    "com < 50 m habts":       {"rayon_km": 3.0},
    "com < 10 m habts":       {"rayon_km": 5.0},
    "com rurale > 2 000 habts":  {"rayon_km": 7.0},
    "com rurale < 2 000 m habts": {"rayon_km": 9.0},
    }


    res = compute_zones_for_relais(
        points_gdf=points_gdf,
        iris_socio_gdf=iris_gdf,
        env_params=env_params,
        col_env="Statut",
        use_tqdm=True,
    )

    zones_df = res["zones_df"]
    iris_agg_df = res["iris_agg_df"]
    stats_globales = res["stats_globales"]

    out_path = OUTPUTS_DIR / "resultats_zones_km.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        zones_df.to_excel(writer, sheet_name="Zones_relais", index=False)
        iris_agg_df.to_excel(writer, sheet_name="IRIS_couvertes", index=False)
        if stats_globales:
            flat_stats_globales = flatten_stats(stats_globales)
            pd.DataFrame([flat_stats_globales]).to_excel(
                writer, sheet_name="Stats_globales", index=False
            )


    print(f"✅ Résultats exportés dans {out_path}")

    # ---------------------------------------------------------
    # 🗺️ Construction de la carte Folium des zones de chalandise
    # ---------------------------------------------------------

    print("🗺️ Construction de la carte Folium...")

    # Colonnes dispo pour la jointure carte
    base_cols = ["CODE_IRIS", "nb_zones_total", "type_env_iris"]
    cols_dispo = [c for c in base_cols if c in iris_agg_df.columns]

    # On ne garde que les IRIS couverts
    iris_map_gdf = iris_gdf.merge(
        iris_agg_df[cols_dispo],
        on="CODE_IRIS",
        how="right",  # right = on garde seulement les IRIS couverts
    )

    # S'assurer du CRS en WGS84 pour Folium
    iris_map_gdf = iris_map_gdf.to_crs(4326)

    # Centre de la carte = France
    m = folium.Map(location=[46.5, 2.5], zoom_start=6, tiles="cartodbpositron")

    # Style des polygones en fonction du type d'environnement (catégorie dominante)
    def style_function(feature):
        env = feature["properties"].get("type_env_iris")

        color_map = {
            "Com > 200 m habts":          "#d73027",
            "Com < 200 m habts":          "#fc8d59",
            "Com < 50 m habts":           "#fee08b",
            "Com < 10 m habts":           "#d9ef8b",
            "Com rurale > 2 000 habts":   "#91bfdb",
            "Com rurale < 2 000 m habts": "#4575b4",
            "Non couverte":               "#bdbdbd",
        }
        color = color_map.get(env, "#bdbdbd")

        return {
            "fillColor": color,
            "color": color,
            "weight": 0.5,
            "fillOpacity": 0.4,
        }

    # Tooltip sur les IRIS
    tooltip_fields = [c for c in ["CODE_IRIS", "type_env_iris", "nb_zones_total"] if c in iris_map_gdf.columns]
    tooltip = folium.GeoJsonTooltip(
        fields=tooltip_fields,
        aliases=["IRIS", "Type environnement", "Nb zones couvrant l'IRIS"][: len(tooltip_fields)],
        localize=True,
        sticky=False,
    )

    folium.GeoJson(
        iris_map_gdf,
        style_function=style_function,
        tooltip=tooltip,
        name="IRIS couverts",
    ).add_to(m)

    # S'assurer que les points sont aussi en WGS84 pour la carte
    if points_gdf.crs is None:
        points_plot = points_gdf.set_crs(4326)
    else:
        points_plot = points_gdf.to_crs(4326)

    # Ajout des relais comme petits points
    for _, row in points_plot.iterrows():
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=3,
            color="#08519c",
            fill=True,
            fill_opacity=0.9,
            popup=f"{row.get('id_point', '')} - {row.get('nom_point', '')}",
        ).add_to(m)

    folium.LayerControl().add_to(m)

    # Sauvegarde
    os.makedirs("output", exist_ok=True)
    m.save("output/zones_chalandise.html")
    print("✅ Carte Folium exportée dans output/zones_chalandise.html")


    # Export HTML
    map_path = OUTPUTS_DIR / "resultats_zones_km.html"
    m.save(str(map_path))
    print(f"🗺️ Carte Folium exportée dans {map_path}")

