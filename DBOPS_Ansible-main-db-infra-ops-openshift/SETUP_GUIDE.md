# DB Infrastructure OPS — Setup Guide

A beginner-friendly, step-by-step guide to run the app **locally** and on **OpenShift**.

---

## Prerequisites — Install These First

You need these tools on your computer before starting anything.

### For local development

| Tool | What it does | How to install |
|------|-------------|----------------|
| Python 3.12+ | Runs the backend | https://python.org/downloads |
| Node.js 20+ | Builds the frontend | https://nodejs.org |
| PostgreSQL 15+ | The database | https://postgresql.org/download |
| Git | Version control | https://git-scm.com |

### For OpenShift deployment (in addition to the above)

| Tool | What it does | How to install |
|------|-------------|----------------|
| Docker or Podman | Builds container images | https://docker.com or `brew install podman` |
| oc CLI | Talks to OpenShift | Download from your OpenShift web console (click **?** → **Command Line Tools**) |

### How to check if you already have them

Open a terminal (Command Prompt on Windows, Terminal on Mac/Linux) and run:

```
python3 --version
node --version
psql --version
git --version
docker --version
oc version
```

Each should print a version number. If it says "command not found", install that tool.

---

## Part 1 — Run Locally (Development)

This gets the app running on your own computer so you can develop and test.

### Step 1: Get the code

```bash
# Unzip the package you downloaded
unzip db-infra-ops-openshift.zip
cd db-infra-ops-openshift
```

### Step 2: Set up PostgreSQL

You need a database running locally. Here is how:

**On Mac (with Homebrew):**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**On Ubuntu/Debian:**
```bash
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

**On Windows:**
Download the installer from https://postgresql.org/download/windows and run it. Use the default port 5432.

Now create the database and user:

```bash
# Connect to PostgreSQL as the admin user
psql -U postgres

# Inside the psql prompt, run these 3 commands:
CREATE USER dbinfra WITH PASSWORD 'dbinfra';
CREATE DATABASE db_infra_ops OWNER dbinfra;
\q
```

To verify it worked:
```bash
psql -U dbinfra -d db_infra_ops -c "SELECT 1;"
```
You should see a table with the number 1. If you get a password error, check your `pg_hba.conf` file.

### Step 3: Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

If you get permission errors, use `pip install --user -r requirements.txt` or create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate          # On Mac/Linux
# venv\Scripts\activate           # On Windows
pip install -r requirements.txt
```

### Step 4: Start the backend

```bash
# Still inside the backend/ folder
uvicorn main:app --reload --port 8090
```

You should see:
```
INFO: Database initialised at localhost:5432/db_infra_ops
INFO: DB Infrastructure OPS backend ready.
INFO: Uvicorn running on http://127.0.0.1:8090
```

Test it by opening http://localhost:8090/api/ping in your browser. You should see:
```json
{"status": "ok"}
```

Leave this terminal running. Open a new terminal for the next step.

### Step 5: Install and start the frontend

```bash
# Open a NEW terminal window, go to the project root
cd db-infra-ops-openshift/frontend

npm install
npm run dev
```

You should see:
```
VITE v5.x.x  ready in 500 ms
➜  Local:   http://localhost:5173/
```

### Step 6: Open the app

Go to **http://localhost:5173** in your browser.

You will see the "Welcome to DB Infra OPS" page with a "Configure Data Source" button. Click it, enter your Zabbix URL and API token, and click Fetch.

### Stopping everything

- Press `Ctrl+C` in the backend terminal to stop the API
- Press `Ctrl+C` in the frontend terminal to stop Vite
- PostgreSQL keeps running in the background (that is fine)

### Troubleshooting — Local

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: No module named 'sqlalchemy'` | Run `pip install -r requirements.txt` again |
| `connection refused` on port 5432 | PostgreSQL is not running. Start it with `brew services start postgresql` or `sudo systemctl start postgresql` |
| `password authentication failed` | The password in `config.py` does not match what you set in PostgreSQL. Default is `dbinfra` / `dbinfra` |
| `npm: command not found` | Install Node.js from https://nodejs.org |
| Frontend shows blank page | Check the backend terminal for errors. Make sure port 8090 is running |
| `CORS error` in browser console | Make sure the backend is running on port 8090 and frontend on port 5173 |

---

## Part 2 — Deploy to OpenShift (Production)

This puts the app on your company's OpenShift cluster so everyone can access it.

### Step 1: Log into OpenShift

```bash
# Get the login command from the OpenShift web console:
# Click your name (top right) → "Copy login command" → paste it here
oc login --token=YOUR_TOKEN --server=https://api.your-cluster.example.com:6443

# Switch to your project/namespace
oc project your-namespace
```

Verify you are logged in:
```bash
oc whoami
# Should print your username
```

### Step 2: Edit the passwords

Before deploying anything, you must change the default password.

Open `k8s/postgres.yaml` in a text editor and find these lines near the top:

```yaml
  database-password: "CHANGE_ME_BEFORE_DEPLOY"
  database-url: "postgresql://dbinfra:CHANGE_ME_BEFORE_DEPLOY@db-infra-ops-db:5432/db_infra_ops"
```

Replace `CHANGE_ME_BEFORE_DEPLOY` with a real password (same password in both places).

For example:
```yaml
  database-password: "MyStr0ngP@ss2024"
  database-url: "postgresql://dbinfra:MyStr0ngP@ss2024@db-infra-ops-db:5432/db_infra_ops"
```

### Step 3: Deploy PostgreSQL

```bash
oc apply -f k8s/postgres.yaml
```

Wait for it to be ready (this takes 30-60 seconds):
```bash
oc get pods -l component=database -w
# Wait until STATUS shows "Running" and READY shows "1/1"
# Press Ctrl+C to stop watching
```

### Step 4: Build the Docker image

```bash
# Make sure you are in the project ROOT folder (not backend/ or frontend/)
cd db-infra-ops-openshift

