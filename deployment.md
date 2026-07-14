# CareBlink - Production Deployment Guide

This document describes how to deploy the CareBlink Smart Patient Emergency Alert portal to various cloud platforms and container runtimes.

---

## 1. Local Containerized Run (Docker Compose)
The easiest way to boot the app alongside a fully provisioned MySQL instance locally is using Docker Compose.

### Steps
1. Make sure you have Docker installed.
2. In the project root, build and run:
   ```bash
   docker-compose up --build
   ```
3. Access the portal at `http://localhost:5000`. 
4. The database is persistent, storing records inside the `mysql_data` volume. Videos and logs are bind-mounted to `./all records` and `./logs` folders.

---

## 2. Deploying on Render / Heroku
Both Render and Heroku use `Procfile` and `runtime.txt` settings automatically.

### Steps
1. Push this codebase to your connected GitHub repository.
2. Log in to Render and create a new **Web Service** linked to your GitHub repo.
3. Configure settings:
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python app.py` (or `gunicorn app:app` after adding gunicorn to requirements)
4. Add environment variables under **Environment Configs** using values from `.env.example`.
5. Save and deploy.

---

## 3. Deploying on Railway
Railway automatically detects Python applications and launches them.

### Steps
1. Connect your GitHub repository to Railway.
2. Create a new service from the repository.
3. Railway reads the `requirements.txt` and starts the app automatically using the command: `python app.py`.
4. In the **Variables** tab, paste the variables from `.env.example`.
5. Save changes to deploy.

---

## 4. Deploying on PythonAnywhere
PythonAnywhere uses WSGI configurations.

### Steps
1. Upload the project files or clone your GitHub repository into PythonAnywhere.
2. Create a virtualenv:
   ```bash
   mkvirtualenv --python=/usr/bin/python3.10 careblink-env
   pip install -r requirements.txt
   ```
3. In the **Web tab** of PythonAnywhere, configure the WSGI configuration file:
   ```python
   import sys
   import os

   path = '/home/yourusername/yourprojectdir'
   if path not in sys.path:
       sys.path.append(path)

   from app import app as application
   ```
4. Set path configurations for Virtualenv, reload the web app, and verify.
