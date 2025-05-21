def generate_prompt(company_name, ticker, sector, market_cap, pe_ratio, range_52w):
    return f"""
You are a financial analyst assistant. Summarize the following company's core business, recent performance, and industry position. Include a brief SWOT analysis and an investor-friendly outlook.

Company: {company_name}
Stock Ticker: {ticker}
Sector: {sector}
Market Cap: {market_cap}
P/E Ratio: {pe_ratio}
52-Week Range: {range_52w}

Format your response using the **exact headers below** (do not rename or reword):

Business Summary  
----------------

SWOT  
----------------

Outlook  
----------------
"""
