export enum BidStatus {
  DRAFT = 'DRAFT',
  TRIAGED = 'TRIAGED',
  IN_PROGRESS = 'IN_PROGRESS',
  WON = 'WON',
  LOST = 'LOST',
}

export enum BidProfile {
  S = 'S',
  M = 'M',
  L = 'L',
  XL = 'XL',
}

/**
 * Bid domain object.
 * Intentionally a plain class (no TypeORM yet) — ORM persistence lands in a
 * later Phase 1.x task. For now BidsService keeps instances in memory.
 */
export class Bid {
  id!: string;
  clientName!: string;
  industry!: string;
  region!: string;
  deadline!: string; // ISO-8601 date string
  scopeSummary!: string;
  technologyKeywords!: string[];
  estimatedProfile!: BidProfile;
  status!: BidStatus;
  workflowId: string | null = null;
  createdAt!: string;
  updatedAt!: string;
}
