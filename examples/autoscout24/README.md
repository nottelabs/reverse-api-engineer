# AutoScout24.ch API Client

A production-ready Python client for scraping car listings from autoscout24.ch. This client interacts with the official AutoScout24 REST API endpoints discovered through reverse engineering.

## 🚀 Features

- **Simple API**: Easy-to-use Python interface for searching car listings
- **Type-Safe**: Full type hints and enums for all parameters
- **Production-Ready**: Error handling, proper HTTP headers, and session management
- **Comprehensive**: Support for all major search filters (make, model, price, year, fuel type, etc.)
- **Well-Documented**: Extensive docstrings and examples

## 📋 API Endpoints Discovered

Through network traffic analysis, the following endpoints were identified:

1. **Search Listings API**
   - `POST https://api.autoscout24.ch/v1/listings/search?language={de|fr|it|en}`
   - Main endpoint for searching car listings with filters

2. **Quality Logos API**
   - `GET https://api.autoscout24.ch/v1/quali-logos/{seller_id}?language={de|fr|it|en}`
   - Get quality badges/certifications for sellers

3. **Listing Details**
   - Available at: `https://www.autoscout24.ch/{language}/d/{listing_id}`
   - Details are server-side rendered in HTML (not via separate API)

## 🔐 Authentication

**No authentication required!** The AutoScout24 search API is publicly accessible without API keys or tokens.

The client automatically includes:
- Standard browser User-Agent headers
- Proper Referer and Origin headers
- Content-Type: application/json

## 📦 Installation

```bash
# Clone or copy the api_client.py file
# Install required dependency
pip install requests
```

## 💻 Usage

### Basic Usage

```python
from api_client import AutoScout24Client, VehicleCategory, FuelType, BodyType

# Initialize client
client = AutoScout24Client(language="de")

# Search for cars
results = client.search_listings(
    make_key="bmw",
    model_key="x1",
    price_from=20000,
    price_to=50000,
    page=0,
    size=20
)

# Print results
for listing in results.get('listings', []):
    print(f"{listing['title']} - CHF {listing['price']:,}")
```

### Search by Make

```python
# Search all BMW vehicles under CHF 50,000
results = client.search_by_make("bmw", price_to=50000)
```

### Search Electric Vehicles

```python
# Find electric cars
results = client.search_electric_cars(
    price_from=30000,
    price_to=60000,
    year_from=2020
)
```

### Search with Multiple Filters

```python
# Used SUVs with warranty, 2020 or newer
results = client.search_listings(
    body_type=BodyType.SUV,
    condition_type=ConditionType.USED,
    has_warranty=True,
    year_from=2020,
    price_from=15000,
    price_to=40000,
    mileage_to=100000,
    page=0,
    size=50
)
```

### Pagination

```python
# Get first page
page_1 = client.search_listings(make_key="audi", page=0, size=20)

# Get second page
page_2 = client.search_listings(make_key="audi", page=1, size=20)

# Get total count
total = page_1.get('totalResultCount', 0)
print(f"Total listings: {total}")
```

### Sorting Results

```python
from api_client import SortType, SortOrder

# Sort by price (lowest first)
results = client.search_listings(
    make_key="mercedes-benz",
    sort_type=SortType.PRICE,
    sort_order=SortOrder.ASC
)

# Sort by year (newest first)
results = client.search_listings(
    make_key="tesla",
    sort_type=SortType.YEAR,
    sort_order=SortOrder.DESC
)
```

## 🔍 Available Search Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `vehicle_categories` | List[VehicleCategory] | Filter by vehicle type | `[VehicleCategory.CAR]` |
| `make_key` | str | Car manufacturer | `"bmw"`, `"audi"`, `"mercedes-benz"` |
| `model_key` | str | Car model | `"x1"`, `"a3"`, `"c-class"` |
| `body_type` | BodyType | Vehicle body type | `BodyType.SUV`, `BodyType.SEDAN` |
| `condition_type` | ConditionType | New or used | `ConditionType.NEW`, `ConditionType.USED` |
| `fuel_type` | FuelType | Fuel type | `FuelType.ELECTRIC`, `FuelType.HYBRID` |
| `price_from` | int | Minimum price (CHF) | `20000` |
| `price_to` | int | Maximum price (CHF) | `50000` |
| `year_from` | int | Minimum year | `2020` |
| `year_to` | int | Maximum year | `2025` |
| `mileage_from` | int | Minimum mileage (km) | `0` |
| `mileage_to` | int | Maximum mileage (km) | `100000` |
| `power_from` | int | Minimum power (HP) | `150` |
| `power_to` | int | Maximum power (HP) | `500` |
| `seller_ids` | List[int] | Filter by seller IDs | `[24860, 12345]` |
| `excluding_ids` | List[int] | Exclude listing IDs | `[20102453]` |
| `zip_code` | str | Search near ZIP code | `"8001"` |
| `radius_km` | int | Search radius (km) | `50` |
| `has_leasing_only` | bool | Only leasing offers | `True` |
| `has_warranty` | bool | Only with warranty | `True` |
| `has_accident_history` | bool | Accident-free only | `False` |
| `page` | int | Page number (0-indexed) | `0`, `1`, `2` |
| `size` | int | Results per page | `20`, `50`, `100` |

## 🎯 Enums

### VehicleCategory
- `CAR` - Personenwagen
- `CAMPER` - Wohnmobil
- `TRUCK` - Nutzfahrzeug
- `MOTORCYCLE` - Motorrad
- `TRAILER` - Anhänger

