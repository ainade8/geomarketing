import math
import tempfile
import io
import requests

import pandas as pd
import streamlit as st

from test import calcul_principal  # ton module métier


# ---------- Utilitaires communs ----------

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Distance en km entre 2 points (latitude/longitude en degrés).
    """
    R = 6371  # km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


@st.cache_data(show_spinner=False)
def directions_google(origin: str, destination: str, mode: str = "driving"):
    """
    Appelle l'API Google Directions pour obtenir un itinéraire.
    mode: "driving" ou "transit"
    Retourne un dict avec distance_km, duration_min, start/end address & coords,
    + status brut et éventuel message d'erreur pour debug.
    """
    api_key = st.secrets.get("GOOGLE_API_KEY", None)
    if api_key is None:
        raise ValueError("La clé GOOGLE_API_KEY n'est pas définie dans les secrets Streamlit.")

    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "key": api_key
    }

    resp = requests.get(url, params=params)
    data = resp.json()

    status = data.get("status")
    error_message = data.get("error_message", None)

    if status != "OK" or not data.get("routes"):
        return {
            "ok": False,
            "status": status,
            "error_message": error_message,
        }

    leg = data["routes"][0]["legs"][0]

    distance_m = leg["distance"]["value"]       # mètres
    duration_s = leg["duration"]["value"]       # secondes
    start_address = leg["start_address"]
    end_address = leg["end_address"]
    start_location = leg["start_location"]      # {"lat": ..., "lng": ...}
    end_location = leg["end_location"]

    return {
        "ok": True,
        "status": status,
        "error_message": error_message,
        "distance_km": distance_m / 1000.0,
        "duration_min": duration_s / 60.0,
        "start_address": start_address,
        "end_address": end_address,
        "start_location": start_location,
        "end_location": end_location,
    }


@st.cache_data(show_spinner=False)
def geocode_google(address: str):
    """
    Géocode une adresse via l'API Google Geocoding.
    Retourne (lat, lon) ou (None, None) si échec.
    """
    api_key = st.secrets.get("GOOGLE_API_KEY", None)
    if api_key is None:
        raise ValueError("La clé GOOGLE_API_KEY n'est pas définie dans les secrets Streamlit.")

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": api_key
    }

    resp = requests.get(url, params=params)
    data = resp.json()

    status = data.get("status")
    if status != "OK" or not data.get("results"):
        return None, None

    location = data["results"][0]["geometry"]["location"]
    return location["lat"], location["lng"]


# ---------- Sous-app 1 : Calcul principal ----------

def app_calcul_principal():
    st.header("🧮 Outil 1 – Calcul principal")

    # Inputs numériques
    param1 = st.number_input("Paramètre 1", value=1.0)
    param2 = st.number_input("Paramètre 2", value=2.0)

    # Upload d’un fichier Excel (optionnel)
    uploaded_file = st.file_uploader(
        "Importer un fichier Excel (optionnel)",
        type=["xlsx", "xls"],
        key="file_calcul_principal"
    )

    if st.button("Lancer le calcul", key="btn_calcul_principal"):
        fichier_path = None

        # Si un fichier est uploadé, on le sauvegarde en temporaire
        if uploaded_file is not None:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp.write(uploaded_file.read())
                fichier_path = tmp.name

        # Appel de ta fonction principale
        result = calcul_principal(param1, param2, fichier_path)

        st.subheader("Résultat")
        if isinstance(result, pd.DataFrame):
            st.dataframe(result)
        else:
            st.write(result)


# ---------- Sous-app 2 : Itinéraire entre 2 adresses ----------

def app_distance_adresses():
    st.header("🗺️ Outil 2 – Itinéraire entre 2 adresses (Google Maps)")

    st.markdown("**Adresse de départ (A)**")
    addr1 = st.text_input(
        "Adresse A",
        value="36 Rue de la Boétie, 75008 Paris",
        key="addrA"
    )

    st.markdown("**Adresse d’arrivée (B)**")
    addr2 = st.text_input(
        "Adresse B",
        value="Gare de Lyon, Paris",
        key="addrB"
    )

    mode_label = st.selectbox(
        "Mode de transport",
        ["🚗 Voiture", "🚆 Transports en commun"],
        index=0,
        key="mode_select"
    )

    # Traduction label -> mode API Google
    mode_api = "driving" if "Voiture" in mode_label else "transit"

    if st.button("Calculer l’itinéraire", key="btn_distance_adresses"):
        if not addr1 or not addr2:
            st.error("Merci de renseigner les deux adresses.")
            return

        try:
            with st.spinner(f"Appel à Google Directions ({mode_label})..."):
                res = directions_google(addr1, addr2, mode=mode_api)
        except ValueError as e:
            st.error(str(e))
            return

        if not res.get("ok"):
            status = res.get("status")
            error_msg = res.get("error_message", "(aucun message)")

            # Cas particulier : pas de transports en commun dispo
            if mode_api == "transit" and status == "ZERO_RESULTS":
                st.warning(
                    "Aucun itinéraire en transports en commun n’a été trouvé "
                    "entre ces deux adresses (ZERO_RESULTS)."
                )
            else:
                st.error(
                    f"Impossible de récupérer un itinéraire.\n\n"
                    f"Status Google : {status}\n"
                    f"Message : {error_msg}"
                )
            return

        dist_km = res["distance_km"]
        dur_min = res["duration_min"]
        start_address = res["start_address"]
        end_address = res["end_address"]
        start_loc = res["start_location"]
        end_loc = res["end_location"]

        # Distance "vol d’oiseau" en bonus
        dist_crow = haversine_distance(
            start_loc["lat"], start_loc["lng"],
            end_loc["lat"], end_loc["lng"]
        )

        if mode_api == "driving":
            mode_txt = "en voiture"
            icon = "🚗"
        else:
            mode_txt = "en transports en commun"
            icon = "🚆"

        st.success(
            f"{icon} Distance {mode_txt} : **{dist_km:.2f} km**  "
            f"(~ **{dur_min:.0f} minutes** selon Google)"
        )
        st.info(
            f"Distance approximative \"vol d’oiseau\" : **{dist_crow:.2f} km**"
        )

        with st.expander("Détails de l’itinéraire et des coordonnées"):
            st.write("**Adresse de départ (interprétée par Google)**")
            st.write(start_address)
            st.write(f"→ lat = {start_loc['lat']:.6f}, lon = {start_loc['lng']:.6f}")

            st.write("**Adresse d’arrivée (interprétée par Google)**")
            st.write(end_address)
            st.write(f"→ lat = {end_loc['lat']:.6f}, lon = {end_loc['lng']:.6f}")


# ---------- Sous-app 3 : Géocoder un fichier d'adresses ----------

def app_geocode_excel():
    st.header("📄 Outil 3 – Convertir un Excel d’adresses en coordonnées")

    st.write(
        "1. Charge un fichier Excel contenant une colonne d’adresses\n"
        "2. Indique le nom de cette colonne (par ex. `Adresse` ou `Adresses`)\n"
        "3. L’outil ajoute automatiquement deux colonnes : **Latitude** et **Longitude**"
    )

    uploaded_file = st.file_uploader(
        "Importer un fichier Excel",
        type=["xlsx", "xls"],
        key="file_geocode_excel"
    )

    col_name = st.text_input(
        "Nom de la colonne contenant les adresses",
        value="Adresse",
        key="addr_column_name"
    )

    if st.button("Lancer la conversion", key="btn_geocode_excel"):
        if uploaded_file is None:
            st.error("Merci d'importer un fichier Excel.")
            return

        if not col_name:
            st.error("Merci d'indiquer le nom de la colonne d'adresses.")
            return

        try:
            df = pd.read_excel(uploaded_file)
        except Exception as e:
            st.error(f"Erreur lors de la lecture du fichier Excel : {e}")
            return

        if col_name not in df.columns:
            st.error(
                f"La colonne '{col_name}' n'existe pas dans le fichier. "
                f"Colonnes disponibles : {list(df.columns)}"
            )
            return

        # On prépare les colonnes Latitude / Longitude
        df["Latitude"] = None
        df["Longitude"] = None

        # Boucle de géocodage
        addresses = df[col_name].astype(str).fillna("")
        total = len(df)

        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, addr in enumerate(addresses.index):
            address_str = str(df.at[addr, col_name])
            if address_str.strip() == "":
                lat, lon = None, None
            else:
                lat, lon = geocode_google(address_str)

            df.at[addr, "Latitude"] = lat
            df.at[addr, "Longitude"] = lon

            progress = (idx + 1) / total
            progress_bar.progress(progress)
            status_text.text(f"Géocodage : {idx + 1}/{total} lignes traitées")

        progress_bar.empty()
        status_text.empty()

        st.success("Conversion terminée ✅")
        st.subheader("Aperçu du fichier géocodé")
        st.dataframe(df.head(20))

        # Préparer un fichier Excel en mémoire pour le téléchargement
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Geocoded")
        output.seek(0)

        st.download_button(
            label="📥 Télécharger le fichier Excel avec coordonnées",
            data=output,
            file_name="adresses_geocodees.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_geocoded_excel"
        )

def app_matrice_agences():
    st.header("🏢 Outil 4 – Matrice de trajets entre agences")

    st.write(
        "1. Charge un fichier Excel avec une colonne d’adresses\n"
        "2. Optionnel : indique une colonne de noms d’agence\n"
        "3. Choisis le mode (voiture, transports, ou le plus rapide)\n"
        "4. L’outil calcule tous les trajets entre toutes les agences (y compris agence → elle-même)\n"
        "5. Affiche une carte des agences géolocalisées"
    )

    uploaded_file = st.file_uploader(
        "Importer un fichier Excel d’agences",
        type=["xlsx", "xls"],
        key="file_matrice_agences"
    )

    col_addr = st.text_input(
        "Nom de la colonne contenant les adresses",
        value="Adresse",
        key="addr_col_matrice"
    )

    has_name = st.checkbox(
        "Mon fichier contient une colonne Nom d’agence",
        value=True,
        key="has_name_matrice"
    )

    col_name = None
    if has_name:
        col_name = st.text_input(
            "Nom de la colonne contenant le nom d’agence",
            value="Nom_agence",
            key="name_col_matrice"
        )

    mode_label = st.selectbox(
        "Mode de calcul",
        [
            "🚗 Voiture",
            "🚆 Transports en commun",
            "⚡ Le plus rapide (voiture ou transports)"
        ],
        index=0,
        key="mode_matrice"
    )

    if "Voiture" in mode_label:
        global_mode = "driving_only"
    elif "Transports" in mode_label:
        global_mode = "transit_only"
    else:
        global_mode = "fastest"

    if st.button("Lancer le calcul de la matrice", key="btn_matrice_agences"):
        if uploaded_file is None:
            st.error("Merci d’importer un fichier Excel.")
            return

        if not col_addr:
            st.error("Merci d’indiquer le nom de la colonne d’adresses.")
            return

        try:
            df = pd.read_excel(uploaded_file)
        except Exception as e:
            st.error(f"Erreur lors de la lecture du fichier : {e}")
            return

        if col_addr not in df.columns:
            st.error(
                f"La colonne d’adresses '{col_addr}' n’existe pas. "
                f"Colonnes disponibles : {list(df.columns)}"
            )
            return

        if has_name and (col_name not in df.columns):
            st.error(
                f"La colonne de noms '{col_name}' n’existe pas. "
                f"Colonnes disponibles : {list(df.columns)}"
            )
            return

        # Petite table des agences (adresses + label)
        work = df[[col_addr]].copy()
        if has_name:
            work[col_name] = df[col_name]
            work["Label"] = df[col_name].astype(str)
        else:
            work["Label"] = df[col_addr].astype(str)

        work = work.reset_index(drop=True)
        n = len(work)

        if n == 0:
            st.error("Aucune ligne à traiter dans le fichier.")
            return

        st.info(f"{n} agences détectées. Calcul de {n*n} paires (y compris agence → elle-même).")

        # 🔹 Étape 1 : géocoder les agences une fois pour la carte
        work["Latitude"] = None
        work["Longitude"] = None

        st.write("Géocodage des agences pour affichage sur la carte...")
        progress_geo = st.progress(0)
        for i in range(n):
            addr = str(work.at[i, col_addr])
            lat, lon = geocode_google(addr)
            work.at[i, "Latitude"] = lat
            work.at[i, "Longitude"] = lon
            progress_geo.progress((i + 1) / n)
        progress_geo.empty()

        # Filtrer celles qui ont bien des coordonnées
        geo_ok = work.dropna(subset=["Latitude", "Longitude"]).copy()

        if len(geo_ok) == 0:
            st.warning("Aucune agence n’a pu être géocodée, carte non affichée.")
        else:
            st.subheader("Carte des agences géocodées")
            map_df = geo_ok.rename(columns={"Latitude": "lat", "Longitude": "lon"})
            st.map(map_df[["lat", "lon"]])  # carte simple avec tous les points

        # 🔹 Étape 2 : calcul de la matrice des trajets
        rows = []
        total_pairs = n * n
        done = 0
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i in range(n):
            origin_label = work.at[i, "Label"]
            origin_addr = work.at[i, col_addr]

            for j in range(n):
                dest_label = work.at[j, "Label"]
                dest_addr = work.at[j, col_addr]

                # Toujours inclure les paires i == j (distance 0, temps 0)
                if i == j:
                    rows.append({
                        "Agence_origine": origin_label,
                        "Agence_destination": dest_label,
                        "Adresse_origine": origin_addr,
                        "Adresse_destination": dest_addr,
                        "Mode": "Même point" if global_mode == "fastest"
                                else ("Voiture" if global_mode == "driving_only" else "Transports"),
                        "Distance_km": 0.0,
                        "Duree_min": 0.0,
                    })
                else:
                    if global_mode == "driving_only":
                        res = directions_google(origin_addr, dest_addr, mode="driving")
                        if res.get("ok"):
                            rows.append({
                                "Agence_origine": origin_label,
                                "Agence_destination": dest_label,
                                "Adresse_origine": origin_addr,
                                "Adresse_destination": dest_addr,
                                "Mode": "Voiture",
                                "Distance_km": res["distance_km"],
                                "Duree_min": res["duration_min"],
                            })
                        else:
                            rows.append({
                                "Agence_origine": origin_label,
                                "Agence_destination": dest_label,
                                "Adresse_origine": origin_addr,
                                "Adresse_destination": dest_addr,
                                "Mode": "Voiture",
                                "Distance_km": None,
                                "Duree_min": None,
                            })

                    elif global_mode == "transit_only":
                        res = directions_google(origin_addr, dest_addr, mode="transit")
                        if res.get("ok"):
                            rows.append({
                                "Agence_origine": origin_label,
                                "Agence_destination": dest_label,
                                "Adresse_origine": origin_addr,
                                "Adresse_destination": dest_addr,
                                "Mode": "Transports",
                                "Distance_km": res["distance_km"],
                                "Duree_min": res["duration_min"],
                            })
                        else:
                            rows.append({
                                "Agence_origine": origin_label,
                                "Agence_destination": dest_label,
                                "Adresse_origine": origin_addr,
                                "Adresse_destination": dest_addr,
                                "Mode": "Transports",
                                "Distance_km": None,
                                "Duree_min": None,
                            })

                    else:  # fastest
                        res_drive = directions_google(origin_addr, dest_addr, mode="driving")
                        res_transit = directions_google(origin_addr, dest_addr, mode="transit")

                        best_mode = None
                        best_dist = None
                        best_dur = None

                        if res_drive.get("ok"):
                            best_mode = "Voiture"
                            best_dist = res_drive["distance_km"]
                            best_dur = res_drive["duration_min"]

                        if res_transit.get("ok"):
                            if best_dur is None or res_transit["duration_min"] < best_dur:
                                best_mode = "Transports"
                                best_dist = res_transit["distance_km"]
                                best_dur = res_transit["duration_min"]

                        rows.append({
                            "Agence_origine": origin_label,
                            "Agence_destination": dest_label,
                            "Adresse_origine": origin_addr,
                            "Adresse_destination": dest_addr,
                            "Mode": best_mode,
                            "Distance_km": best_dist,
                            "Duree_min": best_dur,
                        })

                done += 1
                progress_bar.progress(done / total_pairs)
                status_text.text(f"Paires calculées : {done}/{total_pairs}")

        progress_bar.empty()
        status_text.empty()

        result_df = pd.DataFrame(rows)

        st.success("Matrice de trajets calculée ✅")
        st.subheader("Aperçu")
        st.dataframe(result_df.head(50))

        # Export Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            result_df.to_excel(writer, index=False, sheet_name="Matrice_trajets")
        output.seek(0)

        st.download_button(
            label="📥 Télécharger la matrice des trajets (Excel)",
            data=output,
            file_name="matrice_trajets_agences.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_matrice_agences"
        )




# ---------- App principale avec menu ----------

def main():
    st.title("🌍 Geomarketing – Suite d’outils")

    st.sidebar.title("Menu")
    page = st.sidebar.radio(
        "Choisir une application",
        [
            "🏠 Accueil",
            "🧮 Calcul principal",
            "🗺️ Itinéraire entre 2 adresses",
            "📄 Géocoder un fichier d’adresses",
            "🏢 Matrice de trajets entre agences",
        ]
    )

    if page == "🏠 Accueil":
        st.subheader("Bienvenue dans Geomarketing 👋")
        st.write(
            "Choisis un outil dans le menu de gauche :\n"
            "- **🧮 Calcul principal** : outil avec paramètres + fichier Excel\n"
            "- **🗺️ Itinéraire entre 2 adresses** : distance & durée en voiture ou transports en commun\n"
            "- **📄 Géocoder un fichier d’adresses** : ajoute Latitude/Longitude à un Excel\n"
            "- **🏢 Matrice de trajets entre agences** : calcule tous les trajets entre agences d’un fichier Excel"
        )

    elif page == "🧮 Calcul principal":
        app_calcul_principal()

    elif page == "🗺️ Itinéraire entre 2 adresses":
        app_distance_adresses()

    elif page == "📄 Géocoder un fichier d’adresses":
        app_geocode_excel()

    elif page == "🏢 Matrice de trajets entre agences":
        app_matrice_agences()


if __name__ == "__main__":
    main()

