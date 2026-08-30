"""
매일 아침 지정 종목들의 객관적 데이터를 모아 대시보드(docs/index.html)를 생성하고
카카오톡으로 요약 알림을 보낸다. (GitHub Actions에서 매일 실행)

'분석'(강점/리스크/매수전략)은 사람의 판단이 필요해 채팅에서 Claude가 직접 작성하는
방식으로 운영하지만, 이 자동 발송본은 사람이 개입할 수 없으므로 규칙 기반의 단순 신호로
대체한다 (상승여력·QoQ 실적 추이 기준).
"""
import datetime as dt
from zoneinfo import ZoneInfo
import OpenDartReader
from jinja2 import Environment, FileSystemLoader

KST = ZoneInfo("Asia/Seoul")

import config
import ticker
import data_kis
import data_naver
import data_dart
import data_kakao

STOCK_LIST = ["삼성전자", "오킨스전자", "엔알비", "압타바이오"]
PAGES_URL = "https://kdhyeon04.github.io/daily-stock-report/"


def _comma(n):
    return f"{n:,.0f}" if n is not None else "-"


def build_stock_view(name: str, dart) -> dict:
    stock = ticker.resolve(name)
    code = stock["code"]

    kis = data_kis.inquire_price(code)
    ret_12m = data_kis.twelve_month_return(code)
    cons = data_naver.consensus(code)
    quarters = data_dart.quarterly_operating_profit(dart, code, n_quarters=2)

    pos_52w_pct = (
        round((kis["close"] - kis["low52"]) / (kis["high52"] - kis["low52"]) * 100, 1)
        if kis["high52"] != kis["low52"] else 50.0
    )

    upside_pct = None
    if cons.get("target_price"):
        upside_pct = round((cons["target_price"] - kis["close"]) / kis["close"] * 100, 1)

    qoq_pct = None
    if len(quarters) == 2 and quarters[0]["value_eok"]:
        prev, latest = quarters[0]["value_eok"], quarters[1]["value_eok"]
        if prev != 0:
            qoq_pct = round((latest - prev) / abs(prev) * 100, 1)

    if upside_pct is None:
        signal, signal_class = "데이터부족", "na"
    elif upside_pct >= 20 and (qoq_pct is None or qoq_pct >= 0):
        signal, signal_class = "긍정적 (BUY WATCH)", "buy"
    elif upside_pct <= 0:
        signal, signal_class = "주의 (CAUTION)", "caution"
    else:
        signal, signal_class = "중립 (HOLD)", "hold"

    return {
        "name": stock["name"],
        "code": code,
        "close": kis["close"],
        "close_fmt": _comma(kis["close"]),
        "change_pct": kis["change_pct"],
        "pos_52w_pct": pos_52w_pct,
        "ret_12m": ret_12m,
        "ret_12m_fmt": f"{'+' if ret_12m and ret_12m > 0 else ''}{ret_12m}%" if ret_12m is not None else "-",
        "target_fmt": f"{_comma(cons.get('target_price'))}원" if cons.get("target_price") else "-",
        "upside_fmt": f"{'+' if upside_pct and upside_pct > 0 else ''}{upside_pct}%" if upside_pct is not None else "-",
        "qoq_fmt": f"{'+' if qoq_pct and qoq_pct > 0 else ''}{qoq_pct}%" if qoq_pct is not None else "-",
        "signal": signal,
        "signal_class": signal_class,
    }


def build_dashboard() -> list:
    dart = OpenDartReader(config.DART_API_KEY)
    views = []
    for name in STOCK_LIST:
        try:
            views.append(build_stock_view(name, dart))
        except Exception as e:
            views.append({
                "name": name, "code": "-", "close": 0, "close_fmt": "-", "change_pct": 0,
                "pos_52w_pct": "-", "ret_12m": None, "ret_12m_fmt": "-", "target_fmt": "-",
                "upside_fmt": "-", "qoq_fmt": "-", "signal": f"수집실패", "signal_class": "na",
            })
            print(f"[경고] {name} 데이터 수집 실패: {e}")
    return views


def render_dashboard(views: list) -> str:
    env = Environment(loader=FileSystemLoader(str(config.BASE_DIR)))
    tpl = env.get_template("dashboard_template.html")
    html = tpl.render(stocks=views, generated_at=dt.datetime.now(KST).strftime("%Y.%m.%d %H:%M") + " KST")

    docs_dir = config.BASE_DIR / "docs"
    docs_dir.mkdir(exist_ok=True)
    out_path = docs_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)


def build_kakao_text(views: list) -> str:
    today = dt.datetime.now(KST).strftime("%y.%m.%d")
    lines = [f"📊 오늘의 주식 브리핑 ({today})"]
    for v in views:
        arrow = "▲" if v["change_pct"] and v["change_pct"] > 0 else "▼" if v["change_pct"] and v["change_pct"] < 0 else "-"
        lines.append(f"{v['name']} {v['close_fmt']}원 {arrow}{abs(v['change_pct']) if v['change_pct'] else 0}%")
    lines.append("자세한 수치는 아래 대시보드에서 확인하세요.")
    return "\n".join(lines)


def main():
    views = build_dashboard()
    path = render_dashboard(views)
    print(f"대시보드 생성 완료 -> {path}")

    access_token, new_refresh = data_kakao.refresh_access_token()
    if new_refresh:
        (config.BASE_DIR / ".kakao_new_refresh_token").write_text(new_refresh, encoding="utf-8")
        print("카카오 refresh_token이 갱신됨 -> .kakao_new_refresh_token")

    text = build_kakao_text(views)
    data_kakao.send_text(access_token, text, PAGES_URL)
    print("카카오톡 발송 완료")


if __name__ == "__main__":
    main()
