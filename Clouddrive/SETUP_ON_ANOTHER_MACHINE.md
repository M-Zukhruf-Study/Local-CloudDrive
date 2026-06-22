# CloudDrive setup guide (for another machine)

This file explains exactly how to copy this project to another computer and run it.

---

## 1) What to transfer

Copy these items:
- the whole project folder (the `clouddrive` folder)
- the `data` folder (important because it contains the database and uploaded files)
- the `.env` file (important because it contains your password/JWT secret)

You do NOT need to copy the virtual environment (`venv`) if you want to create a fresh one on the new machine.

---

## 2) Recommended transfer method

### Option A — ZIP file (easiest)
1. Compress the project folder.
2. Copy the ZIP to the other machine.
3. Extract it.

### Option B — Git
If the repository is already on GitHub or Git, run:
```bash
git clone <your-repo-url>
```

---

## 3) Requirements on the new machine

### If using Python directly
Install:
- Python 3.10 or newer
- pip
- A terminal (PowerShell, CMD, or Git Bash on Windows)

### If using Docker
Install:
- Docker
- Docker Compose

### OS note
- On Linux/macOS, use commands like `python3`, `source venv/bin/activate`, and `cp`.
- On Windows, use commands like `py`, `venv\Scripts\activate`, and `copy` or `xcopy`.

---

## 4) Setup using Python (simple and direct)

### Step 1 — open terminal in the project folder

#### Linux/macOS
```bash
cd clouddrive
```

#### Windows
```powershell
cd clouddrive
```

### Step 2 — create a virtual environment

#### Linux/macOS
```bash
python3 -m venv venv
source venv/bin/activate
```

#### Windows
```powershell
py -m venv venv
venv\Scripts\activate
```

### Step 3 — install dependencies

#### Linux/macOS
```bash
python3 -m pip install -r requirements.txt
```

#### Windows
```powershell
py -m pip install -r requirements.txt
```

### Step 4 — make sure the `.env` file exists

#### Linux/macOS
```bash
cp .env.example .env
```

#### Windows
```powershell
copy .env.example .env
```

Then open the file and update these values:
```bash
nano .env
```

Or on Windows use:
```powershell
notepad .env
```

Important values:
- `ADMIN_PASSWORD`
- `JWT_SECRET`
- `ADMIN_USERNAME` (if you want to change the username)

### Step 5 — run the app

#### Linux/macOS
If `uvicorn` is not recognized, activate the environment first and run it explicitly:
```bash
source venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 3167 --timeout-keep-alive 120
```

If you want the same startup behavior as the project script, you can also run:
```bash
bash start.sh
```

#### Windows
```powershell
venv\Scripts\activate
python -m uvicorn main:app --host 0.0.0.0 --port 3167 --timeout-keep-alive 120
```

If port `3167` is already used, change the port number to something free, for example `3168`, and use that same port in the browser URL.

Open the app in the browser:
```text
http://localhost:3167
```

---

## 5) Setup using Docker (recommended if you want easy repeat runs)

### Step 1 — go into the project folder

#### Linux/macOS
```bash
cd clouddrive
```

#### Windows
```powershell
cd clouddrive
```

### Step 2 — create `.env` if needed

#### Linux/macOS
```bash
cp .env.example .env
```

#### Windows
```powershell
copy .env.example .env
```

### Step 3 — build and start the container
```bash
docker compose up -d --build
```

### Step 4 — check logs (optional)
```bash
docker compose logs -f
```

### Step 5 — open the app
```text
http://localhost:8000
```

To stop it later:
```bash
docker compose down
```

---

## 6) Important note about the data folder

The `data` folder contains:
- the SQLite database
- uploaded files
- temporary chunk files

If you want the same files and login data on the new machine, transfer the `data` folder too.

If you do not transfer it, the app will still run, but it will start with a fresh database and empty storage.

---

## 7) If you want the app available on another laptop or phone

If both machines are on the same Wi‑Fi network, run the app using:
```bash
uvicorn main:app --host 0.0.0.0 --port 3167
```

Then on another device open:
```text
http://<server-machine-ip>:3167
```

### Find your IP address
`
#### Linux
```bash
hostname -I
```

#### Windows
```powershell
ipconfig
```

Look for your local IPv4 address, usually something like `192.168.x.x` or `10.0.x.x`.

> If you are using Docker, the app may be reachable at `http://localhost:8000` on the same machine, and on another device use the machine's local IP plus the same port.

---

## 8) Quick start summary

### Fastest local setup — Linux/macOS
```bash
cd clouddrive
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --host 0.0.0.0 --port 3167 --timeout-keep-alive 120
```

### Fastest local setup — Windows
```powershell
cd clouddrive
py -m venv venv
venv\Scripts\activate
py -m pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --host 0.0.0.0 --port 3167 --timeout-keep-alive 120
```

### Fastest Docker setup
```bash
cd clouddrive
cp .env.example .env
docker compose up -d --build
```

On Windows, you can also use `copy .env.example .env` in PowerShell.

---

## 9) OS-specific helper guides

You can use these extra guides if you want a simpler version for your machine:
- [guides/linux_setup.md](guides/linux_setup.md)
- [guides/windows_setup.md](guides/windows_setup.md)
- [guides/troubleshooting.md](guides/troubleshooting.md)

---

## 10) Common issues and fixes

### `python` or `python3` not found
- Install Python from the official website.
- After installation, reopen the terminal and run `python --version` or `python3 --version`.

### `pip` not found
- Reinstall Python and make sure "Add Python to PATH" is enabled on Windows.
- On Linux, install `python3-pip` if needed.

### `uvicorn` command not found
Run:
```bash
python3 -m pip install -r requirements.txt
```
Or on Windows:
```powershell
py -m pip install -r requirements.txt
```

### `Permission denied` while running commands on Linux
Use:
```bash
chmod +x start.sh
```
If needed, run the command with `bash start.sh`.

### App opens but login fails
- Check that `.env` contains the correct `ADMIN_PASSWORD` and `JWT_SECRET`.
- Restart the server after changing `.env`.

### App starts but you cannot open it from another device
Check:
- firewall settings
- port `3167` or `8000` is not blocked
- the correct machine IP is used
- the app is running with `--host 0.0.0.0`

### Database looks empty after transfer
Make sure the `data` folder was copied too, especially:
- `data/db/`
- `data/storage/`
- `data/temp_chunks/`

### Docker says the port is already in use
Stop the other process using that port, or change the port in `docker-compose.yml`.

### `ModuleNotFoundError` during startup
Reinstall dependencies:
```bash
python3 -m pip install -r requirements.txt
```
On Windows:
```powershell
py -m pip install -r requirements.txt
```
