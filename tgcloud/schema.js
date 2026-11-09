import { table, integer, text } from 'sdk/db';

export const downloads = table('downloads', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  chatId: integer('chat_id'),
  url: text('url'),
  platform: text('platform')
});
