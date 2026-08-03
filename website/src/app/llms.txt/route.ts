import { NextResponse } from 'next/server';
import { getDocTree, flattenTree } from '@/lib/docs';
import { appName, appTagline, siteUrl, githubUrl, pypiUrl } from '@/lib/shared';

export const dynamic = 'force-static';

export function GET() {
  const pages = flattenTree(getDocTree());

  const docLines = pages
    .map((p) => `- [${p.title}](${new URL(p.url, siteUrl).toString()})`)
    .join('\n');

  const body = `# ${appName}

> ${appTagline}

${appName} is an open-source CLI that captures browser traffic — in the default agent mode via a browser MCP server (Playwright or Chrome DevTools) or the Vercel agent-browser CLI, or in manual mode via a local Playwright browser (optional \`[manual]\` extra) — and uses your configured AI SDK to generate a typed API client from the captured requests. Output languages: Python, JavaScript, TypeScript, Go, Java, C#, PHP, Ruby, C, and PowerShell.

## Documentation

${docLines}

## Project

- Repository: ${githubUrl}
- PyPI: ${pypiUrl}
- License: MIT
`;

  return new NextResponse(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
