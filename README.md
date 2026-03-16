# Docker Cloud App

FastAPI-App deployed auf Google Cloud Run via GitHub Actions.

## Projektstruktur

```
docker_cloud/
├── .github/workflows/deploy.yml   # CI/CD Pipeline
├── app/main.py                    # FastAPI Application
├── Dockerfile
├── requirements.txt
├── .gitignore
└── .dockerignore
```

## Voraussetzungen

- [Google Cloud Account](https://console.cloud.google.com/) mit Billing
- [gcloud CLI](https://cloud.google.com/sdk/docs/install)
- [GitHub Account](https://github.com)
- Docker (lokal zum Testen)

## Setup – Schritt für Schritt

### 1. Google Cloud Projekt erstellen

```bash
# Einloggen
gcloud auth login

# Projekt erstellen (ersetze DEIN-PROJEKT-ID)
gcloud projects create DEIN-PROJEKT-ID
gcloud config set project DEIN-PROJEKT-ID

# Billing Account verknüpfen (in der Cloud Console)
# https://console.cloud.google.com/billing

# Nötige APIs aktivieren
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable iamcredentials.googleapis.com
```

### 2. Artifact Registry Repository erstellen

```bash
gcloud artifacts repositories create docker-repo \
  --repository-format=docker \
  --location=europe-west1 \
  --description="Docker Repository"
```

### 3. Workload Identity Federation einrichten (für GitHub Actions)

```bash
# Workload Identity Pool erstellen
gcloud iam workload-identity-pools create "github-pool" \
  --project="DEIN-PROJEKT-ID" \
  --location="global" \
  --display-name="GitHub Pool"

# OIDC Provider erstellen
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project="DEIN-PROJEKT-ID" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Service Account erstellen
gcloud iam service-accounts create github-actions-sa \
  --display-name="GitHub Actions Service Account"

# Rollen zuweisen
PROJECT_ID=$(gcloud config get-value project)

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# Workload Identity erlauben (ersetze DEIN-GITHUB-USER/DEIN-REPO)
gcloud iam service-accounts add-iam-policy-binding \
  github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --project="${PROJECT_ID}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')/locations/global/workloadIdentityPools/github-pool/attribute.repository/DEIN-GITHUB-USER/DEIN-REPO"
```

### 4. GitHub Secrets einrichten

Gehe zu **GitHub Repo → Settings → Secrets and variables → Actions** und erstelle:

| Secret | Wert |
|--------|------|
| `GCP_PROJECT_ID` | Deine Google Cloud Projekt-ID |
| `WIF_PROVIDER` | `projects/PROJEKT-NUMMER/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
| `WIF_SERVICE_ACCOUNT` | `github-actions-sa@DEIN-PROJEKT-ID.iam.gserviceaccount.com` |

Die Projekt-Nummer findest du mit:
```bash
gcloud projects describe DEIN-PROJEKT-ID --format='value(projectNumber)'
```

### 5. GitHub Repo erstellen & pushen

```bash
cd docker_cloud
git init
git add .
git commit -m "Initial commit: FastAPI + Cloud Run"
git remote add origin https://github.com/DEIN-USER/DEIN-REPO.git
git branch -M main
git push -u origin main
```

Nach dem Push startet GitHub Actions automatisch das Deployment!

## Lokal testen

```bash
# Docker Image bauen
docker build -t docker-cloud-app .

# Container starten
docker run -p 8080:8080 docker-cloud-app

# Testen
curl http://localhost:8080
curl http://localhost:8080/health
```

## Pipeline-Ablauf

```
Push auf main → GitHub Actions → Docker Build → Push zu Artifact Registry → Deploy auf Cloud Run
```
