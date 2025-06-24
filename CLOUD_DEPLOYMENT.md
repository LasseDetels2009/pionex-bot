# 🌐 Cloud Deployment Guide für Pionex Futures Grid Bot

Dieser Guide zeigt dir, wie du deinen Pionex Futures Grid Bot auf verschiedenen Cloud-Plattformen deployen kannst, damit er 24/7 läuft ohne deinen Laptop anlassen zu müssen.

## 🚀 Schnellstart

### 1. Vorbereitung

```bash
# Repository klonen (falls noch nicht geschehen)
git clone <your-repo-url>
cd V1_Futures_Grid_Bot

# Environment-Datei erstellen
cp env.example .env
```

### 2. API Keys konfigurieren

Bearbeite die `.env` Datei mit deinen API Keys:

```bash
nano .env
```

Fülle folgende Felder aus:
- `TELEGRAM_BOT_TOKEN`: Dein Telegram Bot Token
- `TELEGRAM_CHAT_ID`: Deine Chat ID
- `BINANCE_API_KEY`: Binance API Key (für Live-Daten)
- `BINANCE_SECRET_KEY`: Binance Secret Key
- `PIONEX_API_KEY`: Pionex API Key (für Trading)
- `PIONEX_SECRET_KEY`: Pionex Secret Key

### 3. Deployment ausführen

```bash
# Deployment-Script ausführbar machen
chmod +x deploy.sh

# Deployment starten
./deploy.sh
```

## ☁️ Cloud Provider Optionen

### Option 1: DigitalOcean (Empfohlen für Anfänger)

**Vorteile:**
- Einfach zu bedienen
- Günstige Preise (ab $5/Monat)
- Gute Performance
- 24/7 Support

