"""카카오톡 '나에게 보내기' 발송"""
import json
import requests

import config

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def refresh_access_token() -> tuple[str, str | None]:
    """refresh_token으로 access_token 재발급. 반환: (access_token, 새_refresh_token_또는_None)"""
    r = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": config.KAKAO_REST_API_KEY,
            "client_secret": config.KAKAO_CLIENT_SECRET,
            "refresh_token": config.KAKAO_REFRESH_TOKEN,
        },
        timeout=15,
    )
    body = r.json()
    if "access_token" not in body:
        raise RuntimeError(f"카카오 토큰 재발급 실패: {body}")
    return body["access_token"], body.get("refresh_token")


def send_text(access_token: str, text: str, link_url: str, button_title: str = "리포트 자세히 보기"):
    template = {
        "object_type": "text",
        "text": text,
        "link": {"web_url": link_url, "mobile_web_url": link_url},
        "button_title": button_title,
    }
    r = requests.post(
        SEND_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": json.dumps(template, ensure_ascii=False)},
        timeout=15,
    )
    body = r.json()
    if body.get("result_code") != 0:
        raise RuntimeError(f"카카오 메시지 발송 실패: {body}")
    return body
