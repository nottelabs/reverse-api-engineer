import Link from 'next/link';
import { PackageIcon, BookOpenIcon, CloudIcon } from 'lucide-react';
import { cloudLink, cloudUrl, githubUrl, pypiUrl } from '@/lib/shared';
import { ThemeToggle } from './theme-toggle';

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56v-2c-3.2.7-3.87-1.37-3.87-1.37-.52-1.33-1.27-1.69-1.27-1.69-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.02 1.75 2.67 1.25 3.32.96.1-.74.4-1.25.72-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.18-3.1-.12-.29-.51-1.47.11-3.06 0 0 .96-.31 3.15 1.18a10.94 10.94 0 0 1 5.74 0c2.19-1.49 3.15-1.18 3.15-1.18.62 1.59.23 2.77.11 3.06.73.81 1.18 1.84 1.18 3.1 0 4.42-2.69 5.39-5.25 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
    </svg>
  );
}

export function SiteNav() {
  return (
    <header
      className="sticky top-0 z-50 backdrop-blur-xl backdrop-saturate-150"
      style={{ backgroundColor: 'color-mix(in oklch, var(--color-cream) 58%, transparent)' }}
    >
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-10">
        <Link href="/" className="flex items-baseline gap-1.5 group">
          <span
            className="font-display select-none leading-none inline-block italic transition-transform group-hover:rotate-12"
            style={{
              fontSize: 22,
              color: 'var(--color-fd-primary)',
              fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1",
            }}
            aria-hidden="true"
          >
            *
          </span>
          <span
            className="font-display text-2xl tracking-[-0.04em] italic text-ink"
            style={{ fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}
          >
            rae
          </span>
          <span className="sr-only">reverse-api-engineer</span>
        </Link>
        <nav className="flex items-center gap-1 md:gap-6">
          <Link
            href="/docs"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-ink-soft hover:text-ink transition-colors"
            aria-label="Docs"
          >
            <BookOpenIcon className="size-4" />
            <span className="hidden sm:inline">Docs</span>
          </Link>
          <Link
            href={cloudLink(cloudUrl, 'nav')}
            target="_blank"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-ink-soft hover:text-ink transition-colors"
            aria-label="Anything, the hosted version"
          >
            <CloudIcon className="size-4" />
            <span className="hidden sm:inline">Cloud</span>
          </Link>
          <Link
            href={pypiUrl}
            target="_blank"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-ink-soft hover:text-ink transition-colors"
            aria-label="PyPI"
          >
            <PackageIcon className="size-4" />
            <span className="hidden sm:inline">PyPI</span>
          </Link>
          <Link
            href={githubUrl}
            target="_blank"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-ink-soft hover:text-ink transition-colors"
            aria-label="GitHub"
          >
            <GithubIcon className="size-4" />
            <span className="hidden sm:inline">GitHub</span>
          </Link>
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}
