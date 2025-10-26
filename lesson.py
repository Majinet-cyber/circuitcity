from flask import Flask, render_template, request, redirect, url_for, session
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import plotly.express as px

# âœ… FIRST: create your Flask app!
app = Flask(__name__)
app.secret_key = 'supersecretkey'

# âœ… THEN: your Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "circuit-city-dashboard-7de3805a57c1.json",
    scope
)
client = gspread.authorize(creds)
spreadsheet = client.open("circuit city cashflow")
sheet = spreadsheet.worksheet("Cash Reserve")

# âœ… NOW: define your routes
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if email == 'your@email.com' and password == 'yourpassword':
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            return "Invalid credentials. Try again."
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    # Your dashboard logic here (e.g., pull Google Sheets data)
    return render_template('dashboard.html')

@app.route('/logout')
def logout():
    session['logged_in'] = False
    return redirect(url_for('login'))

# âœ… LAST: run your app
if __name__ == '__main__':
    app.run(debug=True)


