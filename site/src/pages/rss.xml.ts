import { getCollection } from 'astro:content';
import type { APIContext } from 'astro';

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export async function GET(context: APIContext) {
  const site = context.site?.toString().replace(/\/$/, '') ?? 'https://rutasdecrecimiento.com';
  const posts = (await getCollection('blog')).sort((a, b) => b.data.date.localeCompare(a.data.date));

  const items = posts.map(p => {
    const url = `${site}/blog/${p.data.slug}`;
    const pubDate = new Date(p.data.date + 'T12:00:00Z').toUTCString();
    return [
      '<item>',
      `<title>${esc(p.data.title)}</title>`,
      `<link>${url}</link>`,
      `<guid isPermaLink="true">${url}</guid>`,
      `<pubDate>${pubDate}</pubDate>`,
      p.data.description ? `<description>${esc(p.data.description)}</description>` : '',
      '</item>',
    ].filter(Boolean).join('\n');
  }).join('\n');

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Rutas de Crecimiento — Blog</title>
<link>${site}/blog</link>
<description>Guías y análisis sobre viajes que desarrollan habilidades.</description>
<language>es</language>
${items}
</channel>
</rss>`;

  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } });
}
