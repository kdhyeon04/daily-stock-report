"""
사용법: python render.py <종목코드>
data/<code>.json (analysis 채워진 상태) 을 읽어 reports/ 에 HTML 리포트를 생성하고 브라우저로 연다.
"""
import sys
import json
import webbrowser
import datetime as dt
from jinja2 import Environment, FileSystemLoader

import config


def _comma(n):
    if n is None:
        return None
    return f"{n:,.0f}"


def _eok_comma(n):
    if n is None:
        return None
    return f"{n:,.0f}"


def prepare(payload: dict) -> dict:
    price = payload["price"]
    mcap = payload["market_cap"]
    cons = payload["consensus"]
    analysis = payload["analysis"]

    price["close_fmt"] = _comma(price["close"])
    price["high52_fmt"] = _comma(price["high52"])
    price["low52_fmt"] = _comma(price["low52"])
    price["from_high_pct"] = round((price["close"] - price["high52"]) / price["high52"] * 100, 1)

    if mcap.get("marcap"):
        mcap["marcap_fmt"] = f"{mcap['marcap'] / 1e12:,.1f}조"
    else:
        mcap["marcap_fmt"] = "-"

    if cons.get("target_price"):
        cons["target_price_fmt"] = f"{cons['target_price']:,.0f}원"
        upside = (cons["target_price"] - price["close"]) / price["close"] * 100
        cons["upside_pct_fmt"] = f"{'+' if upside >= 0 else ''}{upside:.1f}%"
    else:
        cons["target_price_fmt"] = None
        cons["upside_pct_fmt"] = None

    qops = payload.get("quarterly_operating_profit") or []
    max_abs = max([abs(q["value_eok"]) for q in qops], default=1) or 1
    for q in qops:
        q["bar_pct"] = max(round(abs(q["value_eok"]) / max_abs * 100, 1), 3)
        q["color"] = "var(--red)" if q["value_eok"] < 0 else "var(--cyan)"
        q["value_fmt"] = _eok_comma(q["value_eok"])

    rating = (analysis.get("rating") or "").upper()
    if "매수" in (analysis.get("rating") or "") or "BUY" in rating:
        analysis["rating_class"] = "buy"
    elif "매도" in (analysis.get("rating") or "") or "SELL" in rating:
        analysis["rating_class"] = "sell"
    else:
        analysis["rating_class"] = "hold"

    payload["generated_at"] = payload.get("generated_at", dt.datetime.now().isoformat(timespec="seconds"))
    return payload


def render(code: str):
    path = config.DATA_DIR / f"{code}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload = prepare(payload)

    env = Environment(loader=FileSystemLoader(str(config.BASE_DIR)))
    tpl = env.get_template("template.html")
    html = tpl.render(**payload)

    today = dt.date.today().strftime("%Y%m%d")
    out_path = config.REPORTS_DIR / f"{payload['stock']['name']}_{code}_{today}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"리포트 생성 완료 -> {out_path}")
    webbrowser.open(out_path.resolve().as_uri())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python render.py <종목코드>")
        sys.exit(1)
    render(sys.argv[1])
