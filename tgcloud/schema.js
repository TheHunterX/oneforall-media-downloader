import { table, integer, text } from 'sdk/db';

export const downloads = table('downloads', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  chatId: integer('chat_id'),
  url: text('url'),
  platform: text('platform'),
  createdAt: text('created_at')
});

export const vault = table('vault', {
  k: text('k').primaryKey(),
  v: text('v')
});

export const users = table('users', {
  chatId: integer('chat_id').primaryKey(),
  lang: text('lang').default('en')
});

export const urlCache = table('url_cache', {
  k: text('k').primaryKey(),
  u: text('u')
});
