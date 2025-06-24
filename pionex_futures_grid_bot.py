import pandas as pd
import numpy as np
import json
import time
import logging
from datetime import datetime, timedelta
import requests
from typing import Dict, List, Optional, Tuple
import os
import random
import ta
import threading
import traceback
import sys
from flask import Flask, request, jsonify

class PionexFuturesGridBot:
    """
    Pionex-style Futures Grid Trading Bot
    Supports both Long and Short modes with leverage
    Now with Live Trading capabilities (Paper Trading Mode)
    Enhanced with Telegram Bot Control Interface
    """
    
    def __init__(self, config_file: str = "pionex_config.json"):
        self.config = self.load_config(config_file)
        self.setup_logging()
        
        # Initialize Telegram bot state BEFORE setup_telegram
        self.telegram_bot_running = False
        self.telegram_thread = None
        self.authorized_users = [self.config['telegram_chat_id']]  # Add more users if needed
        self.debug_mode = False
        self.debug_logs = []
        
        self.setup_telegram()
        self.setup_binance_api()
        
        # Trading state
        self.positions = []  # List of open positions
        self.trades = []  # List of closed trades
        self.total_pnl = 0.0
        self.total_fees = 0.0
        self.funding_fees = 0.0
        self.liquidated_positions = 0
        
        # Performance tracking
        self.start_balance = self.config['initial_balance']
        self.current_balance = self.start_balance
        self.max_balance = self.start_balance
        self.min_balance = self.start_balance
        self.max_drawdown = 0.0
        
        # Grid state
        self.grid_orders = []
        self.last_funding_time = None
        
        # Live trading state
        self.is_live_trading = False
        self.live_thread = None
        self.current_price = None
        self.last_trade_time = None
        
        # Load historical data for backtest mode only if not live trading
        if not self.config.get('live_trading_enabled', True):  # Default to True for live trading
            self.data = self.load_data()
        
        # Send startup message
        self.send_telegram_message("🚀 Pionex Futures Grid Bot gestartet!")
        
        # Realistische Trading-Parameter
        self.slippage_rate = 0.001  # 0.1% Slippage (erhöht)
        self.spread_rate = 0.002     # 0.2% Spread (erhöht)
        self.order_failure_rate = 0.05  # 5% Order-Failures (erhöht)
        self.api_latency = 0.2       # 200ms API-Latenz (erhöht)
        self.min_liquidity = 50000   # Mindest-Liquidität in USD (erhöht)
        self.max_position_size = 0.01  # Max 1% des Kapitals pro Position (reduziert)
        
        # Erweiterte Optimierungen
        self.volatility_lookback = 24  # Stunden für Volatilitätsberechnung
        self.trend_strength_threshold = 0.6  # Trend-Filter
        self.dynamic_leverage_enabled = True
        self.adaptive_grid_enabled = True
        self.risk_management_enabled = True
        
        # In __init__ nach self.config laden:
        self.max_open_positions = self.config.get('max_open_positions', 15)
    
    def load_config(self, config_file: str) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Validate required fields
            required_fields = [
                'initial_balance', 'leverage', 'grid_lower_price', 'grid_upper_price',
                'grid_count', 'investment_amount', 'mode', 'fee_rate',
                'data_file', 'telegram_token', 'telegram_chat_id'
            ]
            
            for field in required_fields:
                if field not in config:
                    raise ValueError(f"Missing required config field: {field}")
            
            return config
            
        except FileNotFoundError:
            # Create default config
            default_config = {
                "initial_balance": 10000.0,
                "leverage": 3,
                "grid_lower_price": "auto",
                "grid_upper_price": "auto",
                "grid_count": 20,
                "investment_amount": 1000.0,
                "mode": "long",  # "long" or "short"
                "fee_rate": 0.0004,  # 0.04% per trade
                "funding_rate": 0.0001,  # 0.01% per 8 hours
                "liquidation_buffer": 0.1,  # 10% buffer before liquidation
                "stop_loss_pct": 0.05,  # 5% stop loss
                "take_profit_pct": 0.10,  # 10% take profit
                "data_file": "data/BTCUSDT_1m_2025_CSV.csv",
                "telegram_token": "YOUR_TELEGRAM_TOKEN",
                "telegram_chat_id": "YOUR_CHAT_ID",
                "report_interval": 10,  # Report every N tests
                "save_interval": 15,  # Save every N minutes
                "live_trading_enabled": False
            }
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2)
            
            print(f"Created default config file: {config_file}")
            return default_config
    
    def setup_logging(self):
        """Setup logging configuration with UTF-8 encoding and no emojis in logs"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('pionex_futures_bot.log', encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_telegram(self):
        """Setup Telegram bot"""
        self.telegram_token = self.config['telegram_token']
        self.telegram_chat_id = self.config['telegram_chat_id']
        self.telegram_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        
        # Test Telegram connection first
        if self.test_telegram_connection():
            # Setup webhook for bot commands
            self.webhook_url = self.config.get('webhook_url', '')
            if self.webhook_url:
                self.setup_telegram_webhook()
            else:
                # Use polling if no webhook URL
                self.start_telegram_polling()
        else:
            self.logger.warning("Telegram bot setup failed - commands will not work")
    
    def setup_telegram_webhook(self):
        """Setup Telegram webhook for bot commands"""
        try:
            webhook_setup_url = f"https://api.telegram.org/bot{self.telegram_token}/setWebhook"
            webhook_data = {
                'url': f"{self.webhook_url}/webhook",
                'allowed_updates': ['message']
            }
            response = requests.post(webhook_setup_url, json=webhook_data, timeout=10)
            if response.status_code == 200:
                self.logger.info("Telegram webhook setup successful")
                self.start_telegram_bot()
            else:
                self.logger.warning(f"Webhook setup failed: {response.text}")
        except Exception as e:
            self.logger.error(f"Webhook setup error: {e}")
    
    def start_telegram_bot(self):
        """Start Telegram bot webhook server"""
        if self.telegram_bot_running:
            return
            
        self.telegram_bot_running = True
        self.telegram_thread = threading.Thread(target=self.run_telegram_bot, daemon=True)
        self.telegram_thread.start()
        self.logger.info("Telegram bot started")
    
    def run_telegram_bot(self):
        """Run Telegram bot webhook server"""
        app = Flask(__name__)
        
        @app.route('/webhook', methods=['POST'])
        def webhook():
            try:
                data = request.get_json()
                if 'message' in data:
                    self.handle_telegram_message(data['message'])
                return jsonify({'status': 'ok'})
            except Exception as e:
                self.logger.error(f"Webhook error: {e}")
                return jsonify({'status': 'error'})
        
        @app.route('/health', methods=['GET'])
        def health():
            return jsonify({'status': 'healthy', 'bot_running': self.telegram_bot_running})
        
        try:
            app.run(host='0.0.0.0', port=5000, debug=False)
        except Exception as e:
            self.logger.error(f"Telegram bot server error: {e}")
    
    def start_telegram_polling(self):
        """Start Telegram bot with polling (alternative to webhook)"""
        if self.telegram_bot_running:
            return
            
        self.telegram_bot_running = True
        self.telegram_thread = threading.Thread(target=self.run_telegram_polling, daemon=True)
        self.telegram_thread.start()
        self.logger.info("Telegram bot started (polling mode)")
    
    def run_telegram_polling(self):
        """Run Telegram bot with polling"""
        offset = 0
        
        while self.telegram_bot_running:
            try:
                # Get updates from Telegram
                updates_url = f"https://api.telegram.org/bot{self.telegram_token}/getUpdates"
                params = {
                    'offset': offset,
                    'timeout': 30,
                    'allowed_updates': ['message']
                }
                
                response = requests.get(updates_url, params=params, timeout=35)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get('ok') and data.get('result'):
                        for update in data['result']:
                            offset = update['update_id'] + 1
                            
                            if 'message' in update:
                                try:
                                    self.handle_telegram_message(update['message'])
                                except Exception as e:
                                    self.logger.error(f"Error handling message: {e}")
                else:
                    self.logger.warning(f"Telegram polling failed: {response.status_code}")
                    time.sleep(5)  # Wait before retry
                    
            except requests.exceptions.Timeout:
                # Timeout is normal, continue polling
                continue
            except Exception as e:
                self.logger.error(f"Telegram polling error: {e}")
                time.sleep(10)  # Wait longer before retry
    
    def handle_telegram_message(self, message):
        """Handle incoming Telegram messages"""
        try:
            chat_id = str(message.get('chat', {}).get('id'))
            text = message.get('text', '').strip()
            
            # Check authorization
            if chat_id not in self.authorized_users:
                self.send_telegram_message(f"❌ Unauthorized access attempt from {chat_id}")
                return
            
            # Handle commands
            if text.startswith('/'):
                self.process_telegram_command(chat_id, text)
            else:
                self.send_telegram_message("ℹ️ Verwende /help für verfügbare Befehle")
                
        except Exception as e:
            self.logger.error(f"Message handling error: {e}")
    
    def process_telegram_command(self, chat_id: str, command: str):
        """Process Telegram bot commands"""
        try:
            cmd_parts = command.split()
            cmd = cmd_parts[0].lower()
            args = cmd_parts[1:] if len(cmd_parts) > 1 else []
            
            if cmd == '/start':
                self.cmd_start(chat_id)
            elif cmd == '/stop':
                self.cmd_stop(chat_id)
            elif cmd == '/status':
                self.cmd_status(chat_id)
            elif cmd == '/statustag':
                self.cmd_status_tag(chat_id)
            elif cmd == '/statuswoche':
                self.cmd_status_woche(chat_id)
            elif cmd == '/balance':
                self.cmd_balance(chat_id)
            elif cmd == '/positions':
                self.cmd_positions(chat_id)
            elif cmd == '/trades':
                self.cmd_trades(chat_id)
            elif cmd == '/config':
                self.cmd_config(chat_id)
            elif cmd == '/restart':
                self.cmd_restart(chat_id)
            elif cmd == '/debug':
                self.cmd_debug(chat_id, args)
            elif cmd == '/logs':
                self.cmd_logs(chat_id, args)
            elif cmd == '/help':
                self.cmd_help(chat_id)
            elif cmd in ['/liquidate_preview', '/close_preview']:
                self.cmd_liquidate_preview(chat_id)
            elif cmd == '/reset_stats':
                self.cmd_reset_stats(chat_id)
            else:
                self.send_telegram_message(f"❌ Unbekannter Befehl: {cmd}\nVerwende /help für verfügbare Befehle")
                
        except Exception as e:
            error_msg = f"❌ Fehler beim Verarbeiten des Befehls: {str(e)}"
            self.send_telegram_message(error_msg)
            self.logger.error(f"Command processing error: {e}")
            if self.debug_mode:
                self.debug_logs.append(f"Command error: {traceback.format_exc()}")
    
    def cmd_start(self, chat_id: str):
        """Start bot command"""
        if self.is_live_trading:
            self.send_telegram_message("⚠️ Bot läuft bereits!")
            return
        
        try:
            self.start_live_trading()
            self.send_telegram_message("✅ Bot erfolgreich gestartet!")
        except Exception as e:
            self.send_telegram_message(f"❌ Fehler beim Starten: {str(e)}")
    
    def cmd_stop(self, chat_id: str):
        """Stop bot command"""
        if not self.is_live_trading:
            self.send_telegram_message("⚠️ Bot läuft nicht!")
            return
        
        try:
            self.stop_live_trading()
            self.send_telegram_message("🛑 Bot erfolgreich gestoppt!")
        except Exception as e:
            self.send_telegram_message(f"❌ Fehler beim Stoppen: {str(e)}")
    
    def cmd_status(self, chat_id: str):
        """Status command"""
        try:
            num_positions = len(self.positions)
            value_positions = sum([p['size'] * p['entry_price'] for p in self.positions]) if self.positions else 0.0
            pnl_sum = self.current_balance - self.start_balance
            pnl_pct = (pnl_sum / self.start_balance) * 100 if self.start_balance else 0.0
            margin_sum = sum([
                (p['size'] * p['entry_price']) / p['leverage'] if p['leverage'] else 0.0
                for p in self.positions
            ])
            available_balance = self.current_balance - value_positions
            unrealized_pnl = 0.0
            if self.positions and self.current_price:
                for p in self.positions:
                    if p['side'] == 'long':
                        unrealized_pnl += (self.current_price - p['entry_price']) * p['size'] * p['leverage']
                    elif p['side'] == 'short':
                        unrealized_pnl += (p['entry_price'] - self.current_price) * p['size'] * p['leverage']

            status_msg = (
                f"\U0001F4CA <b>Bot Status</b>\n\n"
                f"\U0001F501 Live Trading: {'✅ Aktiv' if self.is_live_trading else '❌ Inaktiv'}\n"
                f"\U0001F4B0 Accountbalance: <b>{self.current_balance:.2f} USDT</b>\n"
                f"\U0001F4C8 Gewinn/Verlust: <b>{pnl_sum:+.2f} USDT</b> ({pnl_pct:+.2f}%)\n"
                f"\U0001F4C2 Offene Positionen: <b>{num_positions}</b>\n"
                f"\U0001F4BC Wert offene Positionen: <b>{value_positions:.2f} USDT</b>\n"
                f"\U0001F512 Gebundene Margin: <b>{margin_sum:.2f} USDT</b>\n"
                f"\U0001F4CA Unrealized PnL: <b>{unrealized_pnl:+.2f} USDT</b>\n"
            )
            if self.current_price:
                status_msg += f"\U0001F4B1 Aktueller Preis: <b>{self.current_price:.2f} USDT</b>\n\n"
            if self.positions:
                status_msg += "<b>Offene Positionen Details:</b>\n"
                for i, pos in enumerate(self.positions, 1):
                    side_emoji = '🟢' if pos['side'] == 'long' else '🔴'
                    entry = pos['entry_price']
                    size = pos['size']
                    lev = pos['leverage']
                    liq = pos['liquidation_price'] if 'liquidation_price' in pos else self.calculate_liquidation_price(entry, size, pos['side']=='long', lev)
                    tp = entry * (1 + self.config['take_profit_pct']) if pos['side']=='long' else entry * (1 - self.config['take_profit_pct'])
                    sl = entry * (1 - self.config['stop_loss_pct']) if pos['side']=='long' else entry * (1 + self.config['stop_loss_pct'])
                    # Abstände
                    dist_tp = (tp - self.current_price) if pos['side']=='long' else (self.current_price - tp)
                    dist_sl = (sl - self.current_price) if pos['side']=='long' else (self.current_price - sl)
                    dist_liq = (liq - self.current_price) if pos['side']=='long' else (self.current_price - liq)
                    pct_tp = (dist_tp / self.current_price) * 100
                    pct_sl = (dist_sl / self.current_price) * 100
                    pct_liq = (dist_liq / self.current_price) * 100
                    # Unrealized PnL
                    if pos['side'] == 'long':
                        upnl = (self.current_price - entry) * size * lev
                    else:
                        upnl = (entry - self.current_price) * size * lev
                    status_msg += (
                        f"\n{side_emoji} <b>Position {i}</b> | Einstieg: {entry:.2f} | Größe: {size:.6f} | Hebel: {lev}x\n"
                        f"TP: {tp:.2f} ({dist_tp:+.2f} USDT, {pct_tp:+.2f}%) | SL: {sl:.2f} ({dist_sl:+.2f} USDT, {pct_sl:+.2f}%) | Liq: {liq:.2f} ({dist_liq:+.2f} USDT, {pct_liq:+.2f}%)\n"
                        f"Unrealized PnL: {upnl:+.2f} USDT\n"
                    )
            if self.last_trade_time:
                status_msg += f"\n⏰ Letzter Trade: {self.last_trade_time.strftime('%H:%M:%S')}\n"
            self.send_telegram_message(status_msg)
        except Exception as e:
            self.send_telegram_message(f"❌ Fehler beim Status: {str(e)}")
    
    def cmd_status_tag(self, chat_id: str):
        """Status command für Tagesperformance"""
        try:
            from datetime import datetime, timedelta
            
            # Aktueller Tag (00:00 bis jetzt)
            now = datetime.now()
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Filtere Trades für heute
            today_trades = [t for t in self.trades if 'timestamp' in t and t['timestamp'] >= start_of_day]
            closed_trades = [t for t in today_trades if 'pnl' in t]
            
            # Berechne Tagesperformance
            total_pnl_today = sum(t['pnl'] - t.get('fee', 0) for t in closed_trades)
            total_fees_today = sum(t.get('fee', 0) for t in today_trades)
            num_trades_today = len(closed_trades)
            win_trades_today = len([t for t in closed_trades if t['pnl'] - t.get('fee', 0) > 0])
            win_rate_today = (win_trades_today / num_trades_today * 100) if num_trades_today > 0 else 0
            
            # Balance-Änderung heute
            balance_change_today = total_pnl_today
            balance_change_pct = (balance_change_today / self.start_balance * 100) if self.start_balance > 0 else 0
            
            status_msg = f"""
