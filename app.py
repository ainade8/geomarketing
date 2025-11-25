import math
import tempfile
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
        # Pour transit, Google prend "now" par défaut si pas de departure_time
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


# ---------- Sous-app 2 : Distance entre 2 adresses (voiture / transports) ----------

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


# ---------- App principale avec menu ----------

def main():
    st.title("🌍 Geomarketing – Suite d’outils")

    st.sidebar.title("Menu")
    page = st.sidebar.radio(
        "Choisir une application",
        ["🏠 Accueil", "🧮 Calcul principal", "🗺️ Itinéraire entre 2 adresses"]
    )

    if page == "🏠 Accueil":
        st.subheader("Bienvenue dans Geomarketing 👋")
        st.write(
            "Choisis un outil dans le menu de gauche :\n"
            "- **🧮 Calcul principal** : outil avec paramètres + fichier Excel\n"
            "- **🗺️ Itinéraire entre 2 adresses** : distance et durée en voiture ou en transports en commun\n"
        )

    elif page == "🧮 Calcul principal":
        app_calcul_principal()

    elif page == "🗺️ Itinéraire entre 2 adresses":
        app_distance_adresses()


if __name__ == "__main__":
    main()

