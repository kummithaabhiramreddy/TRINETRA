# Deploying TRINETRA to Vercel

This guide outlines the complete setup and deployment of the **TRINETRA Command Center** on Vercel.

---

## 📁 Files Created for Vercel

1. **`vercel.json`**:
   - Configures URL rewrites to route requests to the serverless entrypoint `api/index.py` while serving static assets from `/assets`.
2. **`api/index.py`**:
   - The serverless entrypoint that imports and exposes the Flask `app` instance to Vercel's Python runtime.
3. **`requirements.txt`**:
   - Lightweight production dependencies (`Flask`, `pandas`) optimized for Vercel Serverless Functions to keep the unzipped bundle well below Vercel's 250 MB limit.
4. **`.vercelignore`**:
   - Excludes heavy local model files (`*.pt`, `weights/`), CSV logs, and caches from the build bundle for fast deployment times.
5. **`requirements-local.txt`**:
   - Complete dependency list (including `ultralytics`, `opencv-python`, and `torch`) for running local edge webcam inference.

---

## 🚀 Option 1: Deploy via GitHub (Recommended)

1. **Commit & Push to GitHub**:
   ```bash
   git add .
   git commit -m "Add Vercel deployment configuration"
   git push origin main
   ```
2. **Import Project into Vercel**:
   - Go to [vercel.com/dashboard](https://vercel.com/dashboard).
   - Click **"Add New..."** → **"Project"**.
   - Select your GitHub repository (`sih_final`).
   - Framework Preset: **Other** (Vercel automatically detects the Python runtime).
3. **Deploy**:
   - Click **Deploy**. Vercel will install `requirements.txt` and launch your serverless app in ~1-2 minutes.

---

## ⚡ Option 2: Deploy via Vercel CLI

1. **Install Vercel CLI** (if not already installed):
   ```bash
   npm install -g vercel
   ```
2. **Login and Deploy**:
   ```bash
   vercel
   ```
   - Set up and deploy: **`Y`**
   - Which scope: *(Select your account)*
   - Link to existing project: **`N`**
   - Project name: **`trinetra-dashboard`**
   - Directory: **`./`**
3. **Production Deployment**:
   ```bash
   vercel --prod
   ```

---

## ☁️ Neon Database Connectivity on Vercel

- The dashboard automatically connects to your live **Neon PostgreSQL Cloud database**:
  - Connection string: `postgresql://neondb_owner:...@ep-rapid-sunset-a54uayxa-pooler.us-east-2.aws.neon.tech/neondb`
  - Neon Serverless SQL Endpoint: `https://ep-rapid-sunset-a54uayxa.us-east-2.aws.neon.tech/sql`
- All real-time hazard detections, metric counters, evidence searches, and CSV exports function on your live Vercel URL.
