# MindMate free deployment runbook

This runbook prepares a portfolio/demo deployment. It does not provide an uptime
SLA and is not appropriate for clinical use. Create every resource manually and
keep every service on its explicitly labelled Free or Always Free plan.

## Architecture and order

```text
Browser --HTTPS--> Render Free web
                       |--TLS--> Neon Free PostgreSQL
                       `--TLS--> Upstash Free Redis <--TLS-- Oracle A1 RQ worker
                                                        `--TLS--> Neon PostgreSQL
```

1. Run tests and commit a known-good revision.
2. Create Neon and Upstash Free resources.
3. Generate production secrets locally.
4. Apply Alembic to Neon using its direct connection string.
5. Deploy the web service on Render and verify web/PostgreSQL/Redis connectivity.
6. Create the Oracle A1 VM and start the worker.
7. Submit one journal entry and verify `pending -> processing -> completed`.
8. Enable the supplied maintenance timers and verify Neon restore capability.

Do not put credentials in Git, screenshots, tickets, chat messages, or shell
history. Never use the local development database or Redis database for production.

## 1. Known-good revision

Run locally with dedicated test services:

```bash
TEST_DATABASE_URL=postgresql+psycopg://LOCAL_ROLE@localhost:5432/mindmate_test \
TEST_REDIS_URL=redis://localhost:6379/15 \
python -m pytest
git status
```

Review and commit through your normal Git workflow. Do not deploy an unreviewed or
dirty working tree.

## 2. Neon Free PostgreSQL

1. Sign in at <https://console.neon.tech> and create a Free project in a region
   close to Render and the Oracle home region.
2. Create a production database and a dedicated application role. Do not reuse the
   project-owner credential if Neon lets you grant a narrower role.
3. From **Connect**, copy both connection strings:
   - Direct endpoint: use only for Alembic and administrative work.
   - Pooled endpoint (`-pooler` hostname): use as the runtime `DATABASE_URL`.
4. Keep Neon's supplied `sslmode=require` and `channel_binding=require` query
   parameters. If the URL begins with `postgresql://`, MindMate normalizes it to
   psycopg automatically.

Apply migrations from the trusted local checkout without saving the URL in a file:

```bash
read -rs "DATABASE_URL?Neon direct DATABASE_URL: "
export DATABASE_URL
alembic upgrade head
alembic current
unset DATABASE_URL
```

Expected head revision: `20260904_01`.

Neon Free currently provides 0.5 GB per project, 100 CU-hours per month, automatic
scale-to-zero, and a limited restore window of up to six hours or 1 GB of changes.
That restore window is not a substitute for a separately verified logical backup.
Before accepting meaningful data, create an encrypted `pg_dump`, restore it into
an isolated database, check `alembic current`, and exercise a scoped journal read.

## 3. Upstash Free Redis

1. Sign in at <https://console.upstash.com>, create a Redis Free database, and
   choose a region close to Oracle and Render.
2. Keep automatic paid upgrades disabled and do not add a payment method merely to
   raise limits.
3. Copy the **native Redis TLS** endpoint, not the REST URL/token. It must look like:

   ```text
   rediss://default:PASSWORD@HOST:PORT
   ```

4. From a trusted environment, load that value into `REDIS_URL` and verify:

   ```bash
   python -c "from app.queue import get_redis_connection; print(get_redis_connection().ping())"
   ```

RQ depends on native Redis commands and blocking queue operations; the REST API is
not compatible. The Free plan currently advertises 256 MB, 500,000 commands/month,
and 10 GB/month bandwidth. Commands beyond the free allowance fail. Use `/health`
for Render's frequent health probe; call `/ready` only manually or sparingly so
health checks do not consume the Redis command budget.

## 4. Production secrets

Generate two independent secrets locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Store the values directly in Render and `/etc/mindmate/worker.env`. Do not write
real values into `deploy/mindmate-production.env.example`.

## 5. Render Free web service

The checked-in `render.yaml` documents the configuration, but using a Blueprint
can create resources. For manual control, create one **Web Service** in the Render
dashboard:

- Repository: the reviewed MindMate Git repository
- Branch: the known-good deployment branch
- Runtime: Python
- Plan: Free
- Build command: `python -m pip install .`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers`
- Health check: `/health`
- Python: `.python-version` pins the 3.12 series

Set these environment variables manually:

```text
ENVIRONMENT=production
DATABASE_URL=<Neon pooled TLS URL>
DATABASE_POOL_SIZE=2
DATABASE_MAX_OVERFLOW=1
REDIS_URL=<Upstash native rediss URL>
JWT_SECRET_KEY=<secret one>
REFRESH_JWT_SECRET_KEY=<secret two>
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
PASSWORD_RESET_ENABLED=false
TRUST_PROXY_HEADERS=true
TRUSTED_HOSTS=<service-name>.onrender.com
ALLOWED_ORIGINS=https://<service-name>.onrender.com
```

Deploy and verify:

```text
GET https://<service-name>.onrender.com/health  -> 200
GET https://<service-name>.onrender.com/ready   -> 200 with both checks true
```

Render Free currently spins down after 15 minutes without inbound traffic and can
take about a minute to wake. It has an ephemeral filesystem, 512 MB RAM, 0.1 CPU,
and 750 shared Free instance-hours/month. External Neon/Upstash traffic counts
toward Render bandwidth. Do not enable a paid instance or paid worker. Managed TLS
and custom domains are supported; add the custom hostname to `TRUSTED_HOSTS` and
its exact HTTPS origin to `ALLOWED_ORIGINS` before switching DNS.

## 6. Oracle Always Free A1 worker

Oracle requires payment-card identity verification. A1 capacity can be unavailable,
and idle Always Free instances can be reclaimed. Select only resources labelled
Always Free eligible.

Create one `VM.Standard.A1.Flex` instance in the tenancy home region:

- Ubuntu 24.04 ARM64
- 2 OCPUs and 12 GB RAM
- 50-75 GB Always Free-eligible boot volume
- Public IPv4 only if required for administration
- Inbound SSH restricted to your current IP; no application or Redis ports
- Outbound HTTPS and PostgreSQL/Redis destinations allowed

On the VM, replace `YOUR_GIT_URL` with the repository URL:

```bash
sudo apt update
sudo apt install -y git python3.12 python3.12-venv build-essential
sudo useradd --system --create-home --home-dir /opt/mindmate --shell /usr/sbin/nologin mindmate
sudo install -d -o mindmate -g mindmate /opt/mindmate/current /var/cache/mindmate/huggingface
sudo -u mindmate git clone YOUR_GIT_URL /opt/mindmate/current
cd /opt/mindmate/current
sudo -u mindmate python3.12 -m venv /opt/mindmate/venv
sudo -u mindmate /opt/mindmate/venv/bin/python -m pip install --upgrade pip
sudo -u mindmate /opt/mindmate/venv/bin/python -m pip install '.[worker]'
```

PyTorch recommends Python 3.9-3.12, and the pinned runtime has Linux AArch64
wheels. If pip attempts a source build, stop rather than exhausting the VM; verify
the OS is ARM64 (`uname -m` should print `aarch64`), Python is 3.12, and pip is
current.

Create the worker environment from the supplied example, insert the same Neon,
Upstash, and JWT values, then protect it:

```bash
sudo install -d -m 0750 -o root -g mindmate /etc/mindmate
cd /opt/mindmate/current
sudo install -m 0640 -o root -g mindmate deploy/mindmate-production.env.example /etc/mindmate/worker.env
sudoedit /etc/mindmate/worker.env
```

Keep `HF_HOME=/var/cache/mindmate/huggingface`. Preload both pinned models while
the environment file is loaded by a temporary systemd unit or start the worker and
let its first real job download them. The latter makes the first analysis slow but
avoids placing secrets in shell commands.

Install and start the service and timers:

```bash
cd /opt/mindmate/current
sudo cp deploy/systemd/mindmate-*.service deploy/systemd/mindmate-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mindmate-worker.service
sudo systemctl enable --now mindmate-recover-analysis.timer mindmate-cleanup-security.timer
sudo systemctl status mindmate-worker.service
sudo systemctl list-timers 'mindmate-*'
```

The service runs as `mindmate`, restarts after failure, receives graceful SIGTERM,
and only writes to the persistent Hugging Face cache. Inspect sanitized logs with:

```bash
sudo journalctl -u mindmate-worker.service --since today
```

Do not expose an RQ dashboard or any worker HTTP port.

## 7. End-to-end verification

1. Register, log in, log out, and log back in over HTTPS.
2. Verify Secure cookies, CSRF rejection with a bad token, and login rate limiting.
3. Create an entry and observe `pending`, then `processing`, then `completed`.
4. Confirm sentiment, RoBERTa emotion metadata, MiniLM embedding metadata, and
   themes are stored and displayed.
5. Edit the entry and verify a new analysis generation completes.
6. Verify history, detail, delete, dashboard, weekly summary, long-term analytics,
   export, and account deletion.
7. Stop the worker, create an entry, restart it, and confirm queued work resumes.
8. Run each maintenance service once and inspect only its aggregate counts:

   ```bash
   sudo systemctl start mindmate-recover-analysis.service
   sudo systemctl start mindmate-cleanup-security.service
   ```

## 8. Free-tier guardrails and known limitations

- Render Free, Neon Free, and Upstash Free do not provide production SLAs.
- Render may sleep/restart; Neon may scale to zero; Upstash rejects commands after
  its free command allowance; Oracle may reclaim an idle VM.
- Do not select Render Postgres, Render Key Value, Render background workers,
  Upstash Pay-as-you-go/Fixed, Neon Launch/Scale, Oracle non-eligible shapes,
  additional public IPs, load balancers, or GPU resources.
- Oracle account creation requires card verification. Neon Free states no card is
  required. Review every provider's final confirmation screen before creating a
  resource because pricing and limits can change.
- This stack is appropriate for a light portfolio demo, not dependable storage for
  real sensitive wellness data. Keep the demo-data expectation visible and verify
  backups/restores before inviting other people to use it.

Current provider references:

- Render Free: <https://render.com/docs/free>
- Render health checks: <https://render.com/docs/health-checks>
- Neon pricing: <https://neon.com/pricing>
- Neon pooled connections: <https://neon.com/docs/connect/connection-pooling>
- Upstash Redis pricing: <https://upstash.com/pricing/redis>
- Upstash security: <https://upstash.com/docs/redis/features/security>
- Oracle Always Free: <https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm>
- PyTorch Linux support: <https://docs.pytorch.org/get-started/locally/>
