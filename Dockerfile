FROM python:3.11-slim

# Pour éviter les fichiers .pyc et buffer
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Installer les dépendances système pour GeoPandas / GDAL / Fiona / PROJ
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libspatialindex-dev \
    libgeos-dev \
    proj-bin \
    proj-data \
    libproj-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copier le fichier des dépendances et installer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste du code
COPY . .

# Streamlit écoute sur ce port
ENV PORT=8501

EXPOSE 8501

# Commande de lancement
CMD ["bash", "-c", "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0"]
