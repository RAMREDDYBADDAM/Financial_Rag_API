# Financial Metrics Plot Generator

## Overview

The `plot_generator.py` module automates the extraction of financial metrics from natural-language RAG output and generates matplotlib visualizations as base64-encoded PNG images. This bridges the gap between narrative financial analysis and data-driven visualization.

## Module Architecture

### Core Functions

#### 1. `extract_plot_params(text: str) -> Optional[Dict[str, Any]]`
**Purpose**: Extract company ticker, financial metric, and trend preference from RAG output.

**Inputs**:
- `text`: Natural-language string from RAG model (e.g., "Apple revenue grew in Q1")

**Outputs**:
- Dictionary with keys:
  - `company`: Stock ticker (AAPL, MSFT, GOOGL, TSLA, AMZN, etc.)
  - `metric`: Financial metric (revenue, net_income, operating_income, eps, total_assets, total_liabilities, equity)
  - `is_trend`: Boolean flag for time-series vs. latest-value visualization
- `None` if extraction fails

**Logic**:
- Regex-based case-insensitive matching for company tickers
- Keyword matching for financial metrics
- Heuristic trend detection (keywords: "trend", "growth", "over time", "historical", etc.)

**Example**:
```python
from app.core.plot_generator import extract_plot_params

rag_text = "Apple had strong revenue growth over the past quarters"
params = extract_plot_params(rag_text)
# Returns: {"company": "AAPL", "metric": "revenue", "is_trend": True}
```

---

#### 2. `fetch_metric_series(company_id: int, metric: str, latest_only: bool = False) -> Optional[List[Tuple[str, float]]]`
**Purpose**: Query PostgreSQL for financial metric time-series data.

**Inputs**:
- `company_id`: Company database ID (obtained from `fetch_company_id()`)
- `metric`: Financial metric name (must match schema column)
- `latest_only`: If `True`, return only the most recent value; if `False`, return full time-series

**Outputs**:
- List of tuples: `[(period_1, value_1), (period_2, value_2), ...]`
- `None` if no data found or query fails

**Database Query**:
- Parameterized SQL using `%s` placeholders (safe from SQL injection)
- Queries `financial_metrics` table with `ORDER BY period ASC/DESC`
- Filters for non-NULL metric values

**Example**:
```python
from app.core.plot_generator import fetch_company_id, fetch_metric_series

company_id = fetch_company_id("AAPL")  # Returns: 1
series = fetch_metric_series(company_id, "revenue", latest_only=False)
# Returns: [("Q1 2024", 123456.78), ("Q2 2024", 134567.89), ...]
```

---

#### 3. `plot_metric(series: List[Tuple[str, float]], company: str, metric: str) -> str`
**Purpose**: Generate a matplotlib chart and return as base64-encoded PNG.

**Inputs**:
- `series`: List of (period, value) tuples from `fetch_metric_series()`
- `company`: Company ticker (for title/labels)
- `metric`: Financial metric name (for title/labels)

**Outputs**:
- Base64-encoded PNG string (ready for JSON response or HTML img src)

**Chart Styling**:
- **Line Plot**: Blue line with circular markers (`marker="o"`)
- **Grid**: Enabled with 30% transparency
- **Labels**: 
  - X-axis: "Period"
  - Y-axis: Metric name (capitalized, underscores replaced with spaces)
  - Title: "{COMPANY} - {METRIC} Trend"
- **Size**: 10" × 6" at 100 DPI
- **Layout**: Tight layout with 45° x-axis rotation

**Example**:
```python
from app.core.plot_generator import plot_metric

series = [("Q1 2024", 100.5), ("Q2 2024", 105.3), ("Q3 2024", 110.2)]
plot_b64 = plot_metric(series, "AAPL", "revenue")
# Returns: "iVBORw0KGgoAAAANSUhEUgAAA..."
```

---

#### 4. `generate_plot_from_rag_output(rag_text: str) -> Optional[Dict[str, Any]]`
**Purpose**: Complete orchestration pipeline: extract → query → plot → return JSON.

**Inputs**:
- `rag_text`: Natural-language output from RAG model

**Outputs**:
- JSON-compatible dictionary:
  ```json
  {
    "company": "AAPL",
    "metric": "revenue",
    "data_points": 8,
    "is_trend": true,
    "plot_base64": "iVBORw0KGgoAAAANSUhEUgAAA..."
  }
  ```
