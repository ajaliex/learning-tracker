import streamlit as st
import pandas as pd
import altair as alt
from notion_client import Client
import httpx # Use httpx directly for queries due to notion-client issue
from datetime import datetime, timedelta

# --- Configuration ---
st.set_page_config(
    page_title="学習進捗トラッカー",
    page_icon="QX",
    layout="wide"
)

# --- CSS to Hide Streamlit Branding ---
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- Constants (Property Names) ---
# Modify these if your Notion database properties have different names
PROPERTY_DATE = "日付"
PROPERTY_TIME = "勉強時間(分)"

# --- Notion Data Fetching ---
@st.cache_data(ttl=300)  # Cache data for 5 minutes
def fetch_data():
    """Fetches data from Notion database."""
    try:
        notion = Client(auth=st.secrets["NOTION_TOKEN"])
        database_id = st.secrets["DATABASE_ID"]
        goal_database_id = st.secrets["GOAL_DATABASE_ID"]
    except KeyError:
        st.error("シークレット情報が見つかりません。.streamlit/secrets.toml に NOTION_TOKEN, DATABASE_ID, GOAL_DATABASE_ID を設定してください。")
        return pd.DataFrame()

    results = []
    has_more = True
    start_cursor = None

    with st.spinner("Notionからデータを取得中..."):
        while has_more:
            try:
                # Direct HTTPX call to bypass notion-client issue
                url = f"https://api.notion.com/v1/databases/{database_id}/query"
                headers = {
                    "Authorization": f"Bearer {st.secrets['NOTION_TOKEN']}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json"
                }
                body = {
                    "page_size": 100
                }
                if start_cursor:
                    body["start_cursor"] = start_cursor
                
                resp = httpx.post(url, headers=headers, json=body, timeout=30.0)
                resp.raise_for_status()
                response = resp.json()

                results.extend(response["results"])
                has_more = response["has_more"]
                start_cursor = response["next_cursor"]
            except Exception as e:
                st.error(f"Notionからのデータ取得中にエラーが発生しました: {e}")
                return pd.DataFrame()

    return process_raw_data(results)

@st.cache_data(ttl=300)
def fetch_goal_data():
    """Fetches goal data from Notion database."""
    try:
        notion = Client(auth=st.secrets["NOTION_TOKEN"])
        goal_database_id = st.secrets["GOAL_DATABASE_ID"]
    except KeyError:
        return pd.DataFrame()

    results = []
    has_more = True
    start_cursor = None

    with st.spinner("Notionから目標データを取得中..."):
        while has_more:
            try:
                # Direct HTTPX call to bypass notion-client issue
                url = f"https://api.notion.com/v1/databases/{goal_database_id}/query"
                headers = {
                    "Authorization": f"Bearer {st.secrets['NOTION_TOKEN']}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json"
                }
                body = {
                    "page_size": 100
                }
                if start_cursor:
                    body["start_cursor"] = start_cursor
                
                resp = httpx.post(url, headers=headers, json=body, timeout=30.0)
                resp.raise_for_status()
                response = resp.json()

                results.extend(response["results"])
                has_more = response["has_more"]
                start_cursor = response["next_cursor"]
            except Exception as e:
                st.error(f"Notionからの目標データ取得中にエラーが発生しました: {e}")
                return pd.DataFrame()

    return process_goal_data(results)

def process_raw_data(results):
    """Extracts relevant properties and converts to DataFrame."""
    data = []
    for page in results:
        props = page["properties"]
        
        # Extract Date
        date_prop = props.get(PROPERTY_DATE, {})
        if not date_prop or date_prop["type"] != "date" or not date_prop["date"]:
            continue
        date_str = date_prop["date"]["start"]
        
        # Extract Time
        time_prop = props.get(PROPERTY_TIME, {})
        if not time_prop or time_prop["type"] != "number":
             # Treat missing or wrong type as 0, or skip? 
             # Let's treat as 0 if the property exists but is empty, skip if property missing entirely?
             # User said "Date and Learning Time are the 2 properties". 
             # Let's assume safe extraction.
             learning_time = 0
        else:
             learning_time = time_prop["number"] or 0 # Handle None/null

        data.append({
            "Date": date_str,
            "LearningTime": learning_time
        })
    
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df["Date"] = pd.to_datetime(df["Date"])
    return df

def process_goal_data(results):
    """Extracts goal properties and converts to DataFrame."""
    data = []
    for page in results:
        props = page["properties"]
        
        # Extract Month Title (e.g., "2026-Jan")
        month_prop = props.get("月タイトル", {})
        if not month_prop or not month_prop["title"]:
            continue
        month_str = month_prop["title"][0]["text"]["content"]
        
        # Extract Goal Time
        goal_prop = props.get("目標学習時間", {})
        if not goal_prop or goal_prop["type"] != "number":
             goal_time = 0
        else:
             # Goal is in hours, convert to minutes
             goal_time = (goal_prop["number"] or 0) * 60

        try:
            # Parse "YYYY-Mon" to datetime (1st day of the month)
            date_obj = datetime.strptime(month_str, "%Y-%b")
            data.append({
                "Month": date_obj,
                "GoalTime": goal_time
            })
        except ValueError:
            continue # Skip invalid date formats
    
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    return df

# --- Data Processing (Compounding & Moving Avg) ---
def analyze_data(df):
    if df.empty:
        return df

    # 1. Sort by Date
    df = df.sort_values("Date")

    # 2. Resample to daily frequency to handle missing days
    # Set Date as index
    df = df.set_index("Date")
    # Resample daily ('D'), sum up times if multiple entries per day (or just fill 0)
    # Using sum() in case there are multiple entries for a single day.
    df_daily = df.resample("D").sum().fillna(0)
    
    # Reset index to make Date a column again for Altair
    df_daily = df_daily.reset_index()

    # 3. Calculate Cumulative Time
    df_daily["Cumulative_Time"] = df_daily["LearningTime"].cumsum()

    # 4. Calculate 60-day Moving Average
    # min_periods=1 ensures we get values even with < 60 days of data
    df_daily["Moving_Avg_60d"] = df_daily["LearningTime"].rolling(window=60, min_periods=1).mean()

    return df_daily

    # --- Main App ---
def main():
    # st.title("📊 学習進捗トラッカー") # Hidden for Notion Embed

    # Load Data
    raw_df = fetch_data()
    goal_df = fetch_goal_data() 
    
    if raw_df.empty:
        st.warning("データが見つからないか、取得に失敗しました。")
        st.stop()
        
    df = analyze_data(raw_df)

    # --- Monthly Data Processing ---
    # 1. Initialize/Retrieve Current Month in Session State
    if "current_month" not in st.session_state:
        st.session_state.current_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Note: Streamlit reruns the script on interaction.
    # We'll put navigation buttons here.

    col_prev, col_label, col_next = st.columns([1, 4, 1])
    
    with col_prev:
        if st.button("＜"):
            # Move to previous month
            curr = st.session_state.current_month
            # logic: first day of current month - 1 day -> last day of prev month -> replace day=1
            prev_month = (curr - timedelta(days=1)).replace(day=1)
            st.session_state.current_month = prev_month
            st.rerun()

    with col_next:
        if st.button("＞"):
            # Move to next month
            curr = st.session_state.current_month
            # logic: first day of current month + 32 days -> guaranteed next month -> replace day=1
            next_month = (curr + timedelta(days=32)).replace(day=1)
            st.session_state.current_month = next_month
            st.rerun()
            
    current_month_start = st.session_state.current_month
    
    with col_label:
        # Format month as "2026-Feb."
        month_str = current_month_start.strftime('%Y-%b.')
        st.markdown(f"<h3 style='text-align: center; margin: 0;'>{month_str}</h3>", unsafe_allow_html=True)

    # Calculate Next Month Start for filtering
    if current_month_start.month == 12:
        next_month_start = current_month_start.replace(year=current_month_start.year + 1, month=1)
    else:
        next_month_start = current_month_start.replace(month=current_month_start.month + 1)
    
    # Filter for selected month
    df_month = df[(df["Date"] >= current_month_start) & (df["Date"] < next_month_start)].copy()
    
    # Recalculate Cumulative for this month only
    if not df_month.empty:
        df_month["Monthly_Cumulative"] = df_month["LearningTime"].cumsum()
    else:
        # Create empty if no data yet (but we need dates for the graph)
        df_month = pd.DataFrame({"Date": [], "LearningTime": [], "Monthly_Cumulative": [], "Moving_Avg_60d": []})

    # 2. Target Line Generation
    target_data = []
    current_goal_minutes = 0
    
    if not goal_df.empty:
        # Find goal for this month
        current_goal_row = goal_df[goal_df["Month"] == current_month_start]
        if not current_goal_row.empty:
            current_goal_minutes = current_goal_row.iloc[0]["GoalTime"]
    
    # If no goal found, default to 0 or skip line? Let's assume 0.
    if current_goal_minutes > 0:
        # Generate daily targets
        # Calculate days in selected month
        import calendar
        _, days_in_month = calendar.monthrange(current_month_start.year, current_month_start.month)
        
        for day in range(1, days_in_month + 1):
            try:
                date_val = current_month_start.replace(day=day)
            except ValueError:
                continue # Skip invalid days (e.g. leap year issues if any)

            # Linear target: Goal * (Day / TotalDays)
            daily_target = current_goal_minutes * (day / days_in_month)
            target_data.append({
                "Date": date_val,
                "Target_Cumulative": daily_target
            })
    
    df_target = pd.DataFrame(target_data)

    # --- Moving Average Domain Calculation ---
    # Calculate dynamic domain for Moving Average with padding
    ma_series = df_month["Moving_Avg_60d"].dropna()
    if not ma_series.empty:
        min_ma = ma_series.min()
        max_ma = ma_series.max()
        padding = (max_ma - min_ma) * 0.2 # Increased to 20% padding
        if padding == 0: padding = 20 # Minimum buffer
        # Ensure min doesn't go below 0 unless data is negative
        ma_domain = [max(0, min_ma - padding), max_ma + padding]
    else:
        ma_domain = [0, 300] # Default fallback

    # --- Visualization (Altair) ---
    # st.subheader("バーンアップチャート & 学習ペース") # Hidden for Notion Embed

    # Base chart for Actuals using df_month
    base_actual = alt.Chart(df_month).encode(
        x=alt.X("Date:T", title="", axis=alt.Axis(format="%d")) # Show only day number, no title
    )

    # Left Axis: Monthly Cumulative (Actual)
    line_actual = base_actual.mark_line(color="#1f77b4", point=True).encode(
        y=alt.Y("Monthly_Cumulative:Q", title="Total", axis=alt.Axis(titleColor="#1f77b4")),
        tooltip=["Date:T", alt.Tooltip("Monthly_Cumulative:Q", format=",.0f", title="Total")]
    )

    # Left Axis: Target Line (Red Dotted)
    if not df_target.empty:
        base_target = alt.Chart(df_target).encode(
            x=alt.X("Date:T")
        )
        line_target = base_target.mark_line(color="#d62728", strokeDash=[5, 5], opacity=0.7).encode(
            y=alt.Y("Target_Cumulative:Q"),
            tooltip=["Date:T", alt.Tooltip("Target_Cumulative:Q", format=",.0f", title="Target")]
        )
    else:
        line_target = None

    # Right Axis: Moving Avg (Line) - Filtered to this month
    # We use df_month which already has Moving_Avg_60d calculated from the full history
    line_moving_avg = base_actual.mark_line(color="#ff7f0e", strokeDash=[2, 2]).encode(
        y=alt.Y(
            "Moving_Avg_60d:Q", 
            title="Ave.", 
            axis=alt.Axis(titleColor="#ff7f0e"),
            scale=alt.Scale(domain=ma_domain) # Dynamic domain
        ),
        tooltip=["Date:T", alt.Tooltip("Moving_Avg_60d:Q", format=".1f", title="Ave.")]
    )

    # Combine
    # Create a base layer for the left axis (Actual + Target)
    # This ensures they share the Y scale
    left_layers = [line_actual]
    if line_target:
        left_layers.append(line_target)
    
    chart_left = alt.layer(*left_layers)

    # Combine Left (Actual/Target) and Right (Moving Avg) with independent axes
    chart = alt.layer(
        chart_left,
        line_moving_avg
    ).resolve_scale(
        y='independent'
    ).properties(
        autosize=alt.AutoSizeParams(type='fit', contains='padding'),
        height=300 # Standard "small" widget height
    ).interactive()

    # Metrics (Hidden for Notion Embed)
    # total_time = df["LearningTime"].sum()
    # current_pace = df["Moving_Avg_60d"].iloc[-1] if not df.empty else 0
    
    # col1, col2 = st.columns(2)
    # col1.metric("総学習時間 (分)", f"{total_time:,.0f}")
    # col2.metric("現在の60日間ペース (分/日)", f"{current_pace:.1f}")

    # --- Goal Comparison (Hidden for Notion Embed) ---
    # if not goal_df.empty:
    #     st.subheader("月別目標達成状況")
        
    #     # Aggregate daily data by month
    #     df_monthly = df.set_index("Date").resample("MS")["LearningTime"].sum().reset_index()
    #     df_monthly.rename(columns={"Date": "Month", "LearningTime": "ActualTime"}, inplace=True)
        
    #     # Merge with Goal Data
    #     merged_df = pd.merge(df_monthly, goal_df, on="Month", how="outer").fillna(0)
    #     merged_df["MonthLabel"] = merged_df["Month"].dt.strftime("%Y-%m")
    #     merged_df["AchievementRate"] = (merged_df["ActualTime"] / merged_df["GoalTime"]).replace([float('inf'), -float('inf')], 0).fillna(0) * 100
 
    #     # Bar Chart: Actual vs Goal
    #     base_monthly = alt.Chart(merged_df).encode(
    #         x=alt.X("MonthLabel:O", title="月")
    #     )
 
    #     bar_actual = base_monthly.mark_bar(color="#1f77b4", opacity=0.7).encode(
    #         y=alt.Y("ActualTime:Q", title="学習時間 (分)"),
    #         tooltip=["MonthLabel", "ActualTime", "GoalTime", alt.Tooltip("AchievementRate", format=".1f", title="達成率(%)")]
    #     )
 
    #     # Goal Tick Mark (instead of line for better bar comparison)
    #     tick_goal = base_monthly.mark_tick(color="red", thickness=2).encode(
    #         y="GoalTime:Q",
    #         tooltip=["MonthLabel", "GoalTime"]
    #     )
 
    #     st.altair_chart((bar_actual + tick_goal).interactive(), use_container_width=True)
 
    #     # Current Month Progress
    #     current_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    #     current_month_data = merged_df[merged_df["Month"] == current_month]
        
    #     if not current_month_data.empty:
    #         actual = current_month_data.iloc[0]["ActualTime"]
    #         goal = current_month_data.iloc[0]["GoalTime"]
    #         rate = current_month_data.iloc[0]["AchievementRate"]
            
    #         st.metric(
    #             label=f"今月の進捗 ({current_month.strftime('%Y年%m月')})",
    #             value=f"{actual:,.0f} / {goal:,.0f} 分",
    #             delta=f"{rate:.1f}% 達成"
    #         )

    # --- Visualization (Altair) ---
    # st.subheader("バーンアップチャート & 学習ペース") # Hidden for Notion Embed

    st.altair_chart(chart, use_container_width=True)

    # Show raw data (optional)
    # with st.expander("生データを表示"):
    #     st.dataframe(df.sort_values("Date", ascending=False))

if __name__ == "__main__":
    main()
