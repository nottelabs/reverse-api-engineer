# IKEA API Client

A production-ready Python client for interacting with IKEA's e-commerce APIs. This client provides comprehensive access to IKEA's product catalog, search functionality, and shopping cart management.

## Features

- 🔍 **Product Search** - Search IKEA's entire product catalog
- 📦 **Product Details** - Get detailed product information by item number
- 🛒 **Cart Management** - Add, remove, and update cart items
- 💰 **Price Calculations** - Calculate prices with tax and discounts
- 🔐 **Guest Authentication** - Automatic token management

## Discovered APIs

This client interfaces with the following IKEA API endpoints:

### 1. **Search API** (`sik.search.blue.cdtapps.com`)
- **Endpoint**: `POST /us/en/search`
- **Purpose**: Product search with filters and sorting
- **Features**: Full-text search, faceted filtering, pagination

### 2. **Cart API** (`prod.cart.caas.selling.ingka.com`)
- **Endpoints**:
  - `GET /api/v1/us` - Retrieve cart
  - `POST /api/v1/us/items` - Add items to cart
  - `PATCH /api/v1/us/items/{itemNo}` - Update quantity
  - `DELETE /api/v1/us/items/{itemNo}` - Remove items
- **Purpose**: Shopping cart management
- **Features**: Real-time pricing, item details, quantity management

### 3. **Web API** (`web-api.ikea.com`)
- **Endpoints**:
  - `/v2/calculation/hyperlink/us/en/{amount}` - Price calculations
  - `/wdm/api/discounts/get` - Get product discounts
- **Purpose**: Pricing and discount information

**Note**: Product details are fetched via the Search API using item numbers, as IKEA's direct product API requires additional authentication that is not publicly documented.

### 4. **Authentication API** (`api.ingka.ikea.com`)
- **Endpoint**: `POST /guest/token`
- **Purpose**: Guest user authentication
- **Returns**: JWT access token valid for 720 hours

### 5. **Accounts API** (`accounts.ikea.com`)
- **Endpoint**: `GET /cim/us/en/v1/profile/token`
- **Purpose**: User profile and authentication

## Authentication

The IKEA API uses **JWT-based guest authentication**:

1. The client requests a guest token from `api.ingka.ikea.com/guest/token`
2. Server responds with a JWT token valid for 720 hours (30 days)
3. Token is included in subsequent requests as `Authorization: Bearer {token}`
4. No username/password required for guest operations
5. Token is automatically refreshed when expired

**Token Format**:
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImVxSFFLR3duR3...",
  "expires_in": "720h",
  "token_type": "Bearer"
}
```

## Installation

### Requirements
- Python 3.7+
- `requests` library

### Install Dependencies

```bash
pip install requests
```

## Usage

### Basic Example

```python
from api_client import IKEAAPIClient

# Initialize the client
client = IKEAAPIClient(country="us", language="en")

# Search for products
results = client.search_products("chair", limit=10)

# Get products from results
for result in results.get('results', []):
    if result.get('component') == 'PRIMARY_AREA':
        for product in result.get('products', []):
            print(f"{product['name']} - ${product['salesPrice']['numeral']}")
```

### Search Products

```python
# Basic search
results = client.search_products("sofa")

# Search with limit
results = client.search_products("desk", limit=20)

# Search with sorting
results = client.search_products("lamp", sort="PRICE_LOW_TO_HIGH")
```

### Get Product Details

```python
# Get detailed product information by item number
product = client.get_product_details("59305928")  # POÄNG chair

# Access product information
print(f"Name: {product['name']}")
print(f"Type: {product['typeName']}")
print(f"Price: ${product['salesPrice']['numeral']}")
print(f"Currency: {product['salesPrice']['currencyCode']}")

# Works with or without 'S' prefix
product = client.get_product_details("S59305928")  # Also works
```

### Cart Management

```python
# Get current cart
cart = client.get_cart()
print(f"Cart total: ${cart['cart']['price']['totalPrice']['current']['exclTax']}")

# Add item to cart
client.add_to_cart("59305928", quantity=2)

# Update quantity
client.update_cart_quantity("59305928", quantity=3)

# Remove item
client.remove_from_cart("59305928")
```

### Price Calculations

```python
# Calculate price with tax
price_info = client.calculate_price(149.00)
print(price_info)
```

### Get Discounts

```python
# Check for discounts on products
discounts = client.get_discounts(["59305928", "80153800"])

for discount in discounts.get('discounts', []):
    print(f"Discount: {discount['amount']} on {discount['itemNo']}")
```

## Response Formats

### Search Response
```json
{
  "results": [
    {
      "component": "PRIMARY_AREA",
      "products": [
        {
          "itemNo": "59305928",
          "name": "POÄNG",
          "typeName": "Armchair",
          "salesPrice": {
            "numeral": "149.00",
            "currencyCode": "USD"
          },
          "imageUrl": "https://www.ikea.com/us/en/images/products/...",
          "availability": {...}
        }
      ],
      "filters": [...],
      "collectionMetadata": {
        "start": 0,
        "end": 24,
        "max": 156
      }
    }
  ]
}
```

### Cart Response
```json
{
  "cartId": "507b55a8-b618-3eca-8c59-3fdd94831763",
  "cart": {
    "empty": false,
    "groups": [
      {
        "name": "DEFAULT",
        "items": [
          {
            "itemNo": "59305928",
            "quantity": 1.0,
            "info": {
              "name": "POÄNG",
              "category": "armchair",
              "formattedItemNo": "593.059.28"
            },
            "price": {
              "unitPrice": {
                "current": {
                  "exclTax": 149.0
                }
              }
            }
          }
        ]
      }
    ],
    "price": {
      "totalPrice": {
        "current": {
          "exclTax": 149.0
        }
      }
    }
  }
}
```

## Implementation Details

### Headers Required
- `User-Agent`: Standard browser user agent
- `Accept`: `application/json`
- `Accept-Language`: `{language}-{country.upper()},{language};q=0.9`
- `Authorization`: `Bearer {access_token}` (after authentication)

### API Versioning
- Search API uses version parameter: `v=20250507`
- Cart API uses versioned paths: `/api/v1/`
- Price calculation API uses versioned paths: `/v2/calculation/`

### Country & Language Support
The client supports multiple countries and languages. Common combinations:
- `us` / `en` - United States (English)
- `gb` / `en` - United Kingdom (English)
- `de` / `de` - Germany (German)
- `fr` / `fr` - France (French)
- `se` / `sv` - Sweden (Swedish)

## Limitations

1. **Guest Tokens Only**: This client uses guest authentication. Some features may require full user authentication.

2. **Product Details via Search**: Product details are fetched using the search API with item numbers, as IKEA's direct product API requires additional authentication.

3. **No Checkout**: The API client handles cart management but does not implement the checkout flow (payment, shipping).

4. **Rate Limiting**: IKEA may implement rate limiting. Be respectful with API calls.

5. **Country-Specific**: Product availability and prices vary by country. The client defaults to US.

6. **Cart Persistence**: Guest carts are session-based and may expire after inactivity.

7. **No Image Downloads**: The client provides image URLs but doesn't download images.

## Error Handling

The client raises exceptions for common errors:

```python
try:
    results = client.search_products("chair")
except Exception as e:
    print(f"Search failed: {e}")
```

## Testing

Run the built-in example:

```bash
python api_client.py
```

This will demonstrate all major features of the API client.

## Advanced Usage

### Custom Configuration

```python
from api_client import IKEAAPIClient, IKEAConfig

# Create custom config
config = IKEAConfig(
    country="gb",
    language="en"
)

# Initialize with custom config
client = IKEAAPIClient(country="gb", language="en")
```

### Session Management

```python
# The client uses a persistent session
# Access the session for custom requests
client.session.headers.update({'Custom-Header': 'value'})

# Make custom requests
response = client.session.get('https://www.ikea.com/custom/endpoint')
```

### Token Inspection

```python
# Check token status
if client.access_token:
    print(f"Token expires at: {client.token_expires_at}")
```

## Troubleshooting

**Problem**: "Failed to authenticate"
- **Solution**: Check your internet connection. IKEA's authentication endpoint may be temporarily unavailable.

**Problem**: "Search failed"
- **Solution**: Verify the country/language codes are valid. Try with default settings (us/en).

**Problem**: "Failed to add to cart"
- **Solution**: Ensure the product item number is correct and the product is available in your region.

## License

This is a reverse-engineered API client for educational purposes. Please respect IKEA's terms of service when using this client.

## Disclaimer

This is an unofficial API client and is not affiliated with, endorsed by, or sponsored by IKEA. Use at your own risk. The API structure may change without notice.

---

**Generated with Claude Code** 🤖

---

## Don't want to maintain this?

This client was reverse-engineered locally and is yours to keep — but it is
pinned to ikea.com's API as it looked on the day of capture, and nothing here
re-engineers it when that changes.

[Anything](https://anything.notte.cc?utm_source=rae&utm_medium=example&utm_campaign=ikea)
is the hosted version of this project: you describe the task and get back a
deployed API function, with the proxies, retries, and repair-on-change handled
for you. Check whether IKEA's product catalogue is already covered before building anything:

```bash
reverse-api-engineer marketplace search --site ikea.com
```

If nothing matches yet, describe the task at
[anything.notte.cc](https://anything.notte.cc?utm_source=rae&utm_medium=example&utm_campaign=ikea)
and it gets built for you. Agents can search the same catalogue by pointing an
MCP client at `https://anything.notte.cc/mcp`.