- `None` if any step fails

**Pipeline Steps**:
1. Extract parameters using `extract_plot_params()`
2. Fetch company ID using `fetch_company_id()`
3. Query time-series using `fetch_metric_series()`
4. Generate plot using `plot_metric()`
5. Return JSON response

**Error Handling**:
- Graceful None returns at each step
- Detailed console logging for debugging
- No exceptions raised (safe for API usage)

**Example**:
```python
from app.core.plot_generator import generate_plot_from_rag_output

rag_output = "Microsoft showed consistent net income growth throughout 2024"
result = generate_plot_from_rag_output(rag_output)
# Returns full JSON with company, metric, and base64 plot
```

---

### Helper Functions

#### `_get_db_connection() -> psycopg2.connection`
Creates a PostgreSQL connection from `settings.database_url`.

**Required**: `DATABASE_URL` environment variable.

---

#### `fetch_company_id(ticker: str) -> Optional[int]`
Looks up a company's database ID by stock ticker.

---

## API Integration

### POST `/api/plot`

**Request**:
```json
{
  "user_id": "user123",
  "question": "Show me Apple revenue growth trends"
}
```

**Response (Success)**:
```json
{
  "company": "AAPL",
  "metric": "revenue",
  "data_points": 8,
  "is_trend": true,
  "plot_base64": "iVBORw0KGgoAAAANSUhEUgAAA..."
}
```

**Response (Failure)**:
```json
{
  "error": "Could not generate plot",
  "message": "Unable to extract company ticker or financial metric from input"
}
```

**Usage**:
```bash
curl -X POST "http://localhost:8000/api/plot" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","question":"Apple revenue trend over 2024"}'
```

---

## Configuration

### Required Environment Variables

```bash
# Database connection (required for plot generation)
DATABASE_URL=postgresql://user:password@localhost:5432/financials
```

### Optional Configuration (in `.env`)

- `VECTOR_DB_DIR`: Vector store location (default: `./data/vectorstore`)
- `OPENAI_API_KEY`: For RAG embeddings (if using OpenAI)
- `OLLAMA_MODEL`: Local LLM for entity extraction (if using Ollama)

---

## Supported Companies & Metrics

### Companies
- AAPL (Apple)
- MSFT (Microsoft)
- GOOGL (Google)
- TSLA (Tesla)
- AMZN (Amazon)
- META (Meta)
- NVDA (NVIDIA)

**To add new companies**: Update `COMPANY_TICKERS` list in `plot_generator.py` and insert rows into `companies` table in PostgreSQL.

### Financial Metrics
- `revenue` — Total revenue/sales
- `net_income` — Bottom-line profit
- `operating_income` — Operating profit
- `eps` — Earnings per share
- `total_assets` — Total assets
- `total_liabilities` — Total liabilities
- `equity` — Shareholders' equity

**To add new metrics**: Update `FINANCIAL_METRICS` list and add columns to `financial_metrics` table in PostgreSQL schema.

---

## Database Schema

The module queries the following PostgreSQL tables:

### `companies`
```sql
id (SERIAL PRIMARY KEY)
ticker (VARCHAR UNIQUE)
name (VARCHAR)
-- ...
```

### `financial_metrics`
```sql
id (SERIAL PRIMARY KEY)
company_id (FOREIGN KEY)
period (VARCHAR)  -- e.g., "Q1 2024", "2024-01-31"
revenue (NUMERIC)
net_income (NUMERIC)
operating_income (NUMERIC)
eps (NUMERIC)
total_assets (NUMERIC)
total_liabilities (NUMERIC)
equity (NUMERIC)
-- ...
```

See `db/schema.sql` for full schema and sample data.

---

## Usage Examples

### Example 1: Simple RAG Integration

```python
from app.core.chains import answer_financial_question
from app.core.plot_generator import generate_plot_from_rag_output

# Get RAG answer
rag_result = answer_financial_question("How is Apple's revenue trending?")
answer_text = rag_result.get("answer", "")

# Generate plot from RAG output
plot_result = generate_plot_from_rag_output(answer_text)

if plot_result:
    print(f"Generated plot for {plot_result['company']} {plot_result['metric']}")
    print(f"Data points: {plot_result['data_points']}")
else:
    print("Could not generate plot from this query")
```

### Example 2: Custom Entity Extraction

