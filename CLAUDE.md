# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Docker-based JupyterHub deployment with nginx reverse proxy, Let's Encrypt TLS, and Google (Workspace) OAuth authentication. Uses DockerSpawner to create per-user notebook containers with optional GPU support.

## Architecture

```
Internet -> nginx-proxy (TLS termination) -> jupyterhub (port 8000) -> DockerSpawner -> user containers
                |
          acme-companion (auto-renews Let's Encrypt certs)
```

- **proxy-tier network**: connects nginx-proxy, acme-companion, and jupyterhub
- **jupyterhub-net network**: connects jupyterhub to spawned user containers
- User containers mount host `/workspace` and get a persistent home volume (`jupyterhub-user-{username}`)

## Common Commands

```bash
# Build and start the full stack
docker compose up -d --build

# Watch logs during startup (especially for cert issuance)
docker compose logs -f nginx-proxy acme-companion jupyterhub

# Rebuild hub after config changes
docker compose up -d --build jupyterhub

# Restart hub (e.g., after changing allowed users)
docker compose restart jupyterhub

# Stop everything
docker compose down

# Full cleanup including volumes (destructive)
docker compose down -v
```

### Building Single-User Images

```bash
# CPU-only Python 3.11
docker build -t singleuser:py311 -f singleuser/Dockerfile singleuser

# GPU-enabled Python 3.11 (CUDA 12.2)
docker build -t singleuser:py311-cuda -f singleuser/Dockerfile.gpu singleuser
```

## Key Configuration Files

- `.env` - All environment variables (copy from `.env.example`)
- `hub/jupyterhub_config.py` - Hub configuration (OAuth, spawner, volumes, GPU)
- `hub/allowed_users.txt` - Fallback allowed users list (if `ALLOWED_USERS` env var empty)

## Access Control

Union semantics (a user is allowed if they match any):
1. **Domain-based** (`ALLOWED_DOMAINS`): comma-separated Google Workspace domains (e.g. `nolabs.ai`)
2. **User-based** (`ALLOWED_USERS`): comma-separated Google account emails, or via `hub/allowed_users.txt`

## GPU Configuration

Requires NVIDIA Container Toolkit on host. Set `ENABLE_GPU=true` in `.env` and use a CUDA-enabled singleuser image (`singleuser:py311-cuda` or similar).
