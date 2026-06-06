import os

from oauthenticator.github import GitHubOAuthenticator

c = get_config()  # noqa

# Base Hub settings
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000
c.JupyterHub.bind_url = 'http://:8000'
c.JupyterHub.base_url = os.environ.get('HUB_BASE_URL', '/')
c.JupyterHub.trust_xheaders = True
# User containers resolve the Hub by its container name on the shared network
c.JupyterHub.hub_connect_ip = os.environ.get('HUB_CONNECT_IP', 'jupyterhub')

# Persist cookie secret and database in the /srv/jupyterhub volume
c.JupyterHub.cookie_secret_file = '/srv/jupyterhub/jupyterhub_cookie_secret'
c.JupyterHub.db_url = 'sqlite:////srv/jupyterhub/jupyterhub.sqlite'

# Auth: GitHub OAuth
c.JupyterHub.authenticator_class = GitHubOAuthenticator
c.GitHubOAuthenticator.client_id = os.environ.get('GITHUB_CLIENT_ID')
c.GitHubOAuthenticator.client_secret = os.environ.get('GITHUB_CLIENT_SECRET')
c.GitHubOAuthenticator.oauth_callback_url = os.environ.get('OAUTH_CALLBACK_URL')
# Ensure org membership checks work even for private orgs
c.GitHubOAuthenticator.scope = ["read:org"]

# Access control - UNION semantics (oauthenticator >=16):
# A user is allowed if they match ANY of:
#   - ALLOWED_ORGS env (comma-separated, accepts "org" or "org:team")
#   - ALLOWED_USERS env (comma-separated GitHub usernames)
#   - /srv/jupyterhub/allowed_users.txt (one username per line, # comments ok)
#   - ADMIN_USERS env (admins always allowed)

allowed_orgs_env = os.environ.get('ALLOWED_ORGS', '')
allowed_orgs = [tok.strip() for tok in allowed_orgs_env.split(',') if tok.strip()]
if allowed_orgs:
    c.GitHubOAuthenticator.allowed_organizations = allowed_orgs

allowed_users_env = os.environ.get('ALLOWED_USERS', '')
allowed_users = {u.strip() for u in allowed_users_env.split(',') if u.strip()}

allow_file = '/srv/jupyterhub/allowed_users.txt'
if os.path.exists(allow_file):
    with open(allow_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            allowed_users.add(line)

admin_users_env = os.environ.get('ADMIN_USERS', '')
admin_users = {u.strip() for u in admin_users_env.split(',') if u.strip()}

if allowed_users:
    c.Authenticator.allowed_users = allowed_users
if admin_users:
    c.Authenticator.admin_users = admin_users
c.JupyterHub.admin_access = True

# Spawner: DockerSpawner for per-user containers
c.JupyterHub.spawner_class = 'dockerspawner.DockerSpawner'

singleuser_image = os.environ.get('SINGLEUSER_IMAGE', 'jupyter/datascience-notebook:latest')
c.DockerSpawner.image = singleuser_image
c.DockerSpawner.remove = True
c.DockerSpawner.debug = True
c.DockerSpawner.use_internal_ip = True
c.DockerSpawner.network_name = os.environ.get('DOCKER_NETWORK', 'jupyterhub-net')

# Mount host /workspace and a per-user home volume
host_workspace = os.environ.get('HOST_WORKSPACE', '/workspace')

# Set JupyterLab to open in the user's home directory
# /workspace is available but opening it by default causes issues with JupyterLab's file browser
c.Spawner.default_url = '/lab'
volumes = {
    host_workspace: {'bind': host_workspace, 'mode': 'rw'},
    'jupyterhub-user-{username}': '/home/jovyan',
}
# Optional shared area inside the host workspace, mounted into user home for convenience
shared_subdir = os.environ.get('SHARED_DIR', 'shared')
if shared_subdir:
    host_shared = os.path.join(host_workspace, shared_subdir)
    volumes[host_shared] = {'bind': '/home/jovyan/Shared', 'mode': 'rw'}
c.DockerSpawner.volumes = volumes

# Optional GPU support
enable_gpu = os.environ.get('ENABLE_GPU', 'false').lower() in {'1', 'true', 'yes', 'on'}
if enable_gpu:
    try:
        from docker.types import DeviceRequest
        c.DockerSpawner.extra_host_config = {
            'device_requests': [DeviceRequest(count=-1, capabilities=[["gpu"]])]
        }
        # Helpful environment hints for GPU containers
        extra_env = {
            'NVIDIA_VISIBLE_DEVICES': 'all',
            'NVIDIA_DRIVER_CAPABILITIES': 'compute,utility',
        }
        if getattr(c, 'Spawner', None) and hasattr(c.Spawner, 'environment') and isinstance(c.Spawner.environment, dict):
            c.Spawner.environment.update(extra_env)
        else:
            c.Spawner.environment = extra_env
    except Exception:
        # If Docker SDK is missing or older, continue without GPU host config
        pass
