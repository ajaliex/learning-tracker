import os
import pandas as pd
import altair as alt
from notion_client import Client
from datetime import datetime, timedelta

def fetch_data():
    # Direct HTTPX implementation to bypass client issues
    import httpx
    
    headers = {
        "Authorization": f"Bearer {os.environ['NOTION_API_KEY']}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    database_id = os.environ['NOTION_DATABASE_ID'].strip()

    # Verify database access
    try:
        r = httpx.get(f"https://api.notion.com/v1/databases/{database_id}", headers=headers)
        r.raise_for_status()
        print(f"Successfully accessed database: {database_id}")
    except Exception as e:
        print(f"Error accessing database: {e}")
        if 'r' in locals():
            print(r.text)
        return pd.DataFrame()

    results = []
    has_more = True
    start_cursor = None

    print("Fetching data from Notion...")
    while has_more:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor

        response = httpx.post(
            f"https://api.notion.com/v1/databases/{database_id}/query",
            headers=headers,
            json=body
        )
        
        try:
            response.raise_for_status()
            data = response.json()
            results.extend(data["results"])
            has_more = data["has_more"]
            start_cursor = data["next_cursor"]
        except Exception as e:
            print(f"Error querying database: {e}")
            print(response.text)
            break
    
    print(f"Fetched {len(results)} records.")
    
    data = []
    for page in results:
        props = page["properties"]
        
        # Extract Date
        date_prop = props.get("日付")
        if not date_prop or not date_prop["date"]:
            continue
        date_str = date_prop["date"]["start"]
        
        # Extract Time
        time_prop = props.get("勉強時間(分)")
        minutes = 0
        if time_prop and time_prop["type"] == "number":
            minutes = time_prop["number"] or 0
            
        data.append({"date": date_str, "minutes": minutes})
        
    return pd.DataFrame(data)

def process_data(df):
    if df.empty:
        return pd.DataFrame(columns=["date", "minutes", "monthly_cumulative", "moving_avg_60d"])

    # 1. Sort and convert to datetime
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    
    # 2. Resample to daily frequency (fill missing days with 0)
    # Set index to date for resampling
    df = df.set_index("date").resample("D").sum().fillna(0).reset_index()
    
    # 3. Calculate 60-day Moving Average on FULL history
    df["moving_avg_60d"] = df["minutes"].rolling(window=60, min_periods=1).mean()
    
    # 4. Filter for Current Month
    now = datetime.now()
    current_month_str = now.strftime("%Y-%m")
    
    # Filter using string comparison on date
    df_current_month = df[df["date"].dt.strftime("%Y-%m") == current_month_str].copy()
    
    # 5. Calculate Monthly Cumulative Sum
    df_current_month["monthly_cumulative"] = df_current_month["minutes"].cumsum()
    
    return df_current_month

def create_chart(df):
    if df.empty:
        print("No data for current month.")
        return

    # Determine Month Boundaries
    # Use the date from the dataframe to find the month
    # (Assuming df is filtered to current month already)
    # Safest to use the first date in df, or today's date if df might be partial?
    # process_data filters by current_month_str based on datetime.now()
    
    now = datetime.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Calculate end of month
    import calendar
    _, last_day = calendar.monthrange(now.year, now.month)
    end_of_month = now.replace(day=last_day, hour=0, minute=0, second=0, microsecond=0)
    
    current_month_label = start_of_month.strftime("%B %Y")
    
    # Create Ideal Line Data (0 to 6000 minutes)
    ideal_df = pd.DataFrame([
        {"date": start_of_month, "minutes": 0},
        {"date": end_of_month, "minutes": 6000}  # 100 hours * 60 min
    ])

    # Base Chart
    # We combine both dataframes to ensure the scale covers the full month
    
    # Layer 1: Ideal Line (Red Dotted)
    ideal_line = alt.Chart(ideal_df).mark_line(
        color='red', 
        strokeDash=[4, 4],
        opacity=0.7
    ).encode(
        x=alt.X('date:T'),
        y=alt.Y('minutes:Q')
    )

    # Layer 2: Monthly Cumulative (Area/Line) - Left Axis
    # Uses the main df
    cumulative_base = alt.Chart(df).encode(
        x=alt.X('date:T', axis=alt.Axis(format='%d', title='Date'))
    )

    cumulative_area = cumulative_base.mark_area(opacity=0.3, color='#1f77b4').encode(
        y=alt.Y('monthly_cumulative:Q', title='Monthly Cumulative (min)', axis=alt.Axis(titleColor='#1f77b4')),
        tooltip=['date', 'monthly_cumulative']
    )
    
    cumulative_line = cumulative_base.mark_line(color='#1f77b4').encode(
        y=alt.Y('monthly_cumulative:Q'),
        tooltip=['date', 'monthly_cumulative']
    )

    # Layer 3: 60-day Moving Average (Line) - Right Axis
    moving_avg = cumulative_base.mark_line(color='#ff7f0e', strokeDash=[4, 4]).encode(
        y=alt.Y('moving_avg_60d:Q', title='60-day Moving Avg (min/day)', axis=alt.Axis(titleColor='#ff7f0e')),
        tooltip=['date', 'moving_avg_60d']
    )

    # Combine
    # We layer ideal_line first so it sets the domain? 
    # Actually, we should layer them and let Altair union the domains.
    # ideally, ideal_line shares the Y axis with cumulative.
    
    # To explicit share Y axis between ideal and cumulative, we can do:
    left_layer = alt.layer(ideal_line, cumulative_area, cumulative_line).resolve_scale(y='shared')
    
    chart = alt.layer(
        left_layer, 
        moving_avg
    ).resolve_scale(
        y='independent'
    ).properties(
        title=f"Learning Progress - {current_month_label}",
        width='container',
        height=220, # Compact height
        background='#0e1117' # Dark background
    ).configure(
        background='#0e1117'
    ).configure_axis(
        labelFontSize=10,
        titleFontSize=12,
        labelColor='#fafafa',
        titleColor='#fafafa',
        gridColor='#333333',
        domainColor='#fafafa'
    ).configure_title(
        fontSize=14,
        color='#fafafa',
        anchor='start',
        offset=10
    ).configure_view(
        strokeWidth=0 # Remove border around chart
    ).configure_legend(
        labelColor='#fafafa',
        titleColor='#fafafa'
    )

    return chart

def main():
    if "NOTION_API_KEY" not in os.environ or "NOTION_DATABASE_ID" not in os.environ:
        print("Error: Environment variables NOTION_API_KEY and NOTION_DATABASE_ID must be set.")
        return

    df = fetch_data()
    processed_df = process_data(df)
    
    if processed_df.empty:
        print("No data found for the current month. Generating empty chart.")
        # Create a dummy empty chart or just exit? 
        # Better to save an empty HTML to avoid 404
        with open("index.html", "w") as f:
            f.write("<html><body><h1>No data available for this month</h1></body></html>")
        return

    chart = create_chart(processed_df)
    
    # Save to HTML
    # We embed the data to make it static
    chart.save('index.html')
    
    # Post-process HTML to remove white border
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    # Inject body style
    style = """
    <style>
        html {
            background-color: #0e1117;
            height: 100%;
        }
        body {
            background-color: #0e1117;
            margin: 0;
            padding: 0;
            min-height: 100%;
            overflow: hidden; /* Prevent scrollbars if not needed */
            display: flex;
            align-items: center; /* Vertical center */
            justify-content: center; /* Horizontal center */
        }
        #vis {
            /* Remove margin-top as we center with flexbox */
        }
    </style>
    """
    
    # Insert style before </head>
    if "</head>" in html:
        html = html.replace("</head>", f"{style}</head>")
    else:
        # Fallback if no head tag (unlikely with altair)
        html = style + html
        
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
        
    print("Chart saved to index.html with dark mode styles")

if __name__ == "__main__":
    main()
