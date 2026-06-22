# Troubleshooting guide

## 1) App won't start
- Check that `.env` exists.
- Make sure `ADMIN_PASSWORD` and `JWT_SECRET` are set.
- Reinstall dependencies:
  - Linux/macOS: `python3 -m pip install -r requirements.txt`
  - Windows: `py -m pip install -r requirements.txt`

## 2) Login fails
- Confirm the password in `.env`.
- Restart the server after editing `.env`.
- Make sure you are using the correct URL.

## 3) Files don't appear after copying the project
- Make sure `data/db`, `data/storage`, and `data/temp_chunks` were copied.
- Restart the app after copying the data folder.

## 4) Browser cannot reach the app from another device
- Use the server machine's LAN IP.
- Check firewall rules.
- Ensure the app is running with `--host 0.0.0.0`.

## 5) Docker issues
- Run `docker compose up -d --build` again.
- Check logs with `docker compose logs -f`.
- If a port is already in use, change the port mapping.

## 6) Port already used
- Stop the old process or change the port.
- For example, run on port `3168` instead of `3167`.
