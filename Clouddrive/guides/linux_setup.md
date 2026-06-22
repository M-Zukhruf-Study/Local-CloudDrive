# Linux setup guide

## 1) Install requirements
- Python 3.10+
- pip
- `curl` or another terminal tool (optional)

## 2) Open the project
```bash
cd clouddrive
```

## 3) Create a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

## 4) Install dependencies
```bash
python3 -m pip install -r requirements.txt
```

## 5) Prepare the environment file
```bash
cp .env.example .env
nano .env
```

Update at least:
- `ADMIN_PASSWORD`
- `JWT_SECRET`

## 6) Run the app
If the direct `uvicorn` command is not working, activate the virtual environment first and then run the app:

```bash
source venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 3167 --timeout-keep-alive 120
```

You can also use the launcher script if you prefer:

```bash
bash start.sh
```

Open:
```text
http://localhost:3167
```

## 7) Share on the network
Use your local IP:
```bash
hostname -I
```
Then open:
```text
http://<your-ip>:3167
```

## 8) Common Linux issues
- `python3: command not found` -> install Python
- `pip: command not found` -> install `python3-pip`
- `Permission denied` -> run `chmod +x start.sh`
- `ModuleNotFoundError` -> run `python3 -m pip install -r requirements.txt`
