# Deploying AutoHawk

This guide covers three setups, from simplest to most hands-off:

1. [Local machine with Ollama](#1-local-machine--ollama-free-recommended-start) — free, 10 minutes
2. [Linux VPS with systemd + cron](#2-linux-vps-ubuntu--the-classic-way) — runs daily without your laptop
3. [Docker / docker-compose](#3-docker-deployment) — one command, anywhere Docker runs

Plus [hardware sizing](#hardware-sizing-for-ollama), [security checklist](#security-checklist), and [troubleshooting](#troubleshooting).

---

## How the pieces fit

```
┌─────────────────────── your machine / server ────────────────────────┐
│                                                                       │
│  autohawk fetch ──▶ SQLite (autohawk.db)                              │
│  autohawk score ──▶ Ollama (localhost:11434) ──▶ scores in SQLite     │
│  autohawk report ─▶ reports/shortlist.html                            │
│                                                                       │
│  profile.yaml + .env = all configuration                              │
└───────────────────────────────────────────────────────────────────────┘
```

Everything is local: your profile, the job database, and (with Ollama) the AI itself. No data leaves the machine except the outbound requests to job boards.

**Provider resolution** (`AUTOHAWK_PROVIDER` in `.env`):

| Value | Behavior |
|---|---|
| `auto` (default) | Anthropic if `ANTHROPIC_API_KEY` is set → else Ollama if running → else keyword scoring |
| `ollama` | Force Ollama; errors with instructions if it isn't running |
| `anthropic` | Force Claude; errors if no key |
| `none` | Keyword scoring only |

---

## 1. Local machine + Ollama (free, recommended start)

### Windows

```powershell
# 1. Install Ollama (or download the installer from https://ollama.com/download)
winget install Ollama.Ollama

# 2. Pull a model (one-time, ~5 GB download; see sizing table below)
ollama pull llama3.1:8b

# 3. Point AutoHawk at it
cd Desktop\Projects\AutoHawk
copy .env.example .env
#    edit .env → AUTOHAWK_PROVIDER=ollama   (or leave auto)

# 4. Run the pipeline
autohawk fetch
autohawk score          # prints "Scoring with ollama (llama3.1:8b @ ...)"
autohawk shortlist
autohawk letter <id>
```

The Ollama desktop app starts its server automatically on login. To verify it's up: open `http://localhost:11434` in a browser — it should say "Ollama is running".

### macOS / Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh   # Linux (macOS: download the app)
ollama pull llama3.1:8b
# then same autohawk steps as above
```

---

## 2. Linux VPS (Ubuntu) — the classic way

Runs the pipeline every morning on a small cloud server (Hetzner/DigitalOcean/Oracle Free Tier/EC2), so your shortlist is waiting for you.

**Minimum server**: 2 vCPU / 8 GB RAM for `llama3.1:8b` (see [sizing](#hardware-sizing-for-ollama)). CPU-only is fine — scoring is a batch job, nobody is waiting on latency.

### 2.1 Base setup

```bash
# as root or with sudo, Ubuntu 22.04/24.04
apt update && apt install -y python3 python3-venv python3-pip git

# create an unprivileged user to run everything
adduser --disabled-password --gecos "" autohawk
su - autohawk
```

### 2.2 Install Ollama

```bash
# back as root:
curl -fsSL https://ollama.com/install.sh | sh
```

The installer registers a systemd service (`ollama.service`) that listens on `127.0.0.1:11434` — loopback only by default, which is exactly what you want. Verify:

```bash
systemctl status ollama          # should be active (running)
curl http://localhost:11434      # "Ollama is running"
ollama pull llama3.1:8b          # one-time model download
```

### 2.3 Install AutoHawk

```bash
su - autohawk
git clone https://github.com/vandan08/AutoHawk.git
cd AutoHawk
python3 -m venv .venv
.venv/bin/pip install -e .

# configuration
cp .env.example .env             # set AUTOHAWK_PROVIDER=ollama
cp profile.example.yaml profile.yaml
nano profile.yaml                # your skills, roles, sources

# first run, manually
.venv/bin/autohawk fetch
.venv/bin/autohawk score
.venv/bin/autohawk shortlist
```

### 2.4 Schedule the daily run (systemd timer)

Create `/etc/systemd/system/autohawk.service`:

```ini
[Unit]
Description=AutoHawk daily job pipeline
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=oneshot
User=autohawk
WorkingDirectory=/home/autohawk/AutoHawk
ExecStart=/home/autohawk/AutoHawk/.venv/bin/autohawk fetch
ExecStart=/home/autohawk/AutoHawk/.venv/bin/autohawk score
ExecStart=/home/autohawk/AutoHawk/.venv/bin/autohawk report
# optional: email yourself the top new matches (SMTP settings in .env)
ExecStart=/home/autohawk/AutoHawk/.venv/bin/autohawk digest
```

Create `/etc/systemd/system/autohawk.timer`:

```ini
[Unit]
Description=Run AutoHawk every morning

[Timer]
OnCalendar=*-*-* 06:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and test:

```bash
systemctl daemon-reload
systemctl enable --now autohawk.timer
systemctl start autohawk.service      # run once now to verify
journalctl -u autohawk.service -f     # watch the logs
systemctl list-timers autohawk.timer  # confirm next run time
```

> **Prefer plain cron?** One line in `crontab -e` (as the autohawk user) does the same:
> `30 6 * * * cd ~/AutoHawk && .venv/bin/autohawk fetch && .venv/bin/autohawk score && .venv/bin/autohawk report && .venv/bin/autohawk digest >> ~/autohawk.log 2>&1`

### 2.5 Reading the shortlist remotely

The pipeline writes `reports/shortlist.html`. Three ways to read it, safest first:

1. **Pull it down (recommended, zero server exposure):**
   ```bash
   scp autohawk@your-server:~/AutoHawk/reports/shortlist.html .
   ```
2. **SSH tunnel** when you want to browse it live — or, better, tunnel the
   **interactive dashboard** and click through jobs, statuses, and letters:
   ```bash
   ssh -L 8090:localhost:8090 autohawk@your-server \
       "cd ~/AutoHawk && .venv/bin/autohawk web"
   # then open http://localhost:8090 on your laptop
   ```
   The dashboard binds to `127.0.0.1` only and has no authentication — never
   expose it directly with `--host 0.0.0.0` on an internet-facing box; keep it
   behind the tunnel (or a VPN like Tailscale).
3. **nginx with basic auth** if you want it always available at a URL:
   ```bash
   apt install -y nginx apache2-utils
   htpasswd -c /etc/nginx/.htpasswd you        # choose a strong password
   ```
   `/etc/nginx/sites-available/autohawk`:
   ```nginx
   server {
       listen 80;
       server_name your-domain-or-ip;
       root /home/autohawk/AutoHawk/reports;
       auth_basic "AutoHawk";
       auth_basic_user_file /etc/nginx/.htpasswd;
       location / { try_files /shortlist.html =404; }
   }
   ```
   ```bash
   ln -s /etc/nginx/sites-available/autohawk /etc/nginx/sites-enabled/
   nginx -t && systemctl reload nginx
   ```
   Add TLS with `certbot --nginx` if you point a domain at it.

### 2.6 Updating and maintenance

```bash
su - autohawk && cd AutoHawk
git pull
.venv/bin/pip install -e .        # picks up dependency changes
systemctl start autohawk.service  # (as root) verify a run still works
```

Backup = copy two files: `autohawk.db` and `profile.yaml`.

```bash
# optional: nightly backup line in crontab
0 5 * * * cp ~/AutoHawk/autohawk.db ~/backups/autohawk-$(date +\%a).db
```

---

## 3. Docker deployment

The repo ships a `Dockerfile` and `docker-compose.yml` that run Ollama and the pipeline together — works on any box with Docker (including Windows with Docker Desktop).

```bash
git clone https://github.com/vandan08/AutoHawk.git
cd AutoHawk

# 1. Runtime state lives in ./data — create your profile there
mkdir -p data
cp profile.example.yaml data/profile.yaml
nano data/profile.yaml

# 2. Start both containers
docker compose up -d --build

# 3. One-time: pull the model inside the ollama container (~5 GB)
docker compose exec ollama ollama pull llama3.1:8b

# 4. Watch the first pipeline run
docker compose logs -f autohawk
```

Then open **http://127.0.0.1:8090** — the dashboard comes up with the stack.

What you get:

- `ollama` container with a named volume for models, **no published ports** (only the other containers can reach it)
- `autohawk` container that runs `fetch → score → report` every 24 h (`AUTOHAWK_INTERVAL_HOURS` to change; `0` = run once and exit)
- `dashboard` container serving the web UI on **127.0.0.1:8090**, sharing the same database
- everything persistent in `./data/`: `profile.yaml`, `autohawk.db`, `reports/`, `letters/`

### Exposing the dashboard beyond localhost

The published port is bound to loopback because the dashboard has no login and can start scoring runs. To reach it from another machine, change the **host** side of the binding:

```bash
AUTOHAWK_WEB_BIND=0.0.0.0 docker compose up -d dashboard
```

Only do that behind a VPN (Tailscale) or an authenticating reverse proxy — never straight onto a public IP.

Useful commands:

```bash
docker compose exec autohawk autohawk shortlist        # ranked table in your terminal
docker compose exec autohawk autohawk letter <id>      # cover letter → ./data/letters/
docker compose restart autohawk                        # trigger a fresh run now
AUTOHAWK_OLLAMA_MODEL=llama3.2:3b docker compose up -d # switch model (low-RAM box)
```

The HTML report lands at `./data/reports/shortlist.html` on the host — serve or copy it however you like (see [2.5](#25-reading-the-shortlist-remotely)).

---

## Hardware sizing for Ollama

| Model | Disk | RAM needed | Quality | Use when |
|---|---|---|---|---|
| `llama3.2:3b` | ~2 GB | ~4 GB | okay | 4 GB VPS, quick scoring |
| `llama3.1:8b` (default) | ~5 GB | ~8 GB | good | the sweet spot |
| `qwen2.5:14b` | ~9 GB | ~16 GB | better | beefier box, best letters |

- **CPU-only is fine.** Expect roughly 5–20 tokens/sec on a modern CPU — a scoring call takes ~10–60 s per job. For a nightly batch of 50 jobs that's under an hour while you sleep.
- **GPU is a bonus, not a requirement.** Any NVIDIA GPU with ≥6 GB VRAM makes 8B models near-instant; Ollama uses it automatically.
- Rule of thumb: RAM ≥ model download size × 1.5, plus headroom for the OS.

Switch models any time: `ollama pull <model>` then set `AUTOHAWK_OLLAMA_MODEL=<model>` in `.env`.

---

## Security checklist

- [ ] **Never expose Ollama's port (11434) to the internet.** Default binding is loopback — keep it that way. Ollama has no authentication; an exposed instance lets anyone run inference on your box (or worse with older versions). If you must reach it across machines, use an SSH tunnel or VPN (Tailscale is the easy option).
- [ ] **Firewall the VPS**: `ufw allow OpenSSH && ufw allow 80/tcp && ufw enable` — nothing else.
- [ ] **Run as an unprivileged user** (the `autohawk` user above), not root.
- [ ] **`profile.yaml` and `.env` are gitignored** — keep it that way; they hold your personal data and any keys.
- [ ] **Put basic auth (or better) in front of the report** if you serve it over HTTP — it contains your job-search activity.
- [ ] **Never run `autohawk web --host 0.0.0.0` on an internet-facing machine.** The dashboard has no login and can trigger fetch/score and write statuses. Loopback + SSH tunnel only.
- [ ] **SSH keys, not passwords**, and `PermitRootLogin no` on any internet-facing VPS.

---

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| `Ollama is not reachable at http://localhost:11434` | Ollama isn't running. Desktop: launch the app. Linux: `systemctl start ollama`. Docker: is the `ollama` service up, and is `OLLAMA_HOST=http://ollama:11434` set? |
| `Ollama has no model 'llama3.1:8b'` | Run `ollama pull llama3.1:8b` (in Docker: `docker compose exec ollama ollama pull llama3.1:8b`). |
| Scoring is very slow | Normal on CPU (10–60 s/job). Use `autohawk score -n 20` for smaller batches, switch to `llama3.2:3b`, or schedule the run overnight. |
| Ollama killed / server freezes during scoring | Out of RAM. Use a smaller model (`llama3.2:3b`) or add swap: `fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`. |
| Scores look lazy or identical | Small models sometimes anchor. Try `qwen2.5:14b` if you have the RAM, or compare with `autohawk score --keyword-only` as a sanity baseline. |
| `validation error for ScoreResult` | The model produced malformed JSON despite the schema constraint — rare; the job is retried on the next `autohawk score` run. Persistent? Use a bigger model. |
| Remotive/RemoteOK return irrelevant jobs | Their public APIs are flaky about filters; the `search.title_keywords` list in profile.yaml is the real filter — tighten it. |
| Timer didn't run after a reboot/downtime | Ensure `Persistent=true` is in the `[Timer]` block (it is, in the unit above) — it catches up on missed runs. |
