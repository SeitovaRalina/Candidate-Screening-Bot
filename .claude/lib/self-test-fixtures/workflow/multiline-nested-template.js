const region = 'us-east';

agent(
  `scan region ${region}`,
  {
    model: 'sonnet',
    effort: 'high',
    onDone: () => parallel([
      () => agent('nested cheap check', { model: 'haiku', effort: 'low' }),
    ]),
  }
);
