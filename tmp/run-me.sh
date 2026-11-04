#!/bin/bash
# Deploys bmc-interface to the hackathon BMA, using the Mosquitto broker on
# the hackathon Raspberry Pi (169.254.42.3, LAN cable) and the image built on
# that Pi. No registry, no docker compose (BMAv3 has none). Run from repo root.
# Before running:
#   1. cp deploy/bmc-interface/shared/configuration.example.json \
#         deploy/bmc-interface/shared/configuration.json
#      and replace <MQTT_PASSWORD> (file is gitignored).
#   2. Control Center: BMA G-A2610-0007 -> uncheck "IO-device" -> Save.
set -euo pipefail

HOST=G-A2610-0007
LOCAL_DIR=deploy/bmc-interface
# Relative to the remote home directory; works with every scp protocol.
REMOTE_DIR=bmc-interface
BROKER=169.254.42.3
BROKER_PORT=1883
BROKER_CHECK="import socket; socket.create_connection(('$BROKER', $BROKER_PORT), 5); print('broker $BROKER:$BROKER_PORT reachable')"
# One SSH connection for all steps, so the password is asked only once.
SSH_OPTS=(-o ControlMaster=auto -o "ControlPath=$HOME/.ssh/cm-%r@%h:%p" -o ControlPersist=300)
# Image built on the hackathon Pi from vendor/bmc-interface (see README).
PI_SSH=(-i "$HOME/.ssh/id_rsa" -o IdentitiesOnly=yes pi@hackathon.local)
IMAGE=bmc-interface:hackathon
IMAGE_PINNED=bmc-interface:4fc8393

config="$LOCAL_DIR/shared/configuration.json"
if [ ! -f "$config" ]; then
  echo "Missing $config - copy it from configuration.example.json first." >&2
  exit 1
fi
if grep -q '<MQTT_' "$config"; then
  echo "$config still contains <MQTT_...> placeholders." >&2
  exit 1
fi

echo "== 0/6 Image present on the Pi?"
ssh "${PI_SSH[@]}" "docker image inspect $IMAGE --format '$IMAGE {{.Architecture}} {{.Size}}'" \
  || { echo "Build the image on the Pi first (see deploy/bmc-interface/README.md)." >&2; exit 1; }

echo "== 1/6 Checks on $HOST (read-only)"
# set -e: abort on the first failing check, not only on the last one.
# The node id file is root-only on the BMA, hence sudo.
ssh -t "${SSH_OPTS[@]}" "$HOST" "
  set -e
  docker version --format 'docker engine {{.Server.Version}}'
  sudo python3 -c \"import json; print('node id (target_uuid):', json.load(open('/opt/swarm/config/urban_traffic_config.json'))['node']['id'])\"
  python3 -c \"$BROKER_CHECK\"
"

echo "== 2/6 Is /dev/ttyAMA2 free? (exit 0 = free, 3 = busy)"
set +e
ssh -t "${SSH_OPTS[@]}" "$HOST" \
  "sudo sh -c 'fuser /dev/ttyAMA2 >/dev/null 2>&1 && exit 3; exit 0'"
port_state=$?
set -e
if [ "$port_state" -eq 3 ]; then
  echo "/dev/ttyAMA2 is still in use (curiosity?). Disable IO-device first." >&2
  exit 1
elif [ "$port_state" -ne 0 ]; then
  echo "Port check failed (sudo?), exit code $port_state." >&2
  exit 1
fi

echo "== 3/6 Copy files"
ssh "${SSH_OPTS[@]}" "$HOST" "mkdir -p $REMOTE_DIR/shared"
scp "${SSH_OPTS[@]}" "$LOCAL_DIR/start.sh" "$HOST:$REMOTE_DIR/"
scp "${SSH_OPTS[@]}" "$config" "$HOST:$REMOTE_DIR/shared/"

echo "== 4/6 Copy the image built on the Pi to the BMA (no registry)"
# The image id is a content hash: equal ids mean the BMA already has it.
pi_id=$(ssh "${PI_SSH[@]}" "docker image inspect $IMAGE --format '{{.Id}}'")
bma_id=$(ssh "${SSH_OPTS[@]}" "$HOST" "docker image inspect $IMAGE --format '{{.Id}}' 2>/dev/null || true")
if [ "$pi_id" = "$bma_id" ]; then
  echo "BMA already has $IMAGE ($pi_id), skipping transfer"
else
  # Pi: docker save | gzip  --ssh-->  laptop  --ssh-->  BMA: gunzip | docker load
  ssh "${PI_SSH[@]}" "docker save $IMAGE $IMAGE_PINNED | gzip -1" \
    | ssh "${SSH_OPTS[@]}" "$HOST" "gunzip | docker load"
fi

echo "== 5/6 Can a container reach the broker? (throwaway container, host network like start.sh)"
ssh -t "${SSH_OPTS[@]}" "$HOST" \
  "docker run --rm --network host --entrypoint python3 $IMAGE -c \"$BROKER_CHECK\""

echo "== 6/6 Start and follow logs (Ctrl+C stops following; the container keeps running)"
ssh -t "${SSH_OPTS[@]}" "$HOST" "
  sh $REMOTE_DIR/start.sh &&
  docker logs -f --tail 50 bmc-interface
"
