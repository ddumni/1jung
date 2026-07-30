#jemini 25-35 ver2
import streamlit as st
import pandas as pd
import requests
import plotly.express as px

# 1. 페이지 기본 설정 (와이드 모드)
st.set_page_config(
    page_title="전국 청년 인구 지도 (25~35세)",
    page_icon="🗺️",
    layout="wide"
)

st.title("🗺️ 전국 시군구별 청년 인구 비율 지도 (25~35세)")
st.markdown("읍·면·동별 인구 데이터를 시군구(코드 앞 5자리) 단위로 집계하여 25~35세 청년 비율을 단계구분도로 나타낸 지도입니다.")

# 2. 캐싱을 활용한 데이터 로딩 함수 (앱 속도 향상)
@st.cache_data
def load_data():
    # --- A. 인구 데이터 불러오기 ---
    pop_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    
    # '코드' 열은 5자리 자르기 및 매핑을 위해 문자열(str)로 지정하여 읽기
    df = pd.read_csv(pop_url, dtype={'코드': str})
    
    # 가장 최신 연도 데이터만 필터링
    latest_year = df['연도'].max()
    df_latest = df[df['연도'] == latest_year].copy()
    
    # 행정동 코드(10자리) 앞 5자리를 추출하여 '시군구코드' 열 생성
    df_latest['시군구코드'] = df_latest['코드'].str[:5]
    
    # --- B. 청년 인구 및 총인구 계산 ---
    # 25세~35세에 해당하는 '계_XX세' 열 이름 리스트 생성
    youth_cols = [f'계_{age}세' for age in range(25, 36)]
    
    # 전체 연령대('계_0세' ~ '계_100세 이상') 열 이름 리스트 생성
    total_cols = [f'계_{age}세' for age in range(0, 100)] + ['계_100세 이상']
    
    # 각 읍면동별 청년수 및 총인구 합계 계산
    df_latest['청년인구'] = df_latest[youth_cols].sum(axis=1)
    df_latest['총인구'] = df_latest[total_cols].sum(axis=1)
    
    # 시군구코드(5자리) 기준으로 그룹화하여 합산
    grouped = df_latest.groupby('시군구코드').agg({
        '시도': 'first',
        '시군구': 'first',
        '청년인구': 'sum',
        '총인구': 'sum'
    }).reset_index()
    
    # 청년 비율(%) 계산
    grouped['청년비율'] = (grouped['청년인구'] / grouped['총인구']) * 100
    grouped['청년비율'] = grouped['청년비율'].round(2)
    
    # --- C. GeoJSON 지도 경계 데이터 불러오기 ---
    geojson_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    geojson_data = requests.get(geojson_url).json()
    
    return latest_year, grouped, geojson_data

# 데이터 로드 실행
with st.spinner("데이터를 읽어오는 중입니다..."):
    latest_year, df_sigungu, geojson_kr = load_data()

st.caption(f"기준 연도: {latest_year}년")

# 3. 5단계 구간 나누기 및 색상 설정
# 구간: 미만 19%, 19~23%, 23~28%, 28~38%, 38% 이상
bins = [-float('inf'), 19, 23, 28, 38, float('inf')]
labels = ['19% 미만', '19% 이상 ~ 23% 미만', '23% 이상 ~ 28% 미만', '28% 이상 ~ 38% 미만', '38% 이상']

# 비율에 따라 범주형 열 생성 (순서 보장을 위해 Categorical 지정)
df_sigungu['구간'] = pd.cut(df_sigungu['청년비율'], bins=bins, labels=labels, right=False)
df_sigungu['구간'] = pd.Categorical(df_sigungu['구간'], categories=labels, ordered=True)

# 옅은 색(낮음) -> 진한 색(높음) 단계별 색상 매핑
color_map = {
    '19% 미만': '#edf8fb',
    '19% 이상 ~ 23% 미만': '#b2e2e2',
    '23% 이상 ~ 28% 미만': '#66c2a4',
    '28% 이상 ~ 38% 미만': '#2ca25f',
    '38% 이상': '#006d2c'
}

# 4. Plotly 지도 생성
fig = px.choropleth(
    df_sigungu,
    geojson=geojson_kr,
    locations='시군구코드',       # 데이터의 시군구코드
    featureidkey='properties.코드', # GeoJSON 내부 속성 '코드'
    color='구간',                 # 구간별 Discrete 색상 적용
    color_discrete_map=color_map, # 색상 직접 할당
    category_orders={'구간': labels}, # 범례 순서 정렬
    hover_name='시군구',          # 마우스 오버 시 상단에 표시될 이름
    hover_data={
        '시군구코드': False,      # 툴팁에서 코드 숨기기
        '시도': True,             # 시도 표시
        '청년비율': ':.2f%'       # 비율 표시
    },
    labels={'구간': '청년 비율 구간', '청년비율': '청년 비율'}
)

# 지도 스타일 및 레이아웃 조정 (배경 타일 없이 경계선만 표시)
fig.update_geos(
    fitbounds="locations",  # 데이터 위치에 맞게 지도 자동 확대
    visible=False           # 지리적 배경 요소(해안선, 타일 등) 숨김
)

fig.update_layout(
    margin={"r": 0, "t": 10, "l": 0, "b": 0},
    height=650,
    legend=dict(
        title="<b>청년 비율 (25~35세)</b>",
        yanchor="top",
        y=0.98,
        xanchor="left",
        x=0.02,
        bgcolor="rgba(255, 255, 255, 0.8)"
    )
)

# 스트림릿 화면에 지도 출력
st.plotly_chart(fig, use_container_width=True)

st.divider()

# 5. 하단 순위 표 (상위 10개, 하위 10개 나란히 배치)
st.subheader("📊 전국 시군구별 청년 비율 극단값 비교")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🔴 청년 비율 높은 곳 Top 10")
    top10 = df_sigungu.sort_values(by='청년비율', ascending=False).head(10)
    top10_display = top10[['시도', '시군구', '청년비율']].reset_index(drop=True)
    top10_display.columns = ['시도', '시군구', '청년 비율 (%)']
    st.dataframe(top10_display, use_container_width=True)

with col2:
    st.markdown("### 🔵 청년 비율 낮은 곳 Top 10")
    bottom10 = df_sigungu.sort_values(by='청년비율', ascending=True).head(10)
    bottom10_display = bottom10[['시도', '시군구', '청년비율']].reset_index(drop=True)
    bottom10_display.columns = ['시도', '시군구', '청년 비율 (%)']
    st.dataframe(bottom10_display, use_container_width=True)

st.divider()

# 6. 지역(시·도)별 청년 인구 세부 분석 표 추가
st.subheader("🏙️ 지역(시·도)별 시·군·구 청년 인구 분석")

# 시·도 목록 추출 및 셀렉트박스 생성
sido_list = sorted(df_sigungu['시도'].dropna().unique())
selected_sido = st.selectbox("분석할 지역(시·도)을 선택하세요:", sido_list)

# 선택된 시·도의 데이터만 필터링
sido_df = df_sigungu[df_sigungu['시도'] == selected_sido].copy()

if not sido_df.empty:
    # 해당 시·도 내 전체 청년 인구 및 총인구 계산
    total_sido_youth = sido_df['청년인구'].sum()
    total_sido_pop = sido_df['총인구'].sum()
    sido_youth_ratio = (total_sido_youth / total_sido_pop) * 100

    # 주요 지표(Metric) 카드 출력
    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric(label=f"{selected_sido} 전체 청년 인구", value=f"{total_sido_youth:,} 명")
    m_col2.metric(label=f"{selected_sido} 전체 인구", value=f"{total_sido_pop:,} 명")
    m_col3.metric(label=f"{selected_sido} 평균 청년 비율", value=f"{sido_youth_ratio:.2f} %")

    # 선택된 시·도 내부 청년 점유율(선택된 시·도 청년 중 해당 시군구가 차지하는 비중) 계산
    sido_df['시도 내 청년 점유율 (%)'] = (sido_df['청년인구'] / total_sido_youth) * 100
    sido_df['시도 내 청년 점유율 (%)'] = sido_df['시도 내 청년 점유율 (%)'].round(2)

    # 출력용 데이터프레임 정리 (청년 비율 높은 순으로 정렬)
    analysis_df = sido_df.sort_values(by='청년비율', ascending=False)[
        ['시군구', '청년인구', '총인구', '청년비율', '시도 내 청년 점유율 (%)']
    ].reset_index(drop=True)

    # 컬럼 이름 한국어로 변경
    analysis_df.columns = [
        '시·군·구', 
        '청년 인구수 (명)', 
        '총 인구수 (명)', 
        '청년 비율 (%)', 
        '시·도 내 청년 점유율 (%)'
    ]

    st.markdown(f"**[{selected_sido}] 하위 시·군·구별 청년 인구 현황** (청년 비율 높은 순)")
    
    # 테이블 출력 (숫자 포맷 지정)
    st.dataframe(
        analysis_df.style.format({
            '청년 인구수 (명)': '{:,}',
            '총 인구수 (명)': '{:,}',
            '청년 비율 (%)': '{:.2f}',
            '시·도 내 청년 점유율 (%)': '{:.2f}'
        }),
        use_container_width=True
    )
