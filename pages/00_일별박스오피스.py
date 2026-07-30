from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import altair as alt
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="박스오피스 대시보드", layout="wide")
st.title("🎬 어제의 박스오피스")

# 비밀 금고에서 인증키 꺼내기
KOBIS_KEY = st.secrets["KOBIS_KEY"]

# 한국 시간 기준 어제 날짜 구하기
yesterday_dt = datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=1)
target_dt = yesterday_dt.strftime("%Y%m%d")
st.caption(f"조회 기준일(어제): {yesterday_dt.strftime('%Y-%m-%d')}")

url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
res = requests.get(url, params={"key": KOBIS_KEY, "targetDt": target_dt}, timeout=10)

if res.status_code != 200:
    st.error(f"요청이 실패했습니다 (상태코드: {res.status_code})")
    st.stop()

data = res.json()

if "faultInfo" in data:
    st.error(
        "인증키가 올바르지 않습니다. 금고(Secrets)의 KOBIS_KEY를 확인해 주세요."
    )
    st.stop()

box_list = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])
if not box_list:
    st.warning("그날 자료가 없습니다. 날짜를 하루 더 앞으로 옮겨 보세요.")
    st.stop()

df = pd.DataFrame(box_list)

# 숫자로 타입 변환
for col in ["rank", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]:
    df[col] = pd.to_numeric(df[col])

# 원본 영화명을 보존하기 위한 컬럼 복사
df["raw_movieNm"] = df["movieNm"]

# 🏆 누적관객 100만 명 이상인 영화 이름 뒤에 트로피 이모지 추가
df["movieNm"] = df.apply(
    lambda row: f"{row['movieNm']} 🏆"
    if row["audiAcc"] >= 1000000
    else row["movieNm"],
    axis=1,
)

# 1위 영화 지표 카드 세 장
top = df.sort_values("rank").iloc[0]
c1, c2, c3 = st.columns(3)
c1.metric("어제 1위", top["movieNm"])
c2.metric("어제 관객수", f"{top['audiCnt']:,}명")
c3.metric("누적 관객", f"{top['audiAcc']:,}명")

# 표를 한국어 열 이름으로 정리
table = df[["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
table.columns = ["순위", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]
table = table.sort_values("순위").reset_index(drop=True)

st.subheader("📋 박스오피스 TOP 10")
st.dataframe(table, use_container_width=True)

# 📈 관객수 상위 5편 차트
st.subheader("📈 관객수 상위 5편")
top5 = table.sort_values("관객수", ascending=False).head(5)

max_audi = top5["관객수"].max()
top5["highlight"] = top5["관객수"].apply(
    lambda x: "1위" if x == max_audi else "기타"
)

chart = (
    alt.Chart(top5)
    .mark_bar()
    .encode(
        x=alt.X(
            "영화명:N",
            sort=top5["영화명"].tolist(),
            axis=alt.Axis(labelAngle=-25, title=None),
        ),
        y=alt.Y("관객수:Q", title="어제 관객수 (명)"),
        color=alt.Color(
            "highlight:N",
            scale=alt.Scale(
                domain=["1위", "기타"],
                range=["#FF4B4B", "#808080"],
            ),
            legend=None,
        ),
        tooltip=["영화명", "관객수", "누적관객"],
    )
    .properties(height=350)
)

st.altair_chart(chart, use_container_width=True)


# ---------------------------------------------------------
# 📉 추가 기능: 개봉일부터 어제까지 관람 인원수 추이 그래프
# ---------------------------------------------------------
st.divider()
st.subheader("📉 개봉일부터 어제까지 영화 관람 인원수 추이")

# Top 10 영화 목록 생성 (선택용)
movie_options = df["movieNm"].tolist()
default_movie = top["movieNm"]  # 기본값: 어제 1위 영화

selected_movie_display = st.selectbox(
    "추이를 확인할 영화를 선택하세요 (Top 10 기준 / 직접 검색 가능):",
    options=movie_options,
    index=movie_options.index(default_movie),
)

# 선택된 영화의 원본 정보 가져오기
selected_info = df[df["movieNm"] == selected_movie_display].iloc[0]
target_movie_cd = selected_info["movieCd"]
open_date_str = selected_info["openDt"]


# 개봉일부터 어제까지 일별 박스오피스 데이터를 가져오는 캐싱 함수
@st.cache_data(ttl=3600)
def fetch_movie_trend(api_key, movie_cd, open_dt_str, end_dt_str):
    try:
        start_d = datetime.strptime(open_dt_str, "%Y-%m-%d")
    except ValueError:
        start_d = datetime.strptime(open_dt_str, "%Y%m%d")

    end_d = datetime.strptime(end_dt_str, "%Y%m%d")

    # 개봉일이 어제보다 미래이거나 이상 데이터인 경우 방어 코드
    if start_d > end_d:
        start_d = end_d

    records = []
    curr_d = start_d

    # 개봉일부터 어제까지 날짜별 API 호출
    while curr_d <= end_d:
        dt_param = curr_d.strftime("%Y%m%d")
        api_url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

        try:
            r = requests.get(
                api_url,
                params={"key": api_key, "targetDt": dt_param},
                timeout=5,
            )
            if r.status_code == 200:
                res_json = r.json()
                daily_list = res_json.get("boxOfficeResult", {}).get(
                    "dailyBoxOfficeList", []
                )

                # 해당 날짜 박스오피스에서 선택된 영화 찾기
                for item in daily_list:
                    if item.get("movieCd") == movie_cd:
                        records.append({
                            "날짜": curr_d.strftime("%Y-%m-%d"),
                            "일별관객수": int(item.get("audiCnt", 0)),
                            "누적관객수": int(item.get("audiAcc", 0)),
                            "순위": int(item.get("rank", 0)),
                        })
                        break
        except Exception:
            pass

        curr_d += timedelta(days=1)

    return pd.DataFrame(records)


if open_date_str and open_date_str != " ":
    with st.spinner(f"'{selected_movie_display}'의 일별 관객 데이터를 불러오는 중..."):
        trend_df = fetch_movie_trend(
            KOBIS_KEY, target_movie_cd, open_date_str, target_dt
        )

    if not trend_df.empty:
        # 꺾은선 + 포인트 차트 작성
        line_chart = (
            alt.Chart(trend_df)
            .mark_line(point=True, color="#1F77B4", strokeWidth=3)
            .encode(
                x=alt.X("날짜:T", title="날짜", axis=alt.Axis(format="%m/%d")),
                y=alt.Y("일별관객수:Q", title="일별 관객수 (명)"),
                tooltip=[
                    alt.Tooltip("날짜:T", title="날짜", format="%Y-%m-%d"),
                    alt.Tooltip("일별관객수:Q", title="일별 관객수", format=","),
                    alt.Tooltip("누적관객수:Q", title="누적 관객수", format=","),
                    alt.Tooltip("순위:N", title="당일 순위"),
                ],
            )
            .properties(height=400)
        )

        st.altair_chart(line_chart, use_container_width=True)
    else:
        st.info("해당 기간 동안의 관람객 집계 데이터가 없습니다.")
else:
    st.warning("선택한 영화의 개봉일 정보가 없어 추이를 불러올 수 없습니다.")
