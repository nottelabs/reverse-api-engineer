import Link from 'next/link';
import { cloudLink, cloudMarketplaceUrl, cloudUrl, githubUrl, pypiUrl, gitConfig } from '@/lib/shared';

const LINKS = [
  { label: 'Documentation', href: '/docs' },
  { label: 'Quick start', href: '/docs/quick-start' },
  { label: 'GitHub', href: githubUrl, external: true },
  { label: 'PyPI', href: pypiUrl, external: true },
  { label: 'Hosted version', href: cloudLink(cloudUrl, 'footer'), external: true },
  { label: 'Marketplace', href: cloudLink(cloudMarketplaceUrl, 'footer'), external: true },
];

export function SiteFooter() {
  return (
    <footer style={{ background: '#0d0a07' }}>

      <div
        style={{
          padding: '60px 0 40px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          gap: 36,
        }}
        className="mx-auto max-w-7xl px-6 lg:px-10"
      >
        <div>
          <p
            style={{
              fontFamily: 'var(--font-fraunces, serif)',
              fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1",
              fontStyle: 'italic',
              fontWeight: 400,
              fontSize: 64,
              lineHeight: 0.9,
              letterSpacing: '-0.05em',
              color: 'rgba(255,247,240,0.95)',
              display: 'inline-flex',
              alignItems: 'baseline',
              gap: 8,
            }}
          >
            <span
              aria-hidden="true"
              style={{
                fontSize: 56,
                color: 'var(--color-fd-primary)',
                lineHeight: 1,
              }}
            >
              *
            </span>
            rae
          </p>
          <p
            style={{
              fontFamily: 'var(--font-fraunces, serif)',
              fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1",
              fontStyle: 'italic',
              fontWeight: 400,
              fontSize: 18,
              color: 'rgba(255,247,240,0.38)',
              marginTop: 14,
              letterSpacing: '-0.02em',
            }}
          >
            Turn websites into APIs.
          </p>
        </div>

        <nav style={{ display: 'flex', gap: 28, flexWrap: 'wrap', justifyContent: 'center' }}>
          {LINKS.map((l) => (
            <Link
              key={l.label}
              href={l.href}
              target={l.external ? '_blank' : undefined}
              style={{
                fontFamily: 'var(--font-jetbrains-mono, monospace)',
                fontSize: 11,
                color: 'rgba(255,247,240,0.9)',
                textDecoration: 'none',
              }}
              className="opacity-50 hover:opacity-90 transition-opacity duration-150"
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <p
          style={{
            fontFamily: 'var(--font-jetbrains-mono, monospace)',
            fontSize: 10,
            color: 'rgba(255,247,240,0.2)',
            marginTop: -12,
          }}
        >
          © 2026 · by{' '}
          <Link
            href={`https://github.com/${gitConfig.user}`}
            target="_blank"
            style={{ color: 'inherit', textDecoration: 'underline', textUnderlineOffset: 3 }}
            className="hover:text-fd-primary transition-colors"
          >
            {gitConfig.user}
          </Link>
        </p>
      </div>
    </footer>
  );
}
