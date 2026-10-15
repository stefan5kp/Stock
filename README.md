# Stock
Powershell: 
pip install yfinance (first time)  

## Standalone Dashboard
cd the folder of the .py file and then run: python analyzer.py NVDA  
NVDA can be changed to any symbol  

## Web tool
Double-click `start_web_tool.bat` (or run: `python server.py`).  
It opens http://127.0.0.1:8765 where you can type or pick a symbol, press Run, and view the dashboard.  
Keep the console window open while using it; close it (or press Ctrl+C) to stop.

### Watchlist
Switch to the **Watchlist** tab (top bar) to add symbols of interest and compare them in one table:
price, signal, RSI, the 30-/90-day forecast (median, 90% range, probabilities) and volatility.
Click a column header to sort, a row to open its dashboard, "Run missing / stale" to refresh what wasn't run today,
and "Export CSV" to download the table. The list is saved in `watchlist.json`.
