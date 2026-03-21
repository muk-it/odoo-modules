# MuK LLMs.txt & Markdown

Make your Odoo website AI-ready by implementing the llms.txt standard
and Cloudflare-style markdown content negotiation. AI agents and crawlers
can discover your content via /llms.txt and request any page as clean
markdown via the HTTP Accept header.

## Configuration

After installation, navigate to Website > Configuration > Settings. Under the
"AI & Agents" section you can configure:

- **LLMs.txt**: Enable or disable the /llms.txt endpoint.
- **LLMs Full**: Enable or disable the /llms-full.txt endpoint.
- **Content Signal Policy**: Control how AI may use your content.
- **Content Sources**: Choose which content types to include (pages, blogs, products, events).

## Usage

Once installed and enabled, your website will automatically serve:

- `/llms.txt` -- A structured index of all published content following the
  llms.txt standard (llmstxt.org).
- `/llms-full.txt` -- Full markdown content of all published pages for deep
  AI ingestion.
- Any page responds with clean markdown when an AI agent sends
  `Accept: text/markdown` in the HTTP request.

Response headers include `x-markdown-tokens` (estimated token count) and
`Content-Signal` (AI usage policy).
