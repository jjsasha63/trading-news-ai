#!/usr/bin/env python3
"""
Real-time monitoring dashboard for the trading pipeline.
Runs a simple web server showing pipeline status, data quality, and recent signals.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import json


DB_PATH = Path("data/tna.sqlite")
PORT = 8050


def get_db_stats() -> dict:
    """Get current database statistics."""
    if not DB_PATH.exists():
        return {"error": "Database not found"}
    
    conn = sqlite3.connect(DB_PATH)
    try:
        stats = {}
        
        # Universe stats
        cursor = conn.execute("SELECT COUNT(*) FROM universe_membership")
        stats["universe_symbols"] = cursor.fetchone()[0]
        
        # Prices stats
        cursor = conn.execute("""
            SELECT COUNT(*), MIN(date), MAX(date) 
            FROM prices_daily
        """)
        row = cursor.fetchone()
        stats["price_rows"] = row[0]
        stats["price_date_range"] = f"{row[1]} to {row[2]}" if row[1] else "N/A"
        
        # News stats
        cursor = conn.execute("""
            SELECT COUNT(*), MAX(published_time_utc)
            FROM news_raw
        """)
        row = cursor.fetchone()
        stats["news_articles"] = row[0]
        stats["latest_news"] = row[1] if row[1] else "N/A"
        
        # Features stats
        cursor = conn.execute("""
            SELECT COUNT(*), MAX(date)
            FROM features_daily
        """)
        row = cursor.fetchone()
        stats["feature_rows"] = row[0]
        stats["latest_features"] = row[1] if row[1] else "N/A"
        
        # Backtest results
        try:
            cursor = conn.execute("""
            SELECT run_id, start_date, end_date, total_return, sharpe_ratio, max_drawdown
            FROM backtest_results
            ORDER BY run_id DESC
            LIMIT 1
        """)
            row = cursor.fetchone()
            if row:
                stats["latest_backtest"] = {
                    "run_id": row[0],
                    "period": f"{row[1]} to {row[2]}",
                    "total_return": f"{row[3]:.2%}" if row[3] else "N/A",
                    "sharpe": f"{row[4]:.2f}" if row[4] else "N/A",
                    "max_dd": f"{row[5]:.2%}" if row[5] else "N/A",
                }
            else:
                stats["latest_backtest"] = None
        except:
            stats["latest_backtest"] = None
        
        # Recent signals
        try:
            cursor = conn.execute("""
                SELECT symbol, date, signal, score
                FROM signals
                WHERE date >= date('now', '-7 days')
                ORDER BY date DESC, score DESC
                LIMIT 10
            """)
            stats["recent_signals"] = [
                {"symbol": r[0], "date": r[1], "signal": r[2], "score": f"{r[3]:.3f}"}
                for r in cursor.fetchall()
            ]
        except Exception:
            stats["recent_signals"] = []
        
        return stats
        
    finally:
        conn.close()


def render_html(stats: dict) -> str:
    """Render HTML dashboard."""
    
    if "error" in stats:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Trading News AI - Monitor</title>
            <meta http-equiv="refresh" content="30">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
                .error {{ color: red; font-size: 18px; }}
            </style>
        </head>
        <body>
            <h1>Trading News AI - Monitor</h1>
            <p class="error">ERROR: {stats['error']}</p>
        </body>
        </html>
        """
    
    backtest_html = ""
    if stats.get("latest_backtest"):
        bt = stats["latest_backtest"]
        backtest_html = f"""
        <tr><td>Backtest Period</td><td>{bt['period']}</td></tr>
        <tr><td>Total Return</td><td>{bt['total_return']}</td></tr>
        <tr><td>Sharpe Ratio</td><td>{bt['sharpe']}</td></tr>
        <tr><td>Max Drawdown</td><td>{bt['max_dd']}</td></tr>
        """
    else:
        backtest_html = "<tr><td colspan='2'>No backtest results yet</td></tr>"
    
    signals_html = ""
    for sig in stats.get("recent_signals", []):
        signals_html += f"<tr><td>{sig['symbol']}</td><td>{sig['date']}</td><td>{sig['signal']}</td><td>{sig['score']}</td></tr>"
    
    if not signals_html:
        signals_html = "<tr><td colspan='4'>No recent signals</td></tr>"
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Trading News AI - Monitor</title>
        <meta http-equiv="refresh" content="30">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                border-bottom: 3px solid #667eea;
                padding-bottom: 10px;
            }}
            h2 {{
                color: #555;
                margin-top: 30px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
            }}
            th, td {{
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }}
            th {{
                background-color: #667eea;
                color: white;
                font-weight: bold;
            }}
            tr:hover {{
                background-color: #f5f5f5;
            }}
            .status {{
                display: inline-block;
                padding: 5px 15px;
                border-radius: 20px;
                background: #4caf50;
                color: white;
                font-weight: bold;
            }}
            .timestamp {{
                color: #888;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Trading News AI - Live Monitor</h1>
            <p class="timestamp">Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Auto-refresh: 30s</p>
            <p><span class="status">RUNNING</span></p>
            
            <h2>Pipeline Statistics</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Universe Symbols</td><td>{stats.get('universe_symbols', 0):,}</td></tr>
                <tr><td>Price Data Points</td><td>{stats.get('price_rows', 0):,}</td></tr>
                <tr><td>Price Date Range</td><td>{stats.get('price_date_range', 'N/A')}</td></tr>
                <tr><td>News Articles</td><td>{stats.get('news_articles', 0):,}</td></tr>
                <tr><td>Latest News</td><td>{stats.get('latest_news', 'N/A')}</td></tr>
                <tr><td>Feature Rows</td><td>{stats.get('feature_rows', 0):,}</td></tr>
                <tr><td>Latest Features</td><td>{stats.get('latest_features', 'N/A')}</td></tr>
            </table>
            
            <h2>Latest Backtest Performance</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                {backtest_html}
            </table>
            
            <h2>Recent Signals (Last 7 Days)</h2>
            <table>
                <tr><th>Symbol</th><th>Date</th><th>Signal</th><th>Score</th></tr>
                {signals_html}
            </table>
        </div>
    </body>
    </html>
    """


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            stats = get_db_stats()
            html = render_html(stats)
            
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode())
        
        elif self.path == "/api/stats":
            stats = get_db_stats()
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(stats, indent=2).encode())
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass


def main():
    print(f"Starting monitoring dashboard on http://0.0.0.0:{PORT}")
    print(f"Access from host: http://localhost:{PORT}")
    print("Press Ctrl+C to stop")
    
    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
