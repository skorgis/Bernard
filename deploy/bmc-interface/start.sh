#!/bin/sh
# Starts bmc-interface on BMA G-A2610-0007 (Raspberry Pi CM5) for the Tirol
# hackathon. BMAv3 has no `docker compose`, so this is plain `docker run`.
# Differences from upstream bernard-technologies/bmc-interface:
# - Locally built image (on the hackathon Pi, from vendor/bmc-interface,
#   copied with `docker save | docker load`) instead of swarm.azurecr.io.
# - The BMC hangs on /dev/ttyAMA2 on the CM5; bmc-interface hard-codes the
#   Jetson port /dev/ttyTHS2, so the device is exposed under that name.
# - No env file: the only runtime variable is ALERT_MONITOR_TOKEN, and without
#   it no alert e-mails are sent, which is intended for the hackathon.
# - Host network: from the Docker bridge, the broker on the Pi (169.254.42.3,
#   eth0) times out (forwarded traffic is blocked on the BMA), while the host
#   itself reaches it. bmc-interface only opens outgoing connections.
set -eu

IMAGE=bmc-interface:hackathon
NAME=bmc-interface
cd "$(dirname "$0")"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Image $IMAGE missing - copy it from the Pi first." >&2
  exit 1
fi
if [ ! -f shared/configuration.json ]; then
  echo "shared/configuration.json missing." >&2
  exit 1
fi

# Replaces a previous instance; the restart policy brings it back after reboot.
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --network host \
  -e PYTHONUNBUFFERED=1 \
  -v "$(pwd)/shared:/app/shared" \
  -v /opt/swarm/config:/opt/swarm/config:ro \
  --device /dev/ttyAMA2:/dev/ttyTHS2:rwm \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
  "$IMAGE"