### BodyType
- `SUV` - SUV / Geländewagen
- `SEDAN` - Limousine
- `ESTATE` - Kombi
- `COUPE` - Coupé
- `CABRIOLET` - Cabriolet
- `SMALL_CAR` - Kleinwagen
- `PICKUP` - Pick-up
- `MINIVAN` - Kompaktvan / Minivan
- `BUS` - Bus

### FuelType
- `ELECTRIC` - Elektro
- `PETROL` - Benzin
- `DIESEL` - Diesel
- `HYBRID` - Hybrid
- `MHEV_PETROL` - Mild-Hybrid Benzin
- `MHEV_DIESEL` - Mild-Hybrid Diesel
- `PLUGIN_HYBRID` - Plug-in Hybrid

### ConditionType
- `NEW` - Neuwagen
- `PRE_REGISTERED` - Vorführwagen
- `DEMONSTRATION` - Demonstrationsfahrzeug
- `USED` - Occasion

### SortType
- `RELEVANCE` - Relevanz
- `PRICE` - Preis
- `MILEAGE` - Kilometerstand
- `YEAR` - Jahr
- `POWER` - Leistung

## 📊 Response Format

### Search Results Response

```json
{
  "listings": [
    {
      "id": 20102453,
      "title": "BMW X1 sDrive 20i 48V M Sport INNOVATIONSPAKET",
      "price": 37900,
      "currency": "CHF",
      "year": 2025,
      "mileage": 13280,
      "fuelType": "mhev-petrol",
      "transmission": "automatic",
      "power": 156,
      "powerUnit": "PS",
      "bodyType": "suv",
      "condition": "used",
      "seller": {
        "id": 24860,
        "name": "I.B.A. Automobile AG",
        "type": "dealer"
      },
      "location": {
        "city": "Niederlenz",
        "zipCode": "5702",
        "canton": "AG"
      },
      "images": ["url1", "url2"],
      "warranty": true,
      "accidentFree": true
    }
  ],
  "totalResultCount": 154237,
  "pagination": {
    "currentPage": 0,
    "pageSize": 20,
    "totalPages": 7712
  }
}
```

## 🧪 Testing

Run the included examples:

```bash
python api_client.py
```

This will execute several example searches and display results.

## ⚠️ Limitations & Caveats

1. **Listing Details**: Full listing details are embedded in HTML pages, not available through a separate API endpoint. You'll need to scrape the HTML page at `https://www.autoscout24.ch/{language}/d/{listing_id}` for complete details.

2. **Rate Limiting**: While not explicitly enforced, be respectful and avoid excessive requests. Add delays between requests if scraping large amounts of data.

3. **Make/Model Keys**: Make and model keys use lowercase, hyphenated format:
   - BMW → `"bmw"`
   - Mercedes-Benz → `"mercedes-benz"`
   - Audi A3 → `"a3"`

4. **API Stability**: This is a reverse-engineered API. AutoScout24 may change endpoints or parameters without notice.

5. **Images**: Image URLs are CDN links that may have expiration or access restrictions.

## 🛠️ Advanced Usage

### Custom Headers

```python
client = AutoScout24Client(language="de")

# Add custom headers
client.session.headers.update({
    "X-Custom-Header": "value"
})
```

### Error Handling

```python
try:
    results = client.search_listings(make_key="bmw")
except requests.HTTPError as e:
    print(f"HTTP error occurred: {e}")
except requests.RequestException as e:
    print(f"Request failed: {e}")
```

### Session Reuse

The client uses a persistent `requests.Session`, which reuses TCP connections for better performance.

## 📝 Popular Makes & Models

Common make keys:
- `bmw`, `audi`, `mercedes-benz`, `volkswagen` (or `vw`)
- `tesla`, `porsche`, `ford`, `toyota`, `volvo`
- `hyundai`, `kia`, `nissan`, `honda`, `mazda`
- `skoda`, `seat`, `renault`, `peugeot`, `citroen`

Common model keys:
- BMW: `x1`, `x3`, `x5`, `3-series`, `5-series`
- Audi: `a1`, `a3`, `a4`, `q3`, `q5`, `q7`
- Tesla: `model-3`, `model-s`, `model-x`, `model-y`

## 🔗 Related Resources

- [AutoScout24 Website](https://www.autoscout24.ch)
- [AutoScout24 Search Page](https://www.autoscout24.ch/de/s)
- [Python Requests Documentation](https://requests.readthedocs.io/)

## 📄 License

This is a reverse-engineered API client for educational purposes. Use responsibly and in accordance with AutoScout24's Terms of Service.

## 🤝 Contributing

This client was generated through automated reverse engineering. Improvements and bug fixes are welcome!

---

**Generated by Claude Code** | 2026-01-03

---

## Don't want to maintain this?

This client was reverse-engineered locally and is yours to keep — but it is
pinned to autoscout24.com's API as it looked on the day of capture, and nothing here
re-engineers it when that changes.

[Anything](https://anything.notte.cc?utm_source=rae&utm_medium=example&utm_campaign=autoscout24)
is the hosted version of this project: you describe the task and get back a
deployed API function, with the proxies, retries, and repair-on-change handled
for you. Check whether AutoScout24 listings is already covered before building anything:

```bash
reverse-api-engineer marketplace search --site autoscout24.com
```

If nothing matches yet, describe the task at
[anything.notte.cc](https://anything.notte.cc?utm_source=rae&utm_medium=example&utm_campaign=autoscout24)
and it gets built for you. Agents can search the same catalogue by pointing an
MCP client at `https://anything.notte.cc/mcp`.
