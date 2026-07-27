import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRightIcon, ArrowLeftIcon } from 'lucide-react';
import { MDXRemote } from 'next-mdx-remote/rsc';
import remarkGfm from 'remark-gfm';
import rehypeSlug from 'rehype-slug';
import rehypePrettyCode from 'rehype-pretty-code';
import {
  getDocPage,
  getAllDocPages,
  getDocTree,
  flattenTree,
} from '@/lib/docs';
import { getDocsMdxComponents } from '@/components/docs/mdx-components';
import { JsonLd } from '@/components/json-ld';
import { appName, siteUrl } from '@/lib/shared';

interface PageProps {
  params: Promise<{ slug?: string[] }>;
}

const mdxOptions: any = {
  parseFrontmatter: false,
  mdxOptions: {
    remarkPlugins: [remarkGfm],
    rehypePlugins: [
      rehypeSlug,
      [
        rehypePrettyCode,
        {
          theme: { light: 'github-light', dark: 'github-dark' },
          keepBackground: false,
          defaultLang: 'plaintext',
        },
      ],
    ],
  },
};

export default async function Page({ params }: PageProps) {
  const { slug } = await params;
  const page = getDocPage(slug);
  if (!page) notFound();

  const tree = getDocTree();
  const flat = flattenTree(tree);
  const idx = flat.findIndex((p) => p.url === page.url);
  const prev = idx > 0 ? flat[idx - 1] : null;
  const next = idx >= 0 && idx < flat.length - 1 ? flat[idx + 1] : null;

  const breadcrumbItems = [
    { name: 'Docs', url: new URL('/docs', siteUrl).toString() },
    ...page.slug.map((seg, i) => {
      const segUrl = `/docs/${page.slug.slice(0, i + 1).join('/')}`;
      const node = flat.find((p) => p.url === segUrl);
      return {
        name: node?.title ?? seg,
        url: new URL(segUrl, siteUrl).toString(),
      };
    }),
  ];
  const breadcrumbJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: breadcrumbItems.map((it, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: it.name,
      item: it.url,
    })),
  };

  return (
    <article className="max-w-[740px] mx-auto flex flex-col">
      {page.slug.length > 0 ? <JsonLd data={breadcrumbJsonLd} /> : null}
      {/* Header — title + description, tight rhythm before the body */}
      <header className="pb-4">
        <h1 className="font-display text-4xl md:text-5xl tracking-[-0.04em] text-ink leading-[1.05]">
          {page.frontmatter.title}
        </h1>
        {page.frontmatter.description ? (
          <p className="mt-2 text-lg text-ink-soft leading-relaxed">
            {page.frontmatter.description}
          </p>
        ) : null}
      </header>

      {/* MDX body — all styling on the MDX components themselves.
          `.mdx` scope only handles rehype-pretty-code emissions + Shiki. */}
      <div className="mdx">
        <MDXRemote
          source={page.content}
          components={getDocsMdxComponents()}
          options={mdxOptions}
        />
      </div>

      {/* Prev/Next — generous breathing room above the separator */}
      {(prev || next) && (
        <nav
          className="mt-8 pt-6 pb-2 border-t border-ink/10 grid grid-cols-1 sm:grid-cols-2 gap-4"
        >
          {prev ? (
            <Link
              href={prev.url}
              className="group flex flex-col"
              style={{ textDecoration: 'none', color: 'inherit' }}
            >
              <span className="flex items-center gap-1.5 font-mono text-[0.65rem] uppercase tracking-widest text-ink-soft">
                <ArrowLeftIcon className="size-3 transition-transform duration-200 group-hover:-translate-x-1 group-hover:text-fd-primary" />
                Previous
              </span>
              <span className="mt-1 block font-display text-lg text-ink tracking-tight group-hover:text-fd-primary transition-colors">
                {prev.title}
              </span>
            </Link>
          ) : (
            <span />
          )}
          {next ? (
            <Link
              href={next.url}
              className="group flex flex-col text-right sm:col-start-2"
              style={{ textDecoration: 'none', color: 'inherit' }}
            >
              <span className="flex items-center justify-end gap-1.5 font-mono text-[0.65rem] uppercase tracking-widest text-ink-soft">
                Next
                <ArrowRightIcon className="size-3 transition-transform duration-200 group-hover:translate-x-1 group-hover:text-fd-primary" />
              </span>
              <span className="mt-1 block font-display text-lg text-ink tracking-tight group-hover:text-fd-primary transition-colors">
                {next.title}
              </span>
            </Link>
          ) : (
            <span />
          )}
        </nav>
      )}
    </article>
  );
}

export function generateStaticParams() {
  return getAllDocPages().map((p) => ({ slug: p.slug.length === 0 ? undefined : p.slug }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const page = getDocPage(slug);
  if (!page) return {};
  return {
    title: page.frontmatter.title,
    description: page.frontmatter.description,
    alternates: {
      canonical: page.url,
    },
    openGraph: {
      type: 'article',
      siteName: appName,
      title: `${page.frontmatter.title} · ${appName}`,
      description: page.frontmatter.description,
      url: page.url,
    },
    twitter: {
      card: 'summary',
      title: `${page.frontmatter.title} · ${appName}`,
      description: page.frontmatter.description,
    },
  };
}
