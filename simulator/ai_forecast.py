import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from django.utils import timezone
from datetime import timedelta

from sales.models import Sale  # Assuming we track daily or monthly sales

def ai_forecast(days=90):
    """
    Predicts daily sales for the next N days using historical sales data.
    Fallback: if we don't have enough history, returns flat projections.
    """
    today = timezone.now().date()
    cutoff = today - timedelta(days=365)

    # Load 1 year of sales
    qs = Sale.objects.filter(created_at__gte=cutoff).values("created_at", "quantity")
    if not qs.exists():
        return [{"day": i, "predicted_sales": 0} for i in range(1, days + 1)]

    # Prepare data
    df = pd.DataFrame(list(qs))
    df["created_at"] = pd.to_datetime(df["created_at"])
    df = df.groupby("created_at")["quantity"].sum().reset_index()

    # Build training features
    df["day_num"] = (df["created_at"] - df["created_at"].min()).dt.days
    X = df["day_num"].values.reshape(-1, 1)
    y = df["quantity"].values

    # Train linear regression
    model = LinearRegression()
    model.fit(X, y)

    # Predict future days
    future_days = np.arange(df["day_num"].max() + 1, df["day_num"].max() + days + 1).reshape(-1, 1)
    predictions = model.predict(future_days)

    return [
        {"day": int(i + 1), "predicted_sales": max(round(val, 2), 0)}
        for i, val in enumerate(predictions)
    ]


