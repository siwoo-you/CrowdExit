"""
CrowdExit 추천 엔진

Google Routes API에서 받은 대중교통 후보를 비교한다.

핵심 원칙:
1. 실제 전체 이동시간을 가장 중요하게 본다.
2. 혼잡도가 높으면 혼잡 패널티를 추가한다.
3. 도보/환승/배차간격은 보조 요소로 사용한다.
4. 전체 transit_segments를 유지한다.
5. Gemini에는 전체 환승 경로를 전달한다.
"""

from typing import Dict, List, Any

from services.llm_service import (
    generate_recommendation_reason,
)


# ============================================================
# 기본 점수
# ============================================================

def congestion_score(level: str) -> int:
    scores = {
        "여유": 100,
        "보통": 75,
        "약간 붐빔": 50,
        "붐빔": 25,
        "매우 붐빔": 5,
    }

    return scores.get(
        str(level or "").strip(),
        60,
    )


def duration_score(seconds: float) -> int:
    """
    실제 이동시간을 연속적으로 평가한다.

    기존에는 30분 초과가 전부 30점이어서
    60분과 90분의 차이가 사라지는 문제가 있었다.

    여기서는 시간이 길수록 점수가 계속 감소한다.
    """

    minutes = max(
        seconds / 60,
        0,
    )

    if minutes <= 10:
        return 100

    # 10분 이후 1분마다 약 2.5점 감소
    score = 100 - (
        (minutes - 10) * 2.5
    )

    return max(
        5,
        min(
            100,
            round(score),
        ),
    )


