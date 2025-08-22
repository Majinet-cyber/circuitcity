import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox
import plotly.express as px
import plotly.graph_objects as go
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Google Sheets setup ---
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "circuit-city-dashboard-7de3805a57c1.json",
    scope
)

client = gspread.authorize(creds)
spreadsheet = client.open("circuit city cashflow")
sheet = spreadsheet.worksheet("Cash Reserve")

# ✅ Safe int helper to skip non-numeric cells
def safe_int(cell):
    try:
        return int(cell.replace(',', '').strip())
    except (ValueError, AttributeError):
        return None

dates = sheet.col_values(1)[1:]  # Skip header

savings_raw = sheet.col_values(2)[1:]  # Skip header
savings = [safe_int(cell) for cell in savings_raw if safe_int(cell) is not None]

totals_raw = sheet.col_values(3)[1:]  # Skip header
totals = [safe_int(cell) for cell in totals_raw if safe_int(cell) is not None]

print("Dates:", dates)
print("Savings:", savings)
print("Total savings:", totals)


def load_sales_data():
    file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx;*.xls")])
    if file_path:
        try:
            df = pd.read_excel(file_path)
            df = df.rename(columns={"Location": "Location", "Sales": "Sales", "Date": "Date"})
            generate_dashboard(df)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file: {e}")


def generate_dashboard(df):
    try:
        required_columns = {"Location", "Sales", "Date"}
        if not required_columns.issubset(df.columns):
            messagebox.showerror("Error", "Missing required columns in the dataset.")
            return

        df["Date"] = pd.to_datetime(df["Date"])
        df.sort_values("Date", inplace=True)

        sales_by_location = df.groupby("Location")["Sales"].sum().reset_index()
        fig1 = px.bar(sales_by_location, x="Location", y="Sales", title="Sales by Location")

        df["Profit"] = df["Sales"] * 0.2
        profit_over_time = df.groupby("Date")["Profit"].sum().reset_index()
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=profit_over_time["Date"], y=profit_over_time["Profit"],
                                  mode="lines+markers", name="Profit Growth"))
        fig2.update_layout(title="Profit Growth Over Time", xaxis_title="Date", yaxis_title="Profit")

        # ✅ Live Cash Reserve chart from Google Sheets with safe data
        cashflow_df = pd.DataFrame({
            "Date": dates[:len(savings)],  # Match lengths in case they differ
            "Savings": savings,
            "Total Savings": totals[:len(savings)]
        })
        fig3 = px.bar(cashflow_df, x="Date", y=["Savings", "Total Savings"],
                      barmode="group", title="Live Cash Reserve from Google Sheets")

        output_path = "sales_dashboard.html"
        with open(output_path, "w") as f:
            f.write(fig1.to_html(full_html=False, include_plotlyjs='cdn'))
            f.write(fig2.to_html(full_html=False, include_plotlyjs='cdn'))
            f.write(fig3.to_html(full_html=False, include_plotlyjs='cdn'))

        messagebox.showinfo("Success", f"Dashboard saved as {output_path}")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to generate dashboard: {e}")


def select_output_directory():
    output_dir = filedialog.askdirectory()
    if output_dir:
        output_path = os.path.join(output_dir, "sales_dashboard.html")
        messagebox.showinfo("Output Directory", f"Dashboard will be saved in: {output_path}")


tk_root = tk.Tk()
tk_root.title("Sales Dashboard Generator")
tk_root.geometry("400x200")

tk.Button(tk_root, text="Select Sales Data File", command=load_sales_data).pack(pady=10)
tk.Button(tk_root, text="Select Output Directory", command=select_output_directory).pack(pady=10)

tk_root.mainloop()
