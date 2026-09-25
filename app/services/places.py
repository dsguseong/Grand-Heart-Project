"""주변 식당 찾기 (카카오 로컬 API).

KAKAO_REST_API_KEY 가 없으면 예외를 던지지 않고 빈 결과 + 안내 문구를
돌려줍니다. 키 없이도 앱 전체가 정상 동작해야 하기 때문입니다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

KAKAO_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def search_nearby(keyword: str, lat: float, lng: float, radius: int | None = None) -> dict:
    key = current_app.config.get("KAKAO_REST_API_KEY")
    if not key:
        return {
            "ok": False,
            "places": [],
            "message": "KAKAO_REST_API_KEY 가 설정되지 않아 주변 식당을 불러올 수 없습니다.",
        }

    radius = radius or current_app.config.get("PLACES_RADIUS_M", 1500)
    query = urllib.parse.urlencode(
        {
            "query": keyword,
            "x": lng,
            "y": lat,
            "radius": radius,
            "category_group_code": "FD6",
            "size": 10,
        }
    )
    req = urllib.request.Request(
        f"{KAKAO_URL}?{query}", headers={"Authorization": f"KakaoAK {key}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        current_app.logger.warning("카카오 로컬 API 실패: %s", exc)
        return {"ok": False, "places": [], "message": "주변 식당을 불러오지 못했습니다."}

    places = [
        {
            "name": d.get("place_name"),
            "address": d.get("road_address_name") or d.get("address_name"),
            "phone": d.get("phone"),
            "distance_m": int(d["distance"]) if d.get("distance") else None,
            "url": d.get("place_url"),
        }
        for d in data.get("documents", [])
    ]
    return {"ok": True, "places": places, "message": ""}
