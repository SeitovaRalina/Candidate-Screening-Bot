pipeline(items, stage1, stage2);

phase('gather', () => {
  console.log('no agent() here, just pipeline/phase plumbing');
});
