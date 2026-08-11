"""
CrowdExit FastAPI 서버

기능
1. 서울시 주요 121장소 검색
2. 현재 서울시 권역 혼잡도 조회
3. 일반 상황 → 일반 대중교통 경로 추천
4. 혼잡 상황 → 대체 승차지점 탐색
5. 현재 승차 vs 대체 승차 비교
6. Gemini 최종 안내 생성
7. 프론트엔드에서 사용할 JSON 응답 반환
"""

from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services.seoul_api import get_city_data

# ★ 서울시 121개 장소 검색
from services.area_service import search_areas

from services.route_api import (
    get_google_transit_routes,
)

from services.recommendation_engine import (
    recommend,
)

from services.alternative_boarding_service import (
    find_alternative_boarding_points,
)

from services.distributed_boarding_service import (
    decide_distributed_boarding,
    build_gemini_input,
    apply_event_simulation,
)

from services.llm_service import (
    generate_distributed_boarding_reason,
)


# ============================================================
# FastAPI
# ============================================================

app = FastAPI(
    title="CrowdExit API",
    description="대형행사 종료 후 혼잡 분산 귀가 경로 추천 API",
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 요청 데이터
# ============================================================

class RecommendationRequest(BaseModel):

    # 사용자 현재 위치
    origin_lat: float
    origin_lon: float

    # 목적지
    destination_lat: float
    destination_lon: float

    # 현재 서울시 실시간 도시데이터 권역
    current_area_name: str

    # 주변 비교 권역
    nearby_area_names: List[str] = Field(
        default_factory=list
    )

    # --------------------------------------------------------
    # 시연용 행사 혼잡 모드
    # --------------------------------------------------------
    #
    # True:
    # 현재 권역을 매우 붐빔 상태로 가정
    #
    # False:
    # 실제 서울시 혼잡 데이터 사용
    # --------------------------------------------------------

    simulate_event: bool = False

    simulated_area_penalty_min: float = 18.0


# ============================================================
# 현재 권역 혼잡도
# ============================================================

def get_current_area_congestion(
    area_name: str
) -> dict:

    city_data = get_city_data(
        area_name
    )

    live_population = city_data.get(
        "LIVE_PPLTN_STTS",
        []
    )

    if not live_population:

        return {
            "level": "보통",
            "message": "",
            "measured_at": None,
        }

    current = live_population[0]

    return {
        "level": current.get(
            "AREA_CONGEST_LVL",
            "보통"
        ),

        "message": current.get(
            "AREA_CONGEST_MSG",
            ""
        ),

        "measured_at": current.get(
            "PPLTN_TIME"
        ),
    }


# ============================================================
# 일반 경로 추천
# ============================================================

def get_normal_recommendation(
    request: RecommendationRequest,
    congestion_level: str
) -> dict:

    routes = get_google_transit_routes(
        request.origin_lat,
        request.origin_lon,
        request.destination_lat,
        request.destination_lon,
    )

    if not routes:

        return {
            "mode": "normal",
            "routes": [],
            "recommended_route": None,
            "ai_message": (
                "현재 이용 가능한 대중교통 경로를 "
                "찾지 못했습니다."
            ),
        }

    results = recommend(
        routes,
        congestion_level=congestion_level
    )

    best_route = (
        results[0]
        if results
        else None
    )

    ai_message = ""

    if best_route:

        ai_message = best_route.get(
            "ai_recommendation",
            best_route.get(
                "recommendation",
                ""
            )
        )

    return {
        "mode": "normal",

        "routes": results,

        "recommended_route": (
            best_route
        ),

        "ai_message": (
            ai_message
        ),
    }


# ============================================================
# 분산 승차 추천
# ============================================================

def get_distributed_recommendation(
    request: RecommendationRequest,
    search_condition: str
) -> dict:

    # --------------------------------------------------------
    # 현재 권역 + 주변 권역
    # --------------------------------------------------------

    area_names = [
        request.current_area_name
    ]

    for area_name in (
        request.nearby_area_names
    ):

        if area_name not in area_names:

            area_names.append(
                area_name
            )

    # --------------------------------------------------------
    # 실제 대체 승차 후보 탐색
    # --------------------------------------------------------

    candidates = (
        find_alternative_boarding_points(
            area_names=area_names,

            origin_lat=(
                request.origin_lat
            ),

            origin_lon=(
                request.origin_lon
            ),

            destination_lat=(
                request.destination_lat
            ),

            destination_lon=(
                request.destination_lon
            ),

            congestion_level=(
                search_condition
            ),

            max_results=15,
        )
    )

    # --------------------------------------------------------
    # 시연 모드
    # --------------------------------------------------------

    if request.simulate_event:

        candidates = apply_event_simulation(
            candidates=candidates,

            congested_area_name=(
                request.current_area_name
            ),

            simulated_area_penalty_min=(
                request.simulated_area_penalty_min
            ),
        )

    # --------------------------------------------------------
    # 현재 vs 대체 승차 비교
    # --------------------------------------------------------

    decision = (
        decide_distributed_boarding(
            candidates,
            current_area_name=(
                request.current_area_name
            ),
            minimum_saved_minutes=3.0,
        )
    )

    # --------------------------------------------------------
    # Gemini 입력
    # --------------------------------------------------------

    gemini_input = (
        build_gemini_input(
            decision
        )
    )

    # --------------------------------------------------------
    # Gemini 최종 안내
    # --------------------------------------------------------

    try:

        ai_message = (
            generate_distributed_boarding_reason(
                gemini_input
            )
        )

    except Exception as e:

        print(
            f"Gemini 최종 안내 생성 실패: {e}"
        )

        ai_message = decision.get(
            "reason",
            ""
        )

    return {
        "mode": "distributed",

        "recommend_alternative": (
            decision.get(
                "recommend_alternative",
                False
            )
        ),

        "saved_minutes": (
            decision.get(
                "saved_minutes"
            )
        ),

        "decision_reason": (
            decision.get(
                "reason"
            )
        ),

        "current_route": (
            decision.get(
                "current_route"
            )
        ),

        "alternative_route": (
            decision.get(
                "alternative_route"
            )
        ),

        "ai_message": (
            ai_message
        ),

        "gemini_input": (
            gemini_input
        ),
    }


# ============================================================
# 기본 API
# ============================================================

@app.get("/")
def root():

    return {
        "service": "CrowdExit",
        "status": "running",
    }


@app.get("/health")
def health():

    return {
        "status": "ok"
    }


# ============================================================
# 서울시 주요 121장소 검색 API
# ============================================================

@app.get("/areas")
def get_areas(
    q: str = ""
):

    try:

        areas = search_areas(
            q
        )

        return {
            "count": len(
                areas
            ),

            "areas": areas,
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ============================================================
# 최종 추천 API
# ============================================================

@app.post("/recommend")
def recommend_route(
    request: RecommendationRequest
):

    try:

        # ----------------------------------------------------
        # 서울시 실제 현재 혼잡도
        # ----------------------------------------------------

        congestion = (
            get_current_area_congestion(
                request.current_area_name
            )
        )

        actual_level = congestion.get(
            "level",
            "보통"
        )

        # ----------------------------------------------------
        # 시연 모드
        # ----------------------------------------------------

        if request.simulate_event:

            search_condition = (
                "매우 붐빔"
            )

        else:

            search_condition = (
                actual_level
            )

        # ----------------------------------------------------
        # 혼잡 → 분산 승차 추천
        # ----------------------------------------------------

        if search_condition in (
            "붐빔",
            "매우 붐빔"
        ):

            result = (
                get_distributed_recommendation(
                    request,
                    search_condition
                )
            )

        # ----------------------------------------------------
        # 비혼잡 → 일반 경로 추천
        # ----------------------------------------------------

        else:

            result = (
                get_normal_recommendation(
                    request,
                    actual_level
                )
            )

        # ----------------------------------------------------
        # 공통 정보
        # ----------------------------------------------------

        result[
            "current_area"
        ] = request.current_area_name

        result[
            "actual_congestion"
        ] = actual_level

        result[
            "congestion_message"
        ] = congestion.get(
            "message"
        )

        result[
            "measured_at"
        ] = congestion.get(
            "measured_at"
        )

        result[
            "simulation"
        ] = request.simulate_event

        return result

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )