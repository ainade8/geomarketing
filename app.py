import math
import tempfile
import requests

import pandas as pd
import streamlit as st

from test import calcul_principal  # ton module métier


# ---------- Utilitaires communs ----------

@st.cache_data(show_spinner=False)
def geocode_google(address: str):
    """
    Géocode une adresse via l'API Google Geocoding.
    Retourne (lat, lon) ou None si échec.
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

    # 🔍 DEBUG TEMPORAIRE
    st.write("DEBUG status Google:", data.get("status"))
    st.write("DEBUG message:", data.get("error_message", "(aucun)"))

    if data.get("status") != "OK" or not data.get("results"):
        return None

    location = data["results"][0]["geometry"]["location"]
    return (location["lat"], location["lng"])


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Distance en km entre 2 points (latitude/longitude en degrés).
    """
    R = 6371  # rayon de la Terre en km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


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


# ---------- Sous-app 2 : Distance entre 2 adresses (Google Maps) ----------

def app_distance_adresses():
    st.header("📍 Outil 2 – Distance entre 2 adresses (Google Maps)")

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

    if st.button("Calculer la distance", key="btn_distance_adresses"):
        if not addr1 or not addr2:
            st.error("Merci de renseigner les deux adresses.")
            return

        try:
            with st.spinner("Géocodage des adresses via Google..."):
                coords1 = geocode_google(addr1)
                coords2 = geocode_google(addr2)
        except ValueError as e:
            st.error(str(e))
            return

        if coords1 is None:
            st.error("Impossible de géocoder l'adresse A. Essaie d'ajouter la ville / le pays.")
            return
        if coords2 is None:
            st.error("Impossible de géocoder l'adresse B. Essaie d'ajouter la ville / le pays.")
            return

        lat1, lon1 = coords1
        lat2, lon2 = coords2

        dist_km = haversine_distance(lat1, lon1, lat2, lon2)

        st.success(f"Distance approximative (vol d’oiseau) : **{dist_km:.2f} km**")

        with st.expander("Détails des coordonnées"):
            st.write(f"Adresse A : {addr1}")
            st.write(f"→ lat = {lat1:.6f}, lon = {lon1:.6f}")
            st.write(f"Adresse B : {addr2}")
            st.write(f"→ lat = {lat2:.6f}, lon = {lon2:.6f}")


# ---------- App principale avec menu ----------

def main():
    st.title("🌍 Geomarketing – Suite d’outils")

    st.sidebar.title("Menu")
    page = st.sidebar.radio(
        "Choisir une application",
        ["🏠 Accueil", "🧮 Calcul principal", "📍 Distance entre 2 adresses"]
    )

    if page == "🏠 Accueil":
        st.subheader("Bienvenue dans Geomarketing 👋")
        st.write(
            "Choisis un outil dans le menu de gauche :\n"
            "- **🧮 Calcul principal** : outil avec paramètres + fichier Excel\n"
            "- **📍 Distance entre 2 adresses** : calcul de distance en km via Google Maps"
        )

    elif page == "🧮 Calcul principal":
        app_calcul_principal()

    elif page == "📍 Distance entre 2 adresses":
        app_distance_adresses()


if __name__ == "__main__":
    main()

