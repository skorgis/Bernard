# Parkleitsystem als Docker-Container auf dem Pi

Stand: 04.11.2026

Die [Musterlösung](../../Musterloesung/README.md) läuft als Container
`parkleitsystem` auf dem Raspberry Pi `hackathon.local`, neben dem
[MQTT-Broker](../pi-broker/README.md). Sie schaltet die LED hinter jedem
belegten Parkplatz ein und lässt bei einer Einfahrt die LED des empfohlenen
Platzes blinken. Ein Schild ist nicht angeschlossen (`[display] enabled =
false`).

- Netzwerk: `network_mode: host`, der Broker ist als `localhost:1883`
  erreichbar.
- `restart: unless-stopped`: startet nach einem Neustart des Pi wieder.
- Zugangsdaten in `.env`, Konfiguration in `config.toml`; beide liegen nur
  auf dem Pi und sind nicht im Repository.

## Einrichtung

1. Quellen auf den Pi kopieren (vom Laptop, Repository-Root). Der Build
   braucht das Hauptpaket (`src/`) und die Musterlösung:

```bash
rsync -a --relative --delete \
--exclude .venv --exclude __pycache__ --exclude .pytest_cache \
--exclude .ruff_cache --exclude Musterloesung/config.toml \
--exclude deploy/parkleitsystem/.env \
--exclude deploy/parkleitsystem/config.toml \
-e 'ssh -i ~/.ssh/id_rsa -o IdentitiesOnly=yes' \
./pyproject.toml ./README.md ./src ./Musterloesung ./deploy/parkleitsystem \
pi@hackathon.local:tirol-hackathon/
```

2. Auf dem Pi Konfiguration und Zugangsdaten anlegen (einmalig):

```bash
cd ~/tirol-hackathon/deploy/parkleitsystem
```

```bash
cp ../../Musterloesung/config.example.toml config.toml
```

```bash
read -rs MQTT_PASSWORD && (umask 077 && \
printf 'MQTT_USER=hackathon\nMQTT_PASSWORD=%s\n' "$MQTT_PASSWORD" > .env)
```

3. Bauen und starten:

```bash
docker compose up -d --build
```

## Betrieb

Log ansehen (jede LED-Schaltung und jede Einfahrt erscheint dort):

```bash
docker logs -f parkleitsystem
```

Was bmc-interface auf dem BMA tatsächlich geschaltet hat:

```bash
mosquitto_sub -h localhost -u hackathon -P "$MQTT_PASSWORD" \
-t bmc_interface/tirol-hackathon/events -v
```

Nach einer Änderung an `config.toml` reicht ein Neustart, nach einer
Code-Änderung Schritt 1 und 3:

```bash
docker compose restart
```

Stoppen:

```bash
docker compose down
```

## Schild nachrüsten

Sobald das TFT angeschlossen ist: In `config.toml` `enabled = true` setzen, im
`Dockerfile` `uv sync --frozen --no-dev --extra pi` verwenden und dem Dienst in
`docker-compose.yml` die Geräte `/dev/spidev0.0` und `/dev/gpiochip0`
freigeben (Abschnitt `devices`). Der Container-Benutzer braucht dann Zugriff
auf diese Geräte (Gruppen `spi` und `gpio` des Pi).
