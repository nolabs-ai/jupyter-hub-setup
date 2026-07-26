import os

from oauthenticator.google import GoogleOAuthenticator

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

# Auth: Google OAuth (Workspace). The login identity is the user's @nolabs.ai Google
# account == their GCP principal, so a hub-launched run is attributable to the same email
# used for provisioning, LAUNCHED_BY, and bucket namespacing. See training-infra#14 (pillar 4a).
c.JupyterHub.authenticator_class = GoogleOAuthenticator
c.GoogleOAuthenticator.client_id = os.environ.get('GOOGLE_CLIENT_ID')
c.GoogleOAuthenticator.client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
c.GoogleOAuthenticator.oauth_callback_url = os.environ.get('OAUTH_CALLBACK_URL')
# Login-only scope (4a). 4b adds https://www.googleapis.com/auth/cloud-platform +
# enable_auth_state to derive per-user gcloud creds in the container (separate change).
c.GoogleOAuthenticator.scope = ['openid', 'email']

# Access control - UNION semantics (oauthenticator >=16):
# A user is allowed if they match ANY of:
#   - ALLOWED_DOMAINS env (comma-separated Google Workspace domains, e.g. "nolabs.ai")
#   - ALLOWED_USERS env (comma-separated Google account emails)
#   - /srv/jupyterhub/allowed_users.txt (one email per line, # comments ok)
#   - ADMIN_USERS env (admins always allowed)

# Domain gate: hosted_domain restricts WHO may authenticate; allow_all then permits every
# authenticated (i.e. in-domain) user. Together = "anyone in an allowed Workspace domain".
allowed_domains_env = os.environ.get('ALLOWED_DOMAINS', '')
allowed_domains = [d.strip() for d in allowed_domains_env.split(',') if d.strip()]
if allowed_domains:
    c.GoogleOAuthenticator.hosted_domain = allowed_domains
    c.GoogleOAuthenticator.allow_all = True

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
