#!/usr/bin/env python3
"""
Pionex Futures Grid Bot Runner
Simple script to run the bot in different modes
"""

import argparse
import json
import sys
import time
import threading
from pionex_futures_grid_bot import PionexFuturesGridBot
from pionex_optimizer import PionexOptimizer
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# Global variables for health check
bot = None
start_time = None

def main():
    global bot, start_time
    
    parser = argparse.ArgumentParser(description='Pionex Futures Grid Bot Runner')
    parser.add_argument('--mode', choices=['backtest', 'optimize', 'live'], default='live',
                       help='Mode to run: backtest, optimize, or live (default: live)')
    parser.add_argument('--config', default='pionex_config.json',
                       help='Configuration file path')
    parser.add_argument('--max-tests', type=int, default=None,
                       help='Maximum number of tests for optimization')
    parser.add_argument('--duration', type=int, default=None,
                       help='Live trading duration in minutes (default: run indefinitely)')
    parser.add_argument('--port', type=int, default=5000,
                       help='Port for Flask server (default: 5000)')
    
    args = parser.parse_args()
    
    if args.mode == 'backtest':
        print("🚀 Starting Pionex Futures Grid Bot Backtest...")
        bot = PionexFuturesGridBot(args.config)
        results = bot.run_backtest()
        bot.generate_report(results)
        print("✅ Backtest completed!")
        
    elif args.mode == 'optimize':
        print("🔧 Starting Pionex Futures Grid Bot Optimization...")
        optimizer = PionexOptimizer(args.config)
        optimizer.run_optimization(max_tests=args.max_tests)
        print("✅ Optimization completed!")
        
    elif args.mode == 'live':
        print("🌐 Starting Pionex Futures Grid Bot Live Trading...")
        print("📱 Telegram Bot Control: Sende /help für verfügbare Befehle")
        print("🔧 Debug: Sende /debug info für System-Status")
        
        bot = PionexFuturesGridBot(args.config)
        start_time = datetime.now()
        
        # Start Flask server in a separate thread
        def run_flask():
            app.run(host='0.0.0.0', port=args.port, debug=False)
        
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        try:
            # Start live trading
            bot.start_live_trading()
            
            # Run for specified duration or indefinitely
            if args.duration:
                print(f"⏰ Live trading läuft für {args.duration} Minuten...")
                print("Drücke Ctrl+C zum vorzeitigen Stoppen")
                time.sleep(args.duration * 60)
            else:
                print("⏰ Live trading läuft unbegrenzt...")
                print("Drücke Ctrl+C zum Stoppen")
                print("📱 Verwende /stop über Telegram zum Fernstoppen")
                
                # Keep running indefinitely
                while True:
                    time.sleep(60)  # Check every minute
                    
        except KeyboardInterrupt:
            print("\n🛑 Stoppe Live Trading...")
        finally:
            # Stop live trading
            bot.stop_live_trading()
            print("✅ Live Trading gestoppt!")

@app.route('/health')
def health_check():
    """Health check endpoint for Docker and monitoring"""
    try:
        # Check if bot is running
        bot_status = "running" if bot and hasattr(bot, 'is_running') and bot.is_running else "stopped"
        
        return jsonify({
            'status': 'healthy',
            'bot_status': bot_status,
            'timestamp': datetime.now().isoformat(),
            'uptime': str(datetime.now() - start_time) if start_time else 'unknown'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/metrics')
def metrics():
    """Prometheus metrics endpoint"""
    try:
        # Basic metrics for monitoring
        metrics_data = {
            'pionex_bot_running': 1 if bot and hasattr(bot, 'is_running') and bot.is_running else 0,
            'pionex_bot_uptime_seconds': (datetime.now() - start_time).total_seconds() if start_time else 0,
            'pionex_bot_total_trades': len(bot.trades) if bot and hasattr(bot, 'trades') else 0,
            'pionex_bot_open_positions': len(bot.positions) if bot and hasattr(bot, 'positions') else 0,
            'pionex_bot_balance_usdt': bot.balance if bot and hasattr(bot, 'balance') else 0
        }
        
        # Format as Prometheus metrics
        prometheus_metrics = []
        for metric_name, value in metrics_data.items():
            prometheus_metrics.append(f"# HELP {metric_name} {metric_name}")
            prometheus_metrics.append(f"# TYPE {metric_name} gauge")
            prometheus_metrics.append(f"{metric_name} {value}")
        
        return '\n'.join(prometheus_metrics), 200, {'Content-Type': 'text/plain'}
    except Exception as e:
        return f"# ERROR: {str(e)}", 500, {'Content-Type': 'text/plain'}

if __name__ == "__main__":
    main() 