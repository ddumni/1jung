# claude ver.0
# -*- coding: utf-8 -*-
"""
전국 시군구별 고령화 지도 (Streamlit 앱)
=========================================
65세 이상 인구 비율(고령화율)을 시군구 단위로 지도에 색칠해서 보여주는 앱입니다.

사용하는 데이터
- 인구 데이터: 전국 읍·면·동 단위 연도별 인구 (2015~2026)
- 경계 데이터: 전국 시군구 255개의 경계선이 담긴 GeoJSON

지역을 지도와 연결할 때는 이름이 아니라 '코드'를 기준으로 맞춥니다.
(예: '남구'라는 이름은 여러 시도에 동시에 있어서 이름만으로는 어느 시군구인지 알 수 없기 때문입니다)
"""

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# ----------------------------------------------------------------------------
# 0. 화면 기본 설정
#    st.set_page_config()는 다른 st.xxx() 명령보다 항상 먼저 호출해야 합니다.
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="전국 고령화 지도",
    page_icon="🗺️",
    layout="wide",
)

# 데이터가 있는 주소 (원본 CSV.GZ / GeoJSON 파일)
POPULATION_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEOJSON_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"

# 고령화율(%)을 5단계로 나누는 경계값입니다.
# 전국 시군구를 실제로 다섯 덩어리로 나눈 값(19% · 23% · 28% · 38%)을 그대로 사용합니다.
# -inf, inf를 양 끝에 두면 "19% 미만"이나 "38% 이상"처럼 끝이 열린 구간도 자연스럽게 표현됩니다.
BIN_EDGES = [-np.inf, 19, 23, 28, 38, np.inf]
BIN_LABELS = ["19% 미만", "19% ~ 23%", "23% ~ 28%", "28% ~ 38%", "38% 이상"]

# 낮은 단계는 옅은 색, 높은 단계는 진한 색이 되도록 순서대로 색을 정해둡니다.
BIN_COLORS = {
    "19% 미만": "#fee5d9",
    "19% ~ 23%": "#fcae91",
    "23% ~ 28%": "#fb6a4a",
    "28% ~ 38%": "#de2d26",
    "38% 이상": "#a50f15",
}


# ----------------------------------------------------------------------------
# 1. 데이터 불러오기
#    @st.cache_data를 붙이면 한 번 내려받은 데이터는 저장해두고 재사용해서,
#    페이지를 다시 실행할 때마다 매번 인터넷에서 새로 받지 않아도 됩니다.
# ----------------------------------------------------------------------------
@st.cache_data(show_spinner="인구 데이터를 내려받는 중입니다...")
def load_population_data() -> pd.DataFrame:
    """읍·면·동 단위 연도별 인구 데이터를 CSV(gzip 압축)에서 불러옵니다."""

    df = pd.read_csv(
        POPULATION_URL,
        compression="gzip",
        # '코드'는 계산용 숫자가 아니라 지역을 구분하는 이름표이므로
        # 반드시 문자열(str)로 읽어야 앞자리가 사라지지 않습니다.
        dtype={"코드": str},
        # 이 앱에서는 남녀를 합친 '계_' 열만 사용하므로,
        # '남_'/'여_' 열은 아예 읽지 않도록 걸러서 속도를 높입니다.
        usecols=lambda col: not (col.startswith("남_") or col.startswith("여_")),
    )
    return df


@st.cache_data(show_spinner="지도 경계 데이터를 내려받는 중입니다...")
def load_geojson_data() -> dict:
    """전국 시군구 255개의 경계선이 담긴 GeoJSON 파일을 불러옵니다."""

    response = requests.get(GEOJSON_URL, timeout=30)
    response.raise_for_status()
    geojson_data = response.json()

    # 시군구 코드의 자료형을 문자열 5자리로 통일합니다.
    # (인구 데이터 쪽 코드와 자료형이 다르면 지도에서 매칭이 안 되고 지역이 하얗게 빌 수 있습니다)
    for feature in geojson_data["features"]:
        properties = feature["properties"]
        properties["코드"] = str(properties["코드"]).zfill(5)

    return geojson_data


