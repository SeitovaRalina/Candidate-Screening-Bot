export const meta = { name: 'clean' };

pipeline(items, async () => {
  await agent('summarize the batch', { model: 'sonnet', effort: 'medium' });
});

parallel([
  () => agent('scan file A', { model: 'haiku', effort: 'low' }),
  () => agent('scan file B', { model: 'haiku', effort: 'low' }),
]);

agent('final review', { model: 'opus', effort: 'high' });
