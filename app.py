import streamlit as st
import tempfile
import pandas as pd
import math

from test import calcul_principal  # ton module existant


# ---------- Sous-app 1 : ton outil existant ----------
def app_calcul_principal():
    st.header("🧮 Outil 1 – Calcul principal")

    # -- Inputs numériques
    param1 = st.number_input("Paramètre 1", value=1.0)
    param2 = st.number_input("Paramètre 2", value=2.0)

    # -- Upload d’un fichier Excel (optionnel)
    uploaded_file = st.file_uploader("Importer un fichier Excel (optionnel)", type=["xlsx", "xls"])

    # Bouton d'exécution
    if st.button("Lancer le calcul"):
        fichier_path = None

        # Si un fichier est uploadé, on le sauvegarde en temporaire
        if uploaded_file is not None:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp.write(uploaded_file.read())
                fichier_path = tmp.name

        # Appel de ta fonction principale
        result = calcul_principal(param1, param2, fichier_path)

        st.subheader("Résultat")
        # Gestion simple de différents types de retour
        if isinstance(result, pd.DataFrame):
            st.dataframe(result)
        else:
            st.write(result)


# ---------- Sous-app 2 : calcul de distance entre 2 points ----------
def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Distance en km entre 2 points (latitude/longitude en degrés)
    """
    R = 6371  # rayon de la Terre en km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def app_distance():
    st.header("📍 Outil 2 – Distance entre 2 points")

    st.markdown("**Coordonnées du point A**")
    lat1 = st.number_input("Latitude A", value=48.8566, format="%.6f")
    lon1 = st.number_input("Longitude A", value=2.3522, format="%.6f")

    st.markdown("**Coordonnées du point B**")
    lat2 = st.number_input("Latitude B", value=45.7640, format="%.6f")
    lon2 = st.number_input("Longitude B", value=4.8357, format="%.6f")

    if st.button("Calculer la distance"):
        dist_km = haversine_distance(lat1, lon1, lat2, lon2)
        st.success(f"Distance approximative : **{dist_km:.2f} km**")


# ---------- App principale avec menu ----------
def main():
    st.title("🌍 Geomarketing – Suite d’outils")

    st.sidebar.title("Menu")
    page = st.sidebar.radio(
        "Choisir une application",
        ["🏠 Accueil", "🧮 Calcul principal", "📍 Distance entre 2 points"]
    )

    if page == "🏠 Accueil":
        st.subheader("Bienvenue dans Geomarketing 👋")
        st.write(
            "Choisis un outil dans le menu de gauche :\n"
            "- **🧮 Calcul principal** : ton outil avec Excel + paramètres\n"
            "- **📍 Distance entre 2 points** : calcul de distances en km"
        )

    elif page == "🧮 Calcul principal":
        app_calcul_principal()

    elif page == "📍 Distance entre 2 points":
        app_distance()


if __name__ == "__main__":
    main()

    