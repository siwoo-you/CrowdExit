"""
CrowdExit 혼잡 패널티 계산 서비스

서울시 실시간 도시데이터의
- AREA_CONGEST_LVL
- LIVE_SUB_PPLTN
- LIVE_BUS_PPLTN

을 이용해 후보 승차지점의 혼잡도를 평가한다.

주의:
서울시 LIVE_SUB_PPLTN / LIVE_BUS_PPLTN은
개별 역·정류장이 아니라 해당 권역의 집계 데이터이므로,
SUB_STN_CNT / BUS_STN_CNT로 나누어 평균 이용량을 계산한다.
"""

from typing import Dict, Any

from services.seoul_api import get_city_data


# ============================================================
# 안전한 숫자 변환
# ============================================================

def safe_float(
    value,
    default: float = 0.0
) -> float:

    try:
        return float(value)

    except (TypeError, ValueError):
        return default


# ============================================================
# 권역 혼잡도 → 기본 패널티
# ============================================================

def area_congestion_penalty(
    level: str
) -> float:
    """
    서울시 AREA_CONGEST_LVL을
    CrowdExit 혼잡 패널티(분)로 변환한다.

    이 값은 실제 대기시간이 아니라
    추천 알고리즘에서 사용하는 추정 패널티다.
    """

    penalties = {
        "여유": 0.0,
        "보통": 1.0,
        "약간 붐빔": 2.5,
        "붐빔": 5.0,
        "매우 붐빔": 8.0,
    }

    return penalties.get(
        str(level or "").strip(),
        1.0
    )


# ============================================================
# 최근 이용량 평균 계산
# ============================================================

def calculate_average_boarding(
    live_data: Dict[str, Any],
    transport_type: str
) -> Dict[str, float]:

    if not live_data:

        return {
            "station_count": 0,
            "boarding_5": 0,
            "boarding_10": 0,
            "boarding_30": 0,
            "avg_boarding_5": 0,
            "avg_boarding_10": 0,
            "avg_boarding_30": 0,
        }

    if transport_type == "subway":

        prefix = "SUB"

        station_count = safe_float(
            live_data.get(
                "SUB_STN_CNT"
            ),
            1
        )

    else:

        prefix = "BUS"

        station_count = safe_float(
            live_data.get(
                "BUS_STN_CNT"
            ),
            1
        )

    if station_count <= 0:
        station_count = 1

    boarding_5 = safe_float(
        live_data.get(
            f"{prefix}_5WTHN_GTON_PPLTN_MAX"
        )
    )

    boarding_10 = safe_float(
        live_data.get(
            f"{prefix}_10WTHN_GTON_PPLTN_MAX"
        )
    )

    boarding_30 = safe_float(
        live_data.get(
            f"{prefix}_30WTHN_GTON_PPLTN_MAX"
        )
    )

    return {
        "station_count": int(
            station_count
        ),

        "boarding_5": boarding_5,

        "boarding_10": boarding_10,

        "boarding_30": boarding_30,

        "avg_boarding_5": round(
            boarding_5 / station_count,
            1
        ),

        "avg_boarding_10": round(
            boarding_10 / station_count,
            1
        ),

        "avg_boarding_30": round(
            boarding_30 / station_count,
            1
        ),
    }


# ============================================================
# 이용량 → 패널티
# ============================================================

def boarding_volume_penalty(
    avg_boarding_10: float,
    transport_type: str
) -> float:
    """
    최근 10분 평균 승차량을 기준으로
    추가 혼잡 패널티를 계산한다.

    실제 대기시간 자체가 아니라
    후보 비교를 위한 CrowdExit 추정값이다.
    """

    value = safe_float(
        avg_boarding_10
    )

    if transport_type == "subway":

        if value < 50:
            return 0.0

        if value < 100:
            return 1.0

        if value < 200:
            return 2.0

        if value < 300:
            return 3.5

        return 5.0

    # 버스
    if value < 5:
        return 0.0

    if value < 10:
        return 0.5

    if value < 20:
        return 1.0

    if value < 30:
        return 2.0

    return 3.5


# ============================================================
# 후보 권역 혼잡 평가
# ============================================================

