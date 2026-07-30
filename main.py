#jemini ver3
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

st.title("🗺️ 전국 시군구별 청년 인구 비율 지도 및 연령별 분석 (25~35세)")
st.markdown("전국 읍·면·동 인구 데이터를 바탕으로 25~35세 청년 인구의 연령별 분포 및 지도·지역별 세부 현황을 분석합니다.")

# 2. 캐싱을 활용한 데이터 로딩 함수 (앱 속도 향상)
@st.cache_data
def load_data():
    # --- A. 인구 데이터 불러오기 ---
    pop_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    
    # '코드' 열은 문자열(str)로 지정하여 읽기
    df = pd.read_csv(pop_url, dtype={'코드': str})
    
    # 가장 최신 연도 데이터만 필터링
    latest_year = df['연도'].max()
    df_latest = df[df['연도'] == latest_year].copy()
    
    # 행정동 코드(10자리) 앞 5자리를 추출하여 '시군구코드' 열 생성
    df_latest['시군구코드'] = df_latest['코드'].str[:5]
    
    # --- B. 1살 간격 연령별 컬럼 정의 ---
    # 25세~35세 각 연령별 '계_XX세' 컬럼 목록
    age_cols = [f'계_{age}세' for age in range(25, 36)]
    
    # 전체 연령대('계_0세' ~ '계_100세 이상') 열 이름 리스트 생성
    total_cols = [f'계_{age}세' for age in range(0, 100)] + ['계_100세 이상']
    
    # 읍면동별 총 청년인구 및 총인구 계산
    df_latest['청년인구'] = df_latest[age_cols].sum(axis=1)
    df_latest['총인구'] = df_latest[total_cols].sum(axis=1)
    
    # --- C. 시군구 단위 집계 ---
    # 시군구별로 나이별 인구수 및 총인구 합산
    agg_dict = {col: 'sum' for col in age_cols}
    agg_dict.update({
        '시도': 'first',
        '시군구': 'first',
        '청년인구': 'sum',
        '총인구': 'sum'
    })
    
    df_sigungu = df_latest.groupby('시군구코드').agg(agg_dict).reset_index()
    
    # 시군구 단위 전체 청년 비율(%) 계산
    df_sigungu['청년비율'] = (df_sigungu['청년인구'] / df_sigungu['총인구']) * 100
    df_sigungu['청년비율'] = df_sigungu['청년비율'].round(2)
    
    # 시군구 단위 1살 간격 나이별 비율(%) 계산
    for age in range(25, 36):
        col_name = f'계_{age}세'
        df_sigungu[f'{age}세_비율'] = (df_sigungu[col_name] / df_sigungu['총인구']) * 100
        df_sigungu[f'{age}세_비율'] = df_sigungu[f'{age}세_비율'].round(2)
        
    # --- D. GeoJSON 지도 경계 데이터 불러오기 ---
    geojson_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    geojson_data = requests.get(geojson_url).json()
    
    return latest_year, df_latest, df_sigungu, geojson_data, age_cols

# 데이터 로드 실행
with st.spinner("데이터를 읽어오는 중입니다..."):
    latest_year, df_dong, df_sigungu, geojson_kr, age_cols = load_data()

st.caption(f"기준 연도: {latest_year}년")

# 3. 5단계 구간 나누기 및 색상 설정
bins = [-float('inf'), 19, 23, 28, 38, float('inf')]
labels = ['19% 미만', '19% 이상 ~ 23% 미만', '23% 이상 ~ 28% 미만', '28% 이상 ~ 38% 미만', '38% 이상']

df_sigungu['구간'] = pd.cut(df_sigungu['청년비율'], bins=bins, labels=labels, right=False)
df_sigungu['구간'] = pd.Categorical(df_sigungu['구간'], categories=labels, ordered=True)

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
        '청년비율': ':.2f%'       # 청년 전체 비율 표시
    },
    labels={'구간': '청년 비율 구간', '청년비율': '청년 비율'}
)

fig.update_geos(
    fitbounds="locations",  # 데이터 위치에 맞게 지도 자동 확대
    visible=False           # 지리적 배경 요소 숨김
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

# 6. 지역별 연령별(25~35세 1살 간격) 인원수 세부 분석 표
st.subheader("🏙️ 지역별 연령별(25~35세) 청년 인원수 분석")
st.markdown("시·도만 선택하면 **시·군·구별 표**가 출력되며, 특정 시·군·구를 선택하면 **읍·면·동별 표**로 세분화됩니다.")

# Step 1: 시·도 선택 (필수)
sido_list = sorted(df_dong['시도'].dropna().unique())
selected_sido = st.selectbox("1. 분석할 지역(시·도)을 선택하세요:", sido_list)

# 선택한 시·도의 데이터 필터링
sido_dong_df = df_dong[df_dong['시도'] == selected_sido].copy()

# Step 2: 시·군·구 선택 (선택 사항, 기본값은 전체)
sigungu_options = ["전체 (시·군·구별 보기)"] + sorted(sido_dong_df['시군구'].dropna().unique())
selected_sigungu = st.selectbox("2. 시·군·구를 선택하세요 (선택 사항):", sigungu_options)

# 나이별 컬럼 이름을 보기 좋게 변경하기 위한 매핑 사전
col_rename_map = {f'계_{age}세': f'{age}세 (명)' for age in range(25, 36)}
col_rename_map['청년인구'] = '25~35세 총 청년수 (명)'

# 조건에 따라 시·군·구 단위 또는 읍·면·동 단위 표 생성
if selected_sigungu == "전체 (시·군·구별 보기)":
    # --- A. 시·군·구 단위로 집계 ---
    sido_sigungu_df = df_sigungu[df_sigungu['시도'] == selected_sido].copy()
    
    display_cols = ['시군구'] + age_cols + ['청년인구']
    result_df = sido_sigungu_df[display_cols].copy()
    
    col_rename_map['시군구'] = '시·군·구'
    result_df = result_df.rename(columns=col_rename_map)
    
    # 총 청년 인원수 기준 내림차순 정렬
    result_df = result_df.sort_values(by='25~35세 총 청년수 (명)', ascending=False).reset_index(drop=True)
    
    st.markdown(f"**[{selected_sido}] 시·군·구별 25~35세 연령별 인원수**")

else:
    # --- B. 선택한 시·군·구 내 읍·면·동 단위로 집계 ---
    sigungu_df = sido_dong_df[sido_dong_df['시군구'] == selected_sigungu].copy()
    
    display_cols = ['동'] + age_cols + ['청년인구']
    result_df = sigungu_df[display_cols].copy()
    
    col_rename_map['동'] = '읍·면·동'
    result_df = result_df.rename(columns=col_rename_map)
    
    # 총 청년 인원수 기준 내림차순 정렬
    result_df = result_df.sort_values(by='25~35세 총 청년수 (명)', ascending=False).reset_index(drop=True)
    
    st.markdown(f"**[{selected_sido} {selected_sigungu}] 읍·면·동별 25~35세 연령별 인원수**")

# 표 출력 (숫자에 천 단위 쉼표 적용)
if not result_df.empty:
    first_col = result_df.columns[0]  # '시·군·구' 또는 '읍·면·동'
    format_dict = {col: '{:,}' for col in result_df.columns if col != first_col}
    st.dataframe(result_df.style.format(format_dict), use_container_width=True)
