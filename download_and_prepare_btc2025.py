import os
import requests
import zipfile
import pandas as pd
from datetime import datetime

BINANCE_URL = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-{}.zip"
DATA_DIR = "data"
OUT_FILE = os.path.join(DATA_DIR, "BTCUSDT_1m_2025_CSV.csv")

os.makedirs(DATA_DIR, exist_ok=True)

all_data = []

for month in range(1, 13):
    ym = f"2025-{month:02d}"
    zip_name = f"BTCUSDT-1m-{ym}.zip"
    csv_name = f"BTCUSDT-1m-{ym}.csv"
    zip_path = os.path.join(DATA_DIR, zip_name)
    csv_path = os.path.join(DATA_DIR, csv_name)
    url = BINANCE_URL.format(ym)
    print(f"Lade {url} ...")
    # Download ZIP falls nicht vorhanden
    if not os.path.exists(zip_path):
        r = requests.get(url)
        if r.status_code == 200:
            with open(zip_path, "wb") as f:
                f.write(r.content)
        else:
            print(f"Warnung: {url} nicht gefunden!")
            continue
    # Entpacken
    if not os.path.exists(csv_path):
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(DATA_DIR)
    # Einlesen
    df = pd.read_csv(csv_path, header=None)
    df.columns = [
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_asset_volume", "number_of_trades", "taker_buy_base", "taker_buy_quote", "ignore"
    ]
    # Zeitstempel umwandeln
    df['date'] = pd.to_datetime(df['open_time'], unit='ms')
    # Nur benötigte Spalten und Reihenfolge
    df_out = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
    df_out.rename(columns={'volume': 'volume eth'}, inplace=True)
    all_data.append(df_out)

# Alle Monate zusammenführen
final = pd.concat(all_data)
final = final.sort_values('date').reset_index(drop=True)

# Speichern im gewünschten Format
final.to_csv(OUT_FILE, index=False)
print(f"Fertig! Datei gespeichert unter: {OUT_FILE}") 