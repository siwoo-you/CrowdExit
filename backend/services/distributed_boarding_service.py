"""
CrowdExit 분산 승차 최종 의사결정 서비스

기능:
1. 현재 승차지점과 대체 승차지점 후보 비교
2. Google Routes 기준 실제 탑승 노선 표시
3. 중복 경로 제거
4. 절약시간 계산
5. 대체 승차가 실제로 유리할 때만 추천
6. Gemini 안내용 데이터 생성
7. 행사 종료 혼잡 상황 시뮬레이션
"""

from typing import Dict, List, Any
from copy import deepcopy


# ============================================================
# 실제 탑승 노선 추출
# ============================================================

def get_actual_boarding_info(
    candidate: Dict[str, Any]
) -> Dict[str, str]:

    segments = candidate.get(
        "transit_segments",
        []
    )

    if not segments:
        return {
            "departure_stop": "",
            "arrival_stop": "",
            "line_name": "",
            "vehicle_type": "",
        }

    first_segment = segments[0]

    return {
        "departure_stop": first_segment.get(
            "departure_stop",
            ""
        ),
        "arrival_stop": first_segment.get(
            "arrival_stop",
            ""
        ),
        "line_name": first_segment.get(
            "line_name",
            ""
        ),
        "vehicle_type": first_segment.get(
            "vehicle_type",
            ""
        ),
    }


# ============================================================
# 최종 출력용 후보 데이터 정리
# ============================================================

def normalize_candidate(
    candidate: Dict[str, Any]
) -> Dict[str, Any]:

    actual = get_actual_boarding_info(
        candidate
    )

    result = dict(
        candidate
    )

    result[
        "actual_departure_stop"
    ] = actual[
        "departure_stop"
    ]

    result[
        "actual_arrival_stop"
    ] = actual[
        "arrival_stop"
    ]

    result[
        "actual_line_name"
    ] = actual[
        "line_name"
    ]

    result[
        "actual_vehicle_type"
    ] = actual[
        "vehicle_type"
    ]

    return result


# ============================================================
# 실제 탑승 경로 기준 중복 제거
# ============================================================