# ----------------------------------------------------------------------------
# 2. 나이 열 이름에서 나이(숫자)를 뽑아내는 도우미 함수
#    열 이름은 '계_0세', '계_1세', ... , '계_100세 이상' 형식입니다.
# ----------------------------------------------------------------------------
def extract_age(column_name: str) -> int:
    """'계_0세' -> 0, '계_100세 이상' -> 100 처럼 열 이름에서 나이를 정수로 바꿔줍니다."""

    text = column_name.replace("계_", "")   # '0세' 또는 '100세 이상'
    text = text.replace("세 이상", "")       # '100세 이상' -> '100'
    text = text.replace("세", "")            # '0세' -> '0'
    return int(text)


# ----------------------------------------------------------------------------
# 3. 시군구별 고령화율 계산
# ----------------------------------------------------------------------------
def build_sigungu_table(population_df: pd.DataFrame, geojson_data: dict, year: int) -> pd.DataFrame:
    """선택한 연도의 시군구별 총인구·고령인구·고령화율 표를 만듭니다."""

    # 3-1. 해당 연도 데이터만 남깁니다.
    df_year = population_df[population_df["연도"] == year].copy()
    df_year = df_year.dropna(subset=["코드"])

    # 3-2. 행정동 코드(10자리) 앞 5자리를 잘라서 시군구 코드를 만듭니다.
    #      예: '1111051500' -> '11110' (서울 종로구)
    df_year["시군구코드"] = df_year["코드"].str[:5]

    # 3-3. '계_'로 시작하는 나이별 열(남녀 합계)만 골라냅니다.
    age_columns = [c for c in df_year.columns if c.startswith("계_")]
    old_age_columns = [c for c in age_columns if extract_age(c) >= 65]

    # 3-4. 읍·면·동 한 줄(row)마다 총인구, 65세 이상 인구를 더합니다.
    df_year["총인구"] = df_year[age_columns].sum(axis=1)
    df_year["고령인구"] = df_year[old_age_columns].sum(axis=1)

    # 3-5. 읍·면·동 인구를 시군구 코드 기준으로 합산합니다.
    population_by_sigungu = (
        df_year.groupby("시군구코드")[["총인구", "고령인구"]].sum().reset_index()
    )

    # 3-6. GeoJSON에 들어있는 시군구 목록(코드·이름·시도)을 표로 만듭니다.
    #      지도에 그려질 지역의 이름과 개수는 GeoJSON을 기준으로 삼습니다.
    sigungu_list = pd.DataFrame(
        [
            {
                "시군구코드": feature["properties"]["코드"],
                "시군구": feature["properties"]["시군구"],
                "시도": feature["properties"]["시도"],
            }
            for feature in geojson_data["features"]
        ]
    )

    # 3-7. '코드'를 기준으로 지도 목록과 인구 데이터를 합칩니다. (이름이 아니라 코드로 매칭!)
    merged = sigungu_list.merge(population_by_sigungu, on="시군구코드", how="left")
    merged["고령화율"] = merged["고령인구"] / merged["총인구"] * 100

    return merged


# ----------------------------------------------------------------------------
# 4. 데이터 준비
# ----------------------------------------------------------------------------
try:
    population_df = load_population_data()
    geojson_data = load_geojson_data()
except Exception as error:  # 인터넷 연결 문제 등으로 데이터를 못 받아오는 경우를 대비합니다.
    st.error(f"데이터를 불러오는 중 문제가 발생했습니다: {error}")
    st.stop()

# 데이터에 들어있는 가장 최신 연도를 사용합니다.
latest_year = int(population_df["연도"].max())

sigungu_df = build_sigungu_table(population_df, geojson_data, latest_year)

