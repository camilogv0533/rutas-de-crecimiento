import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';

export const GET: APIRoute = async ({ site }) => {
  const retreats = await getCollection('retreats');
  const skills = await getCollection('skills');
  const destinations = await getCollection('destinations');
  const posts = await getCollection('blog');
  const base = site?.toString().replace(/\/$/, '') || 'https://rutasdecrecimiento.com';

  const lines = [
    '# Rutas de Crecimiento',
    '',
    '> Directorio curado de viajes que desarrollan habilidades. Curamos retiros que toman inspiración del lugar para enseñar una habilidad concreta (ej. Alpes franceses + liderazgo, Ischia + creatividad). No somos agencia de viajes ni buscador genérico de retiros.',
    '',
    '## Habilidades',
    ...skills.map(s => `- [${s.data.name_es}](${base}/habilidades/${s.data.slug}) — ${s.data.type}`),
    '',
    '## Destinos',
    ...destinations.map(d => `- [${d.data.name}](${base}/destinos/${d.data.slug}) — ${d.data.narrative_hook || ''}`),
    '',
    '## Retiros curados',
    ...retreats.map(r => `- [${r.data.title}](${base}/retiros/${r.data.slug}) — ${r.data.tagline || ''}`),
    '',
    '## Blog',
    ...posts.map(p => `- [${p.data.title}](${base}/blog/${p.data.slug}) — ${p.data.description || ''}`),
    ''
  ];

  return new Response(lines.join('\n'), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' }
  });
};