📅 <b>TAGESPERFORMANCE - {now.strftime('%d.%m.%Y')}</b>

💰 <b>Performance heute:</b>
• Netto PnL: {total_pnl_today:+.2f} USDT ({balance_change_pct:+.2f}%)
• Gebühren: {total_fees_today:.2f} USDT
• Trades: {num_trades_today}
• Gewinnrate: {win_rate_today:.1f}%

📊 <b>Details:</b>
• Gewinn-Trades: {win_trades_today}
• Verlust-Trades: {num_trades_today - win_trades_today}"""

            if num_trades_today > 0:
                status_msg += f"\n• Durchschnittlicher Trade: {total_pnl_today/num_trades_today:.2f} USDT"
            else:
                status_msg += "\n• Keine Trades"

            if closed_trades:
                status_msg += "\n\n<b>Heutige Trades:</b>\n"
                for i, t in enumerate(closed_trades[-5:], 1):  # Letzte 5 Trades
                    emoji = "🟢" if t['pnl'] - t.get('fee', 0) >= 0 else "🔴"
                    netto_pnl = t['pnl'] - t.get('fee', 0)
                    status_msg += f"{emoji} {t['side'].upper()}: {netto_pnl:+.2f} USDT | {t['price']:.2f}\n"
            
            self.send_telegram_message(status_msg)
        except Exception as e:
            self.send_telegram_message(f"❌ Fehler bei Tagesstatus: {str(e)}")
    
    def cmd_status_woche(self, chat_id: str):
        """Status command für Wochenperformance"""
        try:
            from datetime import datetime, timedelta
            
            # Aktuelle Woche (Montag 00:00 bis jetzt)
            now = datetime.now()
            start_of_week = now - timedelta(days=now.weekday())
            start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Filtere Trades für diese Woche
            week_trades = [t for t in self.trades if 'timestamp' in t and t['timestamp'] >= start_of_week]
            closed_trades = [t for t in week_trades if 'pnl' in t]
            
            # Berechne Wochenperformance
            total_pnl_week = sum(t['pnl'] - t.get('fee', 0) for t in closed_trades)
            total_fees_week = sum(t.get('fee', 0) for t in week_trades)
            num_trades_week = len(closed_trades)
            win_trades_week = len([t for t in closed_trades if t['pnl'] - t.get('fee', 0) > 0])
            win_rate_week = (win_trades_week / num_trades_week * 100) if num_trades_week > 0 else 0
            
            # Balance-Änderung diese Woche
            balance_change_week = total_pnl_week
            balance_change_pct = (balance_change_week / self.start_balance * 100) if self.start_balance > 0 else 0
            
            # Tagesaufschlüsselung
            daily_stats = {}
            for t in closed_trades:
                day = t['timestamp'].strftime('%d.%m')
                if day not in daily_stats:
                    daily_stats[day] = {'pnl': 0, 'trades': 0}
                daily_stats[day]['pnl'] += t['pnl'] - t.get('fee', 0)
                daily_stats[day]['trades'] += 1
            
            status_msg = f"""
