import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Tuple
import itertools
from pionex_futures_grid_bot import PionexFuturesGridBot

class PionexOptimizer:
    """
    Optimizer for Pionex Futures Grid Bot parameters
    """
    
    def __init__(self, base_config_file: str = "pionex_config.json"):
        self.base_config = self.load_config(base_config_file)
        self.setup_logging()
        self.setup_telegram()
        
        # Optimization state
        self.best_result = None
        self.best_params = None
        self.all_results = []
        self.test_count = 0
        self.start_time = time.time()
        
    def load_config(self, config_file: str) -> Dict:
        """Load base configuration"""
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def setup_logging(self):
        """Setup logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('pionex_optimizer.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_telegram(self):
        """Setup Telegram"""
        self.telegram_token = self.base_config['telegram_token']
        self.telegram_chat_id = self.base_config['telegram_chat_id']
        self.telegram_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
    
    def send_telegram_message(self, message: str):
        """Send Telegram message"""
        try:
            if self.telegram_token != "YOUR_TELEGRAM_TOKEN":
                import requests
                payload = {
                    'chat_id': self.telegram_chat_id,
                    'text': message,
                    'parse_mode': 'HTML'
                }
                response = requests.post(self.telegram_url, data=payload, timeout=10)
                if response.status_code != 200:
                    self.logger.warning(f"Telegram failed: {response.text}")
        except Exception as e:
            self.logger.error(f"Telegram error: {e}")
    
    def generate_parameter_combinations(self) -> List[Dict]:
        """Generate parameter combinations to test"""
        # Define parameter ranges
        param_ranges = {
            'leverage': [2, 3, 5],
            'grid_count': [10, 15, 20, 25],
            'investment_amount': [500, 1000, 1500],
            'stop_loss_pct': [0.03, 0.05, 0.07],
            'take_profit_pct': [0.08, 0.10, 0.12],
            'mode': ['long', 'short']
        }
        
        # Generate all combinations
        keys = param_ranges.keys()
        combinations = []
        
        for values in itertools.product(*param_ranges.values()):
            params = dict(zip(keys, values))
            combinations.append(params)
        
        self.logger.info(f"Generated {len(combinations)} parameter combinations")
        return combinations
    
    def create_test_config(self, params: Dict) -> Dict:
        """Create test configuration with given parameters"""
        config = self.base_config.copy()
        config.update(params)
        return config
    
    def save_test_config(self, config: Dict, test_id: int) -> str:
        """Save test configuration to temporary file"""
        filename = f"temp_config_{test_id}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        return filename
    
    def run_single_test(self, params: Dict) -> Tuple[Dict, Dict]:
        """Run single backtest with given parameters"""
        self.test_count += 1
        
        # Create test config
        test_config = self.create_test_config(params)
        config_file = self.save_test_config(test_config, self.test_count)
        
        try:
            # Run backtest
            bot = PionexFuturesGridBot(config_file)
            results = bot.run_backtest()
            
            # Add parameter info to results
            results['parameters'] = params
            results['test_id'] = self.test_count
            
            return results, params
            
        except Exception as e:
            self.logger.error(f"Test {self.test_count} failed: {e}")
            return None, params
        finally:
            # Clean up temp config file
            import os
            if os.path.exists(config_file):
                os.remove(config_file)
    
    def update_best_result(self, results: Dict, params: Dict):
        """Update best result if current is better"""
        if results is None:
            return
        
        if self.best_result is None or results['total_return'] > self.best_result['total_return']:
            self.best_result = results
            self.best_params = params
            
            self.logger.info(f"New best result: {results['total_return']*100:.2f}% return")
            self.logger.info(f"Parameters: {params}")
    
    def generate_progress_report(self) -> str:
        """Generate progress report"""
        elapsed_time = time.time() - self.start_time
        elapsed_hours = elapsed_time / 3600
        
        report = []
        report.append("=" * 50)
        report.append("PIONEX OPTIMIZER - PROGRESS REPORT")
        report.append("=" * 50)
        report.append(f"Tests completed: {self.test_count}")
        report.append(f"Elapsed time: {elapsed_hours:.1f} hours")
        report.append("")
        
        if self.best_result:
            report.append("BEST RESULT SO FAR:")
            report.append("-" * 25)
            report.append(f"Total Return: {self.best_result['total_return']*100:.2f}%")
            report.append(f"Final Balance: ${self.best_result['final_balance']:,.2f}")
            report.append(f"Max Drawdown: {self.best_result['max_drawdown']*100:.2f}%")
            report.append(f"Win Rate: {self.best_result['win_rate']:.2f}%")
            report.append(f"Total Trades: {self.best_result['total_trades']}")
            report.append("")
            report.append("BEST PARAMETERS:")
            report.append("-" * 25)
            for key, value in self.best_params.items():
                report.append(f"{key}: {value}")
        
        report.append("=" * 50)
        
        return "\n".join(report)
    
    def save_progress(self):
        """Save current progress to file"""
        progress_data = {
            'timestamp': datetime.now().isoformat(),
            'test_count': self.test_count,
            'elapsed_time': time.time() - self.start_time,
            'best_result': self.best_result,
            'best_params': self.best_params,
            'all_results': self.all_results
        }
        
        filename = f"pionex_optimization_progress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, indent=2, default=str)
        
        self.logger.info(f"Progress saved to {filename}")
    
    def send_telegram_progress(self):
        """Send progress update via Telegram"""
        if self.best_result:
            message = f"""
