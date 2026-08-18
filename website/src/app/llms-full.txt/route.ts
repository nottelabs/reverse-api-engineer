import { NextResponse } from 'next/server';
import { getAllDocPages } from '@/lib/docs';
import { appName, appTagline, siteUrl, githubUrl, pypiUrl, cloudUrl, cloudMarketplaceUrl, cloudMcpUrl } from '@/lib/shared';

export const dynamic = 'force-static';

export function GET() {
  const pages = getAllDocPages();

  const sections = pages
    .map((p) => {
      const url = new URL(p.url, siteUrl).toString();
      const title = p.frontmatter.title;
      const description = p.frontmatter.description
        ? `\n> ${p.frontmatter.description}\n`
        : '';
      return `\n\n# ${title}\n\nSource: ${url}${description}\n${p.content.trim()}`;
    })
    .join('\n\n---');

  const header = `# ${appName}

> ${appTagline}

Repository: ${githubUrl}
PyPI: ${pypiUrl}
License: MIT

Hosted version: ${cloudUrl} (marketplace: ${cloudMarketplaceUrl}, MCP: ${cloudMcpUrl}).
Search the marketplace before reverse-engineering a site from scratch.

This file concatenates every documentation page in raw MDX. Use it to give
an LLM full context on the project in a single prompt.
`;

  return new NextResponse(header + sections, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