def remove_duplicate_final_routes(
    candidates: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    results = []
    seen = set()

    for candidate in candidates:

        normalized = normalize_candidate(
            candidate
        )

        key = (
            normalized.get(
                "type"
            ),
            normalized.get(
                "actual_departure_stop"
            ),
            normalized.get(
                "actual_arrival_stop"
            ),
            normalized.get(
                "actual_line_name"
            ),
            round(
                float(
                    normalized.get(
                        "adjusted_total_min",
                        0
                    )
                ),
                1
            ),
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        results.append(
            normalized
        )

    return results


# ============================================================
# 현재 승차 후보 결정
# ============================================================

def find_current_boarding_candidate(
    candidates: List[Dict[str, Any]],
    current_area_name: str
) -> Dict[str, Any] | None:

    """
    현재 권역에 속한 후보 중
    CrowdExit 예상 총시간이 가장 짧은 경로를 선택한다.
    """

    current_candidates = [
        candidate
        for candidate in candidates
        if candidate.get(
            "area_name"
        ) == current_area_name
    ]

    if not current_candidates:
        return None

    return min(
        current_candidates,
        key=lambda x: x.get(
            "adjusted_total_min",
            float("inf")
        )
    )


# ============================================================
# 대체 승차 후보 결정
# ============================================================

def find_best_alternative_candidate(
    candidates: List[Dict[str, Any]],
    current_area_name: str
) -> Dict[str, Any] | None:

    """
    현재 권역이 아닌 후보 중
    CrowdExit 예상 총시간이 가장 짧은 경로를 선택한다.
    """

    alternative_candidates = [
        candidate
        for candidate in candidates
        if candidate.get(
            "area_name"
        ) != current_area_name
    ]

    if not alternative_candidates:
        return None

    return min(
        alternative_candidates,
        key=lambda x: x.get(
            "adjusted_total_min",
            float("inf")
        )
    )


# ============================================================
# 분산 승차 최종 판단
# ============================================================

def decide_distributed_boarding(
    candidates: List[Dict[str, Any]],
    current_area_name: str,
    minimum_saved_minutes: float = 3.0
) -> Dict[str, Any]:

    """
    현재 승차 경로와 대체 승차 경로를 비교한다.

    대체 승차 경로가 minimum_saved_minutes 이상
    유리한 경우에만 대체 승차를 추천한다.
    """

    if not candidates:

        return {
            "recommend_alternative": False,
            "reason": "추천 가능한 경로가 없습니다.",
            "current_route": None,
            "alternative_route": None,
            "saved_minutes": 0,
        }

    # 실제 Google 탑승 경로 기준으로 중복 제거
    candidates = remove_duplicate_final_routes(
        candidates
    )

    current_route = find_current_boarding_candidate(
        candidates,
        current_area_name
    )

    alternative_route = find_best_alternative_candidate(
        candidates,
        current_area_name
    )

    # --------------------------------------------------------
    # 현재 권역 경로가 없는 경우
    # --------------------------------------------------------

    if not current_route:

        if alternative_route:

            return {
                "recommend_alternative": True,
                "reason": (
                    "현재 위치 주변에서 적절한 승차 경로를 "
                    "찾기 어려워 대체 승차지점을 추천합니다."
                ),
                "current_route": None,
                "alternative_route": alternative_route,
                "saved_minutes": None,
            }

        return {
            "recommend_alternative": False,
            "reason": "추천 가능한 경로가 없습니다.",
            "current_route": None,
            "alternative_route": None,
            "saved_minutes": 0,
        }

    # --------------------------------------------------------
    # 대체 권역 경로가 없는 경우
    # --------------------------------------------------------

    if not alternative_route:

        return {
            "recommend_alternative": False,
            "reason": (
                "현재 승차지점보다 유리한 "
                "대체 승차지점을 찾지 못했습니다."
            ),
            "current_route": current_route,
            "alternative_route": None,
            "saved_minutes": 0,
        }

    # --------------------------------------------------------
    # 시간 비교
    # --------------------------------------------------------

    current_total = float(
        current_route.get(
            "adjusted_total_min",
            0
        )
    )

    alternative_total = float(
        alternative_route.get(
            "adjusted_total_min",
            0
        )
    )

    saved_minutes = round(
        current_total - alternative_total,
        1
    )

    recommend_alternative = (
        saved_minutes
        >= minimum_saved_minutes
    )

    # --------------------------------------------------------
    # 판단 문구
    # --------------------------------------------------------

    if recommend_alternative:

        reason = (
            f"대체 승차지점을 이용하면 "
            f"약 {saved_minutes}분 절약할 수 있습니다."
        )

    elif saved_minutes > 0:

        reason = (
            f"대체 승차지점이 약 {saved_minutes}분 빠르지만, "
            f"도보 이동 부담을 고려하면 "
            f"현재 승차지점을 이용하는 것이 적절합니다."
        )

    else:

        difference = abs(
            saved_minutes
        )

        reason = (
            f"현재 승차지점이 대체 승차지점보다 "
            f"약 {difference}분 빠릅니다."
        )

    return {
        "recommend_alternative": recommend_alternative,
        "reason": reason,
        "current_route": current_route,
        "alternative_route": alternative_route,
        "saved_minutes": saved_minutes,
    }


# ============================================================
# Gemini 전달 데이터 생성
# ============================================================

def build_gemini_input(
    decision: Dict[str, Any]
) -> Dict[str, Any]:

    current_route = decision.get(
        "current_route"
    )

    alternative_route = decision.get(
        "alternative_route"
    )

    result = {
        "recommend_alternative": decision.get(
            "recommend_alternative",
            False
        ),
        "saved_minutes": decision.get(
            "saved_minutes",
            0
        ),
        "decision_reason": decision.get(
            "reason",
            ""
        ),
    }

    # --------------------------------------------------------
    # 현재 승차 경로
    # --------------------------------------------------------

    if current_route:

        result["current"] = {
            "boarding_point": current_route.get(
                "actual_departure_stop"
            ),
            "line_name": current_route.get(
                "actual_line_name"
            ),
            "vehicle_type": current_route.get(
                "actual_vehicle_type"
            ),
            "walking_min": current_route.get(
                "walking_min",
                0
            ),
            "transit_min": current_route.get(
                "transit_duration_min",
                0
            ),
            "congestion": current_route.get(
                "area_congestion"
            ),
            "congestion_penalty_min": current_route.get(
                "congestion_penalty_min",
                0
            ),
            "total_min": current_route.get(
                "adjusted_total_min",
                0
            ),
        }

    else:

        result["current"] = None

    # --------------------------------------------------------
    # 대체 승차 경로
    # --------------------------------------------------------

    if alternative_route:

        result["alternative"] = {
            "boarding_point": alternative_route.get(
                "actual_departure_stop"
            ),
            "line_name": alternative_route.get(
                "actual_line_name"
            ),
            "vehicle_type": alternative_route.get(
                "actual_vehicle_type"
            ),
            "walking_min": alternative_route.get(
                "walking_min",
                0
            ),
            "transit_min": alternative_route.get(
                "transit_duration_min",
                0
            ),
            "congestion": alternative_route.get(
                "area_congestion"
            ),
            "congestion_penalty_min": alternative_route.get(
                "congestion_penalty_min",
                0
            ),
            "total_min": alternative_route.get(
                "adjusted_total_min",
                0
            ),
        }

    else:

        result["alternative"] = None

    return result


# ============================================================
# 화면 출력용 요약
# ============================================================

def print_route_summary(
    title: str,
    route: Dict[str, Any] | None
):

    print()
    print(title)

    if not route:

        print("경로 없음")
        return

    print(
        "승차지점:",
        route.get(
            "actual_departure_stop"
        )
    )

    print(
        "실제 탑승 노선:",
        route.get(
            "actual_line_name"
        )
    )

    print(
        "도보:",
        route.get(
            "walking_min",
            0
        ),
        "분"
    )

    print(
        "대중교통:",
        route.get(
            "transit_duration_min",
            0
        ),
        "분"
    )

    print(
        "권역 혼잡도:",
        route.get(
            "area_congestion"
        )
    )

    print(
        "혼잡 패널티:",
        route.get(
            "congestion_penalty_min",
            0
        ),
        "분"
    )

    print(
        "CrowdExit 총시간:",
        route.get(
            "adjusted_total_min",
            0
        ),
        "분"
    )


# ============================================================
# 행사 종료 혼잡 시뮬레이션
# ============================================================

def apply_event_simulation(
    candidates: List[Dict[str, Any]],
    congested_area_name: str,
    simulated_area_penalty_min: float = 18.0
) -> List[Dict[str, Any]]:

    """
    테스트/시연을 위해 특정 권역을
    '매우 붐빔' 상태로 가정한다.

    실제 서울시 API 데이터를 변경하지 않고
    candidates 복사본에만 적용한다.
    """

    simulated_candidates = deepcopy(
        candidates
    )

    for candidate in simulated_candidates:

        if (
            candidate.get(
                "area_name"
            )
            != congested_area_name
        ):
            continue

        # ----------------------------------------------------
        # 시뮬레이션 혼잡도
        # ----------------------------------------------------

        candidate[
            "area_congestion"
        ] = "매우 붐빔"

        candidate[
            "area_penalty_min"
        ] = simulated_area_penalty_min

        # 기존 실제 승차량 패널티는 유지
        volume_penalty = float(
            candidate.get(
                "volume_penalty_min",
                0
            )
        )

        congestion_penalty = (
            simulated_area_penalty_min
            + volume_penalty
        )

        candidate[
            "congestion_penalty_min"
        ] = round(
            congestion_penalty,
            1
        )

        # ----------------------------------------------------
        # 시간 재계산
        # ----------------------------------------------------

        walking_min = float(
            candidate.get(
                "walking_min",
                0
            )
        )

        transit_min = float(
            candidate.get(
                "transit_duration_min",
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

        candidate[
            "base_total_min"
        ] = round(
            base_total_min,
            1
        )

        candidate[
            "adjusted_total_min"
        ] = round(
            adjusted_total_min,
            1
        )

        candidate[
            "total_min"
        ] = candidate[
            "adjusted_total_min"
        ]

        candidate[
            "total_seconds"
        ] = round(
            adjusted_total_min * 60
        )

    return simulated_candidates


# ============================================================
# 단독 테스트
# ============================================================

if __name__ == "__main__":

    from services.alternative_boarding_service import (
        find_alternative_boarding_points,
    )

    print("=" * 60)
    print("CrowdExit 행사 종료 혼잡 시뮬레이션")
    print("=" * 60)

    # --------------------------------------------------------
    # 출발지 / 목적지
    # --------------------------------------------------------

    # 잠실야구장 부근
    origin_lat = 37.5150
    origin_lon = 127.0728

    # 강남역
    destination_lat = 37.4979
    destination_lon = 127.0276

    # --------------------------------------------------------
    # 검색할 서울시 citydata 권역
    # --------------------------------------------------------

    area_names = [
        "잠실종합운동장",
        "잠실새내역",
    ]

    current_area_name = (
        "잠실종합운동장"
    )

    # --------------------------------------------------------
    # 대체 승차 후보 탐색
    # --------------------------------------------------------
    #
    # 테스트이므로 대체 승차 탐색 자체는
    # 강제로 실행한다.
    #
    # 후보별 실제 혼잡도는
    # alternative_boarding_service에서
    # 서울시 API를 통해 가져온다.
    # --------------------------------------------------------

    search_condition = (
        "매우 붐빔"
    )

    candidates = find_alternative_boarding_points(
        area_names=area_names,
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        destination_lat=destination_lat,
        destination_lon=destination_lon,
        congestion_level=search_condition,
        max_results=15,
    )

    # --------------------------------------------------------
    # 행사 종료 상황 시뮬레이션 적용
    # --------------------------------------------------------
    #
    # 잠실종합운동장 권역만
    # 매우 붐빔 + 18분 패널티로 가정한다.
    #
    # 잠실새내역은 실제 API 값을 그대로 사용한다.
    # --------------------------------------------------------

    simulated_candidates = apply_event_simulation(
        candidates=candidates,
        congested_area_name="잠실종합운동장",
        simulated_area_penalty_min=18.0,
    )

    # --------------------------------------------------------
    # 현재 승차 vs 대체 승차 비교
    # --------------------------------------------------------

    decision = decide_distributed_boarding(
        simulated_candidates,
        current_area_name=current_area_name,
        minimum_saved_minutes=3.0,
    )

    # --------------------------------------------------------
    # 결과 출력
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("행사 종료 시뮬레이션 결과")
    print("=" * 60)

    print_route_summary(
        "현재 승차 경로",
        decision.get(
            "current_route"
        )
    )

    print_route_summary(
        "대체 승차 경로",
        decision.get(
            "alternative_route"
        )
    )

    print()

    print(
        "대체 승차 추천:",
        decision.get(
            "recommend_alternative"
        )
    )

    print(
        "절약 시간:",
        decision.get(
            "saved_minutes"
        ),
        "분"
    )

    print(
        "판단:",
        decision.get(
            "reason"
        )
    )

    # --------------------------------------------------------
    # Gemini 전달 데이터
    # --------------------------------------------------------

    gemini_input = build_gemini_input(
        decision
    )

    print()
    print("=" * 60)
    print("Gemini 전달 데이터")
    print("=" * 60)

    print(
        gemini_input
    )

    from services.llm_service import (
        generate_distributed_boarding_reason,
    )

    print()
    print("=" * 60)
    print("Gemini 최종 안내")
    print("=" * 60)

    ai_message = generate_distributed_boarding_reason(
        gemini_input
    )

    print(
        ai_message
    )