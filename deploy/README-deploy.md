This is mostly my notes on actions taken to deploy the service so I don't forget anything if I need to re-deploy it sometime or scour the files for some reason.

Create service user:
```bash
sudo useradd \
  --system \
  --home-dir /var/lib/courier-sprite \
  --create-home \
  --shell /usr/sbin/nologin \
  courier-sprite
```

Create config and cache directories:
```bash
sudo mkdir -p /etc/courier-sprite /var/cache/courier-sprite
```

Copy files (or create them):
```bash
sudo cp -av courier-sprite/deploy/config/* /etc/courier-sprite/
sudo cp -av courier-sprite/deploy/sbin/* /usr/local/sbin/
# If you had old state files in user directory
sudo cp -av ~/.local/state/courier-sprite/. /var/lib/courier-sprite/
```

Set up permissions:
```bash
# Configs
sudo chown -R root:courier-sprite /etc/courier-sprite
sudo chmod 750 /etc/courier-sprite
sudo find /etc/courier-sprite -type f -exec chmod 640 {} \;

# Cache & state
sudo chown -R courier-sprite:courier-sprite /var/lib/courier-sprite /var/cache/courier-sprite
sudo chmod 700 /var/lib/courier-sprite /var/cache/courier-sprite
```
Set up ssh using a github read-only access token (here named courier_sprite_pull, the public key must be inserted on github):
```bash
KEY=/var/lib/courier-sprite/.ssh/courier_sprite_pull
export GIT_SSH_COMMAND="ssh -i ${KEY} -o IdentitiesOnly=yes  -o StrictHostKeyChecking=accept-new"
sudo git clone git@github.com:RunnerHub/courier-sprite.git /opt/courier-sprite
```
Set up venv:
```bash
sudo mkdir -p /opt/.venvs
sudo chown root:root /opt/.venvs
sudo chmod 755 /opt/.venvs
sudo mkdir  /opt/.venvs/courier-sprite
sudo chown courier-sprite:courier-sprite /opt/.venvs/courier-sprite
sudo -u courier-sprite python3 -m venv /opt/.venvs/courier-sprite
# Needs pyproject.toml updates, see next code block for replacement
sudo -u courier-sprite /opt/.venvs/courier-sprite/bin/pip install -U pip
sudo -u courier-sprite /opt/.venvs/courier-sprite/bin/pip install /opt/courier-sprite
```
If pyproject.toml hasn't been updated (slight security risk to install python packages as root):
```bash
sudo /opt/.venvs/courier-sprite/bin/pip install -U pip
sudo /opt/.venvs/courier-sprite/bin/pip install /opt/courier-sprite
```

And finally... start the service:
```bash
sudo ln -sf /opt/courier-sprite/deploy/systemd/courier-sprite.service   /etc/systemd/system/courier-sprite.service
sudo systemctl daemon-reload
sudo systemctl enable --now courier-sprite
```