def walking_score(seconds: float) -> int:
    minutes = max(
        seconds / 60,
        0,
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


def transfer_score(count: int) -> int:
    if count <= 0:
        return 100

    if count == 1:
        return 75

    if count == 2:
        return 50

    return 25


def stop_score(count: int) -> int:
    if count <= 1:
        return 100

    if count == 2:
        return 90

    if count <= 4:
        return 75

    if count <= 6:
        return 60

    return 45


def headway_score(seconds: float) -> int:
    """
    배차간격 점수.
    정보가 없으면 중립값을 사용한다.
    """

    if seconds <= 0:
        return 70

    minutes = seconds / 60

    if minutes <= 5:
        return 100

    if minutes <= 8:
        return 90

    if minutes <= 10:
        return 80

    if minutes <= 15:
        return 65

    if minutes <= 20:
        return 45

    return 25


# ============================================================
# 환승 구간 분석
# ============================================================

def analyze_transit_segment(
    segment: Dict[str, Any],
) -> Dict[str, Any]:

    headway_seconds = segment.get(
        "headway_seconds",
        0,
    )

    return {
        "vehicle_type": segment.get(
            "vehicle_type",
            "",
        ),

        "line_name": segment.get(
            "line_name",
            "",
        ),

        "departure_stop": segment.get(
            "departure_stop",
            "",
        ),

        "arrival_stop": segment.get(
            "arrival_stop",
            "",
        ),

        "departure_lat": segment.get(
            "departure_lat",
        ),

        "departure_lng": segment.get(
            "departure_lng",
        ),

        "arrival_lat": segment.get(
            "arrival_lat",
        ),

        "arrival_lng": segment.get(
            "arrival_lng",
        ),

        "stop_count": segment.get(
            "stop_count",
            0,
        ),

        "headsign": segment.get(
            "headsign",
            "",
        ),

        "headway_seconds": headway_seconds,

        "headway_min": (
            round(
                headway_seconds / 60,
                1,
            )
            if headway_seconds
            else None
        ),

        "headway_score": headway_score(
            headway_seconds,
        ),
    }


# ============================================================
# 경로 전체 분석
# ============================================================

def evaluate_route(
    route: Dict[str, Any],
    congestion_level: str = "보통",
) -> Dict[str, Any]:

    duration_seconds = float(
        route.get(
            "duration_seconds",
            0,
        )
        or 0
    )

    walking_seconds = float(
        route.get(
            "walking_seconds",
            0,
        )
        or 0
    )

    transfer_count = int(
        route.get(
            "transfer_count",
            0,
        )
        or 0
    )

    stop_count = int(
        route.get(
            "stop_count",
            0,
        )
        or 0
    )

    transit_segments = (
        route.get(
            "transit_segments",
            [],
        )
        or []
    )


    # --------------------------------------------------------
    # 기본 점수
    # --------------------------------------------------------

    time = duration_score(
        duration_seconds,
    )

    walk = walking_score(
        walking_seconds,
    )

    transfer = transfer_score(
        transfer_count,
    )

    stops = stop_score(
        stop_count,
    )

    congestion = congestion_score(
        congestion_level,
    )


    # --------------------------------------------------------
    # 배차간격
    # --------------------------------------------------------

    headway_scores = []

    for segment in transit_segments:

        score = headway_score(
            segment.get(
                "headway_seconds",
                0,
            )
            or 0
        )

        headway_scores.append(
            score
        )


    if headway_scores:
        headway = (
            sum(headway_scores)
            / len(headway_scores)
        )
    else:
        headway = 70


    # --------------------------------------------------------
    # CrowdExit 점수
    #
    # 전체 이동시간은 여전히 중요하게 반영한다.
    # 다만 CrowdExit의 목적은 "무조건 가장 빠른 길"이 아니라
    # "행사 종료 후 실제로 이용하기 편한 귀가 경로"를 찾는 것이다.
    #
    # 따라서 환승 횟수의 영향력을 기존보다 크게 높인다.
    #
    # 시간      45%
    # 환승      25%
    # 혼잡      12%
    # 도보       8%
    # 배차       7%
    # 정류장     3%
    #
    # 추가로 아래 transfer_penalty를 사용해
    # 환승이 많은 경로가 단순히 시간 몇 분이 짧다는 이유로
    # 1회 환승 경로를 쉽게 앞서지 못하도록 한다.
    # --------------------------------------------------------

    final_score = (
        time * 0.45
        + transfer * 0.25
        + congestion * 0.12
        + walk * 0.08
        + headway * 0.07
        + stops * 0.03
    )

    # --------------------------------------------------------
    # 환승 편의성 보정
    #
    # 0회  → 0분
    # 1회  → 3분
    # 2회  → 9분
    # 3회  → 17분
    # 4회  → 25분
    #
    # 예:
    # 1회 환승 72분 vs 3회 환승 62분이라면
    # 단순 시간만 보면 3회 환승이 빠르지만,
    # 환승 편의성 보정 후에는
    # 72 + 3 = 75분
    # 62 + 17 = 79분
    # 이므로 1회 환승 경로를 우선한다.
    # --------------------------------------------------------

    transfer_penalties = {
        0: 0.0,
        1: 2.0,
        2: 14.0,
        3: 25.0,
        4: 35.0,
    }

    transfer_penalty = transfer_penalties.get(
        transfer_count,
        25.0 + ((transfer_count - 4) * 8.0),
    )

    preference_duration_min = (
        duration_seconds / 60
    ) + transfer_penalty

    result = dict(route)

    result["crowdexit_score"] = round(
        final_score,
        1,
    )

    result["transfer_penalty_min"] = round(
        transfer_penalty,
        1,
    )

    result["preference_duration_min"] = round(
        preference_duration_min,
        1,
    )

    result["score_detail"] = {
        "time": round(time),
        "walking": round(walk),
        "transfer": round(transfer),
        "stops": round(stops),
        "congestion": round(congestion),
        "headway": round(headway),
        "transfer_penalty_min": round(
            transfer_penalty,
            1,
        ),
    }


    # 전체 환승구간 유지
    result["transit_analysis"] = [
        analyze_transit_segment(
            segment
        )
        for segment in transit_segments
    ]


    # 화면에서 사용하기 편하도록
    # 전체 구간 요약도 생성
    result["route_steps"] = build_route_steps(
        transit_segments
    )


    return result


# ============================================================
# 전체 경로 단계 생성
# ============================================================

def build_route_steps(
    transit_segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    steps = []

    for index, segment in enumerate(
        transit_segments,
        start=1,
    ):

        vehicle_type = (
            str(
                segment.get(
                    "vehicle_type",
                    "",
                )
            )
            .upper()
        )

        if vehicle_type in (
            "SUBWAY",
            "RAIL",
            "HEAVY_RAIL",
        ):
            mode = "지하철"

        elif vehicle_type in (
            "BUS",
            "INTERCITY_BUS",
            "TROLLEYBUS",
        ):
            mode = "버스"

        else:
            mode = (
                segment.get(
                    "vehicle_type",
                    "대중교통",
                )
            )


        steps.append(
            {
                "step": index,

                "mode": mode,

                "vehicle_type":
                    segment.get(
                        "vehicle_type",
                        "",
                    ),

                "line_name":
                    segment.get(
                        "line_name",
                        "",
                    ),

                "departure_stop":
                    segment.get(
                        "departure_stop",
                        "",
                    ),

                "arrival_stop":
                    segment.get(
                        "arrival_stop",
                        "",
                    ),

                "headsign":
                    segment.get(
                        "headsign",
                        "",
                    ),

                "stop_count":
                    segment.get(
                        "stop_count",
                        0,
                    ),

                "headway_min": (
                    round(
                        segment.get(
                            "headway_seconds",
                            0,
                        )
                        / 60,
                        1,
                    )
                    if segment.get(
                        "headway_seconds",
                        0,
                    )
                    else None
                ),
            }
        )

    return steps


# ============================================================
# 추천 문구
# ============================================================

def make_recommendation_message(
    route: Dict[str, Any],
    congestion_level: str,
) -> str:

    segments = (
        route.get(
            "transit_segments",
            [],
        )
        or []
    )


    if not segments:
        return (
            "대중교통 구간이 없어 "
            "추천 사유를 분석하기 어렵다."
        )


    messages = []


    # --------------------------------------------------------
    # 혼잡
    # --------------------------------------------------------

    if congestion_level in (
        "붐빔",
        "매우 붐빔",
    ):

        messages.append(
            "현재 주변 지역 혼잡도가 높아 "
            "혼잡 회피를 우선 고려했다."
        )

    elif congestion_level == "약간 붐빔":

        messages.append(
            "현재 주변 지역이 다소 혼잡해 "
            "이동시간과 도보거리를 함께 고려했다."
        )

    else:

        messages.append(
            "현재 주변 지역 혼잡도가 높지 않아 "
            "실제 이동시간을 중심으로 경로를 비교했다."
        )


    # --------------------------------------------------------
    # 전체 경로 설명
    # --------------------------------------------------------

    route_descriptions = []

    for segment in segments:

        line = segment.get(
            "line_name",
            "",
        )

        departure = segment.get(
            "departure_stop",
            "",
        )

        arrival = segment.get(
            "arrival_stop",
            "",
        )

        if line:

            route_descriptions.append(
                f"{departure}에서 "
                f"{line}번을 이용해 "
                f"{arrival}까지 이동"
            )

        else:

            route_descriptions.append(
                f"{departure}에서 "
                f"{arrival}까지 이동"
            )


    if route_descriptions:

        messages.append(
            " 이후 ".join(
                route_descriptions
            )
            + "하는 경로다."
        )


    # --------------------------------------------------------
    # 총시간
    # --------------------------------------------------------

    duration_min = route.get(
        "duration_min",
        0,
    )

    if duration_min:

        messages.append(
            f"전체 예상 이동시간은 "
            f"약 {duration_min:.0f}분이다."
        )


    # --------------------------------------------------------
    # 환승
    # --------------------------------------------------------

    transfer_count = route.get(
        "transfer_count",
        0,
    )

    if transfer_count > 0:

        messages.append(
            f"환승은 총 "
            f"{transfer_count}회 필요하다."
        )

    else:

        messages.append(
            "환승 없이 이동할 수 있다."
        )


    return " ".join(
        messages
    )


# ============================================================
# 중복 제거
# ============================================================

def remove_duplicate_routes(
    routes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    unique_routes = []

    seen = set()

    for route in routes:

        segments = (
            route.get(
                "transit_segments",
                [],
            )
            or []
        )

        if not segments:
            continue

        # ----------------------------------------------------
        # 전체 대중교통 경로를 기준으로 중복 판단
        #
        # 같은 노선 + 같은 출발 정류장 + 같은 도착 정류장
        # + 같은 환승 순서라면 같은 경로로 본다.
        #
        # 시간은 중복 판단에 사용하지 않는다.
        # ----------------------------------------------------

        segment_key = tuple(
            (
                str(
                    segment.get(
                        "vehicle_type",
                        "",
                    )
                ).strip(),

                str(
                    segment.get(
                        "line_name",
                        "",
                    )
                ).strip(),

                str(
                    segment.get(
                        "departure_stop",
                        "",
                    )
                ).strip(),

                str(
                    segment.get(
                        "arrival_stop",
                        "",
                    )
                ).strip(),
            )
            for segment in segments
        )

        if segment_key in seen:
            continue

        seen.add(
            segment_key
        )

        unique_routes.append(
            route
        )

    return unique_routes


# ============================================================
# Gemini 전달 데이터
# ============================================================

def build_gemini_route(
    route: Dict[str, Any],
) -> Dict[str, Any]:

    segments = (
        route.get(
            "transit_segments",
            [],
        )
        or []
    )


    if not segments:
        return {}


    # ★ 첫 구간만 보내지 않고
    # 전체 구간을 보낸다.
    segment_data = []


    for index, segment in enumerate(
        segments,
        start=1,
    ):

        segment_data.append(
            {
                "step": index,

                "vehicle_type":
                    segment.get(
                        "vehicle_type",
                        "",
                    ),

                "line_name":
                    segment.get(
                        "line_name",
                        "",
                    ),

                "departure_stop":
                    segment.get(
                        "departure_stop",
                        "",
                    ),

                "arrival_stop":
                    segment.get(
                        "arrival_stop",
                        "",
                    ),

                "headsign":
                    segment.get(
                        "headsign",
                        "",
                    ),

                "stop_count":
                    segment.get(
                        "stop_count",
                        0,
                    ),

                "headway_min": (
                    round(
                        segment.get(
                            "headway_seconds",
                            0,
                        )
                        / 60,
                        1,
                    )
                    if segment.get(
                        "headway_seconds",
                        0,
                    )
                    else None
                ),
            }
        )


    return {
        # 전체 경로
        "segments": segment_data,

        # 전체 이동정보
        "duration_min": route.get(
            "duration_min",
            0,
        ),

        "walking_min": route.get(
            "walking_min",
            0,
        ),

        "transit_min": route.get(
            "transit_min",
            0,
        ),

        "transfer_count": route.get(
            "transfer_count",
            0,
        ),

        "stop_count": route.get(
            "stop_count",
            0,
        ),

        "crowdexit_score": route.get(
            "crowdexit_score",
            0,
        ),
    }


# ============================================================
# 전체 추천
# ============================================================

def recommend(
    routes: List[Dict[str, Any]],
    congestion_level: str = "보통",
) -> List[Dict[str, Any]]:

    if not routes:
        return []


    evaluated = []


    # --------------------------------------------------------
    # 1. 모든 후보 평가
    # --------------------------------------------------------

    for route in routes:

        result = evaluate_route(
            route,
            congestion_level,
        )

        result["recommendation"] = (
            make_recommendation_message(
                result,
                congestion_level,
            )
        )

        evaluated.append(
            result
        )


    # --------------------------------------------------------
    # 2. 중복 제거
    # --------------------------------------------------------

    evaluated = (
        remove_duplicate_routes(
            evaluated
        )
    )


    # --------------------------------------------------------
    # 3. 추천 순서
    #
    # CrowdExit는 "가장 빠른 경로 하나"만 찾는 것이 아니다.
    #
    # 실제 이용자가 체감하기 쉬운 순서:
    #
    # ① 전체 이동시간
    # ② 환승 편의성
    # ③ 혼잡/도보/배차 등 보조 요소
    #
    # 특히 환승이 2~3회 이상인 경로는
    # 몇 분 빠르다는 이유만으로 1회 환승 경로를
    # 쉽게 앞서지 못하도록 한다.
    #
    # preference_duration_min =
    #     실제 이동시간 + 환승 편의성 보정
    #
    # 이 값을 1차 정렬 기준으로 사용하고,
    # 비슷한 경로에서는 CrowdExit 점수를 사용한다.
    # --------------------------------------------------------

    evaluated.sort(
        key=lambda x: (
            x.get(
                "preference_duration_min",
                999999,
            ),

            -x.get(
                "crowdexit_score",
                0,
            ),

            x.get(
                "transfer_count",
                999,
            ),

            x.get(
                "duration_seconds",
                999999,
            ),
        )
    )


    # --------------------------------------------------------
    # 4. 순위
    # --------------------------------------------------------

    for index, route in enumerate(
        evaluated,
        start=1,
    ):

        route["recommendation_rank"] = (
            index
        )

        route["is_recommended"] = (
            index == 1
        )


    # --------------------------------------------------------
    # 5. Gemini
    # --------------------------------------------------------

    if evaluated:

        best_route = evaluated[0]

        gemini_route = (
            build_gemini_route(
                best_route
            )
        )


        if gemini_route:

            try:

                best_route[
                    "ai_recommendation"
                ] = (
                    generate_recommendation_reason(
                        gemini_route
                    )
                )

            except Exception as e:

                print(
                    f"Gemini 추천 문구 생성 실패: {e}"
                )

                best_route[
                    "ai_recommendation"
                ] = (
                    best_route.get(
                        "recommendation",
                        "",
                    )
                )


    return evaluated


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":

    from services.route_api import (
        get_google_transit_routes,
    )


    print("=" * 60)
    print("CrowdExit 추천 엔진 테스트")
    print("=" * 60)


    routes = (
        get_google_transit_routes(
            37.5701,
            126.9769,
            37.5547,
            126.9707,
        )
    )


    print(
        f"\nGoogle Routes 후보: "
        f"{len(routes)}개"
    )


    results = recommend(
        routes,
        congestion_level="보통",
    )


    print(
        "\n"
        + "=" * 60
    )

    print(
        "추천 결과"
    )

    print(
        "=" * 60
    )


    for route in results:

        print(
            f"\n[{route['recommendation_rank']}위]"
        )


        print(
            f"전체 시간: "
            f"{route.get('duration_min', 0)}분"
        )


        print(
            f"환승 편의 보정 후: "
            f"{route.get('preference_duration_min', 0)}분"
        )


        print(
            f"도보: "
            f"{route.get('walking_min', 0)}분"
        )


        print(
            f"환승: "
            f"{route.get('transfer_count', 0)}회"
        )


        print(
            "\n전체 경로:"
        )


        for step in route.get(
            "route_steps",
            [],
        ):

            print(
                f"  {step['step']}. "
                f"{step['mode']} "
                f"{step['line_name']} | "
                f"{step['departure_stop']} → "
                f"{step['arrival_stop']}"
            )


        print(
            f"\n추천 이유: "
            f"{route.get('recommendation', '')}"
        )


        if route.get(
            "is_recommended"
        ):

            print(
                f"Gemini: "
                f"{route.get('ai_recommendation', '')}"
            )