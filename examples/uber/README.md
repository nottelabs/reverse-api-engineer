# Uber Careers API Client

> Reverse-engineered API client for fetching job listings from Uber's careers website.

## 📋 Overview

This Python client provides a clean, production-ready interface to interact with Uber's public careers API. It was reverse-engineered from HAR file analysis and supports fetching job listings with various filters including location, department, team, and line of business.

## 🔍 API Endpoints Discovered

### 1. **loadFilterOptions**
- **URL**: `https://www.uber.com/api/loadFilterOptions?localeCode=en`
- **Method**: POST
- **Purpose**: Retrieves all available filter options for job searches
- **Authentication**: None required
- **Request Body**: `{}`
- **Response**: Returns available locations, departments, teams, business lines, and time types

### 2. **loadSearchJobsResults**
- **URL**: `https://www.uber.com/api/loadSearchJobsResults?localeCode=en`
- **Method**: POST
- **Purpose**: Search for jobs with pagination and filtering
- **Authentication**: None required
- **Request Body**:
  ```json
  {
    "limit": 10,
    "page": 0,
    "params": {
      "department": [],
      "lineOfBusinessName": [],
      "location": [],
      "programAndPlatform": [],
      "team": []
    }
  }
  ```
- **Response**: Returns job listings with title, description, location, department, team, and more

## 🔐 Authentication Patterns

**No authentication required!** These are public API endpoints. However, the following headers are recommended for consistency with the web application:

- `x-csrf-token: x` - Simple CSRF token
- `Content-Type: application/json`
- `Origin: https://www.uber.com`
- `Referer: https://www.uber.com/us/en/careers/`
- Standard browser headers (User-Agent, Accept, etc.)

### Optional Cookies
The API works without cookies, but the web application uses these session tracking cookies:
- `jwt-session` - JWT session token
- `__cf_bm` - Cloudflare bot management
- `utag_main_*` - Analytics tracking
- `_ua` - User analytics
- `marketing_vistor_id` - Marketing tracking

**Note**: None of these cookies are required for API access.

## 📦 Installation

```bash
# Clone or download the api_client.py file
pip install requests  # Only dependency
```

## 🚀 Quick Start

```python
from api_client import UberCareersAPI

# Initialize the client
api = UberCareersAPI()

# Get all available filter options
filters = api.get_filter_options()
print(f"Available locations: {len(filters.locations)}")
print(f"Departments: {list(filters.departments.keys())}")

# Search for jobs
jobs, total = api.search_jobs(
    limit=20,
    locations=[{'country': 'USA', 'city': 'San Francisco'}],
    departments=['Engineering']
)

print(f"Found {total} jobs")
for job in jobs:
    print(f"{job.title} - {job.department} - {job.location.city}")
    print(f"URL: {job.url}")
```

## 📚 Usage Examples

### Example 1: Get Filter Options

```python
api = UberCareersAPI()
filters = api.get_filter_options()

# Browse available locations
for loc in filters.locations[:10]:
    print(f"{loc.city}, {loc.country_name}")

# Browse departments and their teams
for dept, teams in filters.departments.items():
    print(f"{dept}: {', '.join(teams[:3])}")
```

### Example 2: Search with Multiple Filters

```python
jobs, total = api.search_jobs(
    limit=50,
    page=0,
    departments=['Engineering', 'Data Science'],
    line_of_business=['Ridesharing', 'Uber Eats'],
    locations=[
        {'country': 'USA', 'region': 'California', 'city': 'San Francisco'},
        {'country': 'USA', 'region': 'New York', 'city': 'New York'}
    ],
    teams=['Machine Learning', 'Backend']
)
```

### Example 3: Fetch ALL Jobs with Pagination

```python
# Fetch all engineering jobs (automatically handles pagination)
all_jobs = api.get_all_jobs(
    departments=['Engineering'],
    max_results=None,  # Get all results
    page_size=50       # Fetch 50 per page
)

print(f"Total engineering jobs: {len(all_jobs)}")
```

### Example 4: Extract Job Data

```python
jobs, _ = api.search_jobs(limit=10)

for job in jobs:
    job_data = {
        'title': job.title,
        'url': job.url,
        'location': f"{job.location.city}, {job.location.country_name}",
        'description': job.description,
        'department': job.department,
        'team': job.team,
        'level': job.level,
        'timeType': job.time_type
    }
    print(job_data)
```

## 🏗️ Architecture

### Data Models

#### `Job`
- `id`: Unique job identifier
- `title`: Job title
- `description`: Full job description (HTML/Markdown)
- `url`: Direct URL to job posting
- `location`: Primary location (Location object)
- `all_locations`: All locations for this job
- `department`: Department name
- `team`: Team name
- `level`: Job level (e.g., "3", "4", "5B")
- `time_type`: "Full-Time" or "Part-Time"
- `creation_date`: ISO 8601 timestamp
- `updated_date`: ISO 8601 timestamp

#### `Location`
- `country`: 3-letter country code (e.g., "USA")
- `country_name`: Full country name
- `region`: State/province (optional)
- `city`: City name (optional)

