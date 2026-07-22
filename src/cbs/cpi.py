import requests

CPI_TABLE_ID = "83131ENG"

_cpi_cache = {}

def _get_cpi_data(years: tuple[int, ...]):
    """Fetch CPI rows for any number of years. Years is a tuple so the result can be cached."""
    years_to_fetch = [year for year in years if str(year) not in _cpi_cache]
    if not years_to_fetch:
        return [row for year in years for row in _cpi_cache[str(year)].values()]

    # CBS uses 'JJ00' suffixes to denote yearly averages (e.g., '2023JJ00')
    periods = [f"{y}JJ00" for y in years_to_fetch]

    # Query the CBS OData API v4 endpoint directly
    url = f"https://opendata.cbs.nl/ODataApi/odata/{CPI_TABLE_ID}/TypedDataSet"
    # Build filter like: (Periods eq '2020JJ00' or Periods eq '2021JJ00' ...)
    filters = " or ".join(f"Periods eq '{p}'" for p in periods)
    params = {"$filter": f"({filters})"}

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json().get('value', [])

    for row in data:
        year = row.get("Periods", "")[:4]
        if year not in _cpi_cache:
            _cpi_cache[year] = {}
        _cpi_cache[year][row.get("ExpenditureCategories", "").strip().lower()] = row

    return data

def get_cpi_multiplier(year_a: int, year_b: int, cpi_code: str = "T001112") -> float:
    """
    Fetches CBS CPI data to calculate the inflation multiplier between two years.
    
    Args:
        year_a: The base year (e.g., 2018).
        year_b: The target year (e.g., 2023).
        cpi_code: The COICOP category code. Default 'T001112' represents 'All items'.
        table_id: The CBS StatLine table ID. Default '83131ENG' is the English CPI 2015=100.
        
    Returns:
        A float factor you can multiply a year_a value by to get its year_b equivalent.
    """
    # fetch only the two years we need
    data = _get_cpi_data((year_a, year_b))

    cpi_a, cpi_b = None, None

    for row in data:
        # Check if the row belongs to the target CPI category (e.g., '000000')
        # We check values() to be agnostic of the specific dimension column name 
        # (which might be 'ArticleGroups' or 'ProductGroepen' depending on the table)
        if cpi_code.lower().strip() == row.get("ExpenditureCategories", "").lower().strip():
            period = row.get("Periods")
        # CBS primary metrics often end in '_1' (e.g., 'ConsumerPriceIndex_1')
        cpi_value = next((val for key, val in row.items() if key.endswith("_1") and isinstance(val, (int, float))), None)

        if period == f"{year_a}JJ00":
            cpi_a = cpi_value
        elif period == f"{year_b}JJ00":
            cpi_b = cpi_value

    if cpi_a is None and cpi_b is None:
        raise ValueError(f"Could not locate data for CPI code '{cpi_code}' in both {year_a} and {year_b}.")
    elif cpi_a is None:
        raise ValueError(f"Could not locate data for CPI code '{cpi_code}' in {year_a}.")
    elif cpi_b is None:
        raise ValueError(f"Could not locate data for CPI code '{cpi_code}' in {year_b}.")
        
    return cpi_b / cpi_a

def get_cpi_weight(year: int, cpi_code: str = "T001112") -> float:
    cpi_data = _get_cpi_data((year,))
    for row in cpi_data:
        if cpi_code.lower().strip() == row.get("ExpenditureCategories", "").lower().strip():
            weight = next((val for key, val in row.items() if key.lower().startswith("weighting") and isinstance(val, (int, float))), None)
            if weight is not None:
                return weight
    return None