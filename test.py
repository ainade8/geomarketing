def calcul_principal(param1: float, param2: float, fichier_excel_path: str | None = None):
    """
    Ta logique principale ici.
    Retourne soit un nombre, soit un dict, soit un dataframe, etc.
    """
    # Exemple très simple
    result = param1 + param2

    # Si tu utilises un fichier Excel :
    if fichier_excel_path is not None:
        import pandas as pd
        df = pd.read_excel(fichier_excel_path)
        # faire des trucs avec df...
        # result = ...

    return result