🔄 <b>Pionex Optimizer Progress</b>

📊 <b>Status:</b>
• Tests completed: {self.test_count}
• Best return: {self.best_result['total_return']*100:.2f}%
• Best balance: ${self.best_result['final_balance']:,.2f}

⚙️ <b>Best Parameters:</b>
• Leverage: {self.best_params['leverage']}x
• Grids: {self.best_params['grid_count']}
• Mode: {self.best_params['mode']}
• Investment: ${self.best_params['investment_amount']}
            """
            
            self.send_telegram_message(message)
    
    def run_optimization(self, max_tests: int = None):
        """Run complete optimization"""
        self.logger.info("Starting Pionex Futures Grid Optimization...")
        self.send_telegram_message("🚀 Pionex Optimizer gestartet!")
        
        # Generate parameter combinations
        combinations = self.generate_parameter_combinations()
        
        if max_tests:
            combinations = combinations[:max_tests]
        
        self.logger.info(f"Will test {len(combinations)} combinations")
        
        # Test each combination
        for i, params in enumerate(combinations):
            self.logger.info(f"Testing combination {i+1}/{len(combinations)}: {params}")
            
            results, _ = self.run_single_test(params)
            
            if results:
                self.all_results.append(results)
                self.update_best_result(results, params)
            
            # Progress reporting
            if (i + 1) % self.base_config.get('report_interval', 10) == 0:
                print(self.generate_progress_report())
                self.save_progress()
                self.send_telegram_progress()
            
            # Save interval
            if (i + 1) % self.base_config.get('save_interval', 15) == 0:
                self.save_progress()
        
        # Final report
        self.generate_final_report()
        
        self.logger.info("Optimization completed!")
        self.send_telegram_message("✅ Pionex Optimizer abgeschlossen!")
    
    def generate_final_report(self):
        """Generate final optimization report"""
        if not self.best_result:
            self.logger.warning("No successful tests completed")
            return
        
        # Sort all results by return
        sorted_results = sorted(self.all_results, key=lambda x: x['total_return'], reverse=True)
        
        # Generate report
        report = []
        report.append("=" * 60)
        report.append("PIONEX FUTURES GRID - OPTIMIZATION FINAL REPORT")
        report.append("=" * 60)
        report.append(f"Total tests: {len(self.all_results)}")
        report.append(f"Optimization time: {(time.time() - self.start_time)/3600:.1f} hours")
        report.append("")
        
        # Top 10 results
        report.append("TOP 10 RESULTS:")
        report.append("-" * 30)
        for i, result in enumerate(sorted_results[:10]):
            report.append(f"{i+1}. Return: {result['total_return']*100:.2f}% | "
                         f"Balance: ${result['final_balance']:,.2f} | "
                         f"Drawdown: {result['max_drawdown']*100:.2f}% | "
                         f"Trades: {result['total_trades']}")
        report.append("")
        
        # Best result details
        report.append("BEST RESULT DETAILS:")
        report.append("-" * 30)
        report.append(f"Total Return: {self.best_result['total_return']*100:.2f}%")
        report.append(f"Final Balance: ${self.best_result['final_balance']:,.2f}")
        report.append(f"Max Drawdown: {self.best_result['max_drawdown']*100:.2f}%")
        report.append(f"Win Rate: {self.best_result['win_rate']:.2f}%")
        report.append(f"Total Trades: {self.best_result['total_trades']}")
        report.append(f"Liquidated Positions: {self.best_result['liquidated_positions']}")
        report.append("")
        
        report.append("BEST PARAMETERS:")
        report.append("-" * 30)
        for key, value in self.best_params.items():
            report.append(f"{key}: {value}")
        report.append("")
        
        # Statistics
        returns = [r['total_return'] for r in self.all_results]
        report.append("STATISTICS:")
        report.append("-" * 30)
        report.append(f"Average Return: {np.mean(returns)*100:.2f}%")
        report.append(f"Median Return: {np.median(returns)*100:.2f}%")
        report.append(f"Best Return: {max(returns)*100:.2f}%")
        report.append(f"Worst Return: {min(returns)*100:.2f}%")
        report.append(f"Standard Deviation: {np.std(returns)*100:.2f}%")
        report.append("")
        
        report.append("=" * 60)
        
        # Save report
        report_text = "\n".join(report)
        with open("pionex_optimization_final_report.txt", 'w', encoding='utf-8') as f:
            f.write(report_text)
        
        print(report_text)
        
        # Save best config
        best_config = self.create_test_config(self.best_params)
        with open("pionex_best_config.json", 'w', encoding='utf-8') as f:
            json.dump(best_config, f, indent=2)
        
        self.logger.info("Final report saved")

def main():
    """Main function"""
    import numpy as np
    
    optimizer = PionexOptimizer()
    
    # Run optimization with limited tests for quick testing
    optimizer.run_optimization(max_tests=50)

if __name__ == "__main__":
    main() 