"""DART 공시 기반 분기 실적 데이터 수집"""
import datetime as dt
import OpenDartReader

REPORT_CODES = ["11013", "11012", "11014", "11011"]  # 1Q, 반기, 3Q, 사업(연간)


def _amount(val):
    if val in (None, "", "-"):
        return None
    try:
        return float(str(val).replace(",", ""))
    except ValueError:
        return None


def quarterly_operating_profit(dart, code: str, n_quarters: int = 5) -> list:
    """최근 n분기 영업이익(연결 우선, 없으면 별도)을 [{label, value_eok}] 리스트로 반환.

    DART 표준 재무제표에서 reprt_code=11012(반기)/11014(3분기)의 thstrm_amount는
    이미 해당 분기 단독 값이다(11012=2분기 단독, 11014=3분기 단독).
    누적치는 thstrm_add_amount 쪽에 들어있다. 4분기만 연간(11011) 실적에서
    3분기 누적치를 빼서 역산해야 한다.
    """
    this_year = dt.date.today().year
    vals = {}  # (year, reprt_code) -> {"amount": 단독값, "add_amount": 누적값}

    for y in [this_year, this_year - 1, this_year - 2]:
        for rc in REPORT_CODES:
            try:
                df = dart.finstate(code, y, reprt_code=rc)
            except Exception:
                continue
            if df is None or df.empty:
                continue
            row = df[(df["account_nm"] == "영업이익") & (df["fs_div"] == "CFS")]
            if row.empty:
                row = df[(df["account_nm"] == "영업이익") & (df["fs_div"] == "OFS")]
            if row.empty:
                continue
            r = row.iloc[0]
            vals[(y, rc)] = {
                "amount": _amount(r["thstrm_amount"]),
                "add_amount": _amount(r.get("thstrm_add_amount")),
            }

    quarter_vals = {}
    for y in sorted(set(k[0] for k in vals)):
        q1 = vals.get((y, "11013"), {}).get("amount")
        q2 = vals.get((y, "11012"), {}).get("amount")
        q3 = vals.get((y, "11014"), {}).get("amount")
        q3_cum = vals.get((y, "11014"), {}).get("add_amount")
        fy = vals.get((y, "11011"), {}).get("amount")
        if q1 is not None:
            quarter_vals[(y, 1)] = q1
        if q2 is not None:
            quarter_vals[(y, 2)] = q2
        if q3 is not None:
            quarter_vals[(y, 3)] = q3
        if fy is not None and q3_cum is not None:
            quarter_vals[(y, 4)] = fy - q3_cum

    keys = sorted(quarter_vals.keys())[-n_quarters:]
    return [
        {"label": f"{str(y)[2:]}Q{q}", "value_eok": round(quarter_vals[(y, q)] / 1e8, 0)}
        for y, q in keys
    ]


def company_info(dart, code: str) -> dict:
    info = dart.company(code)
    return {
        "corp_name": info.get("corp_name"),
        "corp_code": info.get("corp_code"),
        "induty_code": info.get("induty_code"),
        "est_dt": info.get("est_dt"),
    }
