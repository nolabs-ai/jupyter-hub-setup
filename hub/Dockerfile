FROM jupyterhub/jupyterhub:5

# Install OAuth (Google/GitHub), DockerSpawner, and Docker Engine SDK
RUN pip install --no-cache-dir \
    oauthenticator>=16.0.0 \
    dockerspawner==14.0.0 \
    docker>=7.1.0

# Copy Hub configuration and optional allowed users seed file
COPY jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py
COPY allowed_users.txt /srv/jupyterhub/allowed_users.txt

WORKDIR /srv/jupyterhub
