import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("SEOUL_API_KEY")
BASE_URL = "http://openapi.seoul.go.kr:8088"


def get_city_data(area_name: str) -> dict:
    """
    서울시 실시간 도시데이터 API 호출
    """

    if not API_KEY:
        raise ValueError(
            "SEOUL_API_KEY가 .env에 설정되어 있지 않습니다."
        )

    url = f"{BASE_URL}/{API_KEY}/json/citydata/1/5/{area_name}"

    response = httpx.get(url, timeout=10)
    response.raise_for_status()

    data = response.json()

    result = data.get("RESULT", {})
    result_code = result.get("RESULT.CODE")

    if result_code != "INFO-000":
        message = result.get(
            "RESULT.MESSAGE",
            "알 수 없는 오류"
        )
        raise RuntimeError(
            f"서울시 API 오류: {result_code} - {message}"
        )

    return data.get("CITYDATA", {})


def get_crowd_info(area_name: str) -> dict:
    """
    CrowdExit에서 사용할 형태로
    서울시 실시간 데이터를 정리한다.
    """

    data = get_city_data(area_name)

    live_population = data.get("LIVE_PPLTN_STTS", [])

    if not live_population:
        raise RuntimeError("실시간 인구 데이터를 찾을 수 없습니다.")

    crowd = live_population[0]

    result = {
        "area": data.get("AREA_NM"),
        "area_code": data.get("AREA_CD"),

        "congestion": crowd.get("AREA_CONGEST_LVL"),
        "congestion_message": crowd.get("AREA_CONGEST_MSG"),

        "population": {
            "min": int(crowd.get("AREA_PPLTN_MIN", 0)),
            "max": int(crowd.get("AREA_PPLTN_MAX", 0)),
        },

        "measured_at": crowd.get("PPLTN_TIME"),

        "forecast": []
    }

    # 혼잡도 예측 데이터
    forecasts = crowd.get("FCST_PPLTN", [])

    for forecast in forecasts:
        result["forecast"].append({
            "time": forecast.get("FCST_TIME"),
            "congestion": forecast.get("FCST_CONGEST_LVL"),
            "population_min": int(
                forecast.get("FCST_PPLTN_MIN", 0)
            ),
            "population_max": int(
                forecast.get("FCST_PPLTN_MAX", 0)
            )
        })

    # 날씨 정보
    weather_list = data.get("WEATHER_STTS", [])

    if weather_list:
        weather = weather_list[0]

        result["weather"] = {
            "temperature": float(
                weather.get("TEMP", 0)
            ),
            "humidity": float(
                weather.get("HUMIDITY", 0)
            ),
            "precipitation": weather.get("PRECIPITATION"),
            "precipitation_type": weather.get("PRECPT_TYPE"),
            "rain_message": weather.get("PCP_MSG")
        }
    else:
        result["weather"] = None

    # 도로 통제 / 행사 정보
    controls = data.get("ACDNT_CNTRL_STTS", [])

    result["traffic_controls"] = []

    for control in controls:
        result["traffic_controls"].append({
            "type": control.get("ACDNT_TYPE"),
            "detail_type": control.get("ACDNT_DTYPE"),
            "info": control.get("ACDNT_INFO"),
            "expected_clear": control.get("EXP_CLR_DT"),
            "x": control.get("ACDNT_X"),
            "y": control.get("ACDNT_Y")
        })

    return result


if __name__ == "__main__":
    data = get_crowd_info("광화문·덕수궁")

    print("지역:", data["area"])
    print("현재 혼잡도:", data["congestion"])
    print(
        "현재 인구:",
        data["population"]["min"],
        "~",
        data["population"]["max"]
    )
    print("측정시간:", data["measured_at"])

    print("\n날씨:")
    print(data["weather"])

    print("\n도로 통제:")
    for control in data["traffic_controls"]:
        print("-", control["info"])

    print("\n혼잡도 예측:")
    for forecast in data["forecast"]:
        print(
            forecast["time"],
            forecast["congestion"],
            forecast["population_min"],
            "~",
            forecast["population_max"]
        )

def get_bus_station_data(area_name: str) -> list:
    """
    서울시 실시간 도시데이터에서
    해당 지역의 버스 정류장별 실시간 승하차 데이터를 추출한다.
    """

    data = get_city_data(area_name)

    bus_stations = data.get("BUS_STN_STTS", [])

    if not bus_stations:
        raise RuntimeError(
            "버스 정류장 데이터를 찾을 수 없습니다."
        )

    results = []

    for station in bus_stations:
        results.append({
            "station_id": station.get("BUS_STN_ID"),
            "ars_id": station.get("BUS_ARS_ID"),
            "station_name": station.get("BUS_STN_NM"),

            "longitude": station.get("BUS_STN_X"),
            "latitude": station.get("BUS_STN_Y"),

            # 현재 실시간 버스 이용량
            "live_population": station.get(
                "LIVE_BUS_PPLTN"
            ),

            # 당일 누적 승하차
            "daily_boarding_min": station.get(
                "BUS_ACML_GTON_PPLTN_MIN"
            ),
            "daily_boarding_max": station.get(
                "BUS_ACML_GTON_PPLTN_MAX"
            ),
            "daily_alighting_min": station.get(
                "BUS_ACML_GTOFF_PPLTN_MIN"
            ),
            "daily_alighting_max": station.get(
                "BUS_ACML_GTOFF_PPLTN_MAX"
            ),

            # 최근 30분
            "boarding_30_min": station.get(
                "BUS_30WTHN_GTON_PPLTN_MAX"
            ),
            "alighting_30_min": station.get(
                "BUS_30WTHN_GTOFF_PPLTN_MAX"
            ),

            # 최근 10분
            "boarding_10_min": station.get(
                "BUS_10WTHN_GTON_PPLTN_MAX"
            ),
            "alighting_10_min": station.get(
                "BUS_10WTHN_GTOFF_PPLTN_MAX"
            ),

            # 최근 5분
            "boarding_5_min": station.get(
                "BUS_5WTHN_GTON_PPLTN_MAX"
            ),
            "alighting_5_min": station.get(
                "BUS_5WTHN_GTOFF_PPLTN_MAX"
            ),
        })

    return results
