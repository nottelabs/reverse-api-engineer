# Ashby ATS API Client - Reverse Engineering Documentation

## Overview

This directory contains a reverse-engineered Python client for Ashby's public job board APIs. The API was analyzed from a HAR file capturing OpenAI's career page interactions with Ashby (their ATS provider).

**Original Goal:** Retrieve all job postings from companies using Ashby as their Applicant Tracking System.

## API Discovery Summary

### Base Information

- **Base URL:** `https://jobs.ashbyhq.com/api/non-user-graphql`
- **Protocol:** GraphQL (Apollo Client)
- **Authentication:** None required (public API)
- **HTTP Method:** POST for all operations
- **Content Type:** `application/json`

### Key Endpoints Discovered

The API uses a single GraphQL endpoint with different operation names passed as query parameters:

1. **ApiJobBoardWithTeams** - Main endpoint for listing all jobs
2. **ApiOrganizationFromHostedJobsPageName** - Organization metadata and branding
3. **ApiJobPosting** - Detailed job posting information
4. **ApiAutocompleteGeoLocation** - Location autocomplete for forms

## Architecture Analysis

### Request Pattern

All requests follow this structure:

```
POST https://jobs.ashbyhq.com/api/non-user-graphql?op={OperationName}

Headers:
  apollographql-client-name: frontend_non_user
  apollographql-client-version: 0.1.0
  content-type: application/json
  origin: https://jobs.ashbyhq.com
  referer: https://jobs.ashbyhq.com/{organization_slug}

Body:
{
  "operationName": "{OperationName}",
  "variables": { ... },
  "query": "query {OperationName}(...) { ... }"
}
```

### Authentication

**No authentication is required** for these public job board APIs. The API relies only on:
- Standard browser security headers (CORS, sec-fetch-*)
- Session cookies (`_dd_s` for DataDog analytics)
- Apollo GraphQL client identification headers

This makes the API extremely accessible for programmatic scraping and integration.

### CDN & Performance

- Served through **Cloudflare CDN**
- Supports **HTTP/3 (QUIC protocol)**
- **Brotli compression** for responses
- Response sizes:
  - Organization info: ~1.5 KB compressed
  - Job board (200+ jobs): ~22 KB compressed
  - Job details: ~9 KB compressed

## Detailed API Endpoints

### 1. Get Job Board with Teams

**Purpose:** Retrieve all available jobs and organizational teams in a single request.

**Operation:** `ApiJobBoardWithTeams`

**Variables:**
```json
{
  "organizationHostedJobsPageName": "openai"
}
```

**Response Structure:**
```json
{
  "data": {
    "jobBoard": {
      "teams": [
        {
          "id": "team-uuid",
          "name": "Engineering",
          "externalName": null,
          "parentTeamId": "parent-uuid"
        }
      ],
      "jobPostings": [
        {
          "id": "job-uuid",
          "title": "Backend Software Engineer",
          "teamId": "team-uuid",
          "locationId": "location-uuid",
          "locationName": "San Francisco",
          "workplaceType": "Hybrid",
          "employmentType": "FullTime",
          "compensationTierSummary": "$255K – $405K • Offers Equity",
          "secondaryLocations": [
            {
              "locationId": "location-uuid",
              "locationName": "New York City"
            }
          ]
        }
      ]
    }
  }
}
```

**Key Fields:**
- `teams[]`: Hierarchical team structure with parent-child relationships
- `jobPostings[]`: Summary of all open positions
- `workplaceType`: "Hybrid" | "Remote" | "Onsite"
- `employmentType`: "FullTime" | "PartTime" | "Contract" | "Internship"
- `compensationTierSummary`: Human-readable compensation range

**Use Case:** This is the primary endpoint for building a job board or scraping all positions.

---

### 2. Get Organization Information

**Purpose:** Fetch company branding, theme, and configuration.

**Operation:** `ApiOrganizationFromHostedJobsPageName`

**Variables:**
```json
{
  "organizationHostedJobsPageName": "openai",
  "searchContext": "JobBoard"
}
```

**Response Structure:**
```json
{
  "data": {
    "organization": {
      "name": "OpenAI",
      "publicWebsite": "https://openai.com/",
      "hostedJobsPageSlug": "openai",
      "allowJobPostIndexing": true,
      "timezone": "America/Los_Angeles",
      "theme": {
        "colors": {
          "colorPrimary600": "#000000",
          "colorPrimary900": "#000000"
        },
        "showJobFilters": true,
        "showLocationAddress": false,
        "showTeams": false,
        "logoWordmarkImageUrl": "https://app.ashbyhq.com/api/images/...",
        "logoSquareImageUrl": "https://app.ashbyhq.com/api/images/...",
        "jobPostingBackUrl": "https://openai.com/careers/search/"
      },
      "activeFeatureFlags": [
        "AnonymousCandidateExperience",
        "JobPostingApplicationDeadlines",
        ...
      ]
    }
  }
}
```

**Key Fields:**
- `name`: Company name
- `publicWebsite`: Company's main website
- `theme`: Complete branding configuration
- `activeFeatureFlags`: Enabled features for this organization
- `timezone`: Organization's primary timezone

**Use Case:** Customizing the UI, understanding company settings, or downloading logos.

---

### 3. Get Job Posting Details

**Purpose:** Retrieve complete information for a specific job, including application form structure.

**Operation:** `ApiJobPosting`

**Variables:**
```json
{
  "organizationHostedJobsPageName": "openai",
  "jobPostingId": "73eb1b69-095d-4f27-84ba-54f5df9bc230"
}
```

**Response Structure:**
```json
{
  "data": {
    "jobPosting": {
      "id": "73eb1b69-095d-4f27-84ba-54f5df9bc230",
      "title": "Backend Software Engineer - B2B Applications",
      "departmentName": "Applied AI",
      "locationName": "San Francisco",
      "workplaceType": "Hybrid",
      "employmentType": "FullTime",
      "descriptionHtml": "<p>Full job description HTML...</p>",
      "isListed": true,
      "isConfidential": false,
      "teamNames": ["Applied AI", "B2B Applications"],
      "secondaryLocationNames": ["New York City"],
      "compensationTierSummary": "$255K – $405K • Offers Equity",
      "scrapeableCompensationSalarySummary": "$255K - $405K",
      "compensationPhilosophyHtml": "<p>Compensation philosophy...</p>",
      "applicationDeadline": null,
      "applicationForm": {
        "id": "form-uuid",
        "sections": [
          {
            "title": null,
            "fieldEntries": [
              {
                "id": "field-uuid",
                "field": {
                  "title": "Name",
                  "type": "String",
                  "path": "_systemfield_name"
                },
                "isRequired": true
              },
              {
                "field": {
                  "title": "Email",
                  "type": "Email"
                },
                "isRequired": true
              },
              {
                "field": {
                  "title": "Resume",
                  "type": "File"
                },
                "isRequired": true
              },
              {
                "field": {
                  "title": "Where are you currently located?",
                  "type": "Location",
                  "locationTypes": ["Country", "Region", "City"]
                },
                "isRequired": true
              }
            ]
          }
        ]
      },
      "surveyForms": [
        {
          "id": "survey-uuid"
          // EEOC voluntary self-identification form
        }
      ]
    }
  }
}
```

**Key Fields:**
- `descriptionHtml`: Full job description (rich HTML)
- `compensationTierSummary`: Human-readable compensation
- `scrapeableCompensationSalarySummary`: Machine-readable compensation
- `applicationForm`: Complete form structure with field types and requirements
- `surveyForms`: Optional EEOC/diversity forms

**Application Form Field Types:**
- `String`: Text input
- `Email`: Email validation
- `Phone`: Phone number
- `File`: File upload (resume, cover letter)
- `Location`: Geographic location with autocomplete
- `Select`: Dropdown selection
- `MultiSelect`: Multiple choice
- `LongText`: Textarea
- `Date`: Date picker

**Use Case:** Displaying job details, understanding application requirements, or auto-filling forms.

---

### 4. Autocomplete Geographic Location

**Purpose:** Provide location suggestions for application form location fields.

**Operation:** `ApiAutocompleteGeoLocation`

**Variables:**
```json
{
  "text": "San Fr",
  "locationTypes": ["Country", "Region", "City"]
}
```

**Response Structure:**
```json
{
  "data": {
    "result": {
      "suggestions": [
        {
          "name": "San Francisco, California, United States",
          "geoLocationPath": [
            {
              "name": "United States",
              "type": "Country",
              "providerLocationId": "ChIJCzYy5IS..."
            },
            {
              "name": "California",
              "type": "Region",
              "providerLocationId": "ChIJPV4oX_65..."
            },
            {
              "name": "San Francisco",
              "type": "City",
              "providerLocationId": "ChIJIQBpAG2ah..."
            }
          ]
        }
      ]
    }
  }
}
```

**Key Fields:**
- `suggestions[]`: Array of matching locations
- `name`: Full location name with hierarchy
- `geoLocationPath`: Array of geographic entities from country to city
- `providerLocationId`: Google Places API identifier

**Use Case:** Implementing location autocomplete in application forms.

---

## Python Client Usage

### Installation

```bash
pip install requests
```

### Basic Usage

```python
from api_client import AshbyAPIClient

# Initialize client
client = AshbyAPIClient()

# Get all jobs from OpenAI
jobs = client.get_all_jobs("openai")
print(f"Found {len(jobs)} positions")

# Display jobs
for job in jobs:
    print(f"{job['title']} - {job['locationName']}")
    if job.get('compensationTierSummary'):
        print(f"  Compensation: {job['compensationTierSummary']}")
```

### Advanced Usage

```python
from api_client import AshbyAPIClient

with AshbyAPIClient() as client:
    # Get organization info
    org = client.get_organization_info("openai")
    print(f"Company: {org.name}")
    print(f"Website: {org.public_website}")

    # Get full job board
    board = client.get_job_board_with_teams("openai")

    # Access teams
    teams = board['teams']
    print(f"Teams: {len(teams)}")

    # Access jobs
    jobs = board['jobPostings']

    # Filter jobs
    remote_jobs = [j for j in jobs if j['workplaceType'] == 'Remote']
    sf_jobs = [j for j in jobs if 'San Francisco' in j['locationName']]

    # Get detailed job info
    if jobs:
        job_id = jobs[0]['id']
        details = client.get_job_posting_details("openai", job_id)

        print(f"Title: {details.title}")
        print(f"Department: {details.department_name}")
        print(f"Compensation: {details.compensation_tier_summary}")
        print(f"Description: {details.description_html}")

        # Inspect application form
        for section in details.application_form['sections']:
            for field in section['fieldEntries']:
                print(f"Field: {field['field']['title']}")
                print(f"  Type: {field['field']['type']}")
                print(f"  Required: {field['isRequired']}")
```

### Filtering Examples

```python
from api_client import AshbyAPIClient

with AshbyAPIClient() as client:
    jobs = client.get_all_jobs("openai")

    # Filter by location
    sf_jobs = [j for j in jobs if "San Francisco" in j['locationName']]

    # Filter by workplace type
    remote_jobs = [j for j in jobs if j['workplaceType'] == 'Remote']
    hybrid_jobs = [j for j in jobs if j['workplaceType'] == 'Hybrid']

    # Filter by employment type
    fulltime_jobs = [j for j in jobs if j['employmentType'] == 'FullTime']
    internships = [j for j in jobs if j['employmentType'] == 'Internship']

    # Filter by compensation (if available)
    high_paying = [j for j in jobs
                   if j.get('compensationTierSummary')
                   and '$300K' in j['compensationTierSummary']]

    # Filter by team
    board = client.get_job_board_with_teams("openai")
    teams_by_id = {t['id']: t['name'] for t in board['teams']}

    engineering_jobs = [
        j for j in board['jobPostings']
        if 'Engineering' in teams_by_id.get(j['teamId'], '')
    ]
```

### Error Handling

```python
from api_client import AshbyAPIClient
import requests

client = AshbyAPIClient(timeout=30)

try:
    jobs = client.get_all_jobs("openai")
except requests.exceptions.Timeout:
    print("Request timed out")
except requests.exceptions.RequestException as e:
    print(f"Network error: {e}")
except ValueError as e:
    print(f"API error: {e}")
finally:
    client.close()
```

## Other Companies Using Ashby

The same API client can be used for any company using Ashby ATS. Just replace the organization slug:

**Known Examples:**
- **OpenAI:** `openai`
- **Anthropic:** `anthropic`
- **Stripe:** `stripe`
- **Vercel:** `vercel`
- **Loom:** `loom`
- **Ramp:** `ramp`
- **Scale AI:** `scaleai`
- **Figma:** `figma`

```python
# Example: Get jobs from multiple companies
companies = ["openai", "anthropic", "stripe", "vercel"]

with AshbyAPIClient() as client:
    for company in companies:
        try:
            jobs = client.get_all_jobs(company)
            print(f"{company}: {len(jobs)} jobs")
        except Exception as e:
            print(f"{company}: Error - {e}")
```

## Data Models

### Team
```python
@dataclass
class Team:
    id: str
    name: str
    external_name: Optional[str]
    parent_team_id: Optional[str]
```

### JobPosting (Summary)
```python
@dataclass
class JobPosting:
    id: str
    title: str
    team_id: str
    location_id: str
    location_name: str
    workplace_type: str  # "Hybrid" | "Remote" | "Onsite"
    employment_type: str  # "FullTime" | "PartTime" | "Contract" | "Internship"
    compensation_tier_summary: Optional[str]
    secondary_locations: List[Dict[str, str]]
```

### JobPostingDetails (Full)
```python
@dataclass
class JobPostingDetails:
    id: str
    title: str
    department_name: str
    location_name: str
    workplace_type: str
    employment_type: str
    description_html: str
    is_listed: bool
    is_confidential: bool
    team_names: List[str]
    secondary_location_names: List[str]
    compensation_tier_summary: Optional[str]
    application_form: Dict[str, Any]
    survey_forms: List[Dict[str, Any]]
    # ... more fields
```

### Organization
```python
@dataclass
class Organization:
    name: str
    public_website: str
    hosted_jobs_page_slug: str
    allow_job_post_indexing: bool
    timezone: str
    theme: Dict[str, Any]
    active_feature_flags: List[str]
```

## Rate Limiting & Best Practices

### Observed Behavior
- No explicit rate limits detected in HAR analysis
- No API keys or authentication required
- Responses are heavily cached (via Cloudflare)

### Recommendations
1. **Respect the service:** Don't hammer the API unnecessarily
2. **Cache responses:** Job postings don't change frequently (cache for 1-24 hours)
3. **Use pagination:** When available (not observed in current API)
4. **Set reasonable timeouts:** Default is 30 seconds
5. **Handle errors gracefully:** Network issues, invalid organization slugs, etc.

### Suggested Caching Strategy

```python
import time
from functools import lru_cache

class CachedAshbyClient(AshbyAPIClient):
    def __init__(self, cache_ttl: int = 3600):
        super().__init__()
        self.cache_ttl = cache_ttl
        self._cache = {}

    def get_all_jobs(self, org_slug: str):
        cache_key = f"jobs_{org_slug}"

        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return cached_data

        # Fetch fresh data
        data = super().get_all_jobs(org_slug)
        self._cache[cache_key] = (time.time(), data)
        return data
```

## Security & Privacy Considerations

### What This API Does NOT Provide
- ❌ Access to candidate applications
- ❌ Access to internal company data
- ❌ Ability to submit applications (different endpoint, requires reCAPTCHA)
- ❌ Access to private/confidential job postings
- ❌ Personal information of candidates or employees

### What This API DOES Provide
- ✅ Public job board information (same as visiting the website)
- ✅ Job descriptions and requirements
- ✅ Compensation ranges (if company chooses to publish)
- ✅ Application form structure (field types, requirements)
- ✅ Organization branding and theme

**Note:** All data accessible through this API is publicly available by visiting `https://jobs.ashbyhq.com/{organization_slug}` in a browser. This client simply provides programmatic access to that public data.

## Limitations

1. **Job Application Submission:** This API does not include the job application submission endpoint, which requires:
   - reCAPTCHA token
   - File uploads (multipart/form-data)
   - Additional CSRF protections

2. **Private Jobs:** Confidential or unlisted job postings (`isListed: false`) may not be returned

3. **Real-time Updates:** Job postings are not real-time; there may be a delay between a job being posted and appearing in the API

4. **Compensation Data:** Not all companies publish compensation ranges

## Future Enhancements

Potential additions to this client:

1. **Application Submission:** Reverse engineer the job application endpoint
2. **Pagination Support:** If Ashby adds pagination to handle large job boards
3. **Webhooks/Polling:** Monitor for new job postings
4. **Analytics:** Track job posting trends over time
5. **Export Formats:** Export to CSV, JSON, Excel
6. **Search/Filter API:** More advanced filtering capabilities

## Technical Details

### HAR File Analysis Source
- **File:** `/Users/kalilbouzigues/Projects/browgents/reverse-api/har/245412bd3019/recording.har`
- **Size:** 866.3 KB
- **Captured:** OpenAI careers page (`https://jobs.ashbyhq.com/openai`)
- **Browser:** Chrome (based on user-agent)
- **Network:** HTTP/3, Brotli compression

### GraphQL Schema Observations

The API uses Apollo GraphQL with these characteristics:
- Client name: `frontend_non_user`
- Client version: `0.1.0`
- Schema fragments for reusable query components
- Type system with `__typename` metadata
- Supports complex nested queries

### CDN Configuration
- **Provider:** Cloudflare
- **Static Assets:** `cdn.ashbyprd.com`
- **API Endpoint:** `jobs.ashbyhq.com`
- **Image CDN:** `app.ashbyhq.com/api/images/`

## License & Legal

This is a reverse-engineered API client based on publicly accessible endpoints.

**Important:**
- This client accesses only public data
- No authentication bypass or security circumvention is performed
- Respect Ashby's terms of service
- Use responsibly and ethically
- Consider rate limiting to avoid overwhelming the service

## Support & Contributions

This client was created through HAR file analysis. If you discover:
- New endpoints
- API changes
- Bugs or issues
- Additional features

Please document and share your findings.

## Version History

- **v1.0** (2024): Initial reverse engineering from HAR file
  - 4 GraphQL operations discovered
  - Complete job board API coverage
  - Production-ready Python client

## Contact

For questions about this reverse engineering project, refer to the HAR analysis source file.

---

## Don't want to maintain this?

This client was reverse-engineered locally and is yours to keep — but it is
pinned to jobs.ashbyhq.com's API as it looked on the day of capture, and nothing here
re-engineers it when that changes.

[Anything](https://anything.notte.cc?utm_source=rae&utm_medium=example&utm_campaign=ashby)
is the hosted version of this project: you describe the task and get back a
deployed API function, with the proxies, retries, and repair-on-change handled
for you. Check whether Ashby-hosted job boards is already covered before building anything:

```bash
reverse-api-engineer marketplace search --site jobs.ashbyhq.com
```

If nothing matches yet, describe the task at
[anything.notte.cc](https://anything.notte.cc?utm_source=rae&utm_medium=example&utm_campaign=ashby)
and it gets built for you. Agents can search the same catalogue by pointing an
MCP client at `https://anything.notte.cc/mcp`.
