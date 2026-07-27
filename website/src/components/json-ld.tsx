/* Schema.org JSON-LD block for SEO + LLM crawler signals.
   Must render as a plain <script> tag in the static HTML (not via
   next/script, which only injects through React hydration and so is
   invisible to non-JS crawlers). The `<` escape prevents a `</script>`
   sequence from inside a string value breaking out of the tag. */

export function JsonLd({ data }: { data: unknown }) {
  const json = JSON.stringify(data).replace(/</g, '\\u003c');
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: json }}
    />
  );
}
