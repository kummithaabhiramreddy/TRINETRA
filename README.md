# TRINETRA (त्रिनेत्र) — AI-Powered Road Hazard & Urban Surveillance Command Center

TRINETRA is an intelligent transit surveillance and civic infrastructure monitoring system. By combining high-speed edge vision (YOLOv8) with a cloud-synced GIS command center and Neon PostgreSQL, TRINETRA detects road surface anomalies (potholes, cracks) and urban hazards (overflowing garbage bins) in real-time from transit buses and municipal fleets.

---

## 🌟 Key Features

- **Live Edge AI Vision**: Real-time YOLOv8 object detection pipeline for asphalt potholes and civic waste piles.
- **Neon PostgreSQL Cloud Storage**: Every detected hazard is committed directly to Neon PostgreSQL with GIS coordinates, confidence scores, severity ratings, and automated work orders.
- **Dynamic Real-Time Command Center**:
  - Live metric counters synced to Neon DB.
  - Interactive Leaflet map with clustered hazard pins and Google Maps navigation.
  - Live telemetry detections feed table with status pills.
  - Captured evidence repository modal with search, category filtering, and direct CSV export.
- **Vercel Serverless Ready**: Optimized for deployment on Vercel with zero-config serverless architecture and instant cold starts.
- **Dual-Mode Architecture**:
  - **Cloud Mode (Vercel)**: Full REST API, Neon database sync, telemetry feeds, and command center analytics.
  - **Edge Mode (Local)**: Live hardware camera processing, OpenCV MJPEG video streaming, and real-time YOLOv8 inference.

---

## 🚀 Quick Start (Local Edge Mode)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/kummithaabhiramreddy/TRINETRA.git
   cd TRINETRA
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements-local.txt
   ```

3. **Run the Command Center**:
   ```bash
   python app.py
   ```
   Open your browser at `http://127.0.0.1:5000` to view the command center.

---

## ☁️ Deploying to Vercel

1. **Via GitHub (Recommended)**:
   - Go to [Vercel Dashboard](https://vercel.com/new).
   - Import your repository: `kummithaabhiramreddy/TRINETRA`.
   - Vercel automatically detects the Python runtime via `requirements.txt` and `api/index.py`.
   - Click **Deploy**.

2. **Via Vercel CLI**:
   ```bash
   npx vercel --prod
   ```

---

## 📂 Project Architecture

```text
├── api/
│   └── index.py            # Vercel Serverless Function entrypoint
├── assets/                 # Frontend assets (Neon DB client, branding)
│   └── js/neon-db.js       # Neon PostgreSQL serverless client
├── templates/              # Jinja2 dashboard & UI templates
│   ├── dashboard.html      # Main Command Center UI
│   ├── login.html          # Authentication view
│   └── camera.html         # Camera inspection view
├── app.py                  # Core Flask backend & Neon DB ingestion engine
├── vercel.json             # Vercel routing and rewrite configuration
├── requirements.txt        # Production dependencies for Vercel
├── requirements-local.txt  # Full dependencies for local YOLOv8 & OpenCV
└── .vercelignore           # Excludes heavy model files from Vercel bundle
```

---

## 🔒 Neon Database Schema

Detections are committed to the `hazards` table in Neon PostgreSQL Cloud:
- `id`: Unique hazard ID (`HAZ-...`)
- `bus_id`: Fleet vehicle identifier
- `type`: `POTHOLE`, `GARBAGE`, etc.
- `severity`: Numeric severity (1 to 5)
- `confidence`: AI model detection confidence percentage
- `latitude` / `longitude`: GPS coordinates
- `google_maps_url`: Direct navigation link
- `status`: Lifecycle state (`active`, `resolved`)
- `detected_at`: Timestamp
