"""네이버/KRX 기반 가격·시세·컨센서스 데이터 수집"""
import re
import datetime as dt
import requests
from bs4 import BeautifulSoup
import FinanceDataReader as fdr

HEADERS = {"User-Agent": "Mozilla/5.0"}


def price_snapshot(code: str) -> dict:
    """최근 1년 시세로 현재가/전일대비/52주 고저/12개월 수익률 계산"""
    end = dt.date.today()
    start = end - dt.timedelta(days=380)
    df = fdr.DataReader(code, start, end)
    if df.empty:
        raise ValueError(f"{code} 시세 데이터를 가져오지 못했습니다.")

    df = df.sort_index()
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    close = float(last["Close"])
    prev_close = float(prev["Close"])
    change_pct = (close - prev_close) / prev_close * 100 if prev_close else 0.0

    year_df = df.tail(252) if len(df) > 252 else df
    high52 = float(year_df["High"].max())
    high52_date = year_df["High"].idxmax().strftime("%y.%m.%d")
    low52 = float(year_df["Low"].min())
    low52_date = year_df["Low"].idxmin().strftime("%y.%m.%d")

    base_idx = df.index[df.index <= (df.index[-1] - dt.timedelta(days=365))]
    if len(base_idx) > 0:
        base_close = float(df.loc[base_idx[-1], "Close"])
        ret_12m = (close - base_close) / base_close * 100
    else:
        base_close = float(df.iloc[0]["Close"])
        ret_12m = (close - base_close) / base_close * 100

    return {
        "date": last.name.strftime("%Y.%m.%d"),
        "close": close,
        "change_pct": round(change_pct, 2),
        "high52": high52,
        "high52_date": high52_date,
        "low52": low52,
        "low52_date": low52_date,
        "ret_12m": round(ret_12m, 1),
        "pos_52w_pct": round((close - low52) / (high52 - low52) * 100, 1) if high52 != low52 else 50.0,
    }


def market_cap(code: str) -> dict:
    listing = fdr.StockListing("KRX")
    row = listing[listing["Code"] == code]
    if row.empty:
        return {"marcap": None, "shares": None}
    r = row.iloc[0]
    return {"marcap": float(r["Marcap"]), "shares": float(r["Stocks"])}


def consensus(code: str) -> dict:
    """네이버(FnGuide/WiseReport) 컨센서스 투자의견·목표주가"""
    url = "https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx"
    try:
        r = requests.get(url, params={"cmp_cd": code}, headers=HEADERS, timeout=10)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "lxml")
        text = soup.get_text(" ", strip=True)

        opinion, target, eps, per, num_analysts = None, None, None, None, None
        m = re.search(
            r"투자의견컨센서스\s*([\d.]+)\s*투자의견\s*목표주가\s*\(원\)\s*EPS\s*\(원\)\s*PER\s*\(배\)\s*추정기관수\s*"
            r"[\d.]+\s*([\d,]+)\s*([\d,\-]+)\s*([\d.\-]+)\s*(\d+)",
            text,
        )
        if m:
            opinion = float(m.group(1))
            target = float(m.group(2).replace(",", ""))
            eps = m.group(3).replace(",", "")
            per = m.group(4)
            num_analysts = int(m.group(5))
        return {
            "opinion_score": opinion,
            "target_price": target,
            "eps": eps,
            "per": per,
            "num_analysts": num_analysts,
        }
    except Exception:
        return {"opinion_score": None, "target_price": None}