#### `FilterOptions`
- `locations`: List of all available locations
- `departments`: Dict mapping departments to teams
- `line_of_business`: List of business lines
- `time_types`: List of employment types

### API Client Features

- **Automatic pagination**: `get_all_jobs()` handles pagination automatically
- **Rate limiting**: Built-in delay between requests (configurable)
- **Error handling**: Comprehensive error handling with logging
- **Type hints**: Full type annotations for IDE support
- **Dataclasses**: Clean, immutable data models

## 🔧 Configuration

```python
api = UberCareersAPI(
    locale_code='en',           # Language code (en, es, fr, etc.)
    timeout=30,                 # Request timeout in seconds
    rate_limit_delay=0.5        # Delay between requests in seconds
)
```

## 📊 Available Filters

### Departments (with teams)
- **Sales & Account Management**: Sales, Account Management
- **Engineering**: Backend, Machine Learning, Frontend, iOS, Android, etc.
- **Operations**: Operations, Local Operations, Regional Operations
- **Community Operations**: Community Operations, Support Operations
- **Product**: Product Management, Program Management
- **Data Science**: Data Scientist, Data Analyst
- **Marketing**: Marketing, Regional Marketing
- **And many more...**

### Line of Business
- Corporate
- Ridesharing
- Uber Eats
- Uber for Business

### Locations
75+ locations worldwide including:
- **USA**: San Francisco, New York, Chicago, Seattle, etc.
- **India**: Bangalore, Hyderabad, Gurgaon
- **Europe**: London, Paris, Berlin, Amsterdam, etc.
- **LATAM**: Sao Paulo, Mexico City, Buenos Aires, etc.
- **APAC**: Tokyo, Hong Kong, Seoul, Sydney, etc.

## 🎯 Use Cases

1. **Job Board Aggregators**: Fetch Uber jobs for job listing websites
2. **Career Analytics**: Analyze hiring trends, locations, and departments
3. **Job Alerts**: Build custom notification systems for new postings
4. **Market Research**: Study hiring patterns across regions and teams
5. **Application Automation**: Pre-filter jobs before applying

## ⚠️ Rate Limiting & Best Practices

1. **Respect rate limits**: Built-in 0.5s delay between requests (configurable)
2. **Cache filter options**: They don't change frequently
3. **Use pagination wisely**: Don't fetch all jobs if you only need a subset
4. **Handle errors gracefully**: Network issues can occur
5. **Be a good citizen**: Don't hammer the API unnecessarily

## 🐛 Error Handling

The client raises exceptions for various error conditions:

```python
try:
    jobs, total = api.search_jobs(limit=10)
except requests.exceptions.Timeout:
    print("Request timed out")
except requests.exceptions.HTTPError as e:
    print(f"HTTP error: {e}")
except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")
except ValueError as e:
    print(f"Invalid response: {e}")
```

## 📝 Response Format

### Job Search Response
```json
{
  "status": "success",
  "data": {
    "results": [
      {
        "id": 150116,
        "title": "Account Manager SMB, Uber Eats, Norway",
        "description": "**About the Role**...",
        "department": "Sales & Account Management",
        "team": "Account Management",
        "level": "3",
        "timeType": "Full-Time",
        "location": {
          "country": "NOR",
          "countryName": "Norway",
          "region": null,
          "city": "Oslo"
        },
        "creationDate": "2025-10-21T15:11:00.000Z",
        "updatedDate": "2025-12-15T15:15:00.000Z",
        "allLocations": [...]
      }
    ],
    "totalResults": {
      "low": 797,
      "high": 0,
      "unsigned": false
    }
  }
}
```

## 🔗 Related Resources

- **Uber Careers Website**: https://www.uber.com/us/en/careers/
- **Job Posting Format**: `https://www.uber.com/global/en/careers/list/{job_id}/`

## 📄 License

This is a reverse-engineered API client for educational and personal use. Please respect Uber's terms of service and rate limits.

## 🤝 Contributing

Feel free to submit issues or pull requests to improve this client!

## 📞 Support

For questions or issues, please open an issue in the repository.

---

**Generated**: 2025-12-22
**HAR Analysis ID**: 0c786aa76c2f

---

## Don't want to maintain this?

This client was reverse-engineered locally and is yours to keep — but it is
pinned to uber.com's API as it looked on the day of capture, and nothing here
re-engineers it when that changes.

[Anything](https://anything.notte.cc?utm_source=rae&utm_medium=example&utm_campaign=uber)
is the hosted version of this project: you describe the task and get back a
deployed API function, with the proxies, retries, and repair-on-change handled
for you. Check whether Uber's job board is already covered before building anything:

```bash
reverse-api-engineer marketplace search --site uber.com
```

If nothing matches yet, describe the task at
[anything.notte.cc](https://anything.notte.cc?utm_source=rae&utm_medium=example&utm_campaign=uber)
and it gets built for you. Agents can search the same catalogue by pointing an
MCP client at `https://anything.notte.cc/mcp`.
