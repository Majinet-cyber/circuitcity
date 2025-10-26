from flask import Flask, render_template
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import plotly.express as px

app = Flask(__name__)

# --- Google Sheets setup ---
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "circuit-city-dashboard-xxx.json",  # replace with your actual file name
    scope
)
client = gspread.authorize(creds)
spreadsheet = client.open("circuit city cashflow")
sheet = spreadsheet.worksheet("Cash Reserve")

def safe_int(cell):
    try:
        return int(cell.replace(',', '').strip())
    except (ValueError, AttributeError):
        return None

@app.route('/dashboard')
def dashboard():
    # âœ… Pull data
    dates = sheet.col_values(1)[1:]  # skip header
    savings_raw = sheet.col_values(2)[1:]
    totals_raw = sheet.col_values(3)[1:]

    savings = [safe_int(cell) for cell in savings_raw if safe_int(cell) is not None]
    totals = [safe_int(cell) for cell in totals_raw if safe_int(cell) is not None]

    # âœ… Create DataFrame
    cashflow_df = pd.DataFrame({
        "Date": dates[:len(savings)],
        "Savings": savings,
        "Total Savings": totals[:len(savings)]
    })

    # âœ… Make Plotly chart
    fig = px.bar(cashflow_df, x="Date", y=["Savings", "Total Savings"],
                 barmode="group", title="Live Cash Reserve")

    chart_html = fig.to_html(full_html=False)

    return render_template('dashboard.html', chart_html=chart_html)

if __name__ == '__main__':
    app.run(debug=True)


