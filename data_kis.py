"""한국투자증권(KIS Developers) Open API 연동 - 실시간 시세/시가총액/52주/밸류에이션"""
import json
import time
import datetime as dt
import requests

import config

BASE_URL = "https://openapi.koreainvestment.com:9443"
TOKEN_CACHE = config.BASE_DIR / ".kis_token.json"


def _load_cached_token():
    if not TOKEN_CACHE.exists():
        return None
    try:
        cached = json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
        expire_at = dt.datetime.fromisoformat(cached["expire_at"])
        if dt.datetime.now() < expire_at - dt.timedelta(minutes=10):
            return cached["access_token"]
    except Exception:
        pass
    return None


def get_access_token() -> str:
    cached = _load_cached_token()
    if cached:
        return cached

    r = requests.post(
        f"{BASE_URL}/oauth2/tokenP",
        json={
            "grant_type": "client_credentials",
            "appkey": config.KIS_APP_KEY,
            "appsecret": config.KIS_APP_SECRET,
        },
        timeout=15,
    )
    body = r.json()
    if "access_token" not in body:
        raise RuntimeError(f"KIS 토큰 발급 실패: {body}")

    expire_at = dt.datetime.now() + dt.timedelta(seconds=body.get("expires_in", 86400))
    TOKEN_CACHE.write_text(
        json.dumps({"access_token": body["access_token"], "expire_at": expire_at.isoformat()}),
        encoding="utf-8",
    )
    return body["access_token"]


def _headers(tr_id: str) -> dict:
    return {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {get_access_token()}",
        "appkey": config.KIS_APP_KEY,
        "appsecret": config.KIS_APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P",
    }


def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _get(url: str, tr_id: str, params: dict) -> dict:
    """초당 거래건수 제한(EGW00201) 발생 시 짧게 대기 후 1회 재시도"""
    for attempt in range(2):
        r = requests.get(url, headers=_headers(tr_id), params=params, timeout=15)
        body = r.json()
        if body.get("msg_cd") == "EGW00201" and attempt == 0:
            time.sleep(1.0)
            continue
        return body
    return body


def inquire_price(code: str) -> dict:
    """국내주식 현재가 시세 (현재가/전일대비/시가총액/52주 고저/PER/PBR/EPS/BPS)"""
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}
    body = _get(url, "FHKST01010100", params)
    if body.get("rt_cd") != "0":
        raise RuntimeError(f"KIS 현재가 조회 실패({code}): {body}")
    o = body["output"]

    close = _num(o["stck_prpr"])
    change = _num(o["prdy_vrss"])
    sign = o.get("prdy_vrss_sign")  # 1,2 상승 / 3 보합 / 4,5 하락
    if sign in ("4", "5"):
        change = -abs(change)
    elif sign in ("1", "2"):
        change = abs(change)

    return {
        "date": dt.date.today().strftime("%Y.%m.%d"),
        "close": close,
        "change": change,
        "change_pct": _num(o["prdy_ctrt"]),
        "high52": _num(o["w52_hgpr"]),
        "high52_date": dt.datetime.strptime(o["w52_hgpr_date"], "%Y%m%d").strftime("%y.%m.%d") if o.get("w52_hgpr_date") else None,
        "low52": _num(o["w52_lwpr"]),
        "low52_date": dt.datetime.strptime(o["w52_lwpr_date"], "%Y%m%d").strftime("%y.%m.%d") if o.get("w52_lwpr_date") else None,
        "marcap_eok": _num(o.get("hts_avls")),  # 억원 단위
        "per": _num(o.get("per")),
        "pbr": _num(o.get("pbr")),
        "eps": _num(o.get("eps")),
        "bps": _num(o.get("bps")),
        "shares": _num(o.get("lstn_stcn")),
    }


def daily_chart(code: str, days: int = 380) -> list:
    """국내주식 기간별 시세 (일봉) - 12개월 수익률 계산용.

    inquire-daily-itemchartprice는 조회 구간과 무관하게 FID_INPUT_DATE_2를 기준으로
    직전 최대 100거래일만 반환한다. 필요한 기간을 채울 때까지 종료일을 앞으로
    당겨가며 여러 번 호출해 이어붙인다.
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    target_start = dt.date.today() - dt.timedelta(days=days)

    seen = {}
    window_end = dt.date.today()
    for i in range(8):
        if i > 0:
            time.sleep(0.5)
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": target_start.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": window_end.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        }
        body = _get(url, "FHKST03010100", params)
        if body.get("rt_cd") != "0":
            raise RuntimeError(f"KIS 일봉 조회 실패({code}): {body}")
        rows = [row for row in body.get("output2", []) if row.get("stck_bsop_date")]
        if not rows:
            break

        new_dates = 0
        for row in rows:
            if row["stck_bsop_date"] not in seen:
                seen[row["stck_bsop_date"]] = _num(row["stck_clpr"])
                new_dates += 1

        earliest = min(row["stck_bsop_date"] for row in rows)
        if earliest <= target_start.strftime("%Y%m%d") or new_dates == 0:
            break
        window_end = dt.datetime.strptime(earliest, "%Y%m%d").date() - dt.timedelta(days=1)

    out = [{"date": d, "close": c} for d, c in seen.items()]
    return sorted(out, key=lambda x: x["date"])


def twelve_month_return(code: str) -> float:
    rows = daily_chart(code, days=380)
    if len(rows) < 2:
        return 0.0
    latest = rows[-1]["close"]
    cutoff = (dt.date.today() - dt.timedelta(days=365)).strftime("%Y%m%d")
    base_candidates = [r for r in rows if r["date"] <= cutoff]
    base = base_candidates[-1]["close"] if base_candidates else rows[0]["close"]
    if not base:
        return 0.0
    return round((latest - base) / base * 100, 1)