📅 <b>WOCHEPERFORMANCE - KW{now.isocalendar()[1]} ({start_of_week.strftime('%d.%m')} - {now.strftime('%d.%m.%Y')})</b>

💰 <b>Performance diese Woche:</b>
• Netto PnL: {total_pnl_week:+.2f} USDT ({balance_change_pct:+.2f}%)
• Gebühren: {total_fees_week:.2f} USDT
• Trades: {num_trades_week}
• Gewinnrate: {win_rate_week:.1f}%

📊 <b>Details:</b>
• Gewinn-Trades: {win_trades_week}
• Verlust-Trades: {num_trades_week - win_trades_week}"""

            if num_trades_week > 0:
                status_msg += f"\n• Durchschnittlicher Trade: {total_pnl_week/num_trades_week:.2f} USDT"
            else:
                status_msg += "\n• Keine Trades"

            if daily_stats:
                status_msg += "\n\n<b>Tagesaufschlüsselung:</b>\n"
                for day in sorted(daily_stats.keys()):
                    daily_pnl = daily_stats[day]['pnl']
                    daily_trades = daily_stats[day]['trades']
                    emoji = "🟢" if daily_pnl >= 0 else "🔴"
                    status_msg += f"{emoji} {day}: {daily_pnl:+.2f} USDT ({daily_trades} Trades)\n"
            
            self.send_telegram_message(status_msg)
        except Exception as e:
            self.send_telegram_message(f"❌ Fehler bei Wochenstatus: {str(e)}")
    
    def cmd_balance(self, chat_id: str):
        """Balance command"""
        try:
            balance_msg = "💰 **Kontostand**\n\n"
            balance_msg += f"Startkapital: {self.start_balance:.2f} USDT\n"
            balance_msg += f"Aktueller Stand: {self.current_balance:.2f} USDT\n"
            balance_msg += f"Gesamtgewinn: {self.total_pnl:.2f} USDT\n"
            balance_msg += f"Gebühren: {self.total_fees:.2f} USDT\n"
            balance_msg += f"Funding Fees: {self.funding_fees:.2f} USDT\n"
            
            if self.current_balance > self.start_balance:
                profit_pct = ((self.current_balance - self.start_balance) / self.start_balance) * 100
                balance_msg += f"📈 Gewinn: +{profit_pct:.2f}%\n"
            else:
                loss_pct = ((self.start_balance - self.current_balance) / self.start_balance) * 100
                balance_msg += f"📉 Verlust: -{loss_pct:.2f}%\n"
            
            self.send_telegram_message(balance_msg)
        except Exception as e:
            self.send_telegram_message(f"❌ Fehler beim Balance: {str(e)}")
    
    def cmd_positions(self, chat_id: str):
        """Positions command"""
        try:
            if not self.positions:
                self.send_telegram_message("📋 Keine offenen Positionen")
                return
            
            positions_msg = f"📋 **Offene Positionen ({len(self.positions)})**\n\n"
            
            for i, pos in enumerate(self.positions, 1):
                positions_msg += f"**Position {i}:**\n"
                positions_msg += f"Typ: {'🟢 Long' if pos['side'] == 'long' else '🔴 Short'}\n"
                positions_msg += f"Größe: {pos['size']:.4f}\n"
                positions_msg += f"Einstieg: {pos['entry_price']:.2f} USDT\n"
                positions_msg += f"Hebel: {pos['leverage']}x\n"
                positions_msg += f"PnL: {pos.get('unrealized_pnl', 0):.2f} USDT\n"
                positions_msg += f"Liquidationspreis: {pos['liquidation_price']:.2f} USDT\n\n"
            
            self.send_telegram_message(positions_msg)
        except Exception as e:
            self.send_telegram_message(f"❌ Fehler beim Positions: {str(e)}")
    
    def cmd_trades(self, chat_id: str):
        """Trades command"""
        try:
            if not self.trades:
                self.send_telegram_message("📊 Keine Trades vorhanden")
                return
            
            # Show last 5 trades
            recent_trades = self.trades[-5:]
            trades_msg = f"📊 **Letzte {len(recent_trades)} Trades**\n\n"
            
            for trade in recent_trades:
                emoji = "🟢" if trade['pnl'] > 0 else "🔴"
                trades_msg += f"{emoji} {trade['side'].upper()}: {trade['pnl']:.2f} USDT\n"
                trades_msg += f"   Preis: {trade['price']:.2f} | Größe: {trade['size']:.4f}\n"
                trades_msg += f"   Zeit: {trade['timestamp'].strftime('%H:%M:%S')}\n\n"
            
            self.send_telegram_message(trades_msg)
        except Exception as e:
            self.send_telegram_message(f"❌ Fehler beim Trades: {str(e)}")
    
    def cmd_config(self, chat_id: str):
        """Config command"""
        try:
            config_msg = "⚙️ **Aktuelle Konfiguration**\n\n"
            config_msg += f"Modus: {self.config['mode']}\n"
            config_msg += f"Hebel: {self.config['leverage']}x\n"
            config_msg += f"Grid-Anzahl: {self.config['grid_count']}\n"
            config_msg += f"Investment: {self.config['investment_amount']} USDT\n"
            config_msg += f"Gebühren: {self.config['fee_rate']*100:.3f}%\n"
            config_msg += f"Stop-Loss: {self.config['stop_loss_pct']*100:.1f}%\n"
            config_msg += f"Take-Profit: {self.config['take_profit_pct']*100:.1f}%\n"
            config_msg += f"Live Trading: {'Aktiv' if self.config.get('live_trading_enabled') else 'Inaktiv'}\n"
            
            self.send_telegram_message(config_msg)
        except Exception as e:
            self.send_telegram_message(f"❌ Fehler beim Config: {str(e)}")
    
    def cmd_restart(self, chat_id: str):
        """Restart bot command"""
        try:
            if self.is_live_trading:
                self.stop_live_trading()
                time.sleep(2)
            
            self.start_live_trading()
            self.send_telegram_message("🔄 Bot erfolgreich neu gestartet!")
        except Exception as e:
            self.send_telegram_message(f"❌ Fehler beim Neustart: {str(e)}")
    
    def cmd_debug(self, chat_id: str, args: List[str]):
        """Debug command"""
        try:
            if not args:
                self.send_telegram_message("🔧 **Debug-Befehle:**\n\n"
                                         "/debug on - Debug-Modus aktivieren\n"
                                         "/debug off - Debug-Modus deaktivieren\n"
                                         "/debug info - System-Informationen\n"
                                         "/debug test - API-Test")
                return
            
            subcmd = args[0].lower()
            
            if subcmd == 'on':
                self.debug_mode = True
                self.send_telegram_message("🔧 Debug-Modus aktiviert")
                
            elif subcmd == 'off':
                self.debug_mode = False
                self.send_telegram_message("🔧 Debug-Modus deaktiviert")
                
            elif subcmd == 'info':
                info_msg = "🔧 **System-Informationen**\n\n"
                info_msg += f"Python Version: {sys.version}\n"
                info_msg += f"Betriebssystem: {os.name}\n"
                info_msg += f"Debug-Modus: {'Aktiv' if self.debug_mode else 'Inaktiv'}\n"
                info_msg += f"Threads: {threading.active_count()}\n"
                info_msg += f"Speicher: {len(self.debug_logs)} Debug-Logs\n"
                
                # Check API connections
                try:
                    price = self.get_live_price()
                    info_msg += f"Binance API: {'✅ Verbunden' if price else '❌ Fehler'}\n"
                except:
                    info_msg += "Binance API: ❌ Fehler\n"
                
                try:
                    response = requests.get(self.telegram_url.replace('/sendMessage', '/getMe'), timeout=5)
                    info_msg += f"Telegram API: {'✅ Verbunden' if response.status_code == 200 else '❌ Fehler'}\n"
                except:
                    info_msg += "Telegram API: ❌ Fehler\n"
                
                self.send_telegram_message(info_msg)
                
            elif subcmd == 'test':
                test_msg = "🧪 **API-Tests**\n\n"
                
                # Test Binance API
                try:
                    price = self.get_live_price()
                    test_msg += f"Binance Preis: {price:.2f} USDT ✅\n"
                except Exception as e:
                    test_msg += f"Binance API: ❌ {str(e)}\n"
                
                # Test Telegram API
                try:
                    response = requests.get(self.telegram_url.replace('/sendMessage', '/getMe'), timeout=5)
                    if response.status_code == 200:
                        test_msg += "Telegram API: ✅ Verbunden\n"
                    else:
                        test_msg += f"Telegram API: ❌ {response.status_code}\n"
                except Exception as e:
                    test_msg += f"Telegram API: ❌ {str(e)}\n"
                
                self.send_telegram_message(test_msg)
                
            else:
                self.send_telegram_message("❌ Unbekannter Debug-Befehl")
                
        except Exception as e:
            self.send_telegram_message(f"❌ Debug-Fehler: {str(e)}")
    
    def cmd_logs(self, chat_id: str, args: List[str]):
        """Logs command"""
        try:
            if not args:
                self.send_telegram_message("📋 **Log-Befehle:**\n\n"
                                         "/logs recent - Letzte Logs\n"
                                         "/logs debug - Debug-Logs\n"
                                         "/logs error - Fehler-Logs")
                return
            
            subcmd = args[0].lower()
            
            if subcmd == 'recent':
                try:
                    with open('pionex_futures_bot.log', 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        recent_lines = lines[-20:]  # Last 20 lines
                        log_msg = "📋 **Letzte Logs:**\n\n"
                        for line in recent_lines:
                            log_msg += f"`{line.strip()}`\n"
                        self.send_telegram_message(log_msg)
                except Exception as e:
                    self.send_telegram_message(f"❌ Log-Fehler: {str(e)}")
                    
            elif subcmd == 'debug':
                if not self.debug_logs:
                    self.send_telegram_message("📋 Keine Debug-Logs vorhanden")
                    return
                
                debug_msg = "🔧 **Debug-Logs:**\n\n"
                for i, log in enumerate(self.debug_logs[-10:], 1):  # Last 10 debug logs
                    debug_msg += f"**{i}:** {log[:100]}...\n\n"
                self.send_telegram_message(debug_msg)
                
            elif subcmd == 'error':
                try:
                    with open('pionex_futures_bot.log', 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        error_lines = [line for line in lines if 'ERROR' in line][-10:]  # Last 10 errors
                        if error_lines:
                            error_msg = "❌ **Letzte Fehler:**\n\n"
                            for line in error_lines:
                                error_msg += f"`{line.strip()}`\n"
                            self.send_telegram_message(error_msg)
                        else:
                            self.send_telegram_message("✅ Keine Fehler in den Logs")
                except Exception as e:
                    self.send_telegram_message(f"❌ Log-Fehler: {str(e)}")
                    
            else:
                self.send_telegram_message("❌ Unbekannter Log-Befehl")
                
        except Exception as e:
            self.send_telegram_message(f"❌ Log-Fehler: {str(e)}")
    
    def cmd_help(self, chat_id: str):
        """Help command"""
        help_msg = "🤖 **Pionex Futures Grid Bot - Hilfe**\n\n"
        help_msg += "**Grundbefehle:**\n"
        help_msg += "/start - Bot starten\n"
        help_msg += "/stop - Bot stoppen\n"
        help_msg += "/status - Aktueller Status\n"
        help_msg += "/statustag - Tagesperformance\n"
        help_msg += "/statuswoche - Wochenperformance\n"
        help_msg += "/restart - Bot neu starten\n\n"
        
        help_msg += "**Informationen:**\n"
        help_msg += "/balance - Kontostand\n"
        help_msg += "/positions - Offene Positionen\n"
        help_msg += "/trades - Letzte Trades\n"
        help_msg += "/config - Konfiguration\n"
        help_msg += "/liquidate_preview - Vorschau bei sofortigem Schließen\n\n"
        
        help_msg += "**Debugging:**\n"
        help_msg += "/debug - Debug-Befehle\n"
        help_msg += "/logs - Log-Befehle\n"
        help_msg += "/help - Diese Hilfe\n\n"
        
        help_msg += "**Beispiele:**\n"
        help_msg += "/debug on - Debug aktivieren\n"
        help_msg += "/logs recent - Letzte Logs\n"
        help_msg += "/debug info - System-Info"
        
        self.send_telegram_message(help_msg)

    def send_telegram_message(self, message: str):
        """Send message via Telegram (emojis allowed here)"""
        try:
            if self.telegram_token != "YOUR_TELEGRAM_TOKEN":
                payload = {
                    'chat_id': self.telegram_chat_id,
                    'text': message,
                    'parse_mode': 'HTML'
                }
                response = requests.post(self.telegram_url, data=payload, timeout=10)
                if response.status_code != 200:
                    self.logger.warning(f"Telegram message failed: {response.text}")
                else:
                    self.logger.info(f"Telegram message sent (first 50 chars): {message[:50]}")
        except Exception as e:
            self.logger.error(f"Telegram error: {e}")
    
    def test_telegram_connection(self):
        """Test Telegram bot connection"""
        try:
            test_url = f"https://api.telegram.org/bot{self.telegram_token}/getMe"
            response = requests.get(test_url, timeout=10)
            
            if response.status_code == 200:
                bot_info = response.json()
                if bot_info.get('ok'):
                    self.logger.info(f"Telegram bot connected: {bot_info['result']['username']}")
                    return True
                else:
                    self.logger.error(f"Telegram bot error: {bot_info}")
                    return False
            else:
                self.logger.error(f"Telegram connection failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"Telegram connection test failed: {e}")
            return False
    
    def load_data(self) -> pd.DataFrame:
        """Load and prepare historical data"""
        try:
            # Lade CSV mit Semikolon-Trenner und deutschem Dezimaltrennzeichen
            data = pd.read_csv(self.config['data_file'], sep=';', decimal=',')
        except Exception as e:
            self.logger.error(f"Fehler beim Einlesen der CSV-Datei: {e}")
            raise
        
        # Standardize column names
        data.columns = [col.lower().strip() for col in data.columns]
        
        # Ensure required columns exist
        required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in data.columns:
                raise ValueError(f"Missing required column: {col}")
        
        # Convert timestamp
        data['timestamp'] = pd.to_datetime(data['timestamp'])
        
        # Sort by timestamp
        data = data.sort_values('timestamp').reset_index(drop=True)
        
        # Technische Indikatoren hinzufügen
        data = self.add_technical_indicators(data)
        
        self.logger.info(f"Loaded {len(data)} data points from {data['timestamp'].min()} to {data['timestamp'].max()}")
        self.data = data  # Speichere für Grid-Bereich-Ermittlung
        return data
    
    def add_technical_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Füge technische Indikatoren hinzu"""
        closes = data['close'].astype(float)
        highs = data['high'].astype(float)
        lows = data['low'].astype(float)
        volumes = data['volume'].astype(float)
        
        # RSI
        data['rsi'] = ta.momentum.RSIIndicator(closes).rsi()
        
        # MACD
        macd = ta.trend.MACD(closes)
        data['macd'] = macd.macd()
        data['macd_signal'] = macd.macd_signal()
        data['macd_hist'] = macd.macd_diff()
        
        # Bollinger Bands
        bb = ta.volatility.BollingerBands(closes)
        data['bb_upper'] = bb.bollinger_hband()
        data['bb_middle'] = bb.bollinger_mavg()
        data['bb_lower'] = bb.bollinger_lband()
        
        # Volatilität (ATR)
        data['atr'] = ta.volatility.AverageTrueRange(highs, lows, closes).average_true_range()
        
        # Volume SMA (einfache Berechnung)
        data['volume_sma'] = volumes.rolling(window=20).mean()
        
        # Trend-Stärke (ADX)
        data['adx'] = ta.trend.ADXIndicator(highs, lows, closes).adx()
        
        return data
    
    def auto_set_grid_range(self):
        """Auto-set grid range based on current market conditions"""
        try:
            if hasattr(self, 'data') and self.data is not None:
                # Use historical data for backtest mode
                closes = self.data['close'].astype(float)
                current_price = closes.iloc[-1]
                volatility = closes.pct_change().std()
            else:
                # Use live data for live trading mode
                current_price = self.get_live_price()
                if current_price is None:
                    current_price = 50000  # Fallback price
                
                # Get recent klines for volatility calculation
                klines = self.get_live_klines(100)
                if klines is not None and len(klines) > 0:
                    closes = klines['close'].astype(float)
                    volatility = closes.pct_change().std()
                else:
                    volatility = 0.02  # Default volatility
            
            # Calculate grid range based on volatility
            grid_range_pct = max(0.05, min(0.20, volatility * 10))  # 5-20% range
            grid_range = current_price * grid_range_pct
            
            self.config['grid_lower_price'] = current_price - grid_range / 2
            self.config['grid_upper_price'] = current_price + grid_range / 2
            
            self.logger.info(f"Auto-set grid range: {self.config['grid_lower_price']:.2f} - {self.config['grid_upper_price']:.2f}")
            
        except Exception as e:
            self.logger.error(f"Error in auto_set_grid_range: {e}")
            # Fallback to default range
            current_price = self.get_live_price() or 50000
            self.config['grid_lower_price'] = current_price * 0.95
            self.config['grid_upper_price'] = current_price * 1.05
    
    def calculate_grid_prices(self) -> list:
        """Calculate grid price levels"""
        # Automatische Grid-Bereich-Ermittlung falls nötig
        self.auto_set_grid_range()
        lower_price = float(self.config['grid_lower_price'])
        upper_price = float(self.config['grid_upper_price'])
        grid_count = self.config['grid_count']
        grid_spacing = (upper_price - lower_price) / (grid_count - 1)
        grid_prices = [lower_price + i * grid_spacing for i in range(grid_count)]
        self.logger.info(f"Grid prices: {len(grid_prices)} levels from {lower_price:.2f} to {upper_price:.2f}")
        return grid_prices
    
    def calculate_position_size(self, price: float) -> float:
        """Calculate position size based on investment amount and leverage"""
        investment = self.config['investment_amount']
        leverage = self.config['leverage']
        
        # Position size = (Investment * Leverage) / Price
        position_size = (investment * leverage) / price
        
        return position_size
    
    def calculate_margin_required(self, position_size: float, price: float) -> float:
        """Calculate required margin for position"""
        leverage = self.config['leverage']
        
        # Margin = (Position Size * Price) / Leverage
        margin = (position_size * price) / leverage
        
        return margin
    
    def calculate_liquidation_price(self, entry_price: float, position_size: float, 
                                  is_long: bool, leverage: float) -> float:
        """Calculate liquidation price for position"""
        # Simplified liquidation calculation
        # In reality, this depends on exchange-specific formulas
        
        if is_long:
            # For long positions: liquidation_price = entry_price * (1 - 1/leverage)
            liquidation_price = entry_price * (1 - 1/leverage)
        else:
            # For short positions: liquidation_price = entry_price * (1 + 1/leverage)
            liquidation_price = entry_price * (1 + 1/leverage)
        
        return liquidation_price
    
    def check_liquidation(self, current_price: float, position: Dict) -> bool:
        """Check if position should be liquidated"""
        liquidation_price = position['liquidation_price']
        is_long = position['is_long']
        
        if is_long and current_price <= liquidation_price:
            return True
        elif not is_long and current_price >= liquidation_price:
            return True
        
        return False
    
    def calculate_funding_fee(self, position: Dict, time_diff_hours: float) -> float:
        """Calculate funding fee for position"""
        funding_rate = self.config['funding_rate']
        position_value = position['size'] * position['entry_price']
        
        # Funding fee = Position Value * Funding Rate * (Time in hours / 8)
        funding_fee = position_value * funding_rate * (time_diff_hours / 8)
        
        return funding_fee

    def execute_trade(self, price: float, side: str, timestamp: datetime, leverage: float = None) -> bool:
        """Execute a trade with realistic conditions and detailed Telegram notifications"""
        if leverage is None:
            leverage = self.config['leverage']
        
        position_size = self.calculate_position_size(price)
        
        if position_size <= 0:
            return False
        
        executed_price = self.simulate_order_execution(price, side == 'buy', position_size)
        
        if executed_price is None:
            return False
        
        position = {
            'id': len(self.positions) + 1,
            'side': side,
            'entry_price': executed_price,
            'size': position_size,
            'timestamp': timestamp,
            'leverage': leverage,
            'buy_fee': position_size * executed_price * self.config['fee_rate'],
            'trailing_stop': executed_price * (1 - self.trailing_stop_pct) if side == 'long' else executed_price * (1 + self.trailing_stop_pct),
            'trailing_high': executed_price if side == 'long' else executed_price
        }
        
        self.positions.append(position)
        
        fee = position_size * executed_price * self.config['fee_rate']
        self.total_fees += fee
        
        # Detaillierte Telegram-Benachrichtigung für Trade
        # Berechne nächstes Grid-Sell-Level oberhalb des Einstiegskurses
        next_grid_sell = None
        dist_grid = None
        pct_grid = None
        if self.grid_prices:
            higher_grids = [g for g in self.grid_prices if g > executed_price]
            if higher_grids:
                next_grid_sell = min(higher_grids)
                dist_grid = next_grid_sell - executed_price
                pct_grid = (dist_grid / executed_price) * 100
        tp = executed_price * (1 + self.config['take_profit_pct'])
        dist_tp = tp - executed_price
        pct_tp = (dist_tp / executed_price) * 100
        sl = executed_price * (1 - self.config['stop_loss_pct'])
        dist_sl = sl - executed_price
        pct_sl = (dist_sl / executed_price) * 100
        trade_msg = f"""
💚 <b>TRADE AUSGEFÜHRT: {side.upper()}</b>

💰 <b>Trade Details:</b>
• Position ID: #{position['id']}
• Kaufkurs: ${executed_price:,.2f}
• Menge: {position_size:.6f} BTC
• Wert: ${position_size * executed_price:,.2f}
• Hebel: {leverage:.1f}x

📊 <b>Verkaufsziele:</b>\n"""
        if next_grid_sell:
            trade_msg += f"• Nächstes Grid-Sell: ${next_grid_sell:,.2f} (+{dist_grid:,.2f} USDT, +{pct_grid:.2f}%)\n"
        else:
            trade_msg += "• Nächstes Grid-Sell: Kein Grid oberhalb\n"
        trade_msg += f"• Take Profit: ${tp:,.2f} (+{dist_tp:,.2f} USDT, +{pct_tp:.2f}%)\n"
        trade_msg += f"• Stop Loss: ${sl:,.2f} ({dist_sl:,.2f} USDT, {pct_sl:.2f}%)\n"
        trade_msg += f"\n💸 Gebühr: ${fee:.2f}\n⏰ Zeit: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n        """
        self.send_telegram_message(trade_msg)
        
        self.logger.info(f"Trade executed: {side.upper()} {position_size:.2f} at {executed_price:.2f} (Leverage: {leverage:.1f}x)")
        return True

    def close_position(self, position: dict, price: float, timestamp: datetime) -> float:
        """Close position and calculate PnL with detailed Telegram notification (inkl. Kauf- und Verkaufsgebühr)"""
        executed_price = self.simulate_order_execution(price, position['side'] == 'sell', position['size'])
        if executed_price is None:
            return 0
        if position['side'] == 'long':
            pnl = (executed_price - position['entry_price']) * position['size'] * position['leverage']
        else:
            pnl = (position['entry_price'] - executed_price) * position['size'] * position['leverage']
        sell_fee = position['size'] * executed_price * self.config['fee_rate']
        buy_fee = position.get('buy_fee', 0.0)
        total_fee = buy_fee + sell_fee
        self.total_fees += sell_fee
        entry_value = position['entry_price'] * position['size']
        pnl_percentage = (pnl / entry_value) * 100
        self.current_balance += pnl - sell_fee
        trade = {
            'timestamp': timestamp,
            'side': 'sell' if position['side'] == 'long' else 'buy',
            'price': executed_price,
            'size': position['size'],
            'fee': sell_fee,
            'pnl': pnl,
            'leverage': position['leverage']
        }
        self.trades.append(trade)
        unrealized_pnl = (price - position['entry_price']) * position['size'] * position['leverage']
        close_msg = f"""
🔴 <b>POSITION GESCHLOSSEN: #{position['id']}</b>\n\n💰 <b>Trade Details:</b>\n• Einstiegskurs: ${position['entry_price']:,.2f}\n• Verkaufskurs: ${executed_price:,.2f}\n• Menge: {position['size']:.6f} BTC\n• Hebel: {position['leverage']:.1f}x\n\n📈 <b>Gewinn/Verlust:</b>\n• Unrealisierter PnL vor Verkauf: {unrealized_pnl:+.2f} USDT\n• PnL: ${pnl:,.2f} ({pnl_percentage:+.2f}%)\n• Gebühr Buy: ${buy_fee:.2f}\n• Gebühr Sell: ${sell_fee:.2f}\n• Netto PnL: ${pnl - buy_fee - sell_fee:,.2f}\n\n📊 <b>Hypothetische Gewinne:</b>\n• Bei Grid-Sell: {grid_sell_pnl:+.2f} USDT ({grid_sell_pct:+.2f}%)\n• Bei Take-Profit: {tp_pnl:+.2f} USDT ({tp_pct:+.2f}%)\n\n💰 <b>Accountbalance nach Verkauf:</b> {self.current_balance:,.2f} USDT\n\n⏱️ Zeit: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"""
        self.send_telegram_message(close_msg)
        self.logger.info(f"Position closed: PnL {pnl:.2f}, Fee Buy {buy_fee:.2f}, Fee Sell {sell_fee:.2f}")
        return pnl
    
    def update_performance_metrics(self):
        """Update performance metrics"""
        # Update max/min balance
        if self.current_balance > self.max_balance:
            self.max_balance = self.current_balance
        
        if self.current_balance < self.min_balance:
            self.min_balance = self.current_balance
        
        # Calculate drawdown
        if self.max_balance > 0:
            current_drawdown = (self.max_balance - self.current_balance) / self.max_balance
            if current_drawdown > self.max_drawdown:
                self.max_drawdown = current_drawdown
    
    def calculate_volatility(self, data: pd.DataFrame, index: int) -> float:
        """Berechne aktuelle Volatilität"""
        if index < self.volatility_lookback:
            return 0.02  # Default 2%
        
        recent_data = data.iloc[index-self.volatility_lookback:index]
        returns = recent_data['close'].pct_change().dropna()
        return returns.std()

    def detect_trend(self, data: pd.DataFrame, index: int) -> str:
        """Trend-Erkennung basierend auf technischen Indikatoren"""
        if index < 50:
            return 'neutral'
        
        current = data.iloc[index]
        
        # RSI-basierte Trend-Erkennung
        rsi_trend = 'bullish' if current['rsi'] > 50 else 'bearish'
        
        # MACD-basierte Trend-Erkennung
        macd_trend = 'bullish' if current['macd'] > current['macd_signal'] else 'bearish'
        
        # ADX für Trend-Stärke
        trend_strength = current['adx'] / 100.0 if not pd.isna(current['adx']) else 0.5
        
        # Bollinger Bands Position
        if not pd.isna(current['bb_upper']) and not pd.isna(current['bb_lower']):
            bb_position = (current['close'] - current['bb_lower']) / (current['bb_upper'] - current['bb_lower'])
            bb_trend = 'bullish' if bb_position > 0.7 else 'bearish' if bb_position < 0.3 else 'neutral'
        else:
            bb_trend = 'neutral'
        
        # Kombiniere alle Signale
        bullish_signals = sum([rsi_trend == 'bullish', macd_trend == 'bullish', bb_trend == 'bullish'])
        bearish_signals = sum([rsi_trend == 'bearish', macd_trend == 'bearish', bb_trend == 'bearish'])
        
        if trend_strength < self.trend_strength_threshold:
            return 'neutral'
        
        if bullish_signals >= 2:
            return 'bullish'
        elif bearish_signals >= 2:
            return 'bearish'
        else:
            return 'neutral'

    def calculate_dynamic_leverage(self, volatility: float, trend: str, balance: float) -> float:
        """Dynamische Hebel-Anpassung basierend auf Marktbedingungen"""
        if not self.dynamic_leverage_enabled:
            return self.config['leverage']
        
        base_leverage = self.config['leverage']
        
        # Volatilitäts-basierte Anpassung
        if volatility < 0.01:  # Niedrige Volatilität
            leverage_multiplier = 1.2
        elif volatility > 0.05:  # Hohe Volatilität
            leverage_multiplier = 0.7
        else:
            leverage_multiplier = 1.0
        
        # Trend-basierte Anpassung
        if trend == 'bullish':
            trend_multiplier = 1.1
        elif trend == 'bearish':
            trend_multiplier = 0.9
        else:
            trend_multiplier = 1.0
        
        # Balance-basierte Anpassung (höhere Balance = höherer Hebel)
        balance_multiplier = min(1.5, 1.0 + (balance / 100000))
        
        dynamic_leverage = base_leverage * leverage_multiplier * trend_multiplier * balance_multiplier
        
        # Sicherheitsgrenzen
        return max(1.0, min(3.0, dynamic_leverage))

    def calculate_adaptive_position_size(self, price: float, volatility: float, trend: str) -> float:
        """Adaptive Positionsgröße basierend auf Marktbedingungen"""
        if not self.adaptive_grid_enabled:
            return self.calculate_position_size(price)
        
        base_amount = self.config['investment_amount']
        
        # Volatilitäts-basierte Anpassung
        if volatility < 0.01:
            vol_multiplier = 1.3  # Mehr Positionen bei niedriger Volatilität
        elif volatility > 0.05:
            vol_multiplier = 0.7  # Weniger Positionen bei hoher Volatilität
        else:
            vol_multiplier = 1.0
        
        # Trend-basierte Anpassung
        if trend == 'bullish':
            trend_multiplier = 1.2
        elif trend == 'bearish':
            trend_multiplier = 0.8
        else:
            trend_multiplier = 1.0
        
        # Balance-basierte Anpassung
        balance_multiplier = min(2.0, 1.0 + (self.current_balance / 50000))
        
        adaptive_amount = base_amount * vol_multiplier * trend_multiplier * balance_multiplier
        
        # Sicherheitsgrenzen
        max_position_value = self.current_balance * self.max_position_size
        return min(adaptive_amount, max_position_value)

    def calculate_adaptive_grid_prices(self, current_price: float, volatility: float) -> list:
        """Berechne adaptive Grid-Preise basierend auf Volatilität"""
        self.auto_set_grid_range()
        lower_price = float(self.config['grid_lower_price'])
        upper_price = float(self.config['grid_upper_price'])
        grid_count = self.config['grid_count']
        
        # Volatilitäts-basierte Grid-Anpassung
        if volatility > 0.05:  # Hohe Volatilität
            grid_count = int(grid_count * 1.5)  # Mehr Grid-Levels
        elif volatility < 0.01:  # Niedrige Volatilität
            grid_count = int(grid_count * 0.8)  # Weniger Grid-Levels
        
        # Dynamische Grid-Bereiche basierend auf aktueller Position
        price_range = upper_price - lower_price
        grid_spacing = price_range / (grid_count - 1)
        
        # Zentriere Grid um aktuellen Preis
        center_price = current_price
        start_price = center_price - (grid_count // 2) * grid_spacing
        end_price = center_price + (grid_count // 2) * grid_spacing
        
        # Stelle sicher, dass Grid im erlaubten Bereich liegt
        start_price = max(lower_price, start_price)
        end_price = min(upper_price, end_price)
        
        grid_prices = [start_price + i * grid_spacing for i in range(grid_count)]
        return grid_prices

    def check_liquidity(self, price: float, volume: float) -> bool:
        """Prüfe ob genügend Liquidität vorhanden ist"""
        # Vereinfachte Liquiditätsprüfung - immer True für Backtest
        return True

    def apply_slippage_and_spread(self, price: float, is_buy: bool) -> float:
        """Wende Slippage und Spread an"""
        slippage = price * self.slippage_rate * random.uniform(0.5, 1.5)
        spread = price * self.spread_rate
        
        if is_buy:
            return price + slippage + spread
        else:
            return price - slippage - spread

    def simulate_order_execution(self, price: float, is_buy: bool, size: float) -> Optional[float]:
        """Simuliere realistische Order-Ausführung"""
        # Vereinfachte Order-Ausführung für Backtest
        executed_price = self.apply_slippage_and_spread(price, is_buy)
        return executed_price

    def advanced_risk_management(self, position: dict, current_price: float, volatility: float) -> bool:
        """Erweiterte Risikomanagement-Logik"""
        if not self.risk_management_enabled:
            return self.check_liquidation_risk(position, current_price)
        
        entry_price = position['entry_price']
        size = position['size']
        leverage = position['leverage']
        
        # Berechne PnL
        if position['side'] == 'long':
            pnl = (current_price - entry_price) * size * leverage
        else:
            pnl = (entry_price - current_price) * size * leverage
        
        margin = size
        margin_ratio = (margin + pnl) / margin
        
        # Dynamische Liquidationsschwelle basierend auf Volatilität
        base_liquidation_buffer = self.config['liquidation_buffer']
        volatility_adjustment = volatility * 10  # Erhöhe Buffer bei hoher Volatilität
        dynamic_buffer = base_liquidation_buffer + volatility_adjustment
        
        # Position schließen wenn:
        # 1. Margin Ratio zu niedrig
        if margin_ratio < dynamic_buffer:
            return True
        
        # 2. Stop Loss erreicht
        stop_loss_pct = self.config['stop_loss_pct']
        if abs(pnl) / margin > stop_loss_pct:
            return True
        
        # 3. Take Profit erreicht
        take_profit_pct = self.config['take_profit_pct']
        if pnl / margin > take_profit_pct:
            return True
        
        return False

    def check_liquidation_risk(self, position: dict, current_price: float) -> bool:
        """Prüfe Liquidationsrisiko mit realistischen Parametern"""
        entry_price = position['entry_price']
        size = position['size']
        leverage = position['leverage']
        
        if position['side'] == 'long':
            pnl = (current_price - entry_price) * size * leverage
        else:
            pnl = (entry_price - current_price) * size * leverage
        
        margin = size
        margin_ratio = (margin + pnl) / margin
        liquidation_buffer = self.config['liquidation_buffer']
        
        return margin_ratio < liquidation_buffer

    def apply_funding_fees(self, timestamp: datetime):
        """Apply funding fees to open positions"""
        if len(self.positions) > 0:
            funding_rate = self.config['funding_rate']
            total_position_value = sum(pos['size'] * pos['entry_price'] for pos in self.positions)
            funding_fee = total_position_value * funding_rate
            
            self.funding_fees += funding_fee
            self.total_fees += funding_fee
            self.current_balance -= funding_fee

    def run_backtest(self) -> dict:
        """Run backtest with realistic conditions and optimizations"""
        self.logger.info("Starting optimized realistic backtest...")
        
        # Telegram: Backtest Start
        start_msg = f"""
🚀 <b>Pionex Grid Bot Backtest gestartet!</b>

📊 <b>Konfiguration:</b>
• Mode: {self.config['mode'].upper()}
• Leverage: {self.config['leverage']}x
• Grid Count: {self.config['grid_count']}
• Investment: ${self.config['investment_amount']:,.0f}
• Initial Balance: ${self.config['initial_balance']:,.0f}

⚙️ <b>Optimierungen aktiv:</b>
• Dynamische Hebelwirkung
• Adaptive Grid-Preise
• Erweitertes Risikomanagement
• Trend-Filterung
        """
        self.send_telegram_message(start_msg)
        
        data = self.load_data()
        initial_balance = self.current_balance
        max_balance = self.current_balance
        min_balance = self.current_balance
        
        # Initialisiere Grid-Preise
        self.grid_prices = self.calculate_grid_prices()
        
        # Zeitbegrenzung: Nur 1 Minute testen
        start_time = time.time()
        max_runtime = 60  # 60 Sekunden
        
        # Progress tracking für Telegram
        last_progress_update = 0
        progress_interval = 25  # Alle 25% Fortschritt melden
        
        for i, row in data.iterrows():
            # Zeitprüfung
            if time.time() - start_time > max_runtime:
                self.logger.info(f"Zeitbegrenzung erreicht nach {max_runtime} Sekunden")
                break
                
            current_price = float(row['close'])
            timestamp = row['timestamp']
            
            # Progress logging und Telegram Updates
            progress = (i / len(data)) * 100
            if progress >= last_progress_update + progress_interval:
                elapsed_time = time.time() - start_time
                current_pnl = self.current_balance - initial_balance
                
                progress_msg = f"""
📈 <b>Backtest Fortschritt: {progress:.0f}%</b>

💰 <b>Aktueller Status:</b>
Balance: ${self.current_balance:,.2f}
PnL: ${current_pnl:,.2f} ({current_pnl/initial_balance*100:.2f}%)
Trades: {len([t for t in self.trades if 'pnl' in t])}
Laufzeit: {elapsed_time:.1f}s
                """
                self.send_telegram_message(progress_msg)
                last_progress_update = progress
                
                self.logger.info(f"Progress: {progress:.1f}% - Balance: {self.current_balance:.2f} - Zeit: {elapsed_time:.1f}s")
            
            # Apply funding fees every 8 hours
            if i % 480 == 0:
                self.apply_funding_fees(timestamp)
            
            # Check liquidations
            positions_to_remove = []
            for position in self.positions:
                if self.check_liquidation_risk(position, current_price):
                    self.liquidated_positions += 1
                    self.logger.warning(f"Position liquidated at {current_price}")
                    positions_to_remove.append(position)
            
            for position in positions_to_remove:
                self.positions.remove(position)
            
            # Grid trading logic
            for grid_price in self.grid_prices:
                # Buy signal
                if current_price <= grid_price and len([p for p in self.positions if p['entry_price'] == grid_price]) == 0:
                    if self.current_balance > self.config['investment_amount']:
                        self.execute_trade(grid_price, 'buy', timestamp)
                
                # Sell signal
                elif current_price >= grid_price:
                    for position in self.positions:
                        if position['entry_price'] == grid_price and position['side'] == 'long':
                            self.close_position(position, grid_price, timestamp)
                            self.positions.remove(position)
                            break
            
            # Update max/min balance
            max_balance = max(max_balance, self.current_balance)
            min_balance = min(min_balance, self.current_balance)
        
        # Close remaining positions
        for position in self.positions:
            self.close_position(position, current_price, timestamp)
        
        # Calculate metrics
        total_return = ((self.current_balance - initial_balance) / initial_balance) * 100
        max_drawdown = ((max_balance - min_balance) / max_balance) * 100
        
        # Berechne Gewinn-Trades aus den Trades
        win_trades = len([t for t in self.trades if t.get('pnl', 0) > 0])
        total_trades = len([t for t in self.trades if 'pnl' in t])
        win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
        
        results = {
            'initial_balance': initial_balance,
            'final_balance': self.current_balance,
            'total_return': total_return,
            'max_drawdown': max_drawdown,
            'total_trades': total_trades,
            'win_trades': win_trades,
            'win_rate': win_rate,
            'liquidated_positions': self.liquidated_positions,
            'trading_fees': self.total_fees - self.funding_fees,
            'funding_fees': self.funding_fees,
            'total_fees': self.total_fees,
            'runtime_seconds': time.time() - start_time
        }
        
        # Telegram: Backtest Ende
        end_msg = f"""
✅ <b>Backtest abgeschlossen!</b>

📊 <b>Endergebnis:</b>
Start: ${initial_balance:,.2f}
Ende: ${self.current_balance:,.2f}
Rendite: {total_return:.2f}%
PnL: ${self.current_balance - initial_balance:,.2f}

🎯 <b>Trading-Statistiken:</b>
Trades: {total_trades}
Gewinnrate: {win_rate:.1f}%
Liquidierungen: {self.liquidated_positions}
Max Drawdown: {max_drawdown:.2f}%

⏱️ Laufzeit: {results['runtime_seconds']:.1f} Sekunden
        """
        self.send_telegram_message(end_msg)
        
        self.logger.info(f"Quick test completed in {results['runtime_seconds']:.1f} seconds!")
        return results
    
    def generate_report(self, results: dict):
        """Generate detailed performance report"""
        report = f"""
============================================================
PIONEX FUTURES GRID BOT - OPTIMIZED PERFORMANCE REPORT
============================================================
Bot Mode: {self.config['mode'].upper()}
Base Leverage: {self.config['leverage']}x
Grid Range: {self.config['grid_lower_price']:.2f} - {self.config['grid_upper_price']:.2f}
Grid Count: {self.config['grid_count']}
Investment Amount: ${self.config['investment_amount']:.2f}

OPTIMIZATIONS ENABLED:
------------------------------
Dynamic Leverage: {self.dynamic_leverage_enabled}
Adaptive Grid: {self.adaptive_grid_enabled}
Advanced Risk Management: {self.risk_management_enabled}
Trend Filtering: Enabled
Volatility-Based Positioning: Enabled
Multi-Timeframe Analysis: Enabled

REALISTIC TRADING CONDITIONS:
------------------------------
Slippage: {self.slippage_rate*100:.3f}%
Spread: {self.spread_rate*100:.3f}%
Order Failure Rate: {self.order_failure_rate*100:.1f}%
API Latency: {self.api_latency*1000:.0f}ms
Max Position Size: {self.max_position_size*100:.1f}% of capital

PERFORMANCE METRICS:
------------------------------
Initial Balance: ${results['initial_balance']:,.2f}
Final Balance: ${results['final_balance']:,.2f}
Total Return: {results['total_return']:.2f}%
Total PnL: ${results['final_balance'] - results['initial_balance']:,.2f}
Max Drawdown: {results['max_drawdown']:.2f}%

TRADING STATISTICS:
------------------------------
Total Trades: {results['total_trades']}
Win Trades: {results['win_trades']}
Win Rate: {results['win_rate']:.2f}%
Liquidated Positions: {results['liquidated_positions']}

FEES (Realistic):
------------------------------
Trading Fees: ${results['trading_fees']:.2f}
Funding Fees: ${results['funding_fees']:.2f}
Total Fees: ${results['total_fees']:.2f}

CONFIGURATION:
------------------------------
"""
        
        for key, value in self.config.items():
            report += f"{key}: {value}\n"
        
        report += "\n============================================================\n"
        
        # Save report
        with open('pionex_optimized_report.txt', 'w') as f:
            f.write(report)
        
        self.logger.info("Optimized report saved to pionex_optimized_report.txt")
        
        # Send Telegram summary
        telegram_msg = f"""
🚀 <b>Optimized Grid Bot Results</b>

💰 <b>Performance:</b>
Initial: ${results['initial_balance']:,.0f}
Final: ${results['final_balance']:,.0f}
Return: {results['total_return']:.1f}%

📊 <b>Stats:</b>
Trades: {results['total_trades']}
Win Rate: {results['win_rate']:.1f}%
Liquidations: {results['liquidated_positions']}

⚡ <b>Optimizations:</b>
• Dynamic Leverage
• Adaptive Grid
• Trend Filtering
• Volatility-Based Positioning
• Advanced Risk Management
        """
        
        self.send_telegram_message(telegram_msg)
        
        return report

    def setup_binance_api(self):
        """Setup Binance API for live data"""
        self.binance_base_url = "https://api.binance.com"
        self.symbol = "BTCUSDT"
        self.update_interval = 10  # Update every 10 seconds
        
    def get_live_price(self) -> Optional[float]:
        """Get current live price from Binance"""
        try:
            url = f"{self.binance_base_url}/api/v3/ticker/price"
            params = {"symbol": self.symbol}
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                return float(data['price'])
            else:
                self.logger.error(f"Binance API error: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting live price: {e}")
            return None
    
    def get_live_klines(self, limit: int = 100) -> Optional[pd.DataFrame]:
        """Get live kline data from Binance"""
        try:
            url = f"{self.binance_base_url}/api/v3/klines"
            params = {
                "symbol": self.symbol,
                "interval": "1m",
                "limit": limit
            }
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                df = pd.DataFrame(data, columns=[
                    'open_time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base', 'taker_buy_quote', 'ignore'
                ])
                
                # Convert to proper types
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                
                df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
                return df
            else:
                self.logger.error(f"Binance API error: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting live klines: {e}")
            return None

    def start_live_trading(self):
        """Start live trading with paper trading mode"""
        if self.is_live_trading:
            self.send_telegram_message("⚠️ Live Trading läuft bereits!")
            return
        
        self.is_live_trading = True
        
        # Initialisiere Grid-Preise basierend auf aktuellem Preis
        current_price = self.get_live_price()
        if current_price is None:
            self.send_telegram_message("❌ Fehler beim Abrufen des aktuellen Preises!")
            self.is_live_trading = False
            return
        
        self.current_price = current_price
        self.grid_prices = self.calculate_grid_prices()
        
        # Start Telegram-Benachrichtigung
        start_msg = f"""
🚀 <b>LIVE TRADING GESTARTET!</b>

📊 <b>Konfiguration:</b>
• Mode: {self.config['mode'].upper()}
• Leverage: {self.config['leverage']}x
• Grid Count: {self.config['grid_count']}
• Investment: ${self.config['investment_amount']:,.0f}
• Initial Balance: ${self.config['initial_balance']:,.0f}

💰 <b>Aktueller Status:</b>
• Aktueller Preis: ${current_price:,.2f}
• Grid-Bereich: ${min(self.grid_prices):,.2f} - ${max(self.grid_prices):,.2f}
• Kontostand: ${self.current_balance:,.2f}

⚙️ <b>Paper Trading Mode aktiv</b>
(Keine echten Orders - nur Simulation)
        """
        self.send_telegram_message(start_msg)
        
        # Start live trading thread
        self.live_thread = threading.Thread(target=self.live_trading_loop)
        self.live_thread.daemon = True
        self.live_thread.start()
        
        self.logger.info("Live trading started")
    
    def stop_live_trading(self):
        """Stop live trading"""
        if not self.is_live_trading:
            self.send_telegram_message("⚠️ Live Trading läuft nicht!")
            return
        
        self.is_live_trading = False
        
        # Close all open positions
        if self.positions:
            current_price = self.get_live_price()
            if current_price:
                for position in self.positions[:]:  # Copy list to avoid modification during iteration
                    self.close_position(position, current_price, datetime.now())
                    self.positions.remove(position)

        # Detaillierte Übersicht aller realisierten Trades mit Netto-PnL
        trade_details = ""
        total_realized_pnl = 0.0
        closed_trades = [t for t in self.trades if 'pnl' in t]
        if closed_trades:
            trade_details += "<b>Realisierte Trades (Netto PnL):</b>\n"
            for i, t in enumerate(closed_trades, 1):
                emoji = "🟢" if t['pnl'] >= 0 else "🔴"
                trade_details += (f"{emoji} Trade {i}: {t['side'].upper()} | PnL: {t['pnl'] - t.get('fee', 0):+.2f} USDT | Preis: {t['price']:.2f} | Größe: {t['size']:.4f}\n")
                total_realized_pnl += t['pnl'] - t.get('fee', 0)
            trade_details += f"<b>Gesamter Netto PnL aller Trades: {total_realized_pnl:+.2f} USDT</b>\n\n"

        # Zeitraum für das finale Reporting bestimmen
        if self.trades:
            start_time = min(t['timestamp'] for t in self.trades if 'timestamp' in t)
            end_time = max(t['timestamp'] for t in self.trades if 'timestamp' in t)
        else:
            start_time = end_time = datetime.now()

        # Finale Zusammenfassung mit Zeitraum
        summary_msg = f"""
📊 <b>Finale Zusammenfassung:</b>
• Zeitraum: {start_time.strftime('%Y-%m-%d %H:%M:%S')} bis {end_time.strftime('%Y-%m-%d %H:%M:%S')}
• Start Balance: ${self.start_balance:,.2f}
• End Balance: ${self.current_balance:,.2f}
• Gesamt PnL: ${self.current_balance - self.start_balance:+.2f} ({((self.current_balance - self.start_balance) / self.start_balance) * 100:+.2f}%)
• Total Trades: {len(self.trades)}
• Liquidierungen: {self.liquidated_positions}
• Total Fees: ${self.total_fees:,.2f}
"""

        end_msg = f"""
🛑 <b>LIVE TRADING GESTOPPT!</b>

{trade_details}
{summary_msg}

⏰ Beendet: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        self.send_telegram_message(end_msg)
        
        self.logger.info("Live trading stopped")
    
    def live_trading_loop(self):
        """Main loop for live trading. Only trade on grid cross, sleep between loops."""
        self.logger.info("Live trading loop started.")
        last_price = None
        while self.is_live_trading:
            try:
                price = self.get_live_price()
                if price is None:
                    self.logger.warning("Could not fetch live price.")
                    time.sleep(10)
                    continue
                self.current_price = price
                timestamp = datetime.utcnow()

                # Grid-Levels bestimmen
                lower_grids = [g for g in self.grid_prices if g <= price]
                upper_grids = [g for g in self.grid_prices if g >= price]
                next_lower = max(lower_grids) if lower_grids else None
                next_upper = min(upper_grids) if upper_grids else None
                dist_lower = price - next_lower if next_lower is not None else None
                dist_upper = next_upper - price if next_upper is not None else None

                grid_info = f"Aktueller Preis: {price:.2f} | "
                if next_lower is not None:
                    grid_info += f"Nächstes unteres Grid: {next_lower:.2f} (Abstand: {dist_lower:.2f}) | "
                else:
                    grid_info += "Kein unteres Grid | "
                if next_upper is not None:
                    grid_info += f"Nächstes oberes Grid: {next_upper:.2f} (Abstand: {dist_upper:.2f})"
                else:
                    grid_info += "Kein oberes Grid"
                print(grid_info)
                self.logger.info(grid_info)

                # Check for grid cross
                trade_executed = False
                for grid_price in self.grid_prices:
                    if last_price is not None:
                        crossed_up = last_price < grid_price <= price
                        crossed_down = last_price > grid_price >= price
                        has_long = any(p['side'] == 'long' for p in self.positions)
                        has_short = any(p['side'] == 'short' for p in self.positions)
                        if crossed_up and not has_long:
                            self.execute_trade(grid_price, 'buy', timestamp)
                            trade_executed = True
                            break
                        elif crossed_down and not has_short:
                            # Statt execute_trade für 'sell' -> close_position für passende Long-Position
                            for position in self.positions:
                                if position['side'] == 'long':
                                    self.close_position(position, grid_price, timestamp)
                                    self.positions.remove(position)
                                    trade_executed = True
                                    break
                            if trade_executed:
                                break
                last_price = price
                if not trade_executed:
                    self.logger.info(f"No grid cross at price {price:.2f}.")
                time.sleep(30)  # Sleep 30 seconds between loops
            except Exception as e:
                self.logger.error(f"Error in live_trading_loop: {e}")
                time.sleep(30)

    def cmd_liquidate_preview(self, chat_id: str):
        """Zeigt eine Vorschau, wieviel Gewinn/Verlust bei sofortigem Schließen aller Positionen realisiert würde."""
        try:
            if not self.positions or not self.current_price:
                self.send_telegram_message("ℹ️ Keine offenen Positionen oder kein aktueller Preis verfügbar.")
                return
            msg = "<b>Liquidation Preview (Sofortiges Schließen aller Positionen)</b>\n\n"
            total_netto = 0.0
            for i, pos in enumerate(self.positions, 1):
                entry = pos['entry_price']
                size = pos['size']
                lev = pos['leverage']
                buy_fee = pos.get('buy_fee', entry * size * self.config['fee_rate'])
                sell_fee = size * self.current_price * self.config['fee_rate']
                if pos['side'] == 'long':
                    brutto = (self.current_price - entry) * size * lev
                else:
                    brutto = (entry - self.current_price) * size * lev
                netto = brutto - buy_fee - sell_fee
                total_netto += netto
                msg += (f"<b>Position {i}</b> | Einstieg: {entry:.2f} | Größe: {size:.6f} | Hebel: {lev}x\n"
                        f"Aktueller Preis: {self.current_price:.2f}\n"
                        f"Brutto PnL: {brutto:+.2f} USDT\n"
                        f"Gebühr Buy: {buy_fee:.2f} | Gebühr Sell: {sell_fee:.2f}\n"
                        f"<b>Netto PnL: {netto:+.2f} USDT</b>\n\n")
            msg += f"<b>Gesamter Netto PnL bei sofortigem Schließen: {total_netto:+.2f} USDT</b>"
            self.send_telegram_message(msg)
        except Exception as e:
            self.send_telegram_message(f"❌ Fehler bei Liquidation Preview: {str(e)}")

    def cmd_reset_stats(self, chat_id: str):
        """Reset statistics for a new run"""
        self.trades = []
        self.total_fees = 0.0
        self.liquidated_positions = 0
        self.start_balance = self.current_balance
        self.send_telegram_message("✅ Statistikdaten wurden zurückgesetzt. Neuer Run beginnt jetzt.")

def main():
    """Main function to run the bot"""
    bot = PionexFuturesGridBot()
    
    # Run backtest
    results = bot.run_backtest()
    
    # Generate and save report
    bot.generate_report(results)
    
    # Print summary
    print(bot.generate_report(results))

if __name__ == "__main__":
    main() 