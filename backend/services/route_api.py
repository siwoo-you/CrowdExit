import os
import httpx

from dotenv import load_dotenv


load_dotenv()


GOOGLE_API_KEY = os.getenv(
    "GOOGLE_API_KEY"
)

GOOGLE_ROUTES_URL = (
    "https://routes.googleapis.com/"
    "directions/v2:computeRoutes"
)


# ============================================================
# 공통 유틸
# ============================================================

def _seconds(value):
    """
    Google duration 문자열을
    초 단위 숫자로 변환한다.

    예:
    "650s" -> 650
    """

    if not value:
        return 0

    if isinstance(
        value,
        (int, float)
    ):
        return float(value)

    value = str(value)

    if value.endswith("s"):

        try:
            return float(
                value[:-1]
            )

        except ValueError:
            return 0

    return 0


def _minutes(seconds):
    """
    초 → 분
    """

    return round(
        seconds / 60,
        1
    )


# ============================================================
# CrowdExit 점수용 함수
# ============================================================

def _walking_score(
    walking_seconds
):
    """
    도보 시간이 짧을수록 높은 점수.
    """

    minutes = (
        walking_seconds / 60
    )

    if minutes <= 3:
        return 100

    if minutes <= 5:
        return 90

    if minutes <= 7:
        return 75

    if minutes <= 10:
        return 55

    if minutes <= 15:
        return 30

    return 10


def _transfer_score(
    transfer_count
):
    """
    환승이 적을수록 높은 점수.
    """

    if transfer_count == 0:
        return 100

    if transfer_count == 1:
        return 70

    if transfer_count == 2:
        return 40

    return 20


def _stop_score(
    stop_count
):
    """
    정류장 수가 적을수록
    이동이 단순하다고 판단한다.
    """

    if stop_count <= 1:
        return 100

    if stop_count == 2:
        return 90

    if stop_count <= 4:
        return 75

    if stop_count <= 6:
        return 60

    return 45


def _congestion_score(
    congestion_level
):
    """
    서울시 권역 혼잡도 점수.
    """

    level = str(
        congestion_level or ""
    ).strip()

    scores = {
        "여유": 100,
        "보통": 75,
        "약간 붐빔": 50,
        "붐빔": 25,
        "매우 붐빔": 5,
    }

    return scores.get(
        level,
        60
    )


# ============================================================
# Google Routes 응답 파싱
# ============================================================

def extract_route_candidates(
    data
):
    """
    Google Routes의 대중교통 응답에서
    CrowdExit가 사용할 데이터를 추출한다.
    """

    routes = data.get(
        "routes",
        []
    )

    candidates = []

    for index, route in enumerate(
        routes,
        start=1
    ):

        total_seconds = _seconds(
            route.get(
                "duration"
            )
        )

        distance = route.get(
            "distanceMeters",
            0
        )

        # ----------------------------------------------------
        # 실제 Google 경로선
        # ----------------------------------------------------

        encoded_polyline = (
            route.get(
                "polyline",
                {}
            ).get(
                "encodedPolyline",
                ""
            )
        )

        legs = route.get(
            "legs",
            []
        )

        walking_seconds = 0
        transit_seconds = 0

        transit_segments = []

        for leg in legs:

            steps = leg.get(
                "steps",
                []
            )

            for step in steps:

                travel_mode = (
                    step.get(
                        "travelMode"
                    )
                )

                seconds = _seconds(
                    step.get(
                        "staticDuration"
                    )
                )

                if travel_mode == "WALK":

                    walking_seconds += (
                        seconds
                    )

                elif travel_mode == "TRANSIT":

                    transit_seconds += (
                        seconds
                    )

                    transit = step.get(
                        "transitDetails",
                        {}
                    )

                    stop_details = (
                        transit.get(
                            "stopDetails",
                            {}
                        )
                    )

                    departure_stop = (
                        stop_details.get(
                            "departureStop",
                            {}
                        )
                    )

                    arrival_stop = (
                        stop_details.get(
                            "arrivalStop",
                            {}
                        )
                    )

                    transit_line = (
                        transit.get(
                            "transitLine",
                            {}
                        )
                    )

                    transit_segments.append(
                        {
                            "vehicle_type": (
                                transit_line
                                .get(
                                    "vehicle",
                                    {}
                                )
                                .get(
                                    "type",
                                    ""
                                )
                            ),

                            "line_name": (
                                transit_line
                                .get(
                                    "nameShort",
                                    transit_line.get(
                                        "name",
                                        ""
                                    )
                                )
                            ),

                            "departure_stop": (
                                departure_stop
                                .get(
                                    "name",
                                    ""
                                )
                            ),

                            "arrival_stop": (
                                arrival_stop
                                .get(
                                    "name",
                                    ""
                                )
                            ),

                            "departure_lat": (
                                departure_stop
                                .get(
                                    "location",
                                    {}
                                )
                                .get(
                                    "latLng",
                                    {}
                                )
                                .get(
                                    "latitude"
                                )
                            ),

                            "departure_lng": (
                                departure_stop
                                .get(
                                    "location",
                                    {}
                                )
                                .get(
                                    "latLng",
                                    {}
                                )
                                .get(
                                    "longitude"
                                )
                            ),

                            "arrival_lat": (
                                arrival_stop
                                .get(
                                    "location",
                                    {}
                                )
                                .get(
                                    "latLng",
                                    {}
                                )
                                .get(
                                    "latitude"
                                )
                            ),

                            "arrival_lng": (
                                arrival_stop
                                .get(
                                    "location",
                                    {}
                                )
                                .get(
                                    "latLng",
                                    {}
                                )
                                .get(
                                    "longitude"
                                )
                            ),

                            "stop_count": (
                                transit.get(
                                    "stopCount",
                                    0
                                )
                            ),

                            "headsign": (
                                transit.get(
                                    "headsign",
                                    ""
                                )
                            ),

                            "headway_seconds": (
                                _seconds(
                                    transit.get(
                                        "headway"
                                    )
                                )
                            ),
                        }
                    )

        transfer_count = max(
            len(
                transit_segments
            ) - 1,
            0
        )

        total_stop_count = sum(
            segment.get(
                "stop_count",
                0
            )
            for segment
            in transit_segments
        )

        candidates.append(
            {
                "route_number": (
                    index
                ),

                "distance_m": (
                    distance
                ),

                "duration_seconds": (
                    total_seconds
                ),

                "duration_min": (
                    _minutes(
                        total_seconds
                    )
                ),

                "walking_seconds": (
                    walking_seconds
                ),

                "walking_min": (
                    _minutes(
                        walking_seconds
                    )
                ),

                "transit_seconds": (
                    transit_seconds
                ),

                "transit_min": (
                    _minutes(
                        transit_seconds
                    )
                ),

                "transfer_count": (
                    transfer_count
                ),

                "stop_count": (
                    total_stop_count
                ),

                "transit_segments": (
                    transit_segments
                ),

                # 실제 지도 경로선
                "encoded_polyline": (
                    encoded_polyline
                ),
            }
        )

    return candidates


# ============================================================
# CrowdExit 점수
# ============================================================

def calculate_crowdexit_score(
    candidate,
    congestion_level="보통"
):
    """
    CrowdExit 기본 점수.

    시간       35%
    도보       20%
    환승       15%
    정류장 수  10%
    혼잡       20%
    """

    duration = candidate.get(
        "duration_seconds",
        0
    )

    if duration <= 600:
        time_score = 100

    elif duration <= 900:
        time_score = 85

    elif duration <= 1200:
        time_score = 70

    elif duration <= 1500:
        time_score = 50

    else:
        time_score = 30

    walking_score = (
        _walking_score(
            candidate.get(
                "walking_seconds",
                0
            )
        )
    )

    transfer_score = (
        _transfer_score(
            candidate.get(
                "transfer_count",
                0
            )
        )
    )

    stop_score = (
        _stop_score(
            candidate.get(
                "stop_count",
                0
            )
        )
    )

    congestion_score = (
        _congestion_score(
            congestion_level
        )
    )

    score = (
        time_score * 0.35
        + walking_score * 0.20
        + transfer_score * 0.15
        + stop_score * 0.10
        + congestion_score * 0.20
    )

    return round(
        score
    )


def recommend_routes(
    routes,
    congestion_level="보통"
):
    """
    모든 후보를 평가한 뒤
    점수순으로 반환한다.
    """

    for route in routes:

        route[
            "crowdexit_score"
        ] = (
            calculate_crowdexit_score(
                route,
                congestion_level
            )
        )

    routes.sort(
        key=lambda x: x.get(
            "crowdexit_score",
            0
        ),
        reverse=True
    )

    return routes


# ============================================================
# 실제 대중교통 경로
# ============================================================

def get_google_transit_routes(
    origin_lat,
    origin_lng,
    destination_lat,
    destination_lng,
):
    """
    Google Routes API에서
    실제 대중교통 경로를 가져온다.
    """

    if not GOOGLE_API_KEY:

        raise ValueError(
            "GOOGLE_API_KEY가 "
            ".env에 없습니다."
        )

    request_body = {
        "origin": {
            "location": {
                "latLng": {
                    "latitude": (
                        origin_lat
                    ),
                    "longitude": (
                        origin_lng
                    ),
                }
            }
        },

        "destination": {
            "location": {
                "latLng": {
                    "latitude": (
                        destination_lat
                    ),
                    "longitude": (
                        destination_lng
                    ),
                }
            }
        },

        "travelMode": "TRANSIT",

        "computeAlternativeRoutes": (
            True
        ),

        
        "languageCode": "ko",

        "units": "METRIC",
    }

    headers = {
        "Content-Type": (
            "application/json"
        ),

        "X-Goog-Api-Key": (
            GOOGLE_API_KEY
        ),

        "X-Goog-FieldMask": (
            "routes.duration,"
            "routes.distanceMeters,"
            "routes.polyline.encodedPolyline,"
            "routes.legs.steps.travelMode,"
            "routes.legs.steps.distanceMeters,"
            "routes.legs.steps.staticDuration,"
            "routes.legs.steps.navigationInstruction,"
            "routes.legs.steps.transitDetails"
        ),
    }

    response = httpx.post(
        GOOGLE_ROUTES_URL,
        json=request_body,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    return extract_route_candidates(
        data
    )


# ============================================================
# 실제 도보 경로
# ============================================================

def get_google_walking_route(
    origin_lat,
    origin_lng,
    destination_lat,
    destination_lng,
):
    """
    Google Routes API에서
    실제 도보 경로를 가져온다.

    경로가 없을 경우
    직선거리 기반 추정값을 사용한다.
    """

    if not GOOGLE_API_KEY:

        raise ValueError(
            "GOOGLE_API_KEY가 "
            ".env에 없습니다."
        )

    request_body = {
        "origin": {
            "location": {
                "latLng": {
                    "latitude": (
                        origin_lat
                    ),
                    "longitude": (
                        origin_lng
                    ),
                }
            }
        },

        "destination": {
            "location": {
                "latLng": {
                    "latitude": (
                        destination_lat
                    ),
                    "longitude": (
                        destination_lng
                    ),
                }
            }
        },

        "travelMode": "WALK",

        "languageCode": "ko",

        "units": "METRIC",
    }

    headers = {
        "Content-Type": (
            "application/json"
        ),

        "X-Goog-Api-Key": (
            GOOGLE_API_KEY
        ),

        "X-Goog-FieldMask": (
            "routes.duration,"
            "routes.distanceMeters,"
            "routes.polyline.encodedPolyline"
        ),
    }

    response = httpx.post(
        GOOGLE_ROUTES_URL,
        json=request_body,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    routes = data.get(
        "routes",
        []
    )

    if routes:

        route = routes[0]

        duration_seconds = _seconds(
            route.get(
                "duration"
            )
        )

        distance_m = route.get(
            "distanceMeters",
            0
        )

        encoded_polyline = (
            route.get(
                "polyline",
                {}
            ).get(
                "encodedPolyline",
                ""
            )
        )

        return {
            "distance_m": (
                distance_m
            ),

            "duration_seconds": (
                duration_seconds
            ),

            "duration_min": (
                _minutes(
                    duration_seconds
                )
            ),

            "source": (
                "google_routes"
            ),

            "encoded_polyline": (
                encoded_polyline
            ),
        }

    # ========================================================
    # Google WALK 경로가 없을 때 fallback
    # ========================================================

    from math import (
        radians,
        sin,
        cos,
        sqrt,
        atan2,
    )

    earth_radius = (
        6371000
    )

    lat1 = radians(
        origin_lat
    )

    lat2 = radians(
        destination_lat
    )

    delta_lat = radians(
        destination_lat
        - origin_lat
    )

    delta_lng = radians(
        destination_lng
        - origin_lng
    )

    a = (
        sin(
            delta_lat / 2
        ) ** 2
        + cos(lat1)
        * cos(lat2)
        * sin(
            delta_lng / 2
        ) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(
            1 - a
        )
    )

    distance_m = (
        earth_radius * c
    )

    # 평균 보행속도 약 75m/분
    duration_min = (
        distance_m / 75
    )

    duration_seconds = (
        duration_min * 60
    )

    return {
        "distance_m": round(
            distance_m
        ),

        "duration_seconds": round(
            duration_seconds
        ),

        "duration_min": round(
            duration_min,
            1
        ),

        "source": (
            "estimated"
        ),

        # fallback은 실제 도로 경로가 아니므로
        # polyline 없음
        "encoded_polyline": "",
    }


# ============================================================
# 도보 함수 단독 테스트
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("Google Routes 경로선 테스트")
    print("=" * 60)

    origin_lat = 37.5150
    origin_lng = 127.0728

    destination_lat = 37.4979
    destination_lng = 127.0276

    routes = get_google_transit_routes(
        origin_lat,
        origin_lng,
        destination_lat,
        destination_lng,
    )

    if not routes:

        print(
            "경로를 찾지 못했습니다."
        )

    else:

        for route in routes:

            print()
            print(
                "경로 번호:",
                route.get(
                    "route_number"
                )
            )

            print(
                "시간:",
                route.get(
                    "duration_min"
                ),
                "분"
            )

            polyline = route.get(
                "encoded_polyline",
                ""
            )

            print(
                "Polyline 있음:",
                bool(
                    polyline
                )
            )

            if polyline:

                print(
                    "Polyline 길이:",
                    len(
                        polyline
                    )
                )