# JupyterHub on Docker with Google OAuth, nginx proxy, and Let’s Encrypt

This stack runs a JupyterHub behind an `nginx` reverse proxy with automatic TLS via Let’s Encrypt, using Google (Workspace) OAuth for authentication and DockerSpawner for per-user notebook containers. It also mounts a large host workspace (e.g., `/workspace`) into user containers for models and datasets.

- Reverse proxy: `nginx-proxy` + `acme-companion` (auto certificates)
- Auth: Google OAuth2 (restricted to allowed Workspace domain(s))
- Hub: Custom image based on `jupyterhub/jupyterhub` with `oauthenticator` and `dockerspawner`
- Spawner: DockerSpawner (optional GPU support)
- Storage: Persistent Hub state + host `/workspace` bind mount

Tested target: Ubuntu Deep Learning Base AMI with Single CUDA (Ubuntu 22.04) 20251024.

## Architecture

- `nginx-proxy` terminates TLS on ports 80/443 and routes to Hub.
- `acme-companion` issues/renews Let’s Encrypt certificates automatically.
- `jupyterhub` runs on an internal port (8000) and spawns per-user notebook containers on the `jupyterhub-net` Docker network.
- User containers mount the host’s `/workspace` path for large models and data.
  JupyterLab opens in `/workspace` by default for convenience.

## Prerequisites

- A domain name pointing to your server’s public IP (A/AAAA record). Example: `jhub.example.com`.
- Ports 80 and 443 open to the internet (security group/firewall).
- Docker Engine and Docker Compose plugin installed.
- On the target AMI, NVIDIA drivers are present; for GPU in containers, also ensure the NVIDIA Container Toolkit is installed and working with Docker.
- A Google Cloud project (to create an OAuth client) and a Google Workspace domain for access control.

### NVIDIA Container Toolkit (for GPU, optional)
If your AMI does not already have the toolkit, install it following NVIDIA’s docs. On Ubuntu 22.04, summarized steps:

1. `curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg`
2. `curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
   sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
   sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list`
3. `sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit`
4. `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`

Verify with `docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi`.

## Repository Layout

- `docker-compose.yml` — Orchestrates proxy, certificates, and JupyterHub.
- `hub/Dockerfile` — Custom Hub image with OAuth + DockerSpawner.
- `hub/jupyterhub_config.py` — Hub config (Google OAuth, spawner, volumes, GPU).
- `hub/allowed_users.txt` — Optional list of Google account emails allowed to log in.
- `.env.example` — Template for required environment variables.
- `singleuser/` — Dockerfiles for Python 3.11 single-user images (CPU and GPU).

## Google OAuth Client Setup

1. In the Google Cloud console -> APIs & Services -> Credentials -> Create credentials -> OAuth client ID.
2. Application type: **Web application**; name: anything descriptive (e.g., “JupyterHub”).
3. Authorized redirect URI: `https://YOUR_DOMAIN/hub/oauth_callback`.
4. Configure the OAuth consent screen as **Internal** (restricts sign-in to your Workspace).
5. Create and copy the Client ID and Client Secret.

## Configuration

1. Copy the environment template and edit it:

   ```bash
   cp .env.example .env
   vi .env
   ```

   Required values:
   - `DOMAIN`: your DNS name (e.g., `jhub.example.com`).
   - `LETSENCRYPT_EMAIL`: email for certificate issuance/renewal notices.
   - `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`: from your OAuth client.
   - `OAUTH_CALLBACK_URL`: typically `https://${DOMAIN}/hub/oauth_callback`.
   - Access control (union — a user is allowed if they match any):
     - `ALLOWED_DOMAINS`: comma-separated Google Workspace domains, e.g. `nolabs.ai` (preferred; anyone in the domain is allowed).
     - `ALLOWED_USERS`: comma-separated Google account emails (additive to `ALLOWED_DOMAINS`).
     - `/srv/jupyterhub/allowed_users.txt`: emails, one per line.

   Optional values:
   - `ADMIN_USERS`: subset of allowed users with admin privileges.
   - `SINGLEUSER_IMAGE`: notebook image for user servers (default: Jupyter Docker Stacks).
   - `HOST_WORKSPACE`: path on the host to mount into user containers (default `/workspace`).
   - `ENABLE_GPU`: set to `true` to pass GPUs to user containers.

2. Prepare the host workspace directory:

   ```bash
   sudo mkdir -p /workspace
   sudo chown $USER:$(id -gn) /workspace
   ```

   For sharing between users, also create a shared subfolder that will appear as `~/Shared` in every user’s server:

   ```bash
   sudo mkdir -p /workspace/shared
   sudo chown $USER:$(id -gn) /workspace/shared
   ```

3. (Optional) If not using org-based access, you can manage allowed users via file:
   - Edit `hub/allowed_users.txt` (one GitHub username per line).
   - If `ALLOWED_USERS` is set in `.env`, it takes precedence over the file.

### Org-based access control

- Set `ALLOWED_ORGS` in `.env`, for example:

  ```ini
  ALLOWED_ORGS=my-org,my-org:platform-team
  ```

- The Hub requests the `read:org` scope so it can verify membership even when it is private.
- To use GitHub Teams, use `org:team` entries as above.
- Tip: If you were seeing "403: Forbidden" after successful GitHub auth, ensure `ALLOWED_USERS` is empty when using `ALLOWED_ORGS` (or remove it from `.env`).

## Launch

```bash
# Build the custom Hub image and start the stack
docker compose up -d --build

# Watch logs (first run will obtain certificates)
docker compose logs -f nginx-proxy acme-companion jupyterhub
```

Once certificates are issued and the proxy reloads, browse to:

- `https://YOUR_DOMAIN` — You should see the JupyterHub login (GitHub OAuth).

Log in with a GitHub account listed in `ALLOWED_USERS` (or in `hub/allowed_users.txt`).

## Shared notebooks between users

- A shared directory on the host `${HOST_WORKSPACE}/${SHARED_DIR}` (default `/workspace/shared`) is mounted read/write into every user’s home as `~/Shared`.
- Anything placed in `~/Shared` is immediately visible to all users. Use subfolders to organize projects.
- Permissions: since containers typically run as the same UID (`1000`), files in the shared folder are writable by everyone. If you want stricter control, consider:
  - Using Git + `nbgitpuller` for read-only distribution with version history.
  - Creating a read-only shared area by mounting a second directory with `:ro` (requires a small config tweak).
  - Using filesystem ACLs on the host to control write access.

## Python 3.11 single-user images

You asked for Python 3.11. This repo includes two single-user image options you can build locally:

- CPU-only: `singleuser/Dockerfile`
  - Build: `docker build -t singleuser:py311 -f singleuser/Dockerfile singleuser`
- GPU-enabled: `singleuser/Dockerfile.gpu` (CUDA 12.2 runtime on Ubuntu 22.04)
  - Build: `docker build -t singleuser:py311-cuda -f singleuser/Dockerfile.gpu singleuser`

Update `.env` accordingly:

```ini
# CPU
SINGLEUSER_IMAGE=singleuser:py311
# or GPU
# SINGLEUSER_IMAGE=singleuser:py311-cuda
```

Notes:
- Both images install `jupyterhub` (singleuser), `jupyterlab`, and `ipykernel` on Python 3.11.
- The GPU image relies on host GPU access (see GPU section) and includes CUDA user-space libraries from the base image.
- If you prefer a framework image (e.g., PyTorch/TensorFlow), use that as `SINGLEUSER_IMAGE` provided it has Python 3.11 and `jupyterhub-singleuser` available.

## Usage Notes

- New users get a dedicated Docker container launched by DockerSpawner.
- Each user container mounts the host’s `${HOST_WORKSPACE}` (default `/workspace`) at the same path inside the container and JupyterLab starts there by default.
- JupyterLab opens by default (`/lab`).

### GPU: host driver vs container CUDA

- Containers use the host’s NVIDIA kernel driver. You do NOT “use the host’s CUDA toolkit” directly inside the container.
- For GPU work, the container needs user‑space CUDA libraries (e.g., CUDA runtime, cuDNN, framework libs). Use a GPU‑enabled image.
- The NVIDIA Container Toolkit exposes the GPUs and driver libraries to containers (`--gpus` under the hood). We configure this via DockerSpawner’s device requests when `ENABLE_GPU=true`.
- Recommended flow:
  - Install NVIDIA Container Toolkit on the host (see Prerequisites) and verify: `docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi`.
  - Set `ENABLE_GPU=true` in `.env`.
  - Pick a GPU‑ready single user image in `.env`, for example one you build from `singleuser/Dockerfile.gpu` (`singleuser:py311-cuda`) or a vendor image that includes Python 3.11 and jupyterhub-singleuser.
  - Ensure your chosen image has JupyterLab. If not, build a small derivative that installs JupyterLab.

- In a notebook, verify with:

  ```python
  !nvidia-smi
  ```

### Changing the single-user image

Update `SINGLEUSER_IMAGE` in `.env` and restart the Hub:

```bash
docker compose up -d --build jupyterhub
```

Existing per-user home data persists in Docker volumes named `jupyterhub-user-USERNAME`.

## Operations

- Show status: `docker compose ps`
- Follow logs: `docker compose logs -f`
- Restart Hub: `docker compose restart jupyterhub`
- Rebuild Hub after config changes: `docker compose up -d --build jupyterhub`
- Stop stack: `docker compose down`
- Remove stack and volumes (destructive): `docker compose down -v`

### Adding/removing users

- Via environment: edit `ALLOWED_USERS` in `.env` and run `docker compose restart jupyterhub`.
- Via file: edit `hub/allowed_users.txt` inside the persistent volume path `/srv/jupyterhub/allowed_users.txt` (or re-copy from repo if volume is empty) and restart the Hub.

### Backups

- Hub state (DB + cookie secret) resides in the `jupyterhub_data` volume, mounted at `/srv/jupyterhub` in the container. Back up this volume regularly.
- User notebooks live inside Docker volumes created by DockerSpawner (`jupyterhub-user-USERNAME`) and any data in the bound `${HOST_WORKSPACE}` path.

## Troubleshooting

- 502/Bad Gateway: ensure `jupyterhub` is healthy and attached to the `proxy-tier` network.
- Certificates not issued: confirm DNS points to this host and ports 80/443 are reachable; check `acme-companion` logs.
- OAuth callback mismatch: verify `OAUTH_CALLBACK_URL` in `.env` exactly matches the GitHub OAuth App.
- GPU not visible: confirm NVIDIA Container Toolkit is configured; try `docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi` on the host; ensure the singleuser image supports CUDA.

## Security Notes

- Only listed GitHub usernames can log in. Keep `ALLOWED_USERS` up to date.
- The Hub’s cookie secret is persisted in the `jupyterhub_data` volume.
- Keep images up to date with `docker compose pull` and `docker compose up -d --build`.

## Uninstall / Cleanup

```bash
docker compose down -v
```

This stops all services and deletes the named volumes (`jupyterhub_data`, `nginx_*`). Be sure to back up any important data first. Your host `${HOST_WORKSPACE}` is a bind mount and is not removed.