def get_transport_congestion(
    area_name: str,
    transport_type: str
) -> Dict[str, Any]:

    city_data = get_city_data(
        area_name
    )

    # --------------------------------------------------------
    # 권역 전체 혼잡도
    # --------------------------------------------------------

    population_status = city_data.get(
        "LIVE_PPLTN_STTS",
        []
    )

    if population_status:

        area_status = (
            population_status[0]
        )

        area_level = (
            area_status.get(
                "AREA_CONGEST_LVL",
                "정보 없음"
            )
        )

        measured_at = (
            area_status.get(
                "PPLTN_TIME"
            )
        )

    else:

        area_level = "정보 없음"
        measured_at = None

    # --------------------------------------------------------
    # 교통수단별 이용량
    # --------------------------------------------------------

    if transport_type == "subway":

        live_data = city_data.get(
            "LIVE_SUB_PPLTN",
            {}
        )

    else:

        live_data = city_data.get(
            "LIVE_BUS_PPLTN",
            {}
        )

    boarding = calculate_average_boarding(
        live_data,
        transport_type
    )

    # --------------------------------------------------------
    # 패널티 계산
    # --------------------------------------------------------

    area_penalty = (
        area_congestion_penalty(
            area_level
        )
    )

    volume_penalty = (
        boarding_volume_penalty(
            boarding[
                "avg_boarding_10"
            ],
            transport_type
        )
    )

    total_penalty = (
        area_penalty
        + volume_penalty
    )

    return {
        "area_name": area_name,

        "transport_type": (
            transport_type
        ),

        "area_congestion": (
            area_level
        ),

        "measured_at": (
            measured_at
        ),

        "station_count": (
            boarding[
                "station_count"
            ]
        ),

        "boarding_5": (
            boarding[
                "boarding_5"
            ]
        ),

        "boarding_10": (
            boarding[
                "boarding_10"
            ]
        ),

        "boarding_30": (
            boarding[
                "boarding_30"
            ]
        ),

        "avg_boarding_5": (
            boarding[
                "avg_boarding_5"
            ]
        ),

        "avg_boarding_10": (
            boarding[
                "avg_boarding_10"
            ]
        ),

        "avg_boarding_30": (
            boarding[
                "avg_boarding_30"
            ]
        ),

        "area_penalty_min": (
            area_penalty
        ),

        "volume_penalty_min": (
            volume_penalty
        ),

        "congestion_penalty_min": round(
            total_penalty,
            1
        ),
    }


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":

    test_cases = [
        (
            "잠실종합운동장",
            "subway"
        ),
        (
            "잠실종합운동장",
            "bus"
        ),
        (
            "잠실새내역",
            "subway"
        ),
        (
            "잠실새내역",
            "bus"
        ),
    ]

    print(
        "=" * 60
    )

    print(
        "CrowdExit 혼잡 패널티 테스트"
    )

    print(
        "=" * 60
    )

    for area_name, transport_type in test_cases:

        print()

        print(
            f"[{area_name} / "
            f"{transport_type}]"
        )

        try:

            result = (
                get_transport_congestion(
                    area_name,
                    transport_type
                )
            )

        except Exception as e:

            print(
                "조회 실패:",
                e
            )

            continue

        print(
            "권역 혼잡도:",
            result[
                "area_congestion"
            ]
        )

        print(
            "측정 시간:",
            result[
                "measured_at"
            ]
        )

        print(
            "역/정류장 수:",
            result[
                "station_count"
            ]
        )

        print(
            "최근 5분 승차:",
            result[
                "boarding_5"
            ]
        )

        print(
            "최근 10분 승차:",
            result[
                "boarding_10"
            ]
        )

        print(
            "최근 30분 승차:",
            result[
                "boarding_30"
            ]
        )

        print(
            "1개소당 최근 10분 평균:",
            result[
                "avg_boarding_10"
            ]
        )

        print(
            "권역 혼잡 패널티:",
            result[
                "area_penalty_min"
            ],
            "분"
        )

        print(
            "승차량 패널티:",
            result[
                "volume_penalty_min"
            ],
            "분"
        )

        print(
            "총 혼잡 패널티:",
            result[
                "congestion_penalty_min"
            ],
            "분"
        )