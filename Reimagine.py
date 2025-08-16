import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import folium
import os


def generate_hypothetical_dashboard():
    # Generate sample sales data
    dates = pd.date_range(start="2024-01-01", periods=90, freq='D')
    locations = ["Lilongwe", "Blantyre", "Mzuzu", "Zomba", "Mangochi", "Kasungu"]
    agents = ["Agent A", "Agent B", "Agent C", "Agent D", "Agent E"]

    sales_data = {
        "Date": dates.repeat(len(locations)),
        "Location": np.tile(locations, len(dates)),
        "Sales": np.random.randint(10, 100, len(dates) * len(locations)),
        "Agent": np.random.choice(agents, len(dates) * len(locations))
    }
    df = pd.DataFrame(sales_data)

    # Daily Sales
    daily_sales = df.groupby("Date")["Sales"].sum().reset_index()
    fig1 = px.line(daily_sales, x="Date", y="Sales", title="Daily Sales")

    # Monthly Sales
    df["Month"] = df["Date"].dt.to_period("M")
    monthly_sales = df.groupby("Month")["Sales"].sum().reset_index()
    fig2 = px.bar(monthly_sales, x="Month", y="Sales", title="Monthly Sales")

    # Agent Performance
    agent_performance = df.groupby("Agent")["Sales"].sum().reset_index()
    fig3 = px.bar(agent_performance, x="Agent", y="Sales", title="Agent Performance")

    # Business Trajectory (Cumulative Sales)
    df["Cumulative Sales"] = df["Sales"].cumsum()
    fig4 = px.line(df, x="Date", y="Cumulative Sales", title="Overall Business Trajectory")

    # Map of Malawi Sales by District
    location_coords = {
        "Lilongwe": [-13.9833, 33.7833], "Blantyre": [-15.7861, 35.0058], "Mzuzu": [-11.4500, 34.0333],
        "Zomba": [-15.385, 35.318], "Mangochi": [-14.4781, 35.2645], "Kasungu": [-13.0333, 33.4833]
    }

    sales_map = folium.Map(location=[-13.5, 34], zoom_start=6)
    for location, coord in location_coords.items():
        total_sales = df[df["Location"] == location]["Sales"].sum()
        folium.Marker(
            coord,
            popup=f"{location}: {total_sales} sales",
            tooltip=location
        ).add_to(sales_map)

    sales_map.save("malawi_sales_map.html")

    # Save dashboard
    output_path = "hypothetical_sales_dashboard.html"
    with open(output_path, "w") as f:
        f.write(pio.to_html(fig1, full_html=False, include_plotlyjs='cdn'))
        f.write(pio.to_html(fig2, full_html=False, include_plotlyjs='cdn'))
        f.write(pio.to_html(fig3, full_html=False, include_plotlyjs='cdn'))
        f.write(pio.to_html(fig4, full_html=False, include_plotlyjs='cdn'))

    print(f"Dashboard saved as {output_path}")
    print("Malawi sales map saved as malawi_sales_map.html")


if __name__ == "__main__":
    generate_hypothetical_dashboard()
