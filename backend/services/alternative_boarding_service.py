"""
CrowdExit 대체 승차지점 추천 서비스

1. 서울시 실시간 도시데이터에서 지하철역/버스정류장 후보 탐색
2. 출발지 → 후보 승차지점 도보시간 계산
3. 후보 → 목적지 Google 대중교통 경로 계산
4. 실제 후보 지점에서 탑승하는 경로인지 검증
5. 후보가 속한 권역의 실시간 교통 이용량/혼잡도 반영
6. 최종 예상 귀가시간 계산
7. Google Routes 실제 지도 경로선(polyline) 저장
"""

from typing import Dict, List, Any
from math import radians, sin, cos, sqrt, atan2

from services.seoul_api import get_city_data

from services.route_api import (
    get_google_walking_route,
    get_google_transit_routes,
)

from services.congestion_service import (
    get_transport_congestion,
)


# ============================================================
# 대체 승차 탐색 여부
# ============================================================

def should_search_alternative(
    congestion_level: str
) -> bool:

    level = str(
        congestion_level or ""
    ).strip()

    return level in (
        "붐빔",
        "매우 붐빔"
    )


# ============================================================
# 이름 정규화
# ============================================================

def normalize_name(
    value: str
) -> str:

    value = str(
        value or ""
    ).strip()

    value = value.replace(
        " ",
        ""
    )

    value = value.replace(
        "역",
        ""
    )

    value = value.replace(
        "정류장",
        ""
    )

    return value


# ============================================================
# 직선거리
# ============================================================

def calculate_distance_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:

    earth_radius = 6371000

    lat1_rad = radians(
        lat1
    )

    lat2_rad = radians(
        lat2
    )

    delta_lat = radians(
        lat2 - lat1
    )

    delta_lon = radians(
        lon2 - lon1
    )

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad)
        * cos(lat2_rad)
        * sin(delta_lon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a)
    )

    return earth_radius * c


# ============================================================
# 지하철 후보
# ============================================================

def get_subway_candidates(
    city_data: Dict[str, Any],
    area_name: str,
    origin_lat: float,
    origin_lon: float,
    radius_m: float = 1500
) -> List[Dict[str, Any]]:

    stations = city_data.get(
        "SUB_STTS",
        []
    )

    results = []

    for station in stations:

        try:

            latitude = float(
                station.get(
                    "SUB_STN_Y"
                )
            )

            longitude = float(
                station.get(
                    "SUB_STN_X"
                )
            )

        except (
            TypeError,
            ValueError
        ):
            continue

        distance = calculate_distance_m(
            origin_lat,
            origin_lon,
            latitude,
            longitude
        )

        if distance > radius_m:
            continue

        line = str(
            station.get(
                "SUB_STN_LINE",
                ""
            )
        ).strip()

        if (
            line
            and "호선" not in line
        ):
            line = f"{line}호선"

        results.append({
            "type": "subway",

            "area_name": area_name,

            "name": station.get(
                "SUB_STN_NM",
                ""
            ),

            "line_name": line,

            "latitude": latitude,
            "longitude": longitude,

            "straight_distance_m": round(
                distance
            ),

            "address": station.get(
                "SUB_STN_RADDR"
            ),
        })

    return results


# ============================================================
# 버스 후보
# ============================================================

def get_bus_candidates(
    city_data: Dict[str, Any],
    area_name: str,
    origin_lat: float,
    origin_lon: float,
    radius_m: float = 900
) -> List[Dict[str, Any]]:

    stations = city_data.get(
        "BUS_STN_STTS",
        []
    )

    results = []

    for station in stations:

        try:

            latitude = float(
                station.get(
                    "BUS_STN_Y"
                )
            )

            longitude = float(
                station.get(
                    "BUS_STN_X"
                )
            )

        except (
            TypeError,
            ValueError
        ):
            continue

        distance = calculate_distance_m(
            origin_lat,
            origin_lon,
            latitude,
            longitude
        )

        if distance > radius_m:
            continue

        results.append({
            "type": "bus",

            "area_name": area_name,

            "name": station.get(
                "BUS_STN_NM",
                ""
            ),

            "line_name": "버스",

            "station_id": station.get(
                "BUS_STN_ID"
            ),

            "ars_id": station.get(
                "BUS_ARS_ID"
            ),

            "latitude": latitude,
            "longitude": longitude,

            "straight_distance_m": round(
                distance
            ),
        })

    return results


# ============================================================
# 중복 제거
# ============================================================

