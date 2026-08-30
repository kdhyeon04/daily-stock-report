"""
사용법: python analyze.py <종목명 또는 종목코드>
DART + 한국투자증권(KIS) 실시간 시세/네이버 컨센서스 데이터를 모아 data/<code>.json 으로 저장한다.
(종합점수/강점/리스크/매수전략 등 '분석' 항목은 비워둔 채 저장되며,
 이후 Claude가 이 JSON을 읽고 analysis 블록을 채운 뒤 render.py로 리포트를 만든다.)
"""
import sys
import json
import datetime as dt
import OpenDartReader

import config
import ticker
import data_kis
import data_naver
import data_dart


def _build_price(code: str) -> tuple[dict, dict, dict]:
    kis = data_kis.inquire_price(code)
    ret_12m = data_kis.twelve_month_return(code)

    price = {
        "date": kis["date"],
        "close": kis["close"],
        "change_pct": kis["change_pct"],
        "high52": kis["high52"],
        "high52_date": kis["high52_date"],
        "low52": kis["low52"],
        "low52_date": kis["low52_date"],
        "ret_12m": ret_12m,
        "pos_52w_pct": round((kis["close"] - kis["low52"]) / (kis["high52"] - kis["low52"]) * 100, 1)
        if kis["high52"] != kis["low52"] else 50.0,
    }
    market_cap = {"marcap": kis["marcap_eok"] * 1e8 if kis["marcap_eok"] else None, "shares": kis["shares"]}
    valuation = {"per": kis["per"], "pbr": kis["pbr"], "eps": kis["eps"], "bps": kis["bps"]}
    return price, market_cap, valuation


def build(name_or_code: str) -> dict:
    stock = ticker.resolve(name_or_code)
    code, name, market = stock["code"], stock["name"], stock["market"]

    print(f"[1/4] 종목 확인: {name} ({code}, {market})")

    print("[2/4] KIS 실시간 시세/시가총액 + 네이버 컨센서스 수집 중...")
    price, mcap, valuation = _build_price(code)
    cons = data_naver.consensus(code)

    print("[3/4] DART 분기 영업이익 수집 중...")
    dart = OpenDartReader(config.DART_API_KEY)
    info = data_dart.company_info(dart, code)
    quarters = data_dart.quarterly_operating_profit(dart, code)

    print("[4/4] JSON 저장 중...")
    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "stock": {"code": code, "name": name, "market": market},
        "company": info,
        "price": price,
        "market_cap": mcap,
        "valuation": valuation,
        "consensus": cons,
        "quarterly_operating_profit": quarters,
        # 아래는 Claude가 데이터 검토 후 직접 채우는 분석 영역 (자동 산출 불가한 판단 영역)
        "analysis": {
            "tagline": None,
            "total_score": None,
            "score_breakdown": {
                "industry": None, "growth": None, "finance": None,
                "moat": None, "technical": None, "risk_mgmt": None,
            },
            "rating": None,  # 예: "매수(BUY)" / "중립(HOLD)" / "매도(SELL)"
            "strengths": [],
            "risks": [],
            "entry_range": None,
            "stop_loss": None,
            "recommended_weight": None,
            "commentary": None,
        },
    }

    out_path = config.DATA_DIR / f"{code}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"완료 -> {out_path}")
    return payload


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python analyze.py <종목명 또는 종목코드>")
        sys.exit(1)
    build(" ".join(sys.argv[1:]))