docker build -t db-infra-ops:latest .
```

This takes 2-4 minutes the first time. You will see it:
1. Install Node.js dependencies and build the React frontend
2. Install Python dependencies
3. Copy everything into the final image

If you see errors about npm or pip, check your internet connection.

### Step 5: Push the image to OpenShift

**Option A — Using the OpenShift internal registry (most common):**

```bash
# Find the registry URL
REGISTRY=$(oc get route default-route -n openshift-image-registry -o jsonpath='{.spec.host}' 2>/dev/null)

# If the above gives an error, try this instead:
# REGISTRY=$(oc get route -n openshift-image-registry -o jsonpath='{.items[0].spec.host}')

# Log into the registry
docker login -u $(oc whoami) -p $(oc whoami -t) $REGISTRY

# Tag and push
docker tag db-infra-ops:latest $REGISTRY/your-namespace/db-infra-ops:latest
docker push $REGISTRY/your-namespace/db-infra-ops:latest
```

**Option B — If your cluster uses an external registry (Quay, Harbor, etc.):**

```bash
docker tag db-infra-ops:latest your-registry.example.com/your-namespace/db-infra-ops:latest
docker push your-registry.example.com/your-namespace/db-infra-ops:latest
```

### Step 6: Update the deployment file with your image path

Open `k8s/deployment.yaml` and find this line:

```yaml
image: image-registry.openshift-image-registry.svc:5000/YOUR_NAMESPACE/db-infra-ops:latest
```

Replace `YOUR_NAMESPACE` with your actual namespace. If you used an external registry, replace the entire image path.

Also update the CORS origin. Find:
```yaml
CORS_ORIGINS: "https://db-infra-ops.apps.your-cluster.example.com"
```
You can fix this after step 7 once you know the actual URL.

### Step 7: Deploy the application

```bash
oc apply -f k8s/deployment.yaml
```

Wait for it to start:
```bash
oc get pods -l app=db-infra-ops -w
# Wait until BOTH pods show "Running" and "1/1"
# Press Ctrl+C to stop watching
```

Get your app URL:
```bash
oc get route db-infra-ops
# Look at the HOST/PORT column — that is your URL
```

Open that URL in your browser. You should see the app.

### Step 8: Fix CORS (if needed)

If the app loads but shows errors when you click buttons:

```bash
# Get your actual route URL
ROUTE=$(oc get route db-infra-ops -o jsonpath='{.spec.host}')
echo "Your URL: https://$ROUTE"

# Update the CORS secret
oc patch secret db-infra-ops-app-config -p "{\"stringData\":{\"CORS_ORIGINS\":\"https://$ROUTE\"}}"

# Restart the app to pick up the change
oc rollout restart deployment/db-infra-ops

# Wait for restart
oc rollout status deployment/db-infra-ops
```

### Troubleshooting — OpenShift

| Problem | How to debug |
|---------|-------------|
| Pod stuck in `Pending` | `oc describe pod -l app=db-infra-ops` — look for events at the bottom |
| Pod in `CrashLoopBackOff` | `oc logs -l app=db-infra-ops --previous` — shows why it crashed |
| Pod in `ImagePullBackOff` | Wrong image path or missing permissions. Check `oc describe pod ...` |
| App loads but API returns 500 | `oc logs deploy/db-infra-ops --tail=50` — check for database connection errors |
| "Connection refused" errors | PostgreSQL pod might not be ready: `oc get pods -l component=database` |
| CORS errors in browser | Run the CORS fix commands from Step 8 above |
| Fetch data fails | Check Zabbix connectivity: `oc exec deploy/db-infra-ops -- curl -sf YOUR_ZABBIX_URL -o /dev/null && echo OK` |

### Useful commands

```bash
# See all your pods
oc get pods

# See logs (live)
oc logs -f deploy/db-infra-ops

# Restart the app after changes
oc rollout restart deployment/db-infra-ops

# Connect to the database directly
oc exec -it deploy/db-infra-ops-db -- psql -U dbinfra -d db_infra_ops

# Delete everything and start over
oc delete -f k8s/deployment.yaml
oc delete -f k8s/postgres.yaml
```

---

## Quick Reference — What runs where

```
LOCAL DEVELOPMENT:
  Terminal 1:  uvicorn main:app --reload --port 8090    (backend API)
  Terminal 2:  npm run dev                               (frontend dev server)
  Background:  PostgreSQL on port 5432                   (database)
  Browser:     http://localhost:5173                      (the app)

OPENSHIFT:
  Pod 1:  db-infra-ops      (backend + frontend, port 8090)
  Pod 2:  db-infra-ops-db   (PostgreSQL, port 5432)
  Route:  https://db-infra-ops-<namespace>.apps.<cluster>
```

---

## Environment Variables

These can be set in a `.env` file in the `backend/` folder (for local dev) or via OpenShift Secrets (for production).

| Variable | Default | What it does |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://dbinfra:dbinfra@localhost:5432/db_infra_ops` | PostgreSQL connection string |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:8090` | Allowed frontend URLs (comma-separated) |
| `ZABBIX_VERIFY_TLS` | `false` | Set to `true` if Zabbix has valid TLS certificates |
| `API_TIMEOUT_SHORT` | `30` | Timeout for quick API calls (seconds) |
| `API_TIMEOUT_MEDIUM` | `60` | Timeout for normal API calls (seconds) |
| `API_TIMEOUT_LONG` | `120` | Timeout for heavy API calls (seconds) |
