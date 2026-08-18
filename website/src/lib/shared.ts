export const appName = 'Reverse API Engineer';
export const appTagline = 'Turn websites into APIs.';
export const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://reverseapi.dev';
export const docsRoute = '/docs';
export const docsImageRoute = '/og/docs';
export const docsContentRoute = '/llms.mdx/docs';

export const gitConfig = {
  user: 'kalil0321',
  repo: 'reverse-api-engineer',
  branch: 'main',
};

export const githubUrl = `https://github.com/${gitConfig.user}/${gitConfig.repo}`;
export const pypiUrl = 'https://pypi.org/project/reverse-api-engineer/';

/* ─── Anything (the hosted version) ────────────────────────────────────────
   Every outbound link to the cloud goes through `cloudLink` so the UTM tags
   stay consistent and attribution per placement is actually measurable. */

export const cloudName = 'Anything';
export const cloudHost = 'anything.notte.cc';
export const cloudTagline = 'Describe the task. We engineer the skill.';
export const cloudUrl = `https://${cloudHost}`;
export const cloudMarketplaceUrl = `${cloudUrl}/marketplace`;
export const cloudMcpUrl = `${cloudUrl}/mcp`;

/** Marketplace size, rounded down so the copy ages gracefully. */
export const cloudMarketplaceStats = { functions: '950+', sites: '400+' };

/** Tag a cloud URL with the placement it was clicked from. */
export function cloudLink(url: string, campaign: string): string {
  const u = new URL(url);
  u.searchParams.set('utm_source', 'rae');
  u.searchParams.set('utm_medium', 'website');
  u.searchParams.set('utm_campaign', campaign);
  return u.toString();
}
