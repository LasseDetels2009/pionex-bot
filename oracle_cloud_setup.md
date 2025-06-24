# 🆓 Oracle Cloud Free Tier Setup Guide

## Kostenlose 24/7 Bot-Hosting Lösung

Oracle Cloud bietet **für immer kostenlose** VM-Instances - perfekt für deinen Trading Bot!

## 🚀 Schnellstart (5 Minuten)

### 1. Oracle Cloud Account erstellen

1. Gehe zu [cloud.oracle.com](https://cloud.oracle.com)
2. Klicke "Start for free"
3. Fülle die Registrierung aus (Kreditkarte erforderlich, aber keine Kosten)
4. Bestätige deine E-Mail

### 2. VM Instance erstellen

1. **Compute → Instances → Create Instance**
2. **Name:** `pionex-bot`
3. **Image:** Canonical Ubuntu 22.04
4. **Shape:** VM.Standard.A1.Flex (Always Free)
   - OCPU: 1
   - Memory: 6GB
5. **Network:** Create new VCN
6. **Public IP:** Yes
7. **Create**

### 3. SSH-Zugang einrichten

```bash
# SSH-Key generieren (falls noch nicht vorhanden)
ssh-keygen -t rsa -b 2048 -C "oracle-cloud"

# Öffentlichen Key anzeigen
cat ~/.ssh/id_rsa.pub
```

Kopiere den öffentlichen Key in Oracle Cloud Console → Compute → Instances → Edit → Add SSH Key

### 4. Bot deployen

```bash
# Mit SSH verbinden
ssh ubuntu@your-instance-ip

# System updaten
sudo apt update && sudo apt upgrade -y

# Git installieren
sudo apt install git -y

# Repository klonen
git clone <your-repo-url>
cd V1_Futures_Grid_Bot

# Environment-Datei erstellen
cp env.example .env
nano .env
```

### 5. API Keys konfigurieren

Bearbeite die `.env` Datei:

```bash
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
WEBHOOK_URL=https://your-instance-ip:5000/webhook

# Binance API Configuration
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_SECRET_KEY=your_binance_secret_key_here

# Pionex API Configuration
PIONEX_API_KEY=your_pionex_api_key_here
PIONEX_SECRET_KEY=your_pionex_secret_key_here

# Bot Configuration
TRADING_MODE=paper
LOG_LEVEL=INFO
```

### 6. Bot starten

```bash
# Deployment-Script ausführbar machen
chmod +x deploy.sh

# Bot deployen
./deploy.sh
# Option 5 (VPS) wählen
```

### 7. Firewall konfigurieren

```bash
# UFW Firewall aktivieren
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 5000
sudo ufw allow 3000
sudo ufw allow 9090
```

## 🔧 Erweiterte Konfiguration

### Automatischer Start

```bash
# Systemd Service erstellen
sudo nano /etc/systemd/system/pionex-bot.service
```

```ini
[Unit]
Description=Pionex Futures Grid Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/V1_Futures_Grid_Bot
ExecStart=/usr/bin/python3 run_pionex_bot.py --mode live
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Service aktivieren
sudo systemctl enable pionex-bot
sudo systemctl start pionex-bot
sudo systemctl status pionex-bot
```

### Monitoring einrichten

```bash
# Prometheus und Grafana installieren
sudo docker-compose up -d prometheus grafana

# Zugang:
# Grafana: http://your-ip:3000 (admin/admin123)
# Prometheus: http://your-ip:9090
```

### Backup-Strategie

```bash
# Automatisches Backup
mkdir -p ~/backups
crontab -e

# Täglich um 2 Uhr Backup
0 2 * * * tar -czf ~/backups/bot-$(date +\%Y\%m\%d).tar.gz ~/V1_Futures_Grid_Bot/data ~/V1_Futures_Grid_Bot/logs
```

## 📊 Kostenübersicht

| Service | Kosten | Dauer |
|---------|--------|-------|
| **VM Instance** | $0 | Für immer |
| **Storage** | $0 | 200GB |
| **Bandwidth** | $0 | 10TB/Monat |
| **Gesamt** | **$0** | **Für immer!** |

## 🚨 Wichtige Hinweise

### Oracle Cloud Limits:
- **2 AMD Instances** (immer kostenlos)
- **24GB RAM** gesamt
- **200GB Storage**
- **10TB Bandwidth/Monat**

### Sicherheit:
```bash
# SSH-Port ändern
sudo nano /etc/ssh/sshd_config
# Port 2222
sudo systemctl restart ssh

# Firewall aktualisieren
sudo ufw allow 2222
sudo ufw deny 22
```

### Monitoring:
```bash
# Bot-Status prüfen
sudo systemctl status pionex-bot

# Logs anzeigen
sudo journalctl -u pionex-bot -f

# Ressourcen prüfen
htop
df -h
```

## 🎯 Vorteile von Oracle Cloud Free Tier

✅ **Für immer kostenlos**  
✅ **Keine versteckten Kosten**  
✅ **Gute Performance**  
✅ **24/7 Verfügbarkeit**  
✅ **Automatische Backups**  
✅ **Skalierbar**  

## 📱 Telegram-Befehle

Nach dem Deployment:

- `/start` - Bot starten
- `/stop` - Bot stoppen  
- `/status` - Status anzeigen
- `/balance` - Kontostand
- `/positions` - Offene Positionen
- `/trades` - Letzte Trades
- `/restart` - Bot neu starten

## 🆘 Troubleshooting

### Bot startet nicht:
```bash
# Logs prüfen
sudo journalctl -u pionex-bot -f

# Manuell testen
cd ~/V1_Futures_Grid_Bot
python3 run_pionex_bot.py --mode live
```

### SSH-Verbindung funktioniert nicht:
```bash
# Firewall prüfen
sudo ufw status

# SSH-Service prüfen
sudo systemctl status ssh
```

### Hohe CPU-Last:
```bash
# Prozesse prüfen
htop

# Bot neu starten
sudo systemctl restart pionex-bot
```

## 🎉 Ergebnis

Nach diesem Setup hast du:
- **Kostenlosen 24/7 Trading Bot**
- **Automatische Neustarts**
- **Monitoring und Logs**
- **Telegram-Steuerung**
- **Backup-Strategie**

**Gesamtkosten: $0 für immer!** 🆓 