# Windows setup guide

## 1) Install requirements
- Python 3.10+
- pip
- PowerShell or Command Prompt

## 2) Open the project
```powershell
cd clouddrive
```

## 3) Create a virtual environment
```powershell
py -m venv venv
venv\Scripts\activate
```

## 4) Install dependencies
```powershell
py -m pip install -r requirements.txt
```

## 5) Prepare the environment file
```powershell
copy .env.example .env
notepad .env
```

Update at least:
- `ADMIN_PASSWORD`
- `JWT_SECRET`

## 6) Run the app
```powershell
uvicorn main:app --host 0.0.0.0 --port 3167 --timeout-keep-alive 120
```

Open:
```text
http://localhost:3167
```

## 7) Share on the network
Check your IP:
```powershell
ipconfig
```
Look for your IPv4 address, then open:
```text
http://<your-ip>:3167
```

## 8) Common Windows issues
- `py` not recognized -> install Python and enable PATH
- `pip` not recognized -> reinstall Python
- `uvicorn` not found -> run `py -m pip install -r requirements.txt`
- Port already used -> change the port number in the run command
