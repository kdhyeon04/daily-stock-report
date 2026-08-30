"""종목명 -> 종목코드/시장정보 조회"""
import FinanceDataReader as fdr

_listing_cache = None


def _listing():
    global _listing_cache
    if _listing_cache is None:
        _listing_cache = fdr.StockListing("KRX")
    return _listing_cache


def resolve(name_or_code: str) -> dict:
    """종목명(또는 종목코드)을 받아 {code, name, market} 반환. 못 찾으면 후보 리스트를 담아 예외."""
    q = name_or_code.strip()
    listing = _listing()

    if q.isdigit() and len(q) == 6:
        row = listing[listing["Code"] == q]
        if not row.empty:
            r = row.iloc[0]
            return {"code": r["Code"], "name": r["Name"], "market": r["Market"]}
        raise ValueError(f"종목코드 '{q}'를 찾을 수 없습니다.")

    exact = listing[listing["Name"] == q]
    if not exact.empty:
        r = exact.iloc[0]
        return {"code": r["Code"], "name": r["Name"], "market": r["Market"]}

    partial = listing[listing["Name"].str.contains(q, na=False)]
    if len(partial) == 1:
        r = partial.iloc[0]
        return {"code": r["Code"], "name": r["Name"], "market": r["Market"]}
    if len(partial) > 1:
        candidates = partial[["Code", "Name", "Market"]].to_dict("records")
        raise ValueError(f"'{q}'로 여러 종목이 검색됩니다: {candidates}")

    raise ValueError(f"'{q}'에 해당하는 종목을 찾을 수 없습니다.")
