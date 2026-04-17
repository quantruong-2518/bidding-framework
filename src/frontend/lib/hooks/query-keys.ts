export const bidKeys = {
  all: ['bids'] as const,
  list: () => [...bidKeys.all, 'list'] as const,
  detail: (id: string) => [...bidKeys.all, 'detail', id] as const,
  workflow: (id: string) => [...bidKeys.all, 'workflow', id] as const,
};