# 고령화율을 19% · 23% · 28% · 38% 기준으로 5단계 구간으로 나눕니다. (이어지는 그라데이션이 아니라 계단식 색칠)
sigungu_df["구간"] = pd.cut(
    sigungu_df["고령화율"], bins=BIN_EDGES, labels=BIN_LABELS, right=False
)


# ----------------------------------------------------------------------------
# 5. 제목
# ----------------------------------------------------------------------------
st.title("🗺️ 전국 시군구별 고령화 지도")
st.caption(f"{latest_year}년 기준 · 시군구별 65세 이상 인구 비율(고령화율)")


# ----------------------------------------------------------------------------
# 6. 단계구분도(Choropleth Map) 그리기
#    px.choropleth(지구본 스타일)는 배경 지도를 그릴 때 plot.ly 서버의 세계지도 파일을
#    추가로 내려받는데, 이 요청이 막혀 있으면 지도가 아예 안 그려질 수 있습니다.
#    반면 choropleth_mapbox + mapbox_style="white-bg"는 타일을 전혀 요청하지 않는
#    빈 배경을 쓰기 때문에 더 안전하게 "배경 지도 타일 없이 경계선만" 보여줄 수 있습니다.
# ----------------------------------------------------------------------------
fig = px.choropleth_mapbox(
    sigungu_df,
    geojson=geojson_data,
    locations="시군구코드",            # 우리 표에서 지역을 구분하는 열
    featureidkey="properties.코드",    # GeoJSON에서 지역을 구분하는 속성 (이름이 아니라 코드로 매칭!)
    color="구간",                      # 색은 연속값이 아니라 5단계 구간(범주형)으로 칠합니다.
    color_discrete_map=BIN_COLORS,
    category_orders={"구간": BIN_LABELS},
    custom_data=["시군구", "시도", "고령화율"],  # 마우스오버(hover)에 쓸 값들
    mapbox_style="white-bg",           # 배경 지도 타일 없이 흰 배경만 사용합니다.
    center={"lat": 36.2, "lon": 127.9},  # 대한민국이 가운데 오도록 위치를 지정합니다.
    zoom=6.2,
)

# 마우스를 올리면 시군구 이름 · 시도 · 고령화율(%)이 보이도록 설정합니다.
fig.update_traces(
    marker_line_width=0.6,
    marker_line_color="white",
    hovertemplate=(
        "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
        "고령화율: %{customdata[2]:.1f}%"
        "<extra></extra>"
    ),
)

fig.update_layout(
    legend_title_text="65세 이상 인구 비율",
    margin=dict(l=0, r=0, t=10, b=0),
    height=700,
)

st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------------------------
# 7. 고령화율 높은 지역 / 낮은 지역 TOP 10 표
# ----------------------------------------------------------------------------
st.subheader("고령화율 TOP 10")

# 인구 데이터가 없어 고령화율을 계산하지 못한 지역은 순위표에서 제외합니다.
ranked_df = sigungu_df.dropna(subset=["고령화율"]).copy()
ranked_df["고령화율(%)"] = ranked_df["고령화율"].round(1)

table_columns = ["시도", "시군구", "고령화율(%)"]

top10 = (
    ranked_df.sort_values("고령화율", ascending=False)
    .head(10)[table_columns]
    .reset_index(drop=True)
)
top10.index = top10.index + 1  # 1등부터 시작하도록 순위를 매깁니다.

bottom10 = (
    ranked_df.sort_values("고령화율", ascending=True)
    .head(10)[table_columns]
    .reset_index(drop=True)
)
bottom10.index = bottom10.index + 1

col_high, col_low = st.columns(2)

with col_high:
    st.markdown("**고령화율 높은 지역 10곳**")
    st.dataframe(top10, use_container_width=True)

with col_low:
    st.markdown("**고령화율 낮은 지역 10곳**")
    st.dataframe(bottom10, use_container_width=True)
