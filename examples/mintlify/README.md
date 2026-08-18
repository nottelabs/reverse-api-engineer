# Mintlify AI Assistant API Client

A Python client for interacting with Mintlify's AI assistant API. Works with **any documentation site** using Mintlify's AI feature.

## Overview

This client reverse-engineers Mintlify's AI assistant API, which powers the "Ask AI" feature on documentation sites built with Mintlify. The API uses RAG (Retrieval Augmented Generation) to search documentation and provide contextual answers.

### Tested Sites

- `docs.metronome.com` - Metronome billing platform documentation
- `docs.notte.cc` - Notte AI agents platform documentation

## API Discovery

### Endpoint

```
POST https://leaves.mintlify.com/api/assistant/{subdomain}/message
```

### Authentication

**No authentication required!** The API is publicly accessible. Each Mintlify documentation site has a unique subdomain identifier (e.g., `metronome-b35a6a36`, `notte`).

### Request Format

```json
{
  "id": "subdomain-identifier",
  "messages": [
    {
      "id": "unique-message-id",
      "createdAt": "2024-01-01T00:00:00.000Z",
      "role": "user",
      "content": "Your question here",
      "parts": [{"type": "text", "text": "Your question here"}]
    }
  ],
  "fp": "subdomain-identifier",
  "filter": {
    "groups": ["*"],
    "version": "optional-version"
  },
  "currentPath": "/current/page/path"
}
```

### Response Format

The API uses **Vercel AI Data Stream v1** format (`x-vercel-ai-data-stream: v1`). Responses are streamed line-by-line with type prefixes:

| Prefix | Type | Description |
|--------|------|-------------|
| `f:` | Metadata | Message ID and metadata |
| `9:` | Tool Call | Search tool invocation |
| `a:` | Tool Result | Search results from documentation |
| `e:` | Usage | Token usage statistics |
| `0:` | Text | Streamed response text chunks |

Example stream:
```
f:{"messageId":"msg-xxx"}
9:{"toolCallId":"toolu_xxx","toolName":"search","args":{"query":"..."}}
a:{"toolCallId":"toolu_xxx","result":{"type":"search","results":[...]}}
0:"Metronome is"
0:" a billing"
0:" platform..."
e:{"finishReason":"stop","usage":{"promptTokens":1000,"completionTokens":200}}
```

## Installation

```bash
# No external dependencies beyond requests
pip install requests
```

## Usage

### Basic Usage

```python
from api_client import MintlifyClient

# Create client for any Mintlify-powered docs site
client = MintlifyClient("https://docs.metronome.com")

# Ask a question
response = client.ask("What is Metronome?")
print(response.content)
```

### Quick One-liner

```python
from api_client import ask

response = ask("https://docs.notte.cc", "What is Notte?")
print(response.content)
```

### Streaming Responses

```python
from api_client import MintlifyClient

client = MintlifyClient("https://docs.metronome.com")

# Stream the response
for chunk in client.ask("How do I send usage events?", stream=True):
    print(chunk, end="", flush=True)
```

### Conversation History

```python
from api_client import MintlifyClient

client = MintlifyClient("https://docs.metronome.com")

# First question
response1 = client.ask("What is a billable metric?")
print(response1.content)

# Follow-up question (context is maintained)
response2 = client.ask("How do I create one?")
print(response2.content)

# Clear history to start fresh
client.clear_history()
```

### Access Search Results

```python
from api_client import MintlifyClient

client = MintlifyClient("https://docs.metronome.com")
response = client.ask("How does invoicing work?")

# Access the underlying search results
for result in response.search_results:
    print(f"- {result.title}: {result.href}")

# Get suggested pages
for suggestion in response.suggestions:
    print(f"Suggested: {suggestion}")
```

### Manual Subdomain Configuration

```python
from api_client import MintlifyClient

# If auto-detection fails, provide subdomain manually
client = MintlifyClient(
    docs_url="https://docs.example.com",
    subdomain="example-abc123"
)
```

## API Reference

### MintlifyClient

```python
MintlifyClient(
    docs_url: str,              # Documentation site URL
    subdomain: str = None,      # Mintlify subdomain (auto-detected if not provided)
    filter_groups: list = ["*"],# Content groups to search
    filter_version: str = None, # Documentation version filter
)
```

#### Methods

- `ask(question, current_path="/", stream=False)` - Ask a question
- `clear_history()` - Clear conversation history
- `get_history()` - Get conversation messages

### AssistantResponse

```python
@dataclass
class AssistantResponse:
    content: str                    # The answer text
    message_id: str                 # Unique message ID
    search_results: List[SearchResult]  # Source documents
    suggestions: List[str]          # Suggested page paths
    usage: Dict[str, int]           # Token usage stats
```

### SearchResult

```python
@dataclass
class SearchResult:
    content: str    # Document content snippet
    path: str       # Document path
    title: str      # Document title
    href: str       # Document URL path
```

## How It Works

1. **Subdomain Detection**: The client automatically detects the Mintlify subdomain from the documentation site's HTML/assets.

2. **Message Formatting**: Questions are formatted with unique IDs and timestamps in the Mintlify message format.

3. **Streaming Response**: The API returns a streaming response using Vercel AI Data Stream format, which the client parses line-by-line.

4. **Context Preservation**: Conversation history is maintained automatically for follow-up questions.

## Limitations

- **Rate Limiting**: The API has rate limits (200 requests per hour based on observed headers)
- **Content Scope**: Answers are limited to the documentation content indexed by Mintlify
- **No Authentication**: Since there's no auth, responses may be rate-limited by IP

## Supported Mintlify Sites

This client should work with any documentation site using Mintlify's AI assistant feature. The client auto-detects the subdomain, making it easy to use with any Mintlify-powered site.

## License

MIT License - Feel free to use and modify.

---

## Don't want to maintain this?

This client was reverse-engineered locally and is yours to keep — but it is
pinned to mintlify.com's API as it looked on the day of capture, and nothing here
re-engineers it when that changes.

[Anything](https://anything.notte.cc?utm_source=rae&utm_medium=example&utm_campaign=mintlify)
is the hosted version of this project: you describe the task and get back a
deployed API function, with the proxies, retries, and repair-on-change handled
for you. Check whether Mintlify-hosted docs sites is already covered before building anything:

```bash
reverse-api-engineer marketplace search --site mintlify.com
```

If nothing matches yet, describe the task at
[anything.notte.cc](https://anything.notte.cc?utm_source=rae&utm_medium=example&utm_campaign=mintlify)
and it gets built for you. Agents can search the same catalogue by pointing an
MCP client at `https://anything.notte.cc/mcp`.
