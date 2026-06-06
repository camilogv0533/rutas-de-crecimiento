import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const retreats = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/retreats' }),
  schema: z.object({
    slug: z.string(),
    title: z.string(),
    tagline: z.string().optional(),
    source_url: z.string().url(),
    host_name: z.string().optional(),
    host_url: z.string().optional(),
    location_city: z.string().optional(),
    location_country: z.string().optional(),
    location_region: z.string().optional(),
    duration_days: z.number().optional(),
    recurring: z.string().optional(),
    price_usd_from: z.number().optional(),
    currency_original: z.string().optional(),
    price_original: z.number().optional(),
    language: z.string().optional(),
    group_size_max: z.number().optional(),
    what_unique: z.string().optional(),
    who_for: z.string().optional(),
    skills: z.array(z.string()).default([]),
    destinations: z.array(z.string()).default([]),
    reviewed_by_us: z.boolean().default(false),
    image_urls: z.array(z.string()).default([]),
    categories: z.array(z.string()).default(['retiro'])
  })
});

const skills = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/skills' }),
  schema: z.object({
    slug: z.string(),
    name_es: z.string(),
    name_en: z.string().optional(),
    type: z.enum(['soft', 'hard', 'tech']).optional(),
    description_es: z.string().optional()
  })
});

const destinations = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/destinations' }),
  schema: z.object({
    slug: z.string(),
    name: z.string(),
    country: z.string().optional(),
    region: z.string().optional(),
    narrative_hook: z.string().optional(),
    skills: z.array(z.string()).default([])
  })
});

const blog = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/blog' }),
  schema: z.object({
    title: z.string(),
    slug: z.string(),
    date: z.string(),
    description: z.string().optional(),
    target_keyword: z.string().optional(),
    related_retreats: z.array(z.string()).default([])
  })
});

export const collections = { retreats, skills, destinations, blog };
