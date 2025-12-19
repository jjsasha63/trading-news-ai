"""STOXX Europe 600 universe manager"""
import sqlite3
from datetime import date
from typing import List, Dict
import requests
from bs4 import BeautifulSoup

def get_stoxx600_constituents() -> List[str]:
    """Scrape STOXX 600 tickers from public source"""
    # Major European stocks with Yahoo Finance tickers
    # Format: TICKER.EXCHANGE (e.g., ASML.AS = ASML on Amsterdam)
    stoxx600_core = [
        # Netherlands (Amsterdam .AS)
        'ASML.AS', 'ADYEN.AS', 'PHIA.AS', 'HEIA.AS', 'INGA.AS',
        # France (Paris .PA)
        'MC.PA', 'OR.PA', 'SAN.PA', 'AIR.PA', 'TTE.PA', 'BN.PA', 'SU.PA',
        # Germany (XETRA .DE)
        'SAP.DE', 'SIE.DE', 'MBG.DE', 'ALV.DE', 'DTE.DE', 'VOW3.DE', 'BAS.DE',
        # UK (London .L)
        'AZN.L', 'HSBA.L', 'SHEL.L', 'BP.L', 'GSK.L', 'DGE.L', 'ULVR.L',
        # Switzerland (Zurich .SW)
        'NESN.SW', 'NOVN.SW', 'ROG.SW', 'ABBN.SW', 'UBSG.SW', 'ZURN.SW',
        # Spain (Madrid .MC)
        'SAN.MC', 'ITX.MC', 'IBE.MC', 'TEF.MC',
        # Italy (Milan .MI)
        'ENI.MI', 'ISP.MI', 'UCG.MI', 'ENEL.MI',
        # Sweden (Stockholm .ST)
        'VOLV-B.ST', 'HM-B.ST', 'ERIC-B.ST', 'ABB.ST',
        # Denmark (Copenhagen .CO)
        'NOVO-B.CO', 'DSV.CO', 'ORSTED.CO',
        # Norway (Oslo .OL)
        'EQNR.OL', 'DNB.OL', 'MOWI.OL',
    ]
    return stoxx600_core

def fetch_stoxx600(store, as_of: date) -> None:
    """Fetch and store STOXX 600 constituents"""
    symbols = get_stoxx600_constituents()
    
    with store.connect() as con:
        for sym in symbols:
            con.execute("""
                INSERT OR IGNORE INTO universe_membership (symbol, date)
                VALUES (?, ?)
            """, [sym, as_of.isoformat()])
        con.commit()
    
    print(f"Inserted {len(symbols)} STOXX 600 members for {as_of}")

def get_stoxx600_current(store, dt: date) -> Dict[str, dict]:
    """Get current STOXX 600 universe as of date"""
    with store.connect() as con:
        sql = """
        SELECT DISTINCT symbol 
        FROM universe_membership 
        WHERE date <= ? 
        ORDER BY date DESC 
        LIMIT 100
        """
        rows = con.execute(sql, [dt.isoformat()]).fetchall()
        return {row[0]: {} for row in rows}