def remove_duplicate_candidates(
    candidates: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    results = []
    seen = set()

    for candidate in candidates:

        if candidate.get(
            "type"
        ) == "bus":

            key = (
                "bus",
                candidate.get(
                    "ars_id"
                ),
                candidate.get(
                    "name"
                ),
            )

        else:

            key = (
                "subway",
                candidate.get(
                    "name"
                ),
                candidate.get(
                    "line_name"
                ),
            )

        if key in seen:
            continue

        seen.add(
            key
        )

        results.append(
            candidate
        )

    return results


# ============================================================
# 출발지 → 후보 도보
# ============================================================

def add_walking_route(
    candidate: Dict[str, Any],
    origin_lat: float,
    origin_lon: float
) -> Dict[str, Any]:

    result = dict(
        candidate
    )

    try:

        walking = (
            get_google_walking_route(
                origin_lat,
                origin_lon,
                candidate[
                    "latitude"
                ],
                candidate[
                    "longitude"
                ],
            )
        )

    except Exception as e:

        print(
            f"[도보 경로 오류] "
            f"{candidate.get('name')}: "
            f"{e}"
        )

        walking = None

    if not walking:

        result[
            "walking_distance_m"
        ] = result.get(
            "straight_distance_m",
            0
        )

        result[
            "walking_seconds"
        ] = 0

        result[
            "walking_min"
        ] = 0

        result[
            "walking_source"
        ] = "unknown"

        # 실제 Google 도보 경로선 없음
        result[
            "walking_encoded_polyline"
        ] = ""

        return result

    result[
        "walking_distance_m"
    ] = walking.get(
        "distance_m",
        0
    )

    result[
        "walking_seconds"
    ] = walking.get(
        "duration_seconds",
        0
    )

    result[
        "walking_min"
    ] = walking.get(
        "duration_min",
        0
    )

    result[
        "walking_source"
    ] = walking.get(
        "source",
        "unknown"
    )

    # ========================================================
    # 실제 Google 도보 경로선
    # ========================================================

    result[
        "walking_encoded_polyline"
    ] = walking.get(
        "encoded_polyline",
        ""
    )

    return result


# ============================================================
# 후보에서 실제 탑승하는지 검증
# ============================================================

def route_starts_from_candidate(
    candidate: Dict[str, Any],
    route: Dict[str, Any]
) -> bool:

    segments = route.get(
        "transit_segments",
        []
    )

    if not segments:
        return False

    first_segment = (
        segments[0]
    )

    actual_stop = (
        first_segment.get(
            "departure_stop",
            ""
        )
    )

    actual_vehicle = str(
        first_segment.get(
            "vehicle_type",
            ""
        )
    ).upper()

    candidate_name = (
        normalize_name(
            candidate.get(
                "name",
                ""
            )
        )
    )

    actual_name = (
        normalize_name(
            actual_stop
        )
    )

    if (
        not candidate_name
        or not actual_name
    ):
        return False

    name_matches = (
        candidate_name in actual_name
        or actual_name in candidate_name
    )

    if not name_matches:
        return False

    candidate_type = (
        candidate.get(
            "type"
        )
    )

    if candidate_type == "subway":

        subway_types = {
            "SUBWAY",
            "METRO_RAIL",
            "HEAVY_RAIL",
            "RAIL",
        }

        if (
            actual_vehicle
            not in subway_types
        ):
            return False

    elif candidate_type == "bus":

        if (
            "BUS"
            not in actual_vehicle
        ):
            return False

    return True


# ============================================================
# 후보 → 목적지 대중교통
# ============================================================

def add_destination_route(
    candidate: Dict[str, Any],
    destination_lat: float,
    destination_lon: float
) -> Dict[str, Any]:

    result = dict(
        candidate
    )

    try:

        routes = (
            get_google_transit_routes(
                candidate[
                    "latitude"
                ],
                candidate[
                    "longitude"
                ],
                destination_lat,
                destination_lon,
            )
        )

    except Exception as e:

        print(
            f"[대중교통 경로 오류] "
            f"{candidate.get('name')}: "
            f"{e}"
        )

        routes = []

    valid_routes = []

    for route in routes:

        if route_starts_from_candidate(
            candidate,
            route
        ):

            valid_routes.append(
                route
            )

    if not valid_routes:

        result[
            "transit_available"
        ] = False

        result[
            "encoded_polyline"
        ] = ""

        return result

    best_route = min(
        valid_routes,
        key=lambda x: x.get(
            "duration_seconds",
            float("inf")
        )
    )

    result[
        "transit_available"
    ] = True

    result[
        "transit_duration_seconds"
    ] = best_route.get(
        "duration_seconds",
        0
    )

    result[
        "transit_duration_min"
    ] = best_route.get(
        "duration_min",
        0
    )

    result[
        "transfer_count"
    ] = best_route.get(
        "transfer_count",
        0
    )

    result[
        "stop_count"
    ] = best_route.get(
        "stop_count",
        0
    )

    result[
        "transit_segments"
    ] = best_route.get(
        "transit_segments",
        []
    )

    result[
        "best_transit_route"
    ] = best_route

    # ========================================================
    # 실제 Google 대중교통 경로선
    # ========================================================

    result[
        "encoded_polyline"
    ] = best_route.get(
        "encoded_polyline",
        ""
    )

    return result


# ============================================================
# 실제 혼잡도 추가
# ============================================================

def add_congestion(
    candidate: Dict[str, Any]
) -> Dict[str, Any]:

    result = dict(
        candidate
    )

    area_name = result.get(
        "area_name"
    )

    transport_type = result.get(
        "type"
    )

    try:

        congestion = (
            get_transport_congestion(
                area_name,
                transport_type
            )
        )

    except Exception as e:

        print(
            f"[혼잡도 조회 오류] "
            f"{candidate.get('name')}: "
            f"{e}"
        )

        result[
            "area_congestion"
        ] = "정보 없음"

        result[
            "avg_boarding_10"
        ] = 0

        result[
            "area_penalty_min"
        ] = 0

        result[
            "volume_penalty_min"
        ] = 0

        result[
            "congestion_penalty_min"
        ] = 0

        return result

    result[
        "area_congestion"
    ] = congestion.get(
        "area_congestion"
    )

    result[
        "congestion_measured_at"
    ] = congestion.get(
        "measured_at"
    )

    result[
        "station_count"
    ] = congestion.get(
        "station_count",
        0
    )

    result[
        "boarding_5"
    ] = congestion.get(
        "boarding_5",
        0
    )

    result[
        "boarding_10"
    ] = congestion.get(
        "boarding_10",
        0
    )

    result[
        "boarding_30"
    ] = congestion.get(
        "boarding_30",
        0
    )

    result[
        "avg_boarding_10"
    ] = congestion.get(
        "avg_boarding_10",
        0
    )

    result[
        "area_penalty_min"
    ] = congestion.get(
        "area_penalty_min",
        0
    )

    result[
        "volume_penalty_min"
    ] = congestion.get(
        "volume_penalty_min",
        0
    )

    result[
        "congestion_penalty_min"
    ] = congestion.get(
        "congestion_penalty_min",
        0
    )

    return result


# ============================================================
# 최종 예상 귀가시간
# ============================================================

def calculate_total_time(
    candidate: Dict[str, Any]
) -> Dict[str, Any]:

    result = dict(
        candidate
    )

    walking_min = float(
        result.get(
            "walking_min",
            0
        )
    )

    transit_min = float(
        result.get(
            "transit_duration_min",
            0
        )
    )

    congestion_penalty = float(
        result.get(
            "congestion_penalty_min",
            0
        )
    )

    base_total_min = (
        walking_min
        + transit_min
    )

    adjusted_total_min = (
        base_total_min
        + congestion_penalty
    )

    result[
        "base_total_min"
    ] = round(
        base_total_min,
        1
    )

    result[
        "adjusted_total_min"
    ] = round(
        adjusted_total_min,
        1
    )

    result[
        "total_min"
    ] = result[
        "adjusted_total_min"
    ]

    result[
        "total_seconds"
    ] = round(
        adjusted_total_min * 60
    )

    return result


# ============================================================
# 후보 하나 평가
# ============================================================

def evaluate_candidate(
    candidate: Dict[str, Any],
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float
) -> Dict[str, Any]:

    # --------------------------------------------------------
    # 1. 출발지 → 후보 도보
    # --------------------------------------------------------

    result = add_walking_route(
        candidate,
        origin_lat,
        origin_lon
    )

    # --------------------------------------------------------
    # 2. 후보 → 목적지 대중교통
    # --------------------------------------------------------

    result = add_destination_route(
        result,
        destination_lat,
        destination_lon
    )

    if not result.get(
        "transit_available"
    ):
        return result

    # --------------------------------------------------------
    # 3. 후보 권역 혼잡도
    # --------------------------------------------------------

    result = add_congestion(
        result
    )

    # --------------------------------------------------------
    # 4. 총시간
    # --------------------------------------------------------

    result = calculate_total_time(
        result
    )

    return result


# ============================================================
# 최종 후보 검색
# ============================================================

def find_alternative_boarding_points(
    area_names: List[str],
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    congestion_level: str,
    max_results: int = 15
) -> List[Dict[str, Any]]:

    if not should_search_alternative(
        congestion_level
    ):
        return []

    candidates = []

    # --------------------------------------------------------
    # 권역별 후보 수집
    # --------------------------------------------------------

    for area_name in area_names:

        try:

            city_data = get_city_data(
                area_name
            )

        except Exception as e:

            print(
                f"[서울시 API 오류] "
                f"{area_name}: "
                f"{e}"
            )

            continue

        subway_candidates = (
            get_subway_candidates(
                city_data,
                area_name,
                origin_lat,
                origin_lon
            )
        )

        bus_candidates = (
            get_bus_candidates(
                city_data,
                area_name,
                origin_lat,
                origin_lon
            )
        )

        print(
            f"\n[{area_name}] "
            f"지하철 "
            f"{len(subway_candidates)}개 / "
            f"버스 "
            f"{len(bus_candidates)}개"
        )

        candidates.extend(
            subway_candidates
        )

        candidates.extend(
            bus_candidates
        )

    # --------------------------------------------------------
    # 중복 제거
    # --------------------------------------------------------

    candidates = (
        remove_duplicate_candidates(
            candidates
        )
    )

    # --------------------------------------------------------
    # 가까운 후보부터 평가
    # --------------------------------------------------------

    candidates.sort(
        key=lambda x: x.get(
            "straight_distance_m",
            999999
        )
    )

    candidates = candidates[
        :max_results
    ]

    print(
        "\n실제 평가 후보:"
    )

    for candidate in candidates:

        print(
            "-",
            candidate.get(
                "type"
            ),
            candidate.get(
                "name"
            ),
            "/ 권역:",
            candidate.get(
                "area_name"
            ),
            "/",
            candidate.get(
                "straight_distance_m"
            ),
            "m"
        )

    # --------------------------------------------------------
    # 후보별 평가
    # --------------------------------------------------------

    evaluated = []

    for candidate in candidates:

        print(
            f"\n평가 중: "
            f"{candidate.get('name')} "
            f"({candidate.get('type')})"
        )

        result = evaluate_candidate(
            candidate,
            origin_lat,
            origin_lon,
            destination_lat,
            destination_lon
        )

        if not result.get(
            "transit_available"
        ):

            print(
                "  → 후보 지점에서 "
                "직접 탑승하는 경로 없음"
            )

            continue

        evaluated.append(
            result
        )

    # --------------------------------------------------------
    # 혼잡 보정 총시간 기준 정렬
    # --------------------------------------------------------

    evaluated.sort(
        key=lambda x: x.get(
            "adjusted_total_min",
            float("inf")
        )
    )

    # --------------------------------------------------------
    # 순위
    # --------------------------------------------------------

    for index, candidate in enumerate(
        evaluated,
        start=1
    ):

        candidate[
            "alternative_rank"
        ] = index

        candidate[
            "is_recommended"
        ] = (
            index == 1
        )

    return evaluated


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":

    print(
        "=" * 60
    )

    print(
        "CrowdExit 실제 경로선 포함 테스트"
    )

    print(
        "=" * 60
    )

    # 잠실종합운동장 부근
    origin_lat = 37.5150
    origin_lon = 127.0728

    # 강남역
    destination_lat = 37.4979
    destination_lon = 127.0276

    area_names = [
        "잠실종합운동장",
        "잠실새내역",
    ]

    # 테스트이므로 대체 승차 검색 강제 실행
    congestion_level = (
        "매우 붐빔"
    )

    results = (
        find_alternative_boarding_points(
            area_names=area_names,
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            destination_lat=destination_lat,
            destination_lon=destination_lon,
            congestion_level=congestion_level,
            max_results=15
        )
    )

    print()
    print("=" * 60)
    print("Polyline 확인")
    print("=" * 60)

    for candidate in results:

        print()

        print(
            "후보:",
            candidate.get(
                "name"
            )
        )

        print(
            "도보 polyline:",
            bool(
                candidate.get(
                    "walking_encoded_polyline"
                )
            )
        )

        print(
            "대중교통 polyline:",
            bool(
                candidate.get(
                    "encoded_polyline"
                )
            )
        )

        print(
            "도보 source:",
            candidate.get(
                "walking_source"
            )
        )