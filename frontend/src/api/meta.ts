import type { HealthResponse, PipelineStatus } from "../types/api";
import { request } from "./client";
export const getHealth = (signal?: AbortSignal) =>
  request<HealthResponse>("/health", { signal });
export const getPipelineStatus = (signal?: AbortSignal) =>
  request<PipelineStatus>("/pipeline", { signal });
