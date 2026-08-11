import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  setOptions,
  importLibrary,
} from "@googlemaps/js-api-loader";

import "./App.css";

const SEOUL_CENTER = {
  lat: 37.5665,
  lng: 126.978,
};

function App() {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);

  const markersRef = useRef([]);
  const linesRef = useRef([]);

  const placesLibraryRef = useRef(null);
  const destinationSessionTokenRef = useRef(null);

  const [mapReady, setMapReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const [originQuery, setOriginQuery] = useState("");
  const [areaResults, setAreaResults] = useState([]);
  const [selectedArea, setSelectedArea] = useState(null);
  const [originLocation, setOriginLocation] = useState(null);
  const [showAreaResults, setShowAreaResults] = useState(false);
  const [originResolving, setOriginResolving] = useState(false);

  const [destinationQuery, setDestinationQuery] = useState("");
  const [destinationResults, setDestinationResults] = useState([]);
  const [selectedDestination, setSelectedDestination] = useState(null);
  const [showDestinationResults, setShowDestinationResults] =
    useState(false);

  const [selectedRouteIndex, setSelectedRouteIndex] = useState(0);

  // =========================================================
  // Google Maps 초기화
  // =========================================================

  useEffect(() => {
    const initMap = async () => {
      try {
        const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

        if (!apiKey) {
          throw new Error("Google Maps API Key가 없습니다.");
        }

        setOptions({
          key: apiKey,
          v: "weekly",
          libraries: [
            "marker",
            "geometry",
            "places",
            "geocoding",
          ],
        });

        const { Map } = await importLibrary("maps");

        await importLibrary("marker");
        await importLibrary("geometry");
        await importLibrary("geocoding");

        const places = await importLibrary("places");

        placesLibraryRef.current = places;

        destinationSessionTokenRef.current =
          new places.AutocompleteSessionToken();

        if (!mapRef.current) {
          return;
        }

        const map = new Map(mapRef.current, {
          center: SEOUL_CENTER,
          zoom: 12,
          mapId: "DEMO_MAP_ID",
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: true,
          zoomControl: true,
        });

        mapInstanceRef.current = map;
        setMapReady(true);
      } catch (err) {
        console.error("Google Maps 초기화 오류:", err);
        setError("지도를 불러오지 못했습니다.");
      }
    };

    initMap();
  }, []);

  // =========================================================
  // 출발지 검색
  // =========================================================

  useEffect(() => {
    const keyword = originQuery.trim();

    if (!keyword) {
      setAreaResults([]);
      setShowAreaResults(false);
      return;
    }

    if (
      selectedArea &&
      keyword === selectedArea.area_name
    ) {
      return;
    }

    const timer = setTimeout(async () => {
      try {
        // =====================================================
        // 121개 서울 주요 장소 로컬 JSON 검색
        // Netlify에서 /api/areas 백엔드에 의존하지 않도록
        // public/seoul_121_areas.json을 직접 사용한다.
        // =====================================================

        const response = await fetch(
          "/seoul_121_areas.json"
        );

        if (!response.ok) {
          throw new Error(
            `121장소 데이터 로드 오류: ${response.status}`
          );
        }

        const areas = await response.json();

        const normalizedKeyword =
          keyword.toLowerCase();

        const results = areas.filter((area) => {
          const areaName = String(
            area.area_name || ""
          ).toLowerCase();

          const englishName = String(
            area.english_name || ""
          ).toLowerCase();

          const category = String(
            area.category || ""
          ).toLowerCase();

          return (
            areaName.includes(normalizedKeyword) ||
            englishName.includes(normalizedKeyword) ||
            category.includes(normalizedKeyword)
          );
        });

        setAreaResults(results);
        setShowAreaResults(true);
      } catch (err) {
        console.error("121장소 검색 실패:", err);
        setAreaResults([]);
        setShowAreaResults(true);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [originQuery, selectedArea]);

  // =========================================================
  // 목적지 검색
  // =========================================================

  useEffect(() => {
    const keyword = destinationQuery.trim();

    if (!mapReady) {
      return;
    }

    if (!keyword) {
      setDestinationResults([]);
      setShowDestinationResults(false);
      return;
    }

    if (
      selectedDestination &&
      keyword === selectedDestination.name
    ) {
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const places = placesLibraryRef.current;

        if (!places) {
          return;
        }

        const {
          AutocompleteSuggestion,
          AutocompleteSessionToken,
        } = places;

        if (!destinationSessionTokenRef.current) {
          destinationSessionTokenRef.current =
            new AutocompleteSessionToken();
        }

        const request = {
          input: keyword,
          language: "ko",
          region: "kr",
          locationBias: {
            center: SEOUL_CENTER,
            radius: 50000,
          },
          sessionToken:
            destinationSessionTokenRef.current,
        };

        const { suggestions } =
          await AutocompleteSuggestion.fetchAutocompleteSuggestions(
            request
          );

        const results = (suggestions || [])
          .filter((item) => item.placePrediction)
          .slice(0, 7);

        setDestinationResults(results);
        setShowDestinationResults(true);
      } catch (err) {
        console.error("목적지 검색 실패:", err);
        setDestinationResults([]);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [
    destinationQuery,
    mapReady,
    selectedDestination,
  ]);

  // =========================================================
  // 지도 객체 삭제
  // =========================================================

  const clearMapObjects = () => {
    markersRef.current.forEach((marker) => {
      marker.map = null;
    });

    markersRef.current = [];

    linesRef.current.forEach((line) => {
      line.setMap(null);
    });

    linesRef.current = [];
  };

  // =========================================================
  // 마커
  // =========================================================

  const addMarker = async (
    map,
    position,
    title
  ) => {
    const { AdvancedMarkerElement } =
      await importLibrary("marker");

    const marker = new AdvancedMarkerElement({
      map,
      position,
      title,
    });

    markersRef.current.push(marker);

    return marker;
  };

  // =========================================================
  // 출발 / 도착 지도
  // =========================================================

  const drawSelectedLocations = async (
    origin,
    destination
  ) => {
    const map = mapInstanceRef.current;

    if (!map) {
      return;
    }

    clearMapObjects();

    const bounds =
      new window.google.maps.LatLngBounds();

    if (origin) {
      await addMarker(
        map,
        origin,
        "출발지"
      );

      bounds.extend(origin);
    }

    if (destination) {
      await addMarker(
        map,
        destination,
        "목적지"
      );

      bounds.extend(destination);
    }

    if (origin && destination) {
      map.fitBounds(bounds, 100);
    } else if (origin) {
      map.setCenter(origin);
      map.setZoom(15);
    } else if (destination) {
      map.setCenter(destination);
      map.setZoom(15);
    }
  };

  // =========================================================
  // 출발지 선택
  // =========================================================

  const handleAreaSelect = async (area) => {
    setSelectedArea(area);
    setOriginQuery(area.area_name);
    setAreaResults([]);
    setShowAreaResults(false);
    setResult(null);
    setSelectedRouteIndex(0);
    setError("");
    setOriginResolving(true);

    try {
      const { Geocoder } =
        await importLibrary("geocoding");

      const geocoder = new Geocoder();

      const response =
        await geocoder.geocode({
          address:
            `${area.area_name}, 서울특별시, 대한민국`,
          region: "kr",
        });

      if (
        !response.results ||
        response.results.length === 0
      ) {
        throw new Error(
          "선택한 출발지의 위치를 찾지 못했습니다."
        );
      }

      const location =
        response.results[0].geometry.location;

      const coordinates = {
        lat: location.lat(),
        lng: location.lng(),
      };

      setOriginLocation(coordinates);

      await drawSelectedLocations(
        coordinates,
        selectedDestination?.location || null
      );
    } catch (err) {
      console.error(
        "출발지 좌표 변환 실패:",
        err
      );

      setOriginLocation(null);

      setError(
        `${area.area_name}의 지도 위치를 찾지 못했습니다.`
      );
    } finally {
      setOriginResolving(false);
    }
  };

  // =========================================================
  // 목적지 선택
  // =========================================================

  const handleDestinationSelect = async (
    suggestion
  ) => {
    try {
      setError("");

      const prediction =
        suggestion.placePrediction;

      const place =
        prediction.toPlace();

      await place.fetchFields({
        fields: [
          "displayName",
          "formattedAddress",
          "location",
        ],
      });

      if (!place.location) {
        throw new Error(
          "목적지 좌표를 가져올 수 없습니다."
        );
      }

      const location = {
        lat: place.location.lat(),
        lng: place.location.lng(),
      };

      const destination = {
        name:
          place.displayName ||
          prediction.text.toString(),

        address:
          place.formattedAddress || "",

        location,
      };

      setSelectedDestination(destination);
      setDestinationQuery(destination.name);
      setDestinationResults([]);
      setShowDestinationResults(false);
      setResult(null);
      setSelectedRouteIndex(0);

      const {
        AutocompleteSessionToken,
      } = placesLibraryRef.current;

      destinationSessionTokenRef.current =
        new AutocompleteSessionToken();

      await drawSelectedLocations(
        originLocation,
        location
      );
    } catch (err) {
      console.error(
        "목적지 선택 실패:",
        err
      );

      setError(
        "목적지 정보를 가져오지 못했습니다."
      );
    }
  };

  // =========================================================
  // Polyline
  // =========================================================

  const decodePolyline = (encoded) => {
    if (!encoded) {
      return [];
    }

    try {
      return window.google.maps.geometry.encoding.decodePath(
        encoded
      );
    } catch (err) {
      console.error(
        "Polyline decode 실패:",
        err
      );

      return [];
    }
  };

  // =========================================================
  // 특정 경로 지도 표시
  // =========================================================

  const drawRouteOnMap = async (route) => {
    const map = mapInstanceRef.current;

    if (
      !map ||
      !originLocation ||
      !selectedDestination ||
      !route
    ) {
      return;
    }

    clearMapObjects();

    const { Polyline } =
      await importLibrary("maps");

    const destinationLocation =
      selectedDestination.location;

    // 출발지
    await addMarker(
      map,
      originLocation,
      `출발 · ${
        selectedArea?.area_name || "출발지"
      }`
    );

    // 추천 승차 지점
    const segments =
      Array.isArray(route.transit_segments)
        ? route.transit_segments
        : [];

    if (segments.length > 0) {
      const firstSegment = segments[0];

      const lat = Number(
        firstSegment.departure_lat
      );

      const lng = Number(
        firstSegment.departure_lng
      );

      if (
        Number.isFinite(lat) &&
        Number.isFinite(lng)
      ) {
        await addMarker(
          map,
          { lat, lng },
          `승차 · ${
            firstSegment.departure_stop ||
            firstSegment.line_name ||
            ""
          }`
        );
      }
    }

    // 목적지
    await addMarker(
      map,
      destinationLocation,
      `목적지 · ${selectedDestination.name}`
    );

    const transitPath =
      decodePolyline(
        route.encoded_polyline
      );

    if (transitPath.length > 0) {
      const transitLine =
        new Polyline({
          path: transitPath,
          strokeColor: "#4F46E5",
          strokeOpacity: 1,
          strokeWeight: 7,
        });

      transitLine.setMap(map);
      linesRef.current.push(transitLine);
    }

    const bounds =
      new window.google.maps.LatLngBounds();

    bounds.extend(originLocation);
    bounds.extend(destinationLocation);

    transitPath.forEach((point) => {
      bounds.extend(point);
    });

    map.fitBounds(bounds, 80);
  };

  // =========================================================
  // 추천 API
  // =========================================================

  const handleRecommend = async () => {
    if (!selectedArea) {
      setError(
        "출발지를 검색한 뒤 목록에서 선택해주세요."
      );
      return;
    }

    if (!originLocation) {
      setError(
        "출발지 위치를 확인하는 중입니다."
      );
      return;
    }

    if (!selectedDestination) {
      setError(
        "목적지를 검색한 뒤 목록에서 선택해주세요."
      );
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);
    setSelectedRouteIndex(0);

    try {
      const response = await fetch(
        "/api/recommend",
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json",
          },

          body: JSON.stringify({
            origin_lat:
              originLocation.lat,

            origin_lon:
              originLocation.lng,

            destination_lat:
              selectedDestination.location.lat,

            destination_lon:
              selectedDestination.location.lng,

            current_area_name:
              selectedArea.area_name,

            nearby_area_names: [],

            simulate_event: false,
          }),
        }
      );

      if (!response.ok) {
        const errorData =
          await response
            .json()
            .catch(() => null);

        throw new Error(
          errorData?.detail ||
          `서버 오류: ${response.status}`
        );
      }

      const data =
        await response.json();

      console.log(
        "CrowdExit API:",
        data
      );

      setResult(data);

      const recommended =
        data?.recommended_route ||
        data?.routes?.[0] ||
        null;

      if (recommended) {
        await drawRouteOnMap(
          recommended
        );
      }
    } catch (err) {
      console.error(err);

      setError(
        err.message ||
        "추천 정보를 불러오지 못했습니다."
      );
    } finally {
      setLoading(false);
    }
  };

  // =========================================================
  // 결과 데이터
  // =========================================================

  const routes =
    Array.isArray(result?.routes)
      ? result.routes
      : [];

  const recommendedRoute =
    result?.recommended_route ||
    routes[0] ||
    null;

  const selectedRoute =
    routes[selectedRouteIndex] ||
    recommendedRoute ||
    null;

  const selectedSegments =
    Array.isArray(
      selectedRoute?.transit_segments
    )
      ? selectedRoute.transit_segments
      : [];

  const recommendedSegments =
    Array.isArray(
      recommendedRoute?.transit_segments
    )
      ? recommendedRoute.transit_segments
      : [];

  const recommendedFirstSegment =
    recommendedSegments[0] ||
    null;

  // =========================================================
  // 경로 제목
  // =========================================================

  const getVehicleLabel = (segment) => {
    if (
      segment?.vehicle_type === "BUS"
    ) {
      return "버스";
    }

    if (
      segment?.vehicle_type === "SUBWAY"
    ) {
      return "지하철";
    }

    return segment?.vehicle_type ||
      "대중교통";
  };

  const getSegmentTitle = (segment) => {
    const vehicle =
      getVehicleLabel(segment);

    const line =
      segment?.line_name ||
      "노선";

    return `${vehicle} ${line}`;
  };

  const getRouteTitle = (route) => {
    const segments =
      Array.isArray(
        route?.transit_segments
      )
        ? route.transit_segments
        : [];

    if (segments.length === 0) {
      return "추천 대중교통 경로";
    }

    return segments
      .map(
        (segment) =>
          getSegmentTitle(segment)
      )
      .join(" → ");
  };

  // =========================================================
  // 후보 경로 클릭
  // =========================================================

  const handleRouteSelect = async (
    index
  ) => {
    const route = routes[index];

    if (!route) {
      return;
    }

    setSelectedRouteIndex(index);

    await drawRouteOnMap(route);
  };

  // =========================================================
  // Gemini 문구
  // =========================================================

  const getGeminiMessage = () => {
    if (!selectedRoute) {
      return "현재 선택된 경로를 분석하고 있습니다.";
    }

    // 후순위 경로에 별도의 AI 문구가 있으면 우선 사용
    if (
      selectedRoute.ai_recommendation
    ) {
      return selectedRoute.ai_recommendation;
    }

    // 1순위는 백엔드에서 생성한 Gemini 결과 사용
    if (
      selectedRouteIndex === 0 &&
      result?.ai_message
    ) {
      return result.ai_message;
    }

    // 후순위에는 1순위 Gemini 문구를 복사하지 않음
    const transfer =
      selectedRoute.transfer_count ?? 0;

    const duration =
      selectedRoute.duration_min != null
        ? Number(
            selectedRoute.duration_min
          ).toFixed(1)
        : "-";

    if (transfer === 0) {
      return `환승 없이 이동할 수 있는 경로로, 총 ${duration}분이 예상됩니다. 환승 부담을 줄이고 편하게 이동할 수 있는 경로입니다.`;
    }

    if (transfer === 1) {
      return `총 ${duration}분이 예상되며 환승은 ${transfer}회 필요합니다. 이동시간과 환승 부담을 균형 있게 고려할 수 있는 경로입니다.`;
    }

    return `총 ${duration}분이 예상되며 환승은 ${transfer}회 필요합니다. 이동시간은 단축할 수 있지만 환승이 많아 이동 과정이 다소 복잡할 수 있습니다.`;
  };

  // =========================================================
  // UI
  // =========================================================

  return (
    <div className="app">
      <div className="container">

        {/* =====================================================
            HEADER
        ===================================================== */}

        <header className="header">
          <div>
            <p className="eyebrow">
              SMART CROWD ROUTING
            </p>

            <h1>
              CrowdExit
            </h1>

            <p className="subtitle">
              행사 종료 후 혼잡을 피해
              더 빠르고 편한 귀가 경로를
              안내합니다.
            </p>
          </div>

          <div className="status-badge">
            LIVE
          </div>
        </header>

        {/* =====================================================
            SEARCH + MAP
        ===================================================== */}

        <section
          className="map-card"
          style={{
            position: "relative",
            overflow: "hidden",
            minHeight: "500px",
          }}
        >

          {/* 검색 패널 */}

          {result ? (
            <div
              className="map-search-panel"
              style={{
                position: "absolute",
                zIndex: 20,
                display: "flex",
                alignItems: "center",
                gap: "14px",
                padding: "12px 14px",
              }}
            >
              <div
                style={{
                  flex: 1,
                  minWidth: 0,
                  padding: "11px 15px",
                  borderRadius: "14px",
                  background: "#F7F8FC",
                }}
              >
                <span style={{ display: "block", marginBottom: "3px", color: "#98A2B3", fontSize: "10px", fontWeight: "700" }}>
                  출발
                </span>

                <strong style={{ display: "block", overflow: "hidden", color: "#182230", fontSize: "14px", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {selectedArea?.area_name || originQuery || "출발지"}
                </strong>
              </div>

              <div style={{ color: "#5865F2", fontSize: "22px", fontWeight: "900", flexShrink: 0 }}>
                →
              </div>

              <div
                style={{
                  flex: 1,
                  minWidth: 0,
                  padding: "11px 15px",
                  borderRadius: "14px",
                  background: "#F7F8FC",
                }}
              >
                <span style={{ display: "block", marginBottom: "3px", color: "#98A2B3", fontSize: "10px", fontWeight: "700" }}>
                  도착
                </span>

                <strong style={{ display: "block", overflow: "hidden", color: "#182230", fontSize: "14px", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {selectedDestination?.name || destinationQuery || "목적지"}
                </strong>
              </div>

              <button
                type="button"
                className="map-search-button"
                onClick={() => {
                  setResult(null);
                  setSelectedRouteIndex(0);
                  setError("");
                }}
                style={{ flexShrink: 0 }}
              >
                다시 검색
              </button>
            </div>
          ) : (
            <div
              className="map-search-panel"
              style={{ position: "absolute", zIndex: 20 }}
            >

              {/* 출발 */}

              <div
                className="map-location"
                style={{
                  position: "relative",
                }}
              >

                <span>
                  출발
                </span>

                <input
                  type="text"
                  value={originQuery}
                  placeholder="서울시 주요 장소 검색"
                  onChange={(e) => {
                    setOriginQuery(
                      e.target.value
                    );

                    setSelectedArea(null);
                    setOriginLocation(null);
                    setResult(null);
                  }}
                  onFocus={() => {
                    if (
                      areaResults.length > 0
                    ) {
                      setShowAreaResults(true);
                    }
                  }}
                  style={{
                    width: "100%",
                    border: "none",
                    outline: "none",
                    background: "transparent",
                    fontSize: "16px",
                    fontWeight: "700",
                    padding: "4px 0",
                  }}
                />

                {showAreaResults &&
                  originQuery.trim() && (
                    <div
                      style={{
                        position: "absolute",
                        top: "65px",
                        left: 0,
                        right: 0,
                        background: "#fff",
                        borderRadius: "14px",
                        boxShadow:
                          "0 12px 35px rgba(0,0,0,.18)",
                        zIndex: 9999,
                        padding: "8px",
                        maxHeight: "300px",
                        overflowY: "auto",
                      }}
                    >
                      {areaResults.length > 0 ? (
                        areaResults.map(
                          (area) => (
                            <button
                              key={
                                area.area_code
                              }
                              type="button"
                              onClick={() =>
                                handleAreaSelect(
                                  area
                                )
                              }
                              style={{
                                display: "flex",
                                width: "100%",
                                justifyContent:
                                  "space-between",
                                alignItems:
                                  "center",
                                border: "none",
                                background:
                                  "transparent",
                                cursor:
                                  "pointer",
                                textAlign:
                                  "left",
                                padding:
                                  "12px 14px",
                                borderRadius:
                                  "10px",
                              }}
                            >
                              <span
                                style={{
                                  fontWeight:
                                    "700",
                                }}
                              >
                                {
                                  area.area_name
                                }
                              </span>

                              <span
                                style={{
                                  fontSize:
                                    "12px",
                                  color:
                                    "#6B7280",
                                }}
                              >
                                {
                                  area.category
                                }
                              </span>
                            </button>
                          )
                        )
                      ) : (
                        <div
                          style={{
                            padding:
                              "16px",
                            color:
                              "#6B7280",
                          }}
                        >
                          지원하는 장소가
                          없습니다.
                        </div>
                      )}
                    </div>
                  )}

                {selectedArea &&
                  originLocation &&
                  !originResolving && (
                    <small
                      style={{
                        display: "block",
                        marginTop: "3px",
                        color: "#6366F1",
                        fontSize: "11px",
                      }}
                    >
                      {
                        selectedArea.category
                      }
                      {" · "}
                      {
                        selectedArea.area_code
                      }
                    </small>
                  )}

              </div>

              <div className="map-search-arrow">
                →
              </div>

              {/* 도착 */}

              <div
                className="map-location"
                style={{
                  position: "relative",
                }}
              >

                <span>
                  도착
                </span>

                <input
                  type="text"
                  value={
                    destinationQuery
                  }
                  placeholder="목적지를 검색하세요"
                  onChange={(e) => {
                    setDestinationQuery(
                      e.target.value
                    );

                    setSelectedDestination(
                      null
                    );

                    setResult(null);
                  }}
                  onFocus={() => {
                    if (
                      destinationResults.length >
                      0
                    ) {
                      setShowDestinationResults(
                        true
                      );
                    }
                  }}
                  style={{
                    width: "100%",
                    border: "none",
                    outline: "none",
                    background: "transparent",
                    fontSize: "16px",
                    fontWeight: "700",
                    padding: "4px 0",
                  }}
                />

                {showDestinationResults &&
                  destinationQuery.trim() && (
                    <div
                      style={{
                        position: "absolute",
                        top: "65px",
                        left: 0,
                        right: 0,
                        background: "#fff",
                        borderRadius: "14px",
                        boxShadow:
                          "0 12px 35px rgba(0,0,0,.18)",
                        zIndex: 9999,
                        padding: "8px",
                        maxHeight: "320px",
                        overflowY: "auto",
                      }}
                    >
                      {destinationResults.length >
                      0 ? (
                        destinationResults.map(
                          (
                            suggestion,
                            index
                          ) => {
                            const prediction =
                              suggestion.placePrediction;

                            return (
                              <button
                                key={
                                  prediction
                                    .placeId ||
                                  index
                                }
                                type="button"
                                onClick={() =>
                                  handleDestinationSelect(
                                    suggestion
                                  )
                                }
                                style={{
                                  display:
                                    "block",
                                  width:
                                    "100%",
                                  border:
                                    "none",
                                  background:
                                    "transparent",
                                  cursor:
                                    "pointer",
                                  textAlign:
                                    "left",
                                  padding:
                                    "12px 14px",
                                  borderRadius:
                                    "10px",
                                }}
                              >
                                <strong>
                                  {
                                    prediction
                                      .text
                                      .toString()
                                  }
                                </strong>
                              </button>
                            );
                          }
                        )
                      ) : (
                        <div
                          style={{
                            padding:
                              "16px",
                            color:
                              "#6B7280",
                          }}
                        >
                          검색 결과가
                          없습니다.
                        </div>
                      )}
                    </div>
                  )}

                {selectedDestination && (
                  <small
                    style={{
                      display: "block",
                      marginTop: "3px",
                      color: "#6366F1",
                      fontSize: "11px",
                      whiteSpace:
                        "nowrap",
                      overflow: "hidden",
                      textOverflow:
                        "ellipsis",
                    }}
                  >
                    {
                      selectedDestination.address
                    }
                  </small>
                )}

              </div>

              <button
                className="map-search-button"
                onClick={handleRecommend}
                disabled={
                  loading ||
                  !mapReady ||
                  !selectedArea ||
                  !originLocation ||
                  !selectedDestination
                }
              >
                {loading
                  ? "경로 분석 중..."
                  : "추천 경로 찾기"}
              </button>

            </div>
          )}

          {/* ===================================================
              검색 전
          =================================================== */}

          {!result && (
            <div
              style={{
                position: "absolute",
                inset: 0,
                zIndex: 2,
                display: "flex",
                alignItems:
                  "flex-end",
                justifyContent:
                  "center",
                paddingBottom: "45px",
                pointerEvents:
                  "none",
              }}
            >
              <div
                style={{
                  background:
                    "rgba(255,255,255,.94)",
                  borderRadius:
                    "18px",
                  padding:
                    "18px 26px",
                  boxShadow:
                    "0 10px 30px rgba(0,0,0,.12)",
                  textAlign: "center",
                }}
              >
                <strong
                  style={{
                    display: "block",
                    fontSize:
                      "15px",
                    marginBottom:
                      "5px",
                  }}
                >
                  행사 후 귀가 경로를
                  찾아보세요
                </strong>

                <span
                  style={{
                    color:
                      "#667085",
                    fontSize:
                      "13px",
                  }}
                >
                  출발지와 목적지를
                  선택하면 혼잡도를
                  고려해 추천합니다.
                </span>
              </div>
            </div>
          )}

          {/* ===================================================
              결과가 있을 때
          =================================================== */}

          {result && (
            <div
              style={{
                position: "absolute",
                top: "96px",
                left: 0,
                bottom: 0,
                width: "290px",
                zIndex: 5,
                padding: "12px",
                background: "rgba(255,255,255,.96)",
                borderRight: "1px solid #E5E7EB",
                boxShadow: "8px 0 24px rgba(20,34,66,.08)",
                overflowY: "auto",
              }}
            >
              {routes.map(
                (route, index) => {
                  const active = index === selectedRouteIndex;

                  return (
                    <button
                      key={route.route_id || index}
                      type="button"
                      onClick={() => handleRouteSelect(index)}
                      style={{
                        display: "block",
                        width: "100%",
                        marginBottom: "10px",
                        padding: "15px",
                        borderRadius: "16px",
                        border: active ? "2px solid #5865F2" : "1px solid #E5E7EB",
                        background: active ? "#F5F6FF" : "#FFFFFF",
                        cursor: "pointer",
                        textAlign: "left",
                        boxShadow: active ? "0 6px 18px rgba(88,101,242,.12)" : "none",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "9px" }}>
                        <span style={{ padding: "4px 8px", borderRadius: "999px", background: active ? "#E9EDFF" : "#F1F3F7", color: active ? "#5865F2" : "#667085", fontSize: "10px", fontWeight: "800" }}>
                          {index === 0 ? "추천" : `${index + 1}위`}
                        </span>

                        {index === 0 && (
                          <span style={{ fontSize: "9px", fontWeight: "800", color: "#fff", background: "#182230", padding: "4px 6px", borderRadius: "999px" }}>
                            BEST
                          </span>
                        )}
                      </div>

                      <strong style={{ display: "block", color: "#182230", fontSize: "14px", lineHeight: "1.45", marginBottom: "9px" }}>
                        {getRouteTitle(route)}
                      </strong>

                      <div style={{ display: "flex", gap: "10px", color: "#667085", fontSize: "10px" }}>
                        <span>
                          {route.duration_min != null
                            ? `${Number(route.duration_min).toFixed(1)}분`
                            : "-"}
                        </span>

                        <span>
                          환승 {route.transfer_count ?? 0}회
                        </span>

                        <span>
                          도보 {route.walking_min != null
                            ? `${Number(route.walking_min).toFixed(1)}분`
                            : "-"}
                        </span>
                      </div>
                    </button>
                  );
                }
              )}
            </div>
          )}

          {/* ===================================================
              지도
              결과가 생겨도 같은 mapRef DOM을 계속 유지한다.
          =================================================== */}

          <div
            ref={mapRef}
            className="google-map"
            style={{
              height: result ? "620px" : "500px",
            }}
          />

          {!mapReady && (
            <div className="map-loading">
              지도를 불러오는 중...
            </div>
          )}

        </section>

        {/* =====================================================
            ERROR
        ===================================================== */}

        {error && (
          <div className="error-card">
            {error}
          </div>
        )}

        {/* =====================================================
            선택된 경로 상세
        ===================================================== */}

        {result && selectedRoute && (
          <section
            className="route-detail-panel"
            style={{
              marginTop:
                "18px",
              marginLeft:
                "290px",
              padding:
                "28px",
              border:
                selectedRouteIndex === 0
                  ? "2px solid #5865F2"
                  : "1px solid #E5E7EB",
              borderRadius:
                "22px",
              background:
                "#FFFFFF",
              boxShadow:
                "0 12px 35px rgba(20,34,66,.08)",
            }}
          >

            {/* 제목 */}

            <div
              style={{
                display:
                  "flex",
                justifyContent:
                  "space-between",
                alignItems:
                  "flex-start",
                gap:
                  "20px",
                marginBottom:
                  "22px",
              }}
            >

              <div>

                <span
                  style={{
                    display:
                      "inline-flex",
                    padding:
                      "5px 9px",
                    borderRadius:
                      "999px",
                    background:
                      "#E9EDFF",
                    color:
                      "#5865F2",
                    fontSize:
                      "10px",
                    fontWeight:
                      "800",
                  }}
                >
                  {selectedRouteIndex === 0
                    ? "CrowdExit 추천 · 1위"
                    : `${selectedRouteIndex + 1}위 후보`}
                </span>

                <h2
                  style={{
                    margin:
                      "12px 0 0",
                    fontSize:
                      "25px",
                    lineHeight:
                      "1.4",
                    letterSpacing:
                      "-.7px",
                  }}
                >
                  {
                    getRouteTitle(
                      selectedRoute
                    )
                  }
                </h2>

              </div>

              <div
                style={{
                  flexShrink:
                    0,
                  padding:
                    "12px 18px",
                  borderRadius:
                    "14px",
                  background:
                    "#F0F2FF",
                  textAlign:
                    "center",
                }}
              >
                <span
                  style={{
                    display:
                      "block",
                    color:
                      "#8A94B8",
                    fontSize:
                      "10px",
                    fontWeight:
                      "700",
                  }}
                >
                  예상 시간
                </span>

                <strong
                  style={{
                    color:
                      "#5865F2",
                    fontSize:
                      "20px",
                  }}
                >
                  {selectedRoute.duration_min !=
                  null
                    ? `${Number(
                        selectedRoute.duration_min
                      ).toFixed(1)}분`
                    : "-"}
                </strong>
              </div>

            </div>

            {/* 기본 정보 */}

            <div
              style={{
                display:
                  "grid",
                gridTemplateColumns:
                  "repeat(4,1fr)",
                gap:
                  "10px",
                marginBottom:
                  "24px",
              }}
            >

              <div
                style={{
                  padding:
                    "13px",
                  borderRadius:
                    "14px",
                  background:
                    "#F7F8FC",
                }}
              >
                <span
                  style={{
                    display:
                      "block",
                    color:
                      "#98A2B3",
                    fontSize:
                      "10px",
                    marginBottom:
                      "4px",
                  }}
                >
                  전체 시간
                </span>

                <strong>
                  {selectedRoute.duration_min !=
                  null
                    ? `${Number(
                        selectedRoute.duration_min
                      ).toFixed(1)}분`
                    : "-"}
                </strong>
              </div>

              <div
                style={{
                  padding:
                    "13px",
                  borderRadius:
                    "14px",
                  background:
                    "#F7F8FC",
                }}
              >
                <span
                  style={{
                    display:
                      "block",
                    color:
                      "#98A2B3",
                    fontSize:
                      "10px",
                    marginBottom:
                      "4px",
                  }}
                >
                  도보
                </span>

                <strong>
                  {selectedRoute.walking_min !=
                  null
                    ? `${Number(
                        selectedRoute.walking_min
                      ).toFixed(1)}분`
                    : "-"}
                </strong>
              </div>

              <div
                style={{
                  padding:
                    "13px",
                  borderRadius:
                    "14px",
                  background:
                    "#F7F8FC",
                }}
              >
                <span
                  style={{
                    display:
                      "block",
                    color:
                      "#98A2B3",
                    fontSize:
                      "10px",
                    marginBottom:
                      "4px",
                  }}
                >
                  환승
                </span>

                <strong>
                  {
                    selectedRoute.transfer_count ??
                    0
                  }
                  회
                </strong>
              </div>

              <div
                style={{
                  padding:
                    "13px",
                  borderRadius:
                    "14px",
                  background:
                    "#F7F8FC",
                }}
              >
                <span
                  style={{
                    display:
                      "block",
                    color:
                      "#98A2B3",
                    fontSize:
                      "10px",
                    marginBottom:
                      "4px",
                  }}
                >
                  정류장
                </span>

                <strong>
                  {
                    selectedRoute.stop_count ??
                    0
                  }
                  개
                </strong>
              </div>

            </div>

            {/* 상세 경로 */}

            <h3
              style={{
                margin:
                  "0 0 12px",
                fontSize:
                  "16px",
              }}
            >
              상세 경로
            </h3>

            <div
              style={{
                display:
                  "flex",
                flexDirection:
                  "column",
                gap:
                  "10px",
              }}
            >

              {selectedSegments.map(
                (
                  segment,
                  index
                ) => (
                  <div
                    key={`${segment.line_name}-${index}`}
                    style={{
                      padding:
                        "16px",
                      borderRadius:
                        "15px",
                      background:
                        "#F7F8FC",
                    }}
                  >

                    <div
                      style={{
                        display:
                          "flex",
                        alignItems:
                          "center",
                        gap:
                          "9px",
                        marginBottom:
                          "8px",
                      }}
                    >

                      <strong
                        style={{
                          color:
                            "#5865F2",
                          fontSize:
                            "15px",
                        }}
                      >
                        {
                          getVehicleLabel(
                            segment
                          )
                        }
                      </strong>

                      <strong
                        style={{
                          fontSize:
                            "16px",
                        }}
                      >
                        {
                          segment.line_name ||
                          "노선"
                        }
                      </strong>

                    </div>

                    <div
                      style={{
                        color:
                          "#374151",
                        fontSize:
                          "13px",
                        lineHeight:
                          "1.7",
                      }}
                    >

                      <div>
                        {
                          segment.departure_stop ||
                          "-"
                        }

                        <span
                          style={{
                            margin:
                              "0 8px",
                            color:
                              "#9CA3AF",
                          }}
                        >
                          →
                        </span>

                        {
                          segment.arrival_stop ||
                          "-"
                        }
                      </div>

                      {segment.headsign && (
                        <div
                          style={{
                            marginTop:
                              "3px",
                            color:
                              "#6B7280",
                          }}
                        >
                          방면 ·{" "}
                          {
                            segment.headsign
                          }
                        </div>
                      )}

                      {segment.stop_count !=
                        null && (
                        <div
                          style={{
                            marginTop:
                              "3px",
                            color:
                              "#6B7280",
                          }}
                        >
                          {
                            segment.stop_count
                          }
                          개 정류장
                        </div>
                      )}

                    </div>

                  </div>
                )
              )}

            </div>

            {/* =================================================
                1순위만 추천 이유
            ================================================= */}

            {selectedRouteIndex === 0 &&
              selectedRoute.recommendation && (
                <div
                  style={{
                    marginTop:
                      "16px",
                    padding:
                      "17px",
                    borderRadius:
                      "15px",
                    background:
                      "#F7F8FC",
                  }}
                >
                  <strong
                    style={{
                      display:
                        "block",
                      marginBottom:
                        "7px",
                      fontSize:
                        "13px",
                    }}
                  >
                    추천 이유
                  </strong>

                  <p
                    style={{
                      margin:
                        0,
                      color:
                        "#4B5563",
                      lineHeight:
                        "1.7",
                      fontSize:
                        "13px",
                    }}
                  >
                    {
                      selectedRoute.recommendation
                    }
                  </p>
                </div>
              )}

            {/* =================================================
                Gemini
            ================================================= */}

            <div
              style={{
                marginTop:
                  "16px",
                padding:
                  "20px",
                borderRadius:
                  "17px",
                background:
                  "#182230",
                color:
                  "#FFFFFF",
              }}
            >

              <div
                style={{
                  marginBottom:
                    "9px",
                  color:
                    "#B7C0FF",
                  fontSize:
                    "12px",
                  fontWeight:
                    "800",
                }}
              >
                ✨ Gemini AI 안내
              </div>

              <p
                style={{
                  margin:
                    0,
                  lineHeight:
                    "1.75",
                  wordBreak:
                    "keep-all",
                  fontSize:
                    "13px",
                }}
              >
                {
                  getGeminiMessage()
                }
              </p>

            </div>

          </section>
        )}

      </div>
    </div>
  );
}

export default App;