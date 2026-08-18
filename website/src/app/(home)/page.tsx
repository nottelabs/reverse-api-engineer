import Link from 'next/link';
import type { CSSProperties, ReactNode } from 'react';
import type { Metadata } from 'next';
import { ArrowRightIcon } from 'lucide-react';
import { appName, appTagline, cloudHost, cloudLink, cloudUrl, gitConfig, githubUrl, pypiUrl, siteUrl } from '@/lib/shared';
import { InstallCommand } from '@/components/install-command';
import { BuiltInTheOpen } from '@/components/built-in-the-open';
import { WorksWithAgents } from '@/components/works-with-agents';
import { LocalOrHosted } from '@/components/local-or-hosted';
import { Reveal } from '@/components/reveal';
import { StepBrowse, StepCapture, StepGenerate, StepReview } from '@/components/step-illustrations';
import { JsonLd } from '@/components/json-ld';

const homeDescription =
  'The agent that turns any website into a typed API client in nine languages — generated from the requests the site actually makes.';

export const metadata: Metadata = {
  title: 'Turn websites into APIs',
  description: homeDescription,
  alternates: {
    canonical: '/',
  },
  openGraph: {
    type: 'website',
    title: 'Turn websites into APIs',
    description: homeDescription,
    url: '/',
    images: [
      {
        url: '/reverse-api-banner.png',
        width: 2566,
        height: 1290,
        alt: `${appName} banner`,
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Turn websites into APIs',
    description: homeDescription,
    images: ['/reverse-api-banner.png'],
  },
};

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56v-2c-3.2.7-3.87-1.37-3.87-1.37-.52-1.33-1.27-1.69-1.27-1.69-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.02 1.75 2.67 1.25 3.32.96.1-.74.4-1.25.72-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.18-3.1-.12-.29-.51-1.47.11-3.06 0 0 .96-.31 3.15 1.18a10.94 10.94 0 0 1 5.74 0c2.19-1.49 3.15-1.18 3.15-1.18.62 1.59.23 2.77.11 3.06.73.81 1.18 1.84 1.18 3.1 0 4.42-2.69 5.39-5.25 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
    </svg>
  );
}

const softwareJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: appName,
  description: appTagline,
  applicationCategory: 'DeveloperApplication',
  operatingSystem: 'macOS, Linux, Windows',
  url: siteUrl,
  downloadUrl: pypiUrl,
  codeRepository: githubUrl,
  license: 'https://opensource.org/licenses/MIT',
  programmingLanguage: ['Python', 'JavaScript', 'TypeScript', 'Go', 'Java', 'C#', 'PHP', 'Ruby', 'C'],
  offers: {
    '@type': 'Offer',
    price: '0',
    priceCurrency: 'USD',
  },
  author: {
    '@type': 'Person',
    name: gitConfig.user,
    url: `https://github.com/${gitConfig.user}`,
  },
};

export default function HomePage() {
  return (
    <main className="flex-1">
      <JsonLd data={softwareJsonLd} />
      <Hero />
      <HowItWorks />
      <WorksWithAgents />
      <BuiltInTheOpen />
      <LocalOrHosted />
      <FinalCTA />
    </main>
  );
}

/* ───────────────────────────── Hero ───────────────────────────── */

function Hero() {
  /* A strip of matte scotch tape holding each note. */
  const Tape = () => (
    <span
      aria-hidden
      style={{ position: 'absolute', top: -9, left: '50%', transform: 'translateX(-50%) rotate(-3deg)', width: 58, height: 20, background: 'rgba(245,240,220,0.5)', border: '1px solid rgba(180,175,150,0.35)', boxShadow: '0 1px 2px rgba(0,0,0,0.08)' }}
    />
  );
  const note = (bg: string, rot: number, w: number, d: number, children: ReactNode, className = '') => (
    <div
      className={`la-note ${className}`}
      style={{ position: 'relative', background: bg, boxShadow: '0 10px 22px rgba(0,0,0,0.20)', textAlign: 'center', '--note-width': `${w}px`, '--r': `${rot}deg`, '--d': `${d}s` } as CSSProperties}
    >
      <Tape />
      {children}
    </div>
  );

  return (
    <section className="relative flex min-h-[calc(100svh-3.5rem)] items-center justify-center overflow-hidden bg-cream px-4 py-12 sm:px-10 sm:py-14">
      <h1 className="sr-only">Turn websites into APIs.</h1>

      <Reveal className="relative z-10">
        <div className="flex flex-col items-center gap-10 sm:gap-12">
          {/* Neo-brutalist print with the two notes taped on its corners. */}
          <div className="la-rise">
            <div className="relative" style={{ transform: 'rotate(-1.5deg)' }}>
              <div className="hero-art-frame">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/illustrations/hero-isoB-0.webp" alt="Reverse API Engineer turning a website into a typed client" className="hero-art block w-full" />
              </div>
              <div className="hero-corner-note hero-corner-note-left absolute z-10">
                {note('#fff27a', -4, 240, 0.3,
                  <p className="hero-note-title font-display font-medium" style={{ lineHeight: 1, color: '#1f1f1f', letterSpacing: '-0.02em' }}>Turn websites</p>,
                  'hero-corner-note-card',
                )}
              </div>
              <div className="hero-corner-note hero-corner-note-right absolute z-10">
                {note('#ffb3d1', 5, 250, 0.45,
                  <p className="hero-note-title font-display italic font-medium" style={{ lineHeight: 1, color: '#b3005f', letterSpacing: '-0.02em', fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}>into APIs.</p>,
                  'hero-corner-note-card',
                )}
              </div>
            </div>
          </div>

          {note('var(--color-fd-card)', 2, 360, 0.6, <InstallCommand />, 'hero-install-note')}

          <div className="la-rise inline-flex w-full flex-wrap items-center justify-center gap-3 sm:w-auto" style={{ '--d': '0.7s' } as CSSProperties}>
            <Link href="/docs" className="btn-primary w-full justify-center sm:w-auto">
              Read the docs
              <ArrowRightIcon className="size-4" />
            </Link>
            <Link href={githubUrl} target="_blank" className="btn-secondary w-full justify-center sm:w-auto">
              <GithubIcon className="size-4" />
              View on GitHub
            </Link>
          </div>

          {/* Hosted escape hatch. Deliberately quiet — the OSS CLI is the
              headline; this is for people who don't want to run anything. */}
          <p className="la-rise -mt-4 text-sm text-ink-soft" style={{ '--d': '0.8s' } as CSSProperties}>
            Rather not run it yourself?{' '}
            <Link
              href={cloudLink(cloudUrl, 'home_hero')}
              target="_blank"
              className="text-fd-primary underline decoration-fd-primary/45 decoration-1 underline-offset-[3px] hover:bg-fd-primary/[0.18] rounded px-1 -mx-1 transition-colors"
            >
              {cloudHost}
            </Link>{' '}
            is the hosted version.
          </p>
        </div>
      </Reveal>
    </section>
  );
}

/* ─────────────────────────── How it works ───────────────────────── */

const HIW_STEPS = [
  { Ill: StepBrowse, title: 'Browse', body: 'Open the CLI. Drive the browser, or let the agent.' },
  { Ill: StepCapture, title: 'Capture', body: 'HAR records every request and response.' },
  { Ill: StepGenerate, title: 'Generate', body: 'Your model writes a typed client.' },
  { Ill: StepReview, title: 'Review', body: 'Audit the output, then commit it.' },
];
const HIW_TINT = ['#ffe1eb', '#d6efff', '#d5f1de', '#ffe7d4'];
const HIW_ROT = ['-rotate-3', 'rotate-2', '-rotate-2', 'rotate-3'];

function HowItWorks() {
  return (
    <section className="relative flex items-center overflow-hidden bg-orange md:min-h-[100svh]">
      <div className="relative mx-auto w-full max-w-7xl px-4 py-20 sm:px-6 sm:py-24 md:py-32 lg:px-10">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="section-display mt-3">How it works?</h2>
        </div>

        {/* Polaroid wall — each step is an instant photo, pinned with tape. */}
        <Reveal>
          <div className="mt-10 grid grid-cols-2 items-start gap-4 sm:mt-14 sm:flex sm:flex-wrap sm:justify-center sm:gap-7 md:mt-16">
            {HIW_STEPS.map(({ Ill, title, body }, i) => (
              <div key={title} className="hiw-pol-wrap" style={{ '--d': `${i * 0.12}s` } as CSSProperties}>
                <div className={`${HIW_ROT[i]} w-full bg-white p-2 pb-0 shadow-[0_14px_30px_rgba(0,0,0,0.16)] transition-transform duration-200 hover:-translate-y-2 hover:rotate-0 sm:w-[184px] sm:p-2.5 sm:pb-0`}>
                  <div className="grid h-28 place-items-center sm:h-36" style={{ background: HIW_TINT[i] }}>
                    <div className="w-[84px] sm:w-[112px]"><Ill /></div>
                  </div>
                  <div className="py-4 text-center">
                    <p className="font-display italic text-xl" style={{ color: '#1f1f1f', fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}>{title}</p>
                    <p className="mt-1 px-2 text-[11px] leading-snug" style={{ color: 'rgba(31,31,31,0.6)' }}>{body}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ────────────────────────── Final CTA ──────────────────────────── */

function FinalCTA() {
  return (
    <section className="relative flex items-center overflow-hidden bg-sky md:min-h-[100svh]">
      <div className="absolute inset-0 bg-scanlines pointer-events-none" />
      <span
        aria-hidden="true"
        className="absolute top-12 right-16 hidden md:block font-display italic text-5xl text-fd-primary/40 select-none -rotate-12"
      >
        *
      </span>
      <span
        aria-hidden="true"
        className="absolute bottom-14 left-10 hidden md:block font-display italic text-4xl text-ink/15 select-none rotate-12"
      >
        *
      </span>

      <div className="relative mx-auto w-full max-w-6xl px-4 py-20 sm:px-6 sm:py-28 md:py-40 lg:px-10">
        <Reveal>
          <div className="grid md:grid-cols-[1.1fr_1fr] gap-12 md:gap-16 items-center">
            {/* Left: headline + CTAs */}
            <div className="la-rise">
              <h2 className="hero-display text-left">
                Skip the<br /><em>scraping.</em>
              </h2>
              <p className="mt-8 max-w-md text-base md:text-lg text-ink-soft leading-relaxed">
                Install. Prompt. Get your typed client back.
              </p>
              <div className="mt-10 inline-flex w-full flex-wrap items-center gap-3 sm:w-auto">
                <Link href="/docs/quick-start" className="btn-primary w-full justify-center sm:w-auto">
                  Get started
                  <ArrowRightIcon className="size-4" />
                </Link>
                <Link href={githubUrl} target="_blank" className="btn-secondary w-full justify-center sm:w-auto">
                  <GithubIcon className="size-4" />
                  View on GitHub
                </Link>
              </div>
            </div>

            <PostItCard />
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* The "scraping pains you skip" note, resolving to the typed-client payoff. */
function PostItBody() {
  const pains = ['scraping', 'brittle selectors', 'guessing endpoints'];
  return (
    <>
      <ul
        className="font-display"
        style={{ fontWeight: 500, fontSize: '1.35rem', lineHeight: 1.34, listStyle: 'none', padding: 0, margin: 0, fontVariationSettings: "'opsz' 144, 'SOFT' 50, 'WONK' 0" }}
      >
        {pains.map((p) => (
          <li key={p} style={{ textDecoration: 'line-through', textDecorationColor: 'var(--color-fd-primary)', textDecorationThickness: '2px', color: 'rgba(31,31,31,0.5)' }}>
            {p}
          </li>
        ))}
      </ul>
      <p
        className="font-display"
        style={{ fontWeight: 500, fontSize: '1.75rem', lineHeight: 1.1, color: '#1f1f1f', letterSpacing: '-0.02em', marginTop: 18, fontVariationSettings: "'opsz' 144, 'SOFT' 60, 'WONK' 1" }}
      >
        just a{' '}
        <em style={{ fontStyle: 'italic', color: 'var(--color-fd-primary)', fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}>typed client.</em>
      </p>
    </>
  );
}

/* Mint post-it, pinned with scotch tape — a fixed physical object on the
   themed section, so it looks the same in light and dark. */
function PostItCard() {
  return (
    <div
      className="justify-self-center"
      style={{ position: 'relative', width: 'min(340px, calc(100vw - 3rem))', background: '#c4edd0', padding: '40px 30px 34px', transform: 'rotate(-3deg)', boxShadow: '0 18px 40px rgba(0,0,0,0.26), 0 4px 10px rgba(0,0,0,0.14)' }}
    >
      <span
        aria-hidden
        style={{ position: 'absolute', top: -11, left: '50%', transform: 'translateX(-50%) rotate(-3deg)', width: 70, height: 24, background: 'rgba(245,240,220,0.5)', border: '1px solid rgba(180,175,150,0.35)', boxShadow: '0 1px 2px rgba(0,0,0,0.08)' }}
      />
      <PostItBody />
    </div>
  );
}
