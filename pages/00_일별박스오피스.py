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
yesterday = datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=1)
target_dt = yesterday.strftime("%Y%m%d")
st.caption(f"조회 기준일(어제): {yesterday.strftime('%Y-%m-%d')}")

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

# 📈 관객수 상위 5편 차트 (Altair 활용)
st.subheader("📈 관객수 상위 5편")
top5 = table.sort_values("관객수", ascending=False).head(5)

# 1위 영화 강조용 색상 컬럼 추가
max_audi = top5["관객수"].max()
top5["highlight"] = top5["관객수"].apply(
    lambda x: "1위" if x == max_audi else "기타"
)

# Altair 바 차트 생성 (왼쪽부터 내림차순 정렬 & 1위만 튀는 색상 적용)
chart = (
    alt.Chart(top5)
    .mark_bar()
    .encode(
        x=alt.X(
            "영화명:N",
            sort=top5["영화명"].tolist(),  # 왼쪽부터 관객수 내림차순으로 x축 순서 고정
            axis=alt.Axis(labelAngle=-25, title=None),  # 라벨 각도 조정
        ),
        y=alt.Y("관객수:Q", title="어제 관객수 (명)"),
        color=alt.Color(
            "highlight:N",
            scale=alt.Scale(
                domain=["1위", "기타"],
                range=["#FF4B4B", "#808080"],  # 1위: 포인트 빨간색, 기타: 회색
            ),
            legend=None,  # 범례 숨김
        ),
        tooltip=["영화명", "관객수", "누적관객"],
    )
    .properties(height=400)
)

st.altair_chart(chart, use_container_width=True)
