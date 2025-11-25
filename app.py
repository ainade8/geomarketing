import streamlit as st
import tempfile
import pandas as pd
from test import calcul_principal

st.title("Mon super outil en ligne 🧮")

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