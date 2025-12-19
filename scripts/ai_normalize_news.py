import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo_root / "src"))

import json
import requests
import time
from tna.config import load_config
from tna.storage_sqlite import SQLiteStore

def analyze_with_llama(title: str, summary: str, sp500_symbols: set) -> dict:
    """Call Ollama running on host Mac"""
    # Limit to top 50 symbols to fit in context
    symbol_sample = ', '.join(list(sp500_symbols)[:50])
    
    prompt = f"""Analyze this financial news article and extract:
1. Related S&P 500 stock tickers (only from this list: {symbol_sample}... and similar major stocks)
2. Sentiment score from -1.0 (very bearish) to 1.0 (very bullish)

Article title: {title}
Summary: {summary}

Respond ONLY with valid JSON in this exact format:
{{"tickers": ["AAPL", "MSFT"], "sentiment": 0.65}}

If no relevant stocks, use empty list: {{"tickers": [], "sentiment": 0.0}}"""

    try:
        response = requests.post(
            'http://host.docker.internal:11434/api/generate',
            json={
                "model": "llama3:8b",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3}
            },
            timeout=30
        )
        
        result_text = response.json()['response']
        # Extract JSON from response (LLM might add extra text)
        start = result_text.find('{')
        end = result_text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(result_text[start:end])
        else:
            return {"tickers": [], "sentiment": 0.0}
    except Exception as e:
        print(f"Error analyzing article: {e}")
        return {"tickers": [], "sentiment": 0.0}

if __name__ == "__main__":
    cfg = load_config("config.yml")
    store = SQLiteStore(db_path=Path(cfg.db_path))
    
    # Get S&P 500 symbols
    with store.connect() as con:
        rows = con.execute("SELECT symbol FROM universe_membership").fetchall()
        sp500_symbols = {row[0] for row in rows}
    
    # Get ONLY unprocessed articles (deduplication)
    with store.connect() as con:
        unprocessed = con.execute("""
            SELECT id, title, summary, source, article_url, 
                   published_time_utc, fetched_time_utc
            FROM news_raw
            WHERE id NOT IN (SELECT id FROM news_normalized)
            ORDER BY fetched_time_utc DESC
        """).fetchall()
    
    total = len(unprocessed)
    print(f"Found {total} unprocessed articles")
    
    if total == 0:
        print("✅ All articles already normalized!")
        sys.exit(0)
    
    for idx, row in enumerate(unprocessed, 1):
        article_id, title, summary, source, url, pub_time, fetch_time = row
        
        print(f"[{idx}/{total}] Analyzing: {(title or '')[:60]}...")
        
        # Analyze with Llama3
        result = analyze_with_llama(title or '', summary or '', sp500_symbols)
        
        # Insert into normalized table
        with store.connect() as con:
            con.execute("""
                INSERT OR REPLACE INTO news_normalized 
                (id, source, article_url, published_time_utc, fetched_time_utc,
                 title, summary, text_clean, tickers_json, mapping_debug_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                article_id, source, url, pub_time, fetch_time,
                title, summary, f"{title or ''} {summary or ''}",
                json.dumps(result.get('tickers', [])),
                json.dumps({
                    'sentiment': result.get('sentiment', 0.0),
                    'method': 'llama3_8b'
                })
            ))
            con.commit()
        
        tickers_str = ', '.join(result['tickers']) if result['tickers'] else 'none'
        print(f"  → Tickers: {tickers_str} | Sentiment: {result['sentiment']:.2f}")
        
        # Small delay to not overwhelm Ollama
        time.sleep(0.5)
    
    print(f"\n✅ Processed {total} articles with Llama3")