```python
from app.core.plot_generator import extract_plot_params, fetch_company_id, fetch_metric_series, plot_metric

# Manual extraction from custom source
custom_text = "Tesla's operating income in 2024"
params = extract_plot_params(custom_text)

if params:
    company_id = fetch_company_id(params["company"])
    series = fetch_metric_series(company_id, params["metric"])
    plot_b64 = plot_metric(series, params["company"], params["metric"])
    
    # Use plot_b64 in HTML/JSON response
```

### Example 3: Testing

```python
# Test mode (uses DATABASE_URL from .env)
if __name__ == "__main__":
    example_rag_output = """
    Apple Inc. (AAPL) has shown consistent revenue growth over the past quarters.
    In Q1 2024, the company reported strong financial performance with increasing net income.
    """
    
    result = generate_plot_from_rag_output(example_rag_output)
    if result:
        print(f"Success: {result['company']} - {result['metric']}")
        print(f"Plot size: {len(result['plot_base64'])} chars")
    else:
        print("Failed to generate plot (check DATABASE_URL)")
```

Run as:
```bash
cd /d "project LangChain"
export PYTHONPATH=.
py app/core/plot_generator.py
```

---

## Error Handling & Debugging

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `DATABASE_URL not configured` | Missing `.env` or env var | Set `DATABASE_URL=postgresql://...` in `.env` |
| `Company AAPL not found` | Ticker not in DB or case mismatch | Insert company into `companies` table or check ticker spelling |
| `No data found for AAPL revenue` | Missing metric data | Populate `financial_metrics` table with sample data |
| `ModuleNotFoundError: matplotlib` | Dependency not installed | Run `pip install -r requirements.txt` |
| `Empty series data` | No historical data for metric | Check `financial_metrics` table has non-NULL values |

### Debugging Steps

1. **Check database connectivity**:
   ```python
   from app.core.plot_generator import _get_db_connection
   conn = _get_db_connection()  # Raises ValueError if DATABASE_URL missing
   ```

2. **Test extraction**:
   ```python
   from app.core.plot_generator import extract_plot_params
   params = extract_plot_params("Your test text here")
   print(params)  # Should show company, metric, is_trend
   ```

3. **Inspect database**:
   ```bash
   psql $DATABASE_URL -c "SELECT * FROM companies LIMIT 5;"
   psql $DATABASE_URL -c "SELECT company_id, period, revenue FROM financial_metrics LIMIT 5;"
   ```

4. **Enable logging** (add to `plot_generator.py`):
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

---

## Performance Considerations

- **Extraction**: Regex-based, O(1) complexity
- **Database Queries**: Single parameterized query per metric, indexed on `(company_id, period)`
- **Plotting**: Matplotlib render time ~100-200ms depending on data size
- **Base64 Encoding**: Negligible overhead

**Optimization Tips**:
- Index `financial_metrics(company_id, period)` for faster queries
- Cache plots if querying same metric multiple times
- Consider pagination for very large datasets (>100 data points)

---

## Future Enhancements

- [ ] Support multiple metrics on same plot (e.g., revenue vs. net_income)
- [ ] LLM-based entity extraction (instead of regex)
- [ ] Interactive plots (Plotly instead of matplotlib)
- [ ] Plot caching with Redis
- [ ] Confidence scores for extracted entities
- [ ] Support for other chart types (bar, scatter, heatmap)
- [ ] Multi-company comparison plots
- [ ] Forecast overlays using ARIMA/Prophet

---

## Testing

### Unit Tests

```python
# test_plot_generator.py
import pytest
from app.core.plot_generator import extract_plot_params, plot_metric

def test_extract_apple_revenue():
    text = "Apple revenue growth is strong"
    params = extract_plot_params(text)
    assert params["company"] == "AAPL"
    assert params["metric"] == "revenue"

def test_plot_metric_basic():
    series = [("Q1", 100), ("Q2", 110), ("Q3", 120)]
    plot_b64 = plot_metric(series, "AAPL", "revenue")
    assert plot_b64.startswith("iVBORw0KGgo")  # PNG magic bytes
    assert len(plot_b64) > 1000  # Non-trivial size
```

---

## License & Attribution

Part of the Financial RAG project. Uses:
- **matplotlib**: https://matplotlib.org
- **psycopg2**: https://www.psycopg.org
- **PostgreSQL**: https://www.postgresql.org
