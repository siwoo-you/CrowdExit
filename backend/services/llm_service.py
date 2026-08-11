from google import genai


PROJECT_ID = "proj-aj13-211200020328"
LOCATION = "us-central1"

client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION,
)


# ============================================================
# 일반 추천 경로 설명
# ============================================================

def generate_recommendation_reason(
    route: dict
) -> str:
    """
    일반 대중교통 추천 경로 설명 생성
    """

    prompt = f"""
너는 CrowdExit라는 대형행사 귀가 혼잡 분산 서비스의
AI 안내 도우미다.

사용자가 행사 종료 후 혼잡한 역이나 정류장을 피하면서
빠르고 편하게 귀가할 수 있도록 추천 이유를 설명한다.

다음 경로 정보를 바탕으로
사용자에게 보여줄 자연스러운 한국어 안내문을 작성해줘.

노선: {route.get("line_name", "")}
출발 승차지점: {route.get("departure_stop", "")}
도착지점: {route.get("arrival_stop", "")}
예상 총 이동시간: {route.get("duration_min", "")}분
도보시간: {route.get("walking_min", "")}분
환승 횟수: {route.get("transfer_count", 0)}회
정류장 수: {route.get("stop_count", "")}

조건:
- 2~3문장
- 너무 길지 않게
- 왜 이 경로를 추천하는지 설명
- 데이터에 없는 내용을 임의로 만들지 말 것
- 사용자에게 자연스럽고 친절하게 안내
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    return response.text


# ============================================================
# 대체 승차 추천 설명
# ============================================================

def generate_distributed_boarding_reason(
    decision: dict
) -> str:
    """
    현재 승차지점과 대체 승차지점을 비교하여
    CrowdExit 최종 사용자 안내문을 생성한다.
    """

    recommend_alternative = decision.get(
        "recommend_alternative",
        False
    )

    saved_minutes = decision.get(
        "saved_minutes",
        0
    )

    current = decision.get(
        "current"
    )

    alternative = decision.get(
        "alternative"
    )

    decision_reason = decision.get(
        "decision_reason",
        ""
    )

    prompt = f"""
너는 CrowdExit라는 대형행사 귀가 혼잡 분산 서비스의
AI 안내 도우미다.

CrowdExit 추천 알고리즘이 계산한 결과를
사용자가 이해하기 쉬운 짧은 한국어 안내문으로 설명한다.

대체 승차 추천 여부:
{recommend_alternative}

절약 예상 시간:
{saved_minutes}분

현재 승차 경로:
{current}

대체 승차 경로:
{alternative}

알고리즘 판단:
{decision_reason}

작성 규칙:

1. 대체 승차 추천 여부가 True라면
   - 현재 승차지점이 혼잡하다는 점을 설명
   - 대체 승차지점까지 도보 몇 분인지 안내
   - 실제 이용할 노선을 정확히 안내
   - 예상 절약시간을 설명

2. 대체 승차 추천 여부가 False라면
   - 억지로 다른 역이나 정류장으로 이동하도록 권하지 말 것
   - 현재 승차지점을 이용하는 것이 더 적절한 이유를 설명

3. 데이터에 없는 정보는 절대 만들어내지 말 것.

4. 혼잡 패널티는 CrowdExit 내부 추정값이므로
   사용자에게 '대기시간이 정확히 몇 분이다'라고 단정하지 말 것.

5. 2~3문장으로 작성.

6. 자연스럽고 간결한 한국어로 작성.

7. 'CrowdExit 알고리즘', '패널티', 'API' 같은
   내부 기술 용어는 사용자에게 말하지 말 것.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    return response.text