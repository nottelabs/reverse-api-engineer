import Link from 'next/link';
import { ArrowRightIcon } from 'lucide-react';
import { cloudHost, cloudLink, cloudMarketplaceStats, cloudMarketplaceUrl, cloudUrl } from '@/lib/shared';
import { Reveal } from './reveal';

/* Two index cards, pinned side by side. The comparison is deliberately even —
   the local column is the product this site is for, and overselling the hosted
   one here would read as a bait-and-switch to exactly the audience that
   installs an MIT CLI. */

const ROWS = [
  { label: 'You get', local: 'a client in your repo', hosted: 'a callable endpoint' },
  { label: 'Runs on', local: 'your machine', hosted: 'hosted browsers' },
  { label: 'Site changes', local: 'you re-run the capture', hosted: 're-engineered for you' },
  { label: 'Setup', local: 'install the CLI', hosted: 'an API key' },
  { label: 'Offline', local: 'yes', hosted: 'no' },
];

function Card({
  eyebrow,
  title,
  values,
  accent,
  rotate,
  children,
}: {
  eyebrow: string;
  title: string;
  values: string[];
  accent: string;
  rotate: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="relative bg-fd-card px-6 py-7 sm:px-7 sm:py-8 shadow-[0_14px_34px_rgba(0,0,0,0.16)]"
      style={{ transform: rotate }}
    >
      <span
        aria-hidden
        className="absolute -top-[11px] left-1/2 h-6 w-[70px] -translate-x-1/2 -rotate-3 border border-[rgba(180,175,150,0.35)] bg-[rgba(245,240,220,0.5)] shadow-[0_1px_2px_rgba(0,0,0,0.08)]"
      />
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-soft/60">{eyebrow}</p>
      <p
        className="font-display italic text-3xl leading-none tracking-[-0.03em] mt-2"
        style={{ color: accent, fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1" }}
      >
        {title}
      </p>

      <dl className="mt-6 space-y-3">
        {ROWS.map((row, i) => (
          <div key={row.label} className="flex items-baseline justify-between gap-4 border-b border-fd-border pb-2 last:border-0">
            <dt className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-soft/55">{row.label}</dt>
            <dd className="text-right text-sm text-ink">{values[i]}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-7">{children}</div>
    </div>
  );
}

export function LocalOrHosted() {
  return (
    <section className="relative flex items-center overflow-hidden bg-mint md:min-h-[100svh]">
      <div className="relative mx-auto w-full max-w-6xl px-4 py-20 sm:px-6 sm:py-24 md:py-32 lg:px-10">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="section-display mt-3">Run it, or don&apos;t.</h2>
          <p className="mt-5 text-base text-ink-soft leading-relaxed">
            Same job, two form factors. The difference is who owns it when the site changes.
          </p>
        </div>

        <Reveal>
          <div className="mt-12 grid gap-8 sm:mt-16 md:grid-cols-2 md:gap-10">
            <Card
              eyebrow="Open source"
              title="rae"
              accent="var(--color-ink)"
              rotate="rotate(-1.5deg)"
              values={ROWS.map((r) => r.local)}
            >
              <Link href="/docs/quick-start" className="btn-primary w-full justify-center">
                Get started
                <ArrowRightIcon className="size-4" />
              </Link>
            </Card>

            <Card
              eyebrow="Hosted"
              title="anything"
              accent="var(--color-fd-primary)"
              rotate="rotate(1.5deg)"
              values={ROWS.map((r) => r.hosted)}
            >
              <Link
                href={cloudLink(cloudUrl, 'home_compare')}
                target="_blank"
                className="btn-secondary w-full justify-center"
              >
                {cloudHost}
                <ArrowRightIcon className="size-4" />
              </Link>
            </Card>
          </div>
        </Reveal>

        <p className="mt-10 text-center text-sm text-ink-soft">
          {cloudMarketplaceStats.functions} functions across {cloudMarketplaceStats.sites} sites are already built —{' '}
          <Link
            href={cloudLink(cloudMarketplaceUrl, 'home_compare')}
            target="_blank"
            className="text-fd-primary underline decoration-fd-primary/45 decoration-1 underline-offset-[3px] rounded px-1 -mx-1 transition-colors hover:bg-fd-primary/[0.18]"
          >
            check before you capture
          </Link>
          .
        </p>
      </div>
    </section>
  );
}