**Schritte:**
1. Account auf [DigitalOcean](https://digitalocean.com) erstellen
2. Droplet erstellen:
   - Ubuntu 22.04 LTS
   - Basic Plan: $5/Monat (1GB RAM, 1 CPU)
   - Datacenter: Frankfurt (niedrige Latenz)
3. SSH-Zugang einrichten
4. Repository auf Server klonen
5. `./deploy.sh` ausführen und Option 2 wählen

**Kosten:** ~$5-10/Monat

### Option 2: AWS EC2 (Professionell)

**Vorteile:**
- Sehr zuverlässig
- Skalierbar
- Viele Services
- Free Tier verfügbar

**Schritte:**
1. AWS Account erstellen
2. EC2 Instance erstellen:
   - Amazon Linux 2 oder Ubuntu
   - t3.micro (Free Tier) oder t3.small
   - Security Group: Port 22, 80, 443, 5000 öffnen
3. SSH-Zugang einrichten
4. Repository deployen
5. `./deploy.sh` ausführen und Option 1 wählen

**Kosten:** $0-15/Monat (je nach Instance)

### Option 3: Google Cloud Platform

**Vorteile:**
- Gute Performance
- Free Tier
- Einfache Bedienung

**Schritte:**
1. GCP Account erstellen
2. Compute Engine VM erstellen:
   - Ubuntu 22.04
   - e2-micro (Free Tier) oder e2-small
3. Firewall-Regeln konfigurieren
4. Repository deployen
5. `./deploy.sh` ausführen und Option 3 wählen

**Kosten:** $0-10/Monat

### Option 4: Azure

**Vorteile:**
- Microsoft-Ökosystem
- Gute Integration
- Free Tier

**Schritte:**
1. Azure Account erstellen
2. Virtual Machine erstellen:
   - Ubuntu Server 22.04
   - B1s (Free Tier) oder B2s
3. Network Security Group konfigurieren
4. Repository deployen
5. `./deploy.sh` ausführen und Option 4 wählen

**Kosten:** $0-12/Monat

### Option 5: VPS Provider (Contabo, Hetzner, etc.)

**Vorteile:**
- Sehr günstig
- Gute Performance
- Direkter Support

**Empfohlene Provider:**
- **Contabo**: Ab €4/Monat (4GB RAM, 2 CPU)
- **Hetzner**: Ab €3/Monat (2GB RAM, 1 CPU)
- **OVH**: Ab €3/Monat (2GB RAM, 1 CPU)

**Schritte:**
1. VPS bei gewähltem Provider mieten
2. Ubuntu 22.04 installieren
3. SSH-Zugang einrichten
4. Repository deployen
5. `./deploy.sh` ausführen und Option 5 wählen

## 🔧 Erweiterte Konfiguration

### SSL-Zertifikat einrichten

Für sichere Telegram Webhooks:

```bash
# Im deploy.sh Script Option 7 wählen
# Domain eingeben (z.B. bot.yourdomain.com)
# Let's Encrypt Zertifikat wird automatisch installiert
```

### Monitoring einrichten

Das Deployment-Script installiert automatisch:
- **Prometheus**: Metriken-Sammlung
- **Grafana**: Dashboard und Visualisierung

Zugang:
- Grafana: `http://your-ip:3000` (admin/admin123)
- Prometheus: `http://your-ip:9090`

### Backup-Strategie

```bash
# Automatisches Backup erstellen
mkdir -p backups
crontab -e

# Täglich um 2 Uhr Backup erstellen
0 2 * * * tar -czf /home/user/backups/bot-$(date +\%Y\%m\%d).tar.gz /app/data /app/logs
```

## 📊 Monitoring und Wartung

### Bot-Status prüfen

```bash
# Status anzeigen
./deploy.sh  # Option 8

# Oder direkt
sudo docker-compose ps
sudo docker-compose logs --tail=50 pionex-bot
```

### Bot neu starten

```bash
# Bot stoppen
./deploy.sh  # Option 9

# Bot starten
./deploy.sh  # Option 10

# Oder direkt
sudo docker-compose restart
```

### Updates installieren

```bash
# Bot updaten
./deploy.sh  # Option 11

# Oder direkt
git pull
sudo docker-compose down
sudo docker-compose up -d --build
```

## 🔒 Sicherheit

### Firewall konfigurieren

```bash
# UFW Firewall aktivieren
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw allow 5000
sudo ufw allow 3000
sudo ufw allow 9090
```

### SSH-Sicherheit

```bash
# SSH-Konfiguration sichern
sudo nano /etc/ssh/sshd_config

# Folgende Zeilen ändern:
Port 2222  # Standard-Port ändern
PermitRootLogin no
PasswordAuthentication no
```

### API Keys schützen

```bash
# .env Datei schützen
chmod 600 .env
chown root:root .env
```

## 💰 Kostenoptimierung

### Günstigste Optionen:

1. **Contabo VPS**: €4/Monat (4GB RAM, 2 CPU)
2. **Hetzner VPS**: €3/Monat (2GB RAM, 1 CPU)
3. **AWS Free Tier**: $0/Monat (12 Monate)
4. **Google Cloud Free Tier**: $0/Monat (12 Monate)

### Ressourcen-Optimierung:

```bash
# Docker-Images bereinigen
sudo docker system prune -a

# Logs rotieren
sudo logrotate /etc/logrotate.d/docker
```

## 🚨 Troubleshooting

### Häufige Probleme:

**Bot startet nicht:**
```bash
# Logs prüfen
sudo docker-compose logs pionex-bot

# Environment prüfen
cat .env

# Ports prüfen
sudo netstat -tlnp | grep :5000
```

**Telegram Webhook funktioniert nicht:**
```bash
# SSL-Zertifikat prüfen
sudo certbot certificates

# Webhook-URL prüfen
curl -X POST https://your-domain.com/webhook
```

**Hohe CPU-Last:**
```bash
# Ressourcen prüfen
htop
sudo docker stats

# Container neu starten
sudo docker-compose restart
```

### Support:

- **Logs**: `sudo docker-compose logs -f pionex-bot`
- **Status**: `sudo docker-compose ps`
- **Ressourcen**: `sudo docker stats`

## 📱 Telegram-Befehle

Nach dem Deployment kannst du den Bot über Telegram steuern:

- `/start` - Bot starten
- `/stop` - Bot stoppen
- `/status` - Status anzeigen
- `/balance` - Kontostand anzeigen
- `/positions` - Offene Positionen
- `/trades` - Letzte Trades
- `/config` - Konfiguration anzeigen
- `/restart` - Bot neu starten
- `/help` - Hilfe anzeigen

## 🎯 Empfehlung

**Für Anfänger:** DigitalOcean Droplet ($5/Monat)
**Für Profis:** AWS EC2 t3.small ($15/Monat)
**Für Budget:** Contabo VPS (€4/Monat)

Alle Optionen bieten 24/7 Laufzeit und automatische Neustarts bei Problemen. 