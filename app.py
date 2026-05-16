# =====================================================
# 실전형 AI 투자 플랫폼
# AI 위험도 분석 + 포트폴리오 AI 평가 완전 통합본
# =====================================================

import streamlit as st
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import feedparser
import sqlite3

# =====================================================
# 페이지 설정
# =====================================================
st.set_page_config(
    page_title="실전형 AI 투자 플랫폼",
    layout="wide"
)

# =====================================================
# 스타일
# =====================================================
st.markdown("""

<style>

.block-container{
    padding-top:2rem;
    padding-left:3rem;
    padding-right:3rem;
}

div[data-testid="stMetric"]{
    background:#f8fafc;
    padding:20px;
    border-radius:16px;
    border:1px solid #e2e8f0;
}

</style>

""", unsafe_allow_html=True)

# =====================================================
# 세션 상태
# =====================================================
if "portfolio" not in st.session_state:
    st.session_state.portfolio = []

if "selected_stock" not in st.session_state:
    st.session_state.selected_stock = "005930"

if "search_stock" not in st.session_state:
    st.session_state.search_stock = "005930"



# =====================================================
# SQLite 설정
# =====================================================
DB_NAME = "stock_data.db"

def get_connection():

    return sqlite3.connect(DB_NAME)

def init_database():

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_prices (

            stock_code TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,

            PRIMARY KEY(stock_code, date)

        )
        """
    )

    conn.commit()
    conn.close()

init_database()

# =====================================================
# SQLite 저장
# =====================================================
def save_stock_data(stock_code, df):

    if df.empty:
        return

    conn = get_connection()

    cursor = conn.cursor()

    for idx, row in df.iterrows():

        try:

            cursor.execute(
                """
                INSERT OR REPLACE INTO stock_prices
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stock_code,
                    idx.strftime("%Y-%m-%d"),
                    float(row['시가']),
                    float(row['고가']),
                    float(row['저가']),
                    float(row['종가']),
                    float(row['거래량'])
                )
            )

        except:
            pass

    conn.commit()
    conn.close()

# =====================================================
# SQLite 조회
# =====================================================
@st.cache_data(ttl=600)
def load_stock_data_from_db(stock_code):

    conn = get_connection()

    query = f"""
    SELECT *
    FROM stock_prices
    WHERE stock_code = '{stock_code}'
    ORDER BY date
    """

    df = pd.read_sql(query, conn)

    conn.close()

    if df.empty:
        return pd.DataFrame()

    df['date'] = pd.to_datetime(df['date'])

    df = df.set_index('date')

    df.columns = [
        '종목코드',
        '시가',
        '고가',
        '저가',
        '종가',
        '거래량'
    ]

    return df

# =====================================================
# SQLite 기반 데이터 엔진
# =====================================================
@st.cache_data(ttl=1800)
def download_stock_data(start_date, end_date, stock_code):

    return stock.get_market_ohlcv_by_date(

        start_date.strftime("%Y%m%d"),
        end_date.strftime("%Y%m%d"),
        stock_code

    )

def get_stock_data(start_date, end_date, stock_code):

    db_df = load_stock_data_from_db(stock_code)

    if len(db_df) > 50:

        filtered = db_df[
            (db_df.index >= pd.to_datetime(start_date))
            &
            (db_df.index <= pd.to_datetime(end_date))
        ]

        if len(filtered) > 30:
            return filtered

    new_df = download_stock_data(
        start_date,
        end_date,
        stock_code
    )

    if not new_df.empty:

        save_stock_data(
            stock_code,
            new_df
        )

    return new_df


# =====================================================
# RSI 계산
# =====================================================
def calculate_rsi(data, period=14):

    delta = data.diff()

    gain = delta.where(delta > 0, 0)

    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(period).mean()

    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi

# =====================================================
# 시장 상태 분석
# =====================================================
def analyze_market():

    try:

        today = datetime.today()

        start_day = today - timedelta(days=365)

        df = stock.get_market_ohlcv_by_date(

            start_day.strftime("%Y%m%d"),
            today.strftime("%Y%m%d"),
            "005930"

        )

        current_price = df['종가'].iloc[-1]

        ma20 = df['종가'].rolling(20).mean().iloc[-1]

        ma60 = df['종가'].rolling(60).mean().iloc[-1]

        rsi = calculate_rsi(df['종가']).iloc[-1]

        if current_price > ma20 and ma20 > ma60:

            return {

                "market":"상승 추세",
                "strategy":"추세추종 전략",
                "risk":"보통"

            }

        elif rsi <= 40:

            return {

                "market":"반등 가능",
                "strategy":"RSI 반등 전략",
                "risk":"주의"

            }

        else:

            return {

                "market":"횡보 / 약세",
                "strategy":"관망 전략",
                "risk":"높음"

            }

    except:

        return {

            "market":"분석 실패",
            "strategy":"확인 불가",
            "risk":"확인 불가"

        }



# =====================================================
# 수급 데이터 분석
# =====================================================

def analyze_supply(stock_code):

    try:

        today = datetime.today()

        start_day = today - timedelta(days=30)

        investor_df = stock.get_market_trading_value_by_date(

            start_day.strftime("%Y%m%d"),
            today.strftime("%Y%m%d"),
            stock_code

        )

        foreign_col = None
        institute_col = None

        for col in investor_df.columns:

            if "외국인" in str(col):

                foreign_col = col

            if "기관" in str(col):

                institute_col = col

        foreign_buy = 0
        institute_buy = 0


        if foreign_col is not None:

            investor_df[foreign_col] = pd.to_numeric(
                investor_df[foreign_col],
                errors="coerce"
            ).fillna(0)

            foreign_buy = (
                investor_df[foreign_col]
                .tail(5)
                .sum()
            )

        if institute_col is not None:

            investor_df[institute_col] = pd.to_numeric(
                investor_df[institute_col],
                errors="coerce"
            ).fillna(0)

            institute_buy = (
                investor_df[institute_col]
                .tail(5)
                .sum()
            )


        supply_score = 0

        supply_reason = []

        if foreign_buy > 0:

            supply_score += 15
            supply_reason.append("외국인 순매수 유입")

        else:

            supply_score -= 10
            supply_reason.append("외국인 순매도")

        if institute_buy > 0:

            supply_score += 15
            supply_reason.append("기관 순매수 유입")

        else:

            supply_score -= 10
            supply_reason.append("기관 순매도")

        return {

            "외국인": int(foreign_buy),
            "기관": int(institute_buy),
            "수급점수": supply_score,
            "수급근거": supply_reason

        }

    except Exception as e:

        return {

            "외국인": 0,
            "기관": 0,
            "수급점수": 0,
            "수급근거": [f"수급 분석 실패: {e}"]

        }





# =====================================================
# 금액 단위 변환
# =====================================================
def format_korean_money(value):

    try:

        abs_value = abs(value)

        if abs_value >= 100000000:

            return f"{value / 100000000:.1f}억원"

        elif abs_value >= 10000:

            return f"{value / 10000:.1f}만원"

        else:

            return f"{value:,.0f}원"

    except:

        return str(value)


# =====================================================
# AI 점수 계산
# =====================================================
def calculate_ai_score(df, stock_code=None):

    try:

        market_result = analyze_market()

        current_price = df['종가'].iloc[-1]

        ma20 = df['종가'].rolling(20).mean().iloc[-1]

        ma60 = df['종가'].rolling(60).mean().iloc[-1]

        rsi = calculate_rsi(df['종가']).iloc[-1]

        ema12 = df['종가'].ewm(
            span=12,
            adjust=False
        ).mean()

        ema26 = df['종가'].ewm(
            span=26,
            adjust=False
        ).mean()

        macd = ema12 - ema26

        signal = macd.ewm(
            span=9,
            adjust=False
        ).mean()

        volume_avg = (
            df['거래량']
            .rolling(20)
            .mean()
            .iloc[-1]
        )

        volume_ratio = 1

        if volume_avg != 0:

            volume_ratio = (

                df['거래량'].iloc[-1]
                /
                volume_avg

            )

        score = 50

        trend_up = (
            current_price > ma20
            and
            ma20 > ma60
        )

        if trend_up:
            score += 20

        if market_result['market'] == "상승 추세":
            score += 10

        elif market_result['market'] == "횡보 / 약세":
            score -= 10

        if macd.iloc[-1] > signal.iloc[-1]:
            score += 15

        if rsi <= 40 and trend_up:
            score += 15

        elif rsi >= 75:
            score -= 15

        if volume_ratio >= 2:
            score += 20

        elif volume_ratio >= 1.5:
            score += 10

        recent_volatility = (

            (
                df['고가'].tail(5).max()
                -
                df['저가'].tail(5).min()
            )
            /
            current_price

        ) * 100

        if recent_volatility >= 15:
            score -= 15

        elif recent_volatility >= 10:
            score -= 8



        # 수급 점수 반영
        if stock_code is not None:

            supply_result = analyze_supply(stock_code)

            score += supply_result['수급점수']

        score = max(0, min(100, score))


        return int(score)

    except:

        return 50

# =====================================================
# AI 위험도 분석
# =====================================================
def analyze_risk(df):

    risk_list = []

    risk_score = 0

    try:

        current_price = df['종가'].iloc[-1]

        rsi = calculate_rsi(df['종가']).iloc[-1]

        volume_avg = (
            df['거래량']
            .rolling(20)
            .mean()
            .iloc[-1]
        )

        volume_ratio = 1

        if volume_avg != 0:

            volume_ratio = (
                df['거래량'].iloc[-1]
                /
                volume_avg
            )

        recent_volatility = (

            (
                df['고가'].tail(5).max()
                -
                df['저가'].tail(5).min()
            )
            /
            current_price

        ) * 100

        if rsi >= 75:

            risk_list.append("RSI 과매수 상태")
            risk_score += 30

        if volume_ratio >= 2:

            risk_list.append("거래량 과열")
            risk_score += 25

        if recent_volatility >= 15:

            risk_list.append("변동성 매우 높음")
            risk_score += 35

        elif recent_volatility >= 10:

            risk_list.append("변동성 주의")
            risk_score += 20

        recent_return = (

            (
                current_price
                -
                df['종가'].iloc[-5]
            )
            /
            df['종가'].iloc[-5]

        ) * 100

        if recent_return >= 15:

            risk_list.append("단기 급등 상태")
            risk_score += 30

        if len(risk_list) == 0:

            risk_list.append("리스크 낮음")

        risk_score = min(100, risk_score)

        return risk_list, risk_score

    except:

        return ["분석 불가"], 0

# =====================================================
# 포트폴리오 AI 평가
# =====================================================
def portfolio_ai_analysis(portfolio_df):

    try:

        if len(portfolio_df) == 0:

            return {

                "style":"분석 불가",
                "risk":"데이터 없음",
                "comment":"포트폴리오 없음"

            }

        max_weight = (
            portfolio_df['평가금액'].max()
            /
            portfolio_df['평가금액'].sum()
        ) * 100

        avg_return = portfolio_df['수익률'].mean()

        if max_weight >= 50:

            style = "공격형 포트폴리오"
            risk = "집중 투자 위험"
            comment = "특정 종목 비중이 높습니다."

        elif avg_return >= 10:

            style = "성장형 포트폴리오"
            risk = "중간 위험"
            comment = "수익률 흐름이 양호합니다."

        else:

            style = "안정형 포트폴리오"
            risk = "낮음"
            comment = "분산 투자 성향입니다."

        return {

            "style":style,
            "risk":risk,
            "comment":comment

        }

    except:

        return {

            "style":"분석 실패",
            "risk":"확인 불가",
            "comment":"데이터 부족"

        }




# =====================================================
# 고급 백테스트 엔진
# =====================================================
def backtest_strategy(df):

    try:

        returns = []

        capital = 1000000
        capital_history = [capital]

        for i in range(60, len(df) - 10):

            sample_df = df.iloc[:i]

            ai_score = calculate_ai_score(sample_df)

            if ai_score >= 85:

                buy_price = df['종가'].iloc[i]

                future_prices = df['종가'].iloc[i:i+10]

                sell_price = future_prices.iloc[-1]

                for price in future_prices:

                    change_rate = (
                        (price - buy_price)
                        / buy_price
                    ) * 100

                    # 익절
                    if change_rate >= 10:

                        sell_price = price
                        break

                    # 손절
                    elif change_rate <= -5:

                        sell_price = price
                        break

                profit_rate = (
                    (sell_price - buy_price)
                    / buy_price
                ) * 100

                returns.append(profit_rate)

                capital *= (1 + profit_rate / 100)

                capital_history.append(capital)

        if len(returns) == 0:

            return {

                "승률": 0,
                "평균수익률": 0,
                "최대수익": 0,
                "최대손실": 0,
                "거래횟수": 0,
                "MDD": 0,
                "최종자산": 0

            }

        peak = capital_history[0]

        mdd = 0

        for value in capital_history:

            if value > peak:
                peak = value

            drawdown = (
                (peak - value)
                / peak
            ) * 100

            if drawdown > mdd:
                mdd = drawdown

        win_rate = (
            len([r for r in returns if r > 0])
            / len(returns)
        ) * 100

        return {

            "승률": round(win_rate, 2),
            "평균수익률": round(sum(returns) / len(returns), 2),
            "최대수익": round(max(returns), 2),
            "최대손실": round(min(returns), 2),
            "거래횟수": len(returns),
            "MDD": round(mdd, 2),
            "최종자산": int(capital),
            "시작일": df.index[0].strftime("%Y-%m-%d"),
            "종료일": df.index[-1].strftime("%Y-%m-%d"),
            "백테스트기간": round(
                (df.index[-1] - df.index[0]).days / 365,
                1
            )

        }

    except:

        return {

            "승률": 0,
            "평균수익률": 0,
            "최대수익": 0,
            "최대손실": 0,
            "거래횟수": 0,
            "MDD": 0,
            "최종자산": 0

        }


# =====================================================
# AI 추천 근거
# =====================================================
def get_ai_reason(df):

    reason_list = []

    try:

        current_price = df['종가'].iloc[-1]

        ma20 = df['종가'].rolling(20).mean().iloc[-1]

        ma60 = df['종가'].rolling(60).mean().iloc[-1]

        rsi = calculate_rsi(df['종가']).iloc[-1]

        ema12 = df['종가'].ewm(span=12, adjust=False).mean()

        ema26 = df['종가'].ewm(span=26, adjust=False).mean()

        macd = ema12 - ema26

        signal = macd.ewm(span=9, adjust=False).mean()

        volume_avg = (
            df['거래량']
            .rolling(20)
            .mean()
            .iloc[-1]
        )

        volume_ratio = 1

        if volume_avg != 0:

            volume_ratio = (
                df['거래량'].iloc[-1]
                /
                volume_avg
            )

        if current_price > ma20:
            reason_list.append("20일 이평선 상단")

        if current_price > ma60:
            reason_list.append("장기 상승 추세")

        if macd.iloc[-1] > signal.iloc[-1]:
            reason_list.append("MACD 상승 흐름")

        if rsi <= 40:
            reason_list.append("RSI 관심구간")

        if volume_ratio >= 2:
            reason_list.append("거래량 급증")

        elif volume_ratio >= 1.5:
            reason_list.append("거래량 증가")

        if len(reason_list) == 0:
            reason_list.append("관망 구간")

    except:

        reason_list.append("데이터 부족")

    return reason_list

# =====================================================
# 전략 추천
# =====================================================
def recommend_strategy(df):

    try:

        current_price = df['종가'].iloc[-1]

        ma20 = df['종가'].rolling(20).mean().iloc[-1]

        ma60 = df['종가'].rolling(60).mean().iloc[-1]

        rsi = calculate_rsi(df['종가']).iloc[-1]

        ema12 = df['종가'].ewm(span=12, adjust=False).mean()

        ema26 = df['종가'].ewm(span=26, adjust=False).mean()

        macd = ema12 - ema26

        signal = macd.ewm(span=9, adjust=False).mean()

        if rsi <= 40 and current_price > ma20:

            return "RSI 반등 전략"

        elif current_price > ma20 and ma20 > ma60:

            return "추세추종 전략"

        elif macd.iloc[-1] > signal.iloc[-1]:

            return "MACD 상승 전략"

        else:

            return "관망 전략"

    except:

        return "분석 불가"



# =====================================================
# 전략 추천 근거
# =====================================================
def get_strategy_reason(df):

    reasons = []

    try:

        current_price = df['종가'].iloc[-1]

        ma20 = df['종가'].rolling(20).mean().iloc[-1]

        ma60 = df['종가'].rolling(60).mean().iloc[-1]

        rsi = calculate_rsi(df['종가']).iloc[-1]

        ema12 = df['종가'].ewm(span=12, adjust=False).mean()

        ema26 = df['종가'].ewm(span=26, adjust=False).mean()

        macd = ema12 - ema26

        signal = macd.ewm(span=9, adjust=False).mean()

        if current_price > ma20:

            reasons.append("20일선 상향 돌파")

        if ma20 > ma60:

            reasons.append("장기 상승 추세")

        if macd.iloc[-1] > signal.iloc[-1]:

            reasons.append("MACD 상승 흐름")

        if rsi <= 40:

            reasons.append("RSI 관심구간")

        if len(reasons) == 0:

            reasons.append("관망 구간")

    except:

        reasons.append("전략 분석 실패")

    return reasons


# =====================================================
# 뉴스
# =====================================================
def get_stock_news(stock_name):

    news_list = []

    try:

        url = f"https://news.google.com/rss/search?q={stock_name}+주식&hl=ko&gl=KR&ceid=KR:ko"

        feed = feedparser.parse(url)

        for entry in feed.entries[:5]:

            news_list.append({

                "title": entry.title,
                "link": entry.link

            })

    except:

        pass

    return news_list

# =====================================================
# AI 추천 종목
# =====================================================
def get_ai_recommend_stocks():

    result = []

    today = datetime.today()

    start_day = today - timedelta(days=180)

    tickers = [

        "005930",
        "000660",
        "035420",
        "005380",
        "051910",
        "068270",
        "207940",
        "035720"

    ]

    for code in tickers:

        try:

            df = stock.get_market_ohlcv_by_date(

                start_day.strftime("%Y%m%d"),
                today.strftime("%Y%m%d"),
                code

            )

            if df.empty:
                continue

            if len(df) < 60:
                continue

            name = stock.get_market_ticker_name(code)

            ai_score = calculate_ai_score(df, code)

            if ai_score < 70:
                continue

            current_price = int(df['종가'].iloc[-1])

            reason_list = get_ai_reason(df)

            result.append({

                "종목": name,
                "종목코드": code,
                "AI점수": ai_score,
                "현재가": current_price,
                "추천근거": ", ".join(reason_list[:3])

            })

        except:

            continue

    result_df = pd.DataFrame(result)

    if len(result_df) > 0:

        result_df = result_df.sort_values(
            by="AI점수",
            ascending=False
        ).head(3)

    return result_df


# =====================================================
# 종목 리스트
# =====================================================
ticker_map = {

    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "NAVER": "035420",
    "카카오": "035720",
    "LG에너지솔루션": "373220",
    "현대차": "005380",
    "셀트리온": "068270",
    "삼성바이오로직스": "207940",
    "LG화학": "051910",
    "기아": "000270",
    "POSCO홀딩스": "005490",
    "한화에어로스페이스": "012450",
    "알테오젠": "196170",
    "에코프로": "086520",
    "에코프로비엠": "247540"

}

ticker_df = pd.DataFrame([

    {

        "종목명": name,
        "종목코드": code

    }

    for name, code in ticker_map.items()

])


# =====================================================
# 제목
# =====================================================
st.title("🚀 실전형 AI 투자 플랫폼")

# =====================================================
# 시장 상태
# =====================================================
st.divider()

st.subheader("📈 AI 시장 상태 분석")

market_result = analyze_market()

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("시장 상태", market_result['market'])

with col2:
    st.metric("추천 전략", market_result['strategy'])

with col3:
    st.metric("위험도", market_result['risk'])

# =====================================================
# 추천 종목
# =====================================================
st.divider()

st.subheader("🤖 오늘의 AI 추천 종목")

if "recommend_loaded" not in st.session_state:
    st.session_state.recommend_loaded = False

if st.button(
    "🤖 AI 추천 종목 불러오기",
    use_container_width=True
):

    st.session_state.recommend_loaded = True

if st.session_state.recommend_loaded:

    with st.spinner("AI 추천 종목 분석 중..."):

        recommend_df = get_ai_recommend_stocks()

    if len(recommend_df) > 0:

        cols = st.columns(len(recommend_df))

        for idx, (_, row) in enumerate(recommend_df.iterrows()):

            with cols[idx]:

                with st.container(border=True):

                    st.markdown(f"### {row['종목']}")

                    st.caption(row['종목코드'])

                    st.metric(
                        "AI 점수",
                        f"{row['AI점수']}점"
                    )

                    st.metric(
                        "현재가",
                        f"{row['현재가']:,}원"
                    )

                    st.info(row['추천근거'])

                    if row['AI점수'] >= 85:
                        st.success("🟢 강한 매수")

                    elif row['AI점수'] >= 75:
                        st.warning("🟡 관심 종목")

                    else:
                        st.info("관망")

                    if st.button(
                        f"{row['종목']} 분석",
                        key=f"recommend_{idx}"
                    ):

                        st.session_state.selected_stock = row['종목코드']

                        st.rerun()

else:

    st.warning("현재 조건에 맞는 추천 종목이 없습니다.")

# =====================================================
# 통합 종목 검색
# =====================================================
st.divider()

st.subheader("🔎 종목 검색")

search_input = st.text_input(
    "종목명 또는 종목코드 입력",
    placeholder="예: 삼성전자 또는 005930"
)

stock_code = st.session_state.selected_stock

if search_input != "":

    # 종목명 검색
    if search_input in ticker_map:

        stock_code = ticker_map[search_input]

        st.session_state.selected_stock = stock_code

    # 종목코드 직접 입력
    elif search_input.isdigit():

        stock_code = search_input

        st.session_state.selected_stock = stock_code

    # 부분검색
    else:

        matched = [

            name for name in ticker_map.keys()

            if search_input.lower() in name.lower()

        ]

        if len(matched) > 0:

            selected_name = st.selectbox(

                "검색 결과",

                matched

            )

            stock_code = ticker_map[selected_name]

            st.session_state.selected_stock = stock_code

            st.success(
                f"{selected_name} ({stock_code}) 선택됨"
            )

col1, col2 = st.columns([4,1])

with col1:

    stock_code = st.text_input(
        "현재 선택 종목코드",
        value=st.session_state.selected_stock
    )

with col2:

    st.markdown("<br>", unsafe_allow_html=True)

    search_clicked = st.button(
        "🔍 검색",
        use_container_width=True
    )

if search_clicked:

    st.session_state.selected_stock = stock_code

stock_code = st.session_state.selected_stock

# =====================================================
# 기간 선택
# =====================================================
period = st.selectbox(

    "기간 선택",

    [
        "3개월",
        "6개월",
        "1년",
        "3년",
        "5년"
    ],

    index=2

)

# =====================================================
# 날짜 계산
# =====================================================
end_date = datetime.today()

if period == "3개월":
    start_date = end_date - timedelta(days=90)

elif period == "6개월":
    start_date = end_date - timedelta(days=180)

elif period == "1년":
    start_date = end_date - timedelta(days=365)

elif period == "3년":
    start_date = end_date - timedelta(days=1095)

else:
    start_date = end_date - timedelta(days=1825)

# =====================================================
# 데이터 조회
# =====================================================
try:

    df = get_stock_data(

        start_date,
        end_date,
        stock_code

    )

    if df.empty:

        st.error("데이터가 없습니다.")

    else:

        stock_name = stock.get_market_ticker_name(stock_code)

        current_price = int(df['종가'].iloc[-1])

        st.subheader(f"{stock_name} ({stock_code})")

        st.subheader(f"현재 주가 : {current_price:,}원")

        # =================================================
        # 보조지표
        # =================================================
        df['MA5'] = df['종가'].rolling(5).mean()
        df['MA20'] = df['종가'].rolling(20).mean()
        df['MA60'] = df['종가'].rolling(60).mean()

        df['RSI'] = calculate_rsi(df['종가'])

        ema12 = df['종가'].ewm(span=12, adjust=False).mean()
        ema26 = df['종가'].ewm(span=26, adjust=False).mean()

        df['MACD'] = ema12 - ema26
        df['SIGNAL'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # =================================================
        # AI 종합 분석
        # =================================================
        st.divider()

        st.subheader("🧠 AI 종합 분석")

        ai_score = calculate_ai_score(df, stock_code)

        current_rsi = round(df['RSI'].iloc[-1], 1)

        volume_avg = (
            df['거래량']
            .rolling(20)
            .mean()
            .iloc[-1]
        )

        volume_ratio = 1

        if volume_avg != 0:

            volume_ratio = round(

                df['거래량'].iloc[-1]
                /
                volume_avg,

                2

            )

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("AI 점수", f"{ai_score}점")

        with col2:
            st.metric("RSI", f"{current_rsi}")

        with col3:
            st.metric("거래량", f"{volume_ratio}배")



        # =================================================
        # AI 수급 분석
        # =================================================
        st.divider()

        st.subheader("💰 외국인 / 기관 수급 분석")

        supply_result = analyze_supply(stock_code)

        sup_col1, sup_col2, sup_col3 = st.columns(3)

        with sup_col1:

            st.metric(
                "외국인 순매수",
                format_korean_money(supply_result['외국인'])
            )

        with sup_col2:

            st.metric(
                "기관 순매수",
                format_korean_money(supply_result['기관'])
            )

        with sup_col3:

            st.metric(
                "수급 점수",
                f"{supply_result['수급점수']}점"
            )

        for reason in supply_result['수급근거']:

            st.info(reason)


        # =================================================
        # AI 위험도 분석
        # =================================================
        st.divider()

        st.subheader("⚠ AI 위험도 분석")

        risk_list, risk_score = analyze_risk(df)

        st.metric(
            "리스크 점수",
            f"{risk_score}점"
        )

        for risk in risk_list:

            if risk == "리스크 낮음":

                st.success(risk)

            else:

                st.warning(risk)

        # =================================================
        # 전략 추천
        # =================================================
        st.divider()

        st.subheader("🤖 AI 전략 자동 추천")


        strategy = recommend_strategy(df)

        st.success(f"추천 전략 : {strategy}")

        strategy_reason = get_strategy_reason(df)

        st.caption("📌 전략 선택 이유")

        for reason in strategy_reason:

            st.info(reason)


        # =================================================
        # AI 시그널
        # =================================================
        st.divider()

        st.subheader("🔥 AI 자동 매매 시그널")


        if ai_score >= 85:
            st.success("🟢 강한 매수 신호")

        elif ai_score >= 70:
            st.warning("🟡 관심 종목")

        else:
            st.error("🔴 관망 필요")

        st.caption("📌 AI 시그널 근거")

        signal_reason = get_ai_reason(df)

        for reason in signal_reason:

            st.info(reason)


        # =================================================
        # 포트폴리오
        # =================================================
        st.divider()

        st.subheader("💼 포트폴리오")

        col1, col2, col3 = st.columns(3)

        with col1:

            portfolio_code = st.text_input(
                "추가할 종목 코드",
                value=stock_code
            )

        with col2:

            portfolio_quantity = st.number_input(
                "보유 수량",
                min_value=1,
                value=1
            )

        with col3:

            portfolio_buy_price = st.number_input(
                "평균 매수가",
                min_value=1,
                value=current_price
            )

        if st.button("➕ 포트폴리오 추가"):

            try:

                portfolio_name = stock.get_market_ticker_name(
                    portfolio_code
                )

                duplicate = False

                for item in st.session_state.portfolio:

                    if item['종목코드'] == portfolio_code:

                        item['수량'] += portfolio_quantity

                        duplicate = True

                        st.success("기존 종목 수량 추가 완료!")

                        break

                if duplicate == False:

                    st.session_state.portfolio.append({

                        "종목": portfolio_name,
                        "종목코드": portfolio_code,
                        "수량": portfolio_quantity,
                        "평균매수가": portfolio_buy_price

                    })

                    st.success("포트폴리오 저장 완료!")

            except:

                st.error("종목코드를 확인해주세요.")

        # =================================================
        # 포트폴리오 출력
        # =================================================
        if len(st.session_state.portfolio) > 0:

            portfolio_result = []

            for item in st.session_state.portfolio:

                try:

                    latest_df = stock.get_market_ohlcv_by_date(

                        (datetime.today() - timedelta(days=10)).strftime("%Y%m%d"),
                        datetime.today().strftime("%Y%m%d"),
                        item['종목코드']

                    )

                    latest_price = int(
                        latest_df['종가'].iloc[-1]
                    )

                    eval_amount = (
                        latest_price
                        * item['수량']
                    )

                    buy_amount = (
                        item['평균매수가']
                        * item['수량']
                    )

                    profit = eval_amount - buy_amount

                    profit_rate = round(

                        (profit / buy_amount) * 100,

                        2

                    )

                    portfolio_result.append({

                        "종목": item['종목'],
                        "현재가": latest_price,
                        "수익률": profit_rate,
                        "평가금액": eval_amount

                    })

                except:

                    continue

            portfolio_df = pd.DataFrame(portfolio_result)

            st.dataframe(

                portfolio_df.style.format({

                    '현재가':'{:,.0f}원',
                    '수익률':'{:.2f}%',
                    '평가금액':'{:,.0f}원'

                }),

                use_container_width=True

            )

            # =================================================
            # 포트폴리오 AI 평가
            # =================================================
            st.divider()

            st.subheader("🧠 포트폴리오 AI 평가")

            portfolio_analysis = portfolio_ai_analysis(
                portfolio_df
            )

            st.info(
                portfolio_analysis['style']
            )

            st.warning(
                portfolio_analysis['risk']
            )

            st.success(
                portfolio_analysis['comment']
            )

            # =================================================
            # 포트폴리오 비중
            # =================================================
            st.divider()

            st.subheader("🥧 포트폴리오 비중")

            pie_fig = go.Figure(

                data=[

                    go.Pie(

                        labels=portfolio_df['종목'],
                        values=portfolio_df['평가금액'],
                        hole=0.4

                    )

                ]

            )

            st.plotly_chart(
                pie_fig,
                use_container_width=True
            )



        # =================================================
        # AI 백테스트
        # =================================================
        st.divider()

        st.subheader("📊 AI 백테스트 결과")

        backtest_result = backtest_strategy(df)

        bt_col1, bt_col2, bt_col3 = st.columns(3)

        with bt_col1:

            st.metric(
                "승률",
                f"{backtest_result['승률']}%"
            )

        with bt_col2:

            st.metric(
                "평균수익률",
                f"{backtest_result['평균수익률']}%"
            )

        with bt_col3:

            st.metric(
                "거래횟수",
                f"{backtest_result['거래횟수']}회"
            )

        bt_col4, bt_col5, bt_col6 = st.columns(3)

        with bt_col4:

            st.success(
                f"최대수익 : {backtest_result['최대수익']}%"
            )

        with bt_col5:

            st.error(
                f"최대손실 : {backtest_result['최대손실']}%"
            )

        with bt_col6:

            st.warning(
                f"MDD : {backtest_result['MDD']}%"
            )

        st.info(
            f"초기자산 100만원 → 최종자산 {backtest_result['최종자산']:,}원"
        )

        st.caption(
            f"백테스트 기간 : "
            f"{backtest_result['시작일']} "
            f"~ "
            f"{backtest_result['종료일']} "
            f"(약 {backtest_result['백테스트기간']}년 기준)"
        )


        # =================================================
        # 차트
        # =================================================
        st.divider()

        st.subheader("📈 AI 기술 차트")

        fig = make_subplots(

            rows=4,
            cols=1,

            shared_xaxes=True,

            vertical_spacing=0.03,

            row_heights=[0.5,0.2,0.15,0.15]

        )

        fig.add_trace(

            go.Candlestick(

                x=df.index,

                open=df['시가'],
                high=df['고가'],
                low=df['저가'],
                close=df['종가'],

                increasing_line_color='red',
                decreasing_line_color='blue',

                name='캔들'

            ),

            row=1,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['MA5'],
                name='5일선'
            ),
            row=1,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['MA20'],
                name='20일선'
            ),
            row=1,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['MA60'],
                name='60일선'
            ),
            row=1,
            col=1
        )

        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df['거래량'],
                name='거래량'
            ),
            row=2,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['RSI'],
                name='RSI'
            ),
            row=3,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['MACD'],
                name='MACD'
            ),
            row=4,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['SIGNAL'],
                name='시그널선'
            ),
            row=4,
            col=1
        )

        fig.update_layout(
            height=1200,
            xaxis_rangeslider_visible=False
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

        # =================================================
        # 뉴스
        # =================================================
        st.divider()

        st.subheader("📰 최신 뉴스")

        news_data = get_stock_news(stock_name)

        for news in news_data:

            st.link_button(
                news['title'],
                news['link'],
                use_container_width=True
            )

except Exception as e:

    st.error(f"에러 발생: {e}")