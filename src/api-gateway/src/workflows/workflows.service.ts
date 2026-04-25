import { HttpService } from '@nestjs/axios';
import {
  BadGatewayException,
  ConflictException,
  HttpException,
  HttpStatus,
  Injectable,
  Logger,
  NotFoundException,
  RequestTimeoutException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { AxiosError, AxiosResponse } from 'axios';
import { firstValueFrom } from 'rxjs';
import { BidsService } from '../bids/bids.service';
import type { Bid } from '../bids/bid.entity';
import type { TriageSignalDto } from './triage-signal.dto';
import type { ReviewSignalDto } from './review-signal.dto';

interface WorkflowStartResponse {
  workflow_id: string;
  run_id?: string;
  status?: string;
}

interface WorkflowStatusResponse {
  workflow_id: string;
  status: string;
  state?: string;
  [key: string]: unknown;
}

/** Header used to propagate the caller's roles to ai-service for RBAC filtering. */
export const X_USER_ROLES_HEADER = 'x-user-roles';

function rolesHeader(roles: readonly string[] | undefined): Record<string, string> {
  if (!roles || roles.length === 0) return {};
  return { [X_USER_ROLES_HEADER]: roles.filter(Boolean).join(',') };
}

@Injectable()
export class WorkflowsService {
  private readonly logger = new Logger(WorkflowsService.name);

  constructor(
    private readonly http: HttpService,
    private readonly config: ConfigService,
    private readonly bidsService: BidsService,
  ) {}

  private baseUrl(): string {
    return (
      this.config.get<string>('AI_SERVICE_URL') ?? 'http://ai-service:8001'
    );
  }

  async trigger(bidId: string): Promise<{ bid: Bid; workflow: WorkflowStartResponse }> {
    const bid = await this.bidsService.findOne(bidId);
    // Nest-side bids are already structured — hit /start-from-card so the workflow skips S0.
    const url = `${this.baseUrl()}/workflows/bid/start-from-card`;
    const body = {
      bid_id: bid.id,
      client_name: bid.clientName,
      industry: bid.industry,
      region: bid.region,
      deadline: bid.deadline,
      scope_summary: bid.scopeSummary,
      technology_keywords: bid.technologyKeywords ?? [],
      estimated_profile: bid.estimatedProfile ?? 'M',
      requirements_raw: [],
    };

    const response = await this.request<WorkflowStartResponse>('POST', url, body);
    const updated = await this.bidsService.attachWorkflow(bid.id, response.workflow_id);
    return { bid: updated, workflow: response };
  }

  async sendTriageSignal(
    bidId: string,
    signal: TriageSignalDto,
  ): Promise<{ status: string }> {
    const workflowId = await this.requireWorkflowId(bidId);
    const url = `${this.baseUrl()}/workflows/bid/${encodeURIComponent(workflowId)}/triage-signal`;
    const body = {
      approved: signal.approved,
      reviewer: signal.reviewer,
      notes: signal.notes,
      bid_profile_override: signal.bidProfileOverride,
    };
    return this.request<{ status: string }>('POST', url, body);
  }

  /**
   * Forward a human S9 review decision to the running workflow.
   *
   * Returns 409 CONFLICT if the workflow is no longer at S9 — handles the
   * double-submit / stale-signal race where the gate already advanced. The
   * upstream ai-service will accept the signal either way; gating here is a
   * UX safety net so the frontend can surface the race gracefully.
   */
  async sendReviewSignal(
    bidId: string,
    signal: ReviewSignalDto,
    roles: readonly string[] = [],
  ): Promise<{ status: string }> {
    const workflowId = await this.requireWorkflowId(bidId);
    const status = await this.getStatus(bidId, roles);
    const state = (status.current_state as string | undefined) ?? status.state;
    if (state && state !== 'S9') {
      throw new ConflictException(
        `Workflow ${workflowId} is at state ${state}; S9 review gate already resolved.`,
      );
    }
    const url = `${this.baseUrl()}/workflows/bid/${encodeURIComponent(workflowId)}/review-signal`;
    const body = {
      verdict: signal.verdict,
      reviewer: signal.reviewer,
      reviewer_role: signal.reviewerRole,
      comments: (signal.comments ?? []).map((c) => ({
        section: c.section,
        severity: c.severity,
        message: c.message,
        target_state: c.targetState,
      })),
      notes: signal.notes,
    };
    return this.request<{ status: string }>('POST', url, body);
  }

  async getStatus(
    bidId: string,
    roles: readonly string[] = [],
  ): Promise<WorkflowStatusResponse> {
    const workflowId = await this.requireWorkflowId(bidId);
    const url = `${this.baseUrl()}/workflows/bid/${encodeURIComponent(workflowId)}`;
    return this.request<WorkflowStatusResponse>('GET', url, undefined, roles);
  }

  /**
   * Return the named artifact field from the current workflow state snapshot.
   * The authoritative list of keys is defined in `ARTIFACT_KEYS` on the controller.
   */
  async getArtifact(
    bidId: string,
    key: string,
    roles: readonly string[] = [],
  ): Promise<unknown> {
    const status = await this.getStatus(bidId, roles);
    if (!Object.prototype.hasOwnProperty.call(status, key)) {
      throw new NotFoundException(
        `Artifact '${key}' is not present on bid ${bidId}.`,
      );
    }
    const value = (status as Record<string, unknown>)[key];
    if (value === null || value === undefined) {
      throw new NotFoundException(
        `Artifact '${key}' has not been produced yet for bid ${bidId}.`,
      );
    }
    return value;
  }

  private async requireWorkflowId(bidId: string): Promise<string> {
    const bid = await this.bidsService.findOne(bidId);
    if (!bid.workflowId) {
      throw new NotFoundException(`Bid ${bidId} has no active workflow.`);
    }
    return bid.workflowId;
  }

  private async request<T>(
    method: 'GET' | 'POST',
    url: string,
    body?: Record<string, unknown>,
    roles: readonly string[] = [],
  ): Promise<T> {
    const headers = rolesHeader(roles);
    try {
      const response: AxiosResponse<T> = await firstValueFrom(
        method === 'GET'
          ? this.http.get<T>(url, { timeout: 10_000, headers })
          : this.http.post<T>(url, body, { timeout: 10_000, headers }),
      );
      return response.data;
    } catch (err) {
      throw this.mapError(err, url);
    }
  }

  private mapError(err: unknown, url: string): HttpException {
    const axiosErr = err as AxiosError<{ message?: string; detail?: string }>;
    if (axiosErr?.code === 'ECONNABORTED' || axiosErr?.code === 'ETIMEDOUT') {
      this.logger.warn(`ai-service timeout on ${url}`);
      return new RequestTimeoutException('ai-service did not respond in time.');
    }
    const status = axiosErr?.response?.status;
    const upstream =
      axiosErr?.response?.data?.message ??
      axiosErr?.response?.data?.detail ??
      axiosErr?.message ??
      'ai-service error';
    if (status === HttpStatus.NOT_FOUND) {
      return new NotFoundException(upstream);
    }
    if (status && status >= 400 && status < 500) {
      return new HttpException(upstream, status);
    }
    this.logger.error(`ai-service upstream failure on ${url}: ${upstream}`);
    return new BadGatewayException(upstream);
  }
}
