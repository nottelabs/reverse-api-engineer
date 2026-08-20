# Apple Jobs API - Reverse Engineered Client

This directory contains a reverse-engineered Python client for the Apple Jobs API, extracted from HAR file analysis.

## 📋 API Overview

The Apple Jobs API provides programmatic access to job listings on `jobs.apple.com`. The API uses a simple REST architecture with JSON payloads.

### Base URL
```
https://jobs.apple.com/api/v1
```

## 🔍 Discovered Endpoints

### 1. GET `/api/v1/CSRFToken`

**Purpose:** Obtain a CSRF token required for search requests

**Authentication:** None required (creates session cookies)

**Request Headers:**
- Standard browser headers
- `browserlocale`: e.g., "en-us", "fr-fr"
- `locale`: e.g., "EN_US", "FR_FR"

**Response:**
- **Status:** 200 OK
- **Headers:**
  - `x-apple-csrf-token`: The CSRF token (required for POST requests)
  - `set-cookie`: Session cookies (`jobs`, `jssid`, `AWSALBAPP-*`)

**Example:**
```bash
curl -X GET 'https://jobs.apple.com/api/v1/CSRFToken' \
  -H 'browserlocale: en-us' \
  -H 'locale: EN_US'
```

---

### 2. POST `/api/v1/search`

**Purpose:** Search for job postings with filters and pagination

**Authentication:**
- Requires CSRF token in `x-apple-csrf-token` header
- Requires session cookies from CSRFToken endpoint

**Request Headers:**
- `Content-Type: application/json`
- `x-apple-csrf-token`: Token from CSRFToken endpoint
- `browserlocale`: Locale string (e.g., "en-us")
- `locale`: Uppercase locale with underscore (e.g., "EN_US")
- `Origin: https://jobs.apple.com`
- `Referer: https://jobs.apple.com/[locale]/search`

**Request Body:**
```json
{
  "query": "",
  "filters": {},
  "page": 1,
  "locale": "en-us",
  "sort": "",
  "format": {
    "longDate": "MMMM D, YYYY",
    "mediumDate": "MMM D, YYYY"
  }
}
```

**Request Parameters:**
- `query` (string): Search term for job title/description
- `filters` (object): Filter criteria (location, team, role, etc.)
- `page` (integer): Page number (1-indexed)
- `locale` (string): Locale for results (e.g., "en-us", "fr-fr")
- `sort` (string): Sort order (empty for default)
- `format` (object): Date format preferences

**Response:**
```json
{
  "res": {
    "searchResults": [
      {
        "id": "PIPE-200125391",
        "positionId": "200125391",
        "postingTitle": "Software Engineer",
        "postingDate": "Dec 22, 2025",
        "jobSummary": "Job description text...",
        "locations": [
          {
            "postLocationId": "postLocation-USA",
            "city": "Cupertino",
            "stateProvince": "California",
            "countryName": "United States",
            "metro": "",
            "region": "",
            "name": "Cupertino",
            "countryID": "iso-country-USA",
            "level": 3
          }
        ],
        "team": {
          "teamName": "Software Engineering",
          "teamID": "teamsAndSubTeams-SFTWR",
          "teamCode": "SFTWR"
        },
        "reqId": "PIPE-200125391",
        "standardWeeklyHours": 40,
        "homeOffice": false,
        "isMultiLocation": false,
        "transformedPostingTitle": "software-engineer"
      }
    ],
    "totalRecords": 6178,
    "talentLimitDetails": {},
    "talentRolesInfoById": {}
  }
}
```

**Response Fields:**
- `searchResults`: Array of job objects
  - `id`: Unique job identifier
  - `positionId`: Position ID (used in job URLs)
  - `postingTitle`: Job title
  - `postingDate`: Date the job was posted
  - `jobSummary`: Full job description
  - `locations`: Array of location objects
  - `team`: Team/department information
  - `transformedPostingTitle`: URL-friendly title
  - `standardWeeklyHours`: Expected weekly hours
  - `homeOffice`: Whether remote work is available
- `totalRecords`: Total number of matching jobs

**Job URL Format:**
```
https://jobs.apple.com/en-us/details/{positionId}/{transformedPostingTitle}
```

**Example:**
```bash
curl -X POST 'https://jobs.apple.com/api/v1/search' \
  -H 'Content-Type: application/json' \
  -H 'x-apple-csrf-token: YOUR_CSRF_TOKEN' \
  -H 'browserlocale: en-us' \
  -H 'locale: EN_US' \
  -H 'Cookie: jobs=...; jssid=...' \
  -d '{
    "query": "engineer",
    "filters": {},
    "page": 1,
    "locale": "en-us",
    "sort": "",
    "format": {
      "longDate": "MMMM D, YYYY",
      "mediumDate": "MMM D, YYYY"
    }
  }'
```

---

## 🔐 Authentication Flow

1. **Get CSRF Token:**
   - Call `GET /api/v1/CSRFToken`
   - Extract token from `x-apple-csrf-token` response header
   - Save session cookies (`jobs`, `jssid`, `AWSALBAPP-*`)

2. **Make Search Requests:**
   - Include CSRF token in `x-apple-csrf-token` header
   - Include session cookies in requests
   - All POST requests require the CSRF token

## 📦 Python Client Usage

### Installation

The client requires only the `requests` library:

```bash
pip install requests
```

### Basic Usage

```python
from api_client import AppleJobsAPI

# Initialize the client
client = AppleJobsAPI(locale="en-us")

# Search for jobs
jobs = client.search_jobs(query="engineer", page=1)

# Print job details
for job in jobs:
    print(f"Title: {job.postingTitle}")
    print(f"Location: {job.locations[0].name if job.locations else 'N/A'}")
    print(f"URL: {job.url}")
    print(f"Description: {job.jobSummary[:100]}...")
    print("-" * 80)
```

### Advanced Usage

```python
# Get total number of jobs
total = client.get_total_jobs(query="software")
print(f"Total software jobs: {total}")

# Search with filters (example structure)
filtered_jobs = client.search_jobs(
    query="engineer",
    filters={
        "postLocation": ["postLocation-USA"],
        "team": ["teamsAndSubTeams-SFTWR"]
    },
    page=1
)

# Get all jobs with pagination
all_jobs = client.search_all_jobs(
    query="data scientist",
    max_pages=10  # Limit to first 10 pages
)
print(f"Fetched {len(all_jobs)} total jobs")
```

### Extracting Specific Fields

The user requested: **URL, Title, Location, Description**

```python
# Get jobs and extract requested fields
jobs = client.search_jobs(query="", page=1)

for job in jobs:
    data = {
        "url": job.url,
        "title": job.postingTitle,
        "location": job.locations[0].name if job.locations else "N/A",
        "description": job.jobSummary
    }
    print(data)
```

### Output to CSV

```python
import csv

jobs = client.search_all_jobs(max_pages=5)

with open('apple_jobs.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['url', 'title', 'location', 'description'])
    writer.writeheader()

    for job in jobs:
        writer.writerow({
            'url': job.url,
            'title': job.postingTitle,
            'location': job.locations[0].name if job.locations else 'N/A',
            'description': job.jobSummary
        })

print(f"Exported {len(jobs)} jobs to apple_jobs.csv")
```

## 📊 Data Structure

### Job Object

Each job contains the following key information:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique job identifier |
| `positionId` | string | Position ID (used in URLs) |
| `postingTitle` | string | Job title |
| `postingDate` | string | Date posted |
| `jobSummary` | string | Full job description |
| `locations` | array | Array of location objects |
| `team` | object | Team/department info |
| `standardWeeklyHours` | integer | Expected weekly hours |
| `homeOffice` | boolean | Remote work available |
| `url` | string | Generated job URL |

### Location Object

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Location name |
| `city` | string | City name |
| `stateProvince` | string | State/province |
| `countryName` | string | Country name |
| `countryID` | string | ISO country code |

## 🎯 Common Use Cases

### 1. Get All Jobs in a Specific Location

```python
# Note: You'll need to discover the correct location ID
jobs = client.search_jobs(
    filters={"postLocation": ["postLocation-FRA"]},  # France
    page=1
)
```

### 2. Search by Keyword

```python
engineering_jobs = client.search_jobs(query="software engineer")
```

### 3. Fetch All Available Jobs

```python
# Warning: This may take a while for thousands of jobs
all_jobs = client.search_all_jobs()
```

### 4. Get Job Count for Different Queries

```python
queries = ["engineer", "designer", "manager", "retail"]
for query in queries:
    count = client.get_total_jobs(query=query)
    print(f"{query}: {count} jobs")
```

## ⚠️ Important Notes

1. **Rate Limiting:** The API doesn't appear to have explicit rate limits in the HAR file, but be respectful and avoid hammering the server.

2. **CSRF Token Lifespan:** CSRF tokens appear to have a session-based lifespan. The client handles token refresh automatically.

3. **Pagination:** Results appear to return ~20 jobs per page. Use `totalRecords` to calculate total pages.

4. **Filters:** The exact filter structure may vary. Common filters include:
   - `postLocation`: Location IDs
   - `team`: Team/department IDs
   - `role`: Role type IDs

5. **Locale Support:** The API supports multiple locales (en-us, fr-fr, etc.). Results are localized based on the locale parameter.

6. **Job URLs:** Job URLs follow the pattern:
   ```
   https://jobs.apple.com/{locale}/details/{positionId}/{transformedPostingTitle}
   ```

## 🛠️ Testing

Run the example script to test the client:

```bash
python api_client.py
```

This will demonstrate:
- Fetching the first page of jobs
- Searching with queries
- Getting total job counts
- Pagination

## 📝 API Changes

This client was reverse-engineered from a HAR file captured on **2025-12-22**. Apple may change their API at any time without notice. If the client stops working:

1. Capture a new HAR file from the jobs.apple.com website
2. Inspect the network requests for API changes
3. Update the client accordingly

## 🤝 Contributing

If you discover additional API endpoints or filter options, please document them here!

## ⚡ Quick Start Example

```python
#!/usr/bin/env python3
from api_client import AppleJobsAPI
import json

# Initialize client
client = AppleJobsAPI(locale="en-us")

# Get first page of jobs
jobs = client.search_jobs(page=1)

# Extract requested fields: URL, Title, Location, Description
results = []
for job in jobs:
    results.append({
        "url": job.url,
        "title": job.postingTitle,
        "location": job.locations[0].name if job.locations else "N/A",
        "description": job.jobSummary
    })

# Print as JSON
print(json.dumps(results, indent=2, ensure_ascii=False))
```

Save this as `quick_example.py` and run it to get started immediately!

---

## Don't want to maintain this?

This client was reverse-engineered locally and is yours to keep — but it is
pinned to jobs.apple.com's API as it looked on the day of capture, and nothing here
re-engineers it when that changes.

[Anything](https://anything.notte.cc?utm_source=rae&utm_medium=example&utm_campaign=apple)
is the hosted version of this project: you describe the task and get back a
deployed API function, with the proxies, retries, and repair-on-change handled
for you. Check whether Apple's careers site is already covered before building anything:

```bash
reverse-api-engineer marketplace search --site jobs.apple.com
```

If nothing matches yet, describe the task at
[anything.notte.cc](https://anything.notte.cc?utm_source=rae&utm_medium=example&utm_campaign=apple)
and it gets built for you. Agents can search the same catalogue by pointing an
MCP client at `https://anything.notte.cc/mcp`.
