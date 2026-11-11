import React, { createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode } from "react";
import { apiClient } from "../api/client";
import type {
  HealthStatus,
  TopologyData,
  ServiceEntity,
  Alert,
  Incident,
  RootCauseAnalysis,
  RemediationResult,
  RecoveryEvidence,
  RemediationAudit,
  CorrelationBenchmarkResult,
} from "../api/types";

interface OpsPilotContextType {
  health: HealthStatus | null;
  topology: TopologyData | null;
  services: ServiceEntity[];
  alerts: Alert[];
  incidents: Incident[];
  selectedIncident: Incident | null;
  selectedIncidentDetails: Incident | null;
  rca: RootCauseAnalysis | null;
  remediation: RemediationResult | null;
  recovery: RecoveryEvidence | null;
  audits: RemediationAudit[];
  benchmark: { total_alerts: number; benchmark: Record<string, CorrelationBenchmarkResult> } | null;
  isLoading: boolean;
  isActionLoading: boolean;
  isPolling: boolean;
  error: string | null;
  lastUpdated: Date | null;
  
  // Actions
  refreshAll: () => Promise<void>;
  selectIncident: (incident: Incident | null) => Promise<void>;
  triggerSync: () => Promise<void>;
  triggerCorrelation: (strategy?: "dependency_aware" | "time_only") => Promise<void>;
  triggerRca: (forceRefresh?: boolean, forceFallback?: boolean) => Promise<void>;
  triggerRemediation: (params?: {
    action?: string;
    target_service?: string;
    mode?: "SIMULATION" | "REAL";
    force?: boolean;
  }) => Promise<void>;
  triggerRecoveryVerification: () => Promise<void>;
  loadBenchmark: () => Promise<void>;
  triggerReset: () => Promise<void>;
  togglePolling: () => void;
  clearError: () => void;
}

const OpsPilotContext = createContext<OpsPilotContextType | undefined>(undefined);

export const OpsPilotProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [topology, setTopology] = useState<TopologyData | null>(null);
  const [services, setServices] = useState<ServiceEntity[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [selectedIncidentDetails, setSelectedIncidentDetails] = useState<Incident | null>(null);
  const [rca, setRca] = useState<RootCauseAnalysis | null>(null);
  const [remediation, setRemediation] = useState<RemediationResult | null>(null);
  const [recovery, setRecovery] = useState<RecoveryEvidence | null>(null);
  const [audits, setAudits] = useState<RemediationAudit[]>([]);
  const [benchmark, setBenchmark] = useState<{
    total_alerts: number;
    benchmark: Record<string, CorrelationBenchmarkResult>;
  } | null>(null);
  
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isActionLoading, setIsActionLoading] = useState<boolean>(false);
  const [isPolling, setIsPolling] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const activeIncidentId = useRef<string | null>(null);

  const clearError = () => setError(null);

  const loadIncidentDetails = useCallback(async (incidentId: string) => {
    try {
      const [details, rcaData, remData, auditList] = await Promise.all([
        apiClient.getIncident(incidentId),
        apiClient.getRootCause(incidentId).catch(() => null),
        apiClient.getLatestRemediation(incidentId).catch(() => null),
        apiClient.getIncidentAuditTrail(incidentId).catch(() => []),
      ]);
      if (activeIncidentId.current !== incidentId) return;
      setSelectedIncidentDetails(details);
      setRca(rcaData);
      setRemediation(remData);
      setRecovery(remData?.recovery_evidence || null);
      setAudits(auditList);
    } catch (err: any) {
      console.error("Failed to load incident details:", err);
      if (activeIncidentId.current === incidentId) {
        setSelectedIncidentDetails(null);
        setRca(null);
        setRemediation(null);
        setRecovery(null);
        setAudits([]);
        setError(`Incident details failed to load: ${err.message}`);
      }
    }
  }, []);

  const refreshAll = useCallback(async () => {
    try {
      const [h, topo, servs, alts, incs] = await Promise.all([
        apiClient.getHealth().catch(() => null),
        apiClient.getTopology().catch(() => null),
        apiClient.getServices().catch(() => []),
        apiClient.getAlerts(200).catch(() => []),
        apiClient.getIncidents().catch(() => []),
      ]);

      if (h) setHealth(h);
      if (topo) setTopology(topo);
      if (servs) setServices(servs);
      if (alts) setAlerts(alts);
      if (incs) {
        setIncidents(incs);
        // Automatically select the first incident if none selected or if selected is outdated
        if (incs.length > 0) {
          const currentIncident = selectedIncident
            ? incs.find((i) => i.incident_id === selectedIncident.incident_id)
            : undefined;
          const nextIncident = currentIncident || incs[0];
          if (!selectedIncident || !currentIncident || currentIncident.updated_at !== selectedIncident.updated_at) {
            activeIncidentId.current = nextIncident.incident_id;
            setSelectedIncident(nextIncident);
            await loadIncidentDetails(nextIncident.incident_id);
          } else {
            setSelectedIncident(currentIncident);
          }
        } else {
          activeIncidentId.current = null;
          setSelectedIncident(null);
          setSelectedIncidentDetails(null);
          setRca(null);
          setRemediation(null);
          setRecovery(null);
          setAudits([]);
        }
      }
      setLastUpdated(new Date());
    } catch (err: any) {
      console.error("Error refreshing OpsPilot data:", err);
    } finally {
      setIsLoading(false);
    }
  }, [selectedIncident, loadIncidentDetails]);

  // Initial load
  useEffect(() => {
    refreshAll();
  }, []);

  // Poll at a measured cadence and schedule the next refresh only after the
  // current one finishes, so slow API responses cannot stack up.
  useEffect(() => {
    if (!isPolling) return;
    let timer: ReturnType<typeof setTimeout>;
    let cancelled = false;
    const poll = async () => {
      await refreshAll();
      if (!cancelled) timer = setTimeout(poll, 5000);
    };
    timer = setTimeout(poll, 5000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [isPolling, refreshAll]);

  const selectIncident = async (incident: Incident | null) => {
    activeIncidentId.current = incident?.incident_id || null;
    setSelectedIncident(incident);
    if (incident) {
      setSelectedIncidentDetails(null);
      setRca(null);
      setRemediation(null);
      setRecovery(null);
      setAudits([]);
      await loadIncidentDetails(incident.incident_id);
    } else {
      activeIncidentId.current = null;
      setSelectedIncidentDetails(null);
      setRca(null);
      setRemediation(null);
      setRecovery(null);
      setAudits([]);
    }
  };

  const triggerSync = async () => {
    setIsActionLoading(true);
    setError(null);
    try {
      await apiClient.syncShopFlow();
      await refreshAll();
    } catch (err: any) {
      setError(`Sync failed: ${err.message}`);
    } finally {
      setIsActionLoading(false);
    }
  };

  const triggerCorrelation = async (strategy: "dependency_aware" | "time_only" = "dependency_aware") => {
    setIsActionLoading(true);
    setError(null);
    try {
      // Auto-sync freshest telemetry from ShopFlow immediately
      await apiClient.syncShopFlow().catch(() => {});
      const res = await apiClient.runCorrelation(strategy, true);
      await refreshAll();
      if (res.incidents && res.incidents.length > 0) {
        activeIncidentId.current = res.incidents[0].incident_id;
        setSelectedIncident(res.incidents[0]);
        await loadIncidentDetails(res.incidents[0].incident_id);
      }
    } catch (err: any) {
      setError(`Correlation failed: ${err.message}`);
    } finally {
      setIsActionLoading(false);
    }
  };

  const triggerRca = async (forceRefresh: boolean = true, forceFallback: boolean = false) => {
    if (!selectedIncident) return;
    setIsActionLoading(true);
    setError(null);
    try {
      const rcaResult = await apiClient.diagnoseRootCause(
        selectedIncident.incident_id,
        forceRefresh,
        forceFallback
      );
      setRca(rcaResult);
      await refreshAll();
    } catch (err: any) {
      setError(`RCA Diagnosis failed: ${err.message}`);
    } finally {
      setIsActionLoading(false);
    }
  };

  const triggerRemediation = async (params: {
    action?: string;
    target_service?: string;
    mode?: "SIMULATION" | "REAL";
    force?: boolean;
  } = {}) => {
    if (!selectedIncident) return;
    setIsActionLoading(true);
    setError(null);
    try {
      const remResult = await apiClient.remediateIncident(selectedIncident.incident_id, {
        ...params,
        mode: params.mode || "SIMULATION",
      });
      setRemediation(remResult);
      if (remResult.recovery_evidence) {
        setRecovery(remResult.recovery_evidence);
      }
      // Reload audits & details
      const auditList = await apiClient.getIncidentAuditTrail(selectedIncident.incident_id);
      setAudits(auditList);
      await refreshAll();
    } catch (err: any) {
      setError(`Remediation failed: ${err.message}`);
    } finally {
      setIsActionLoading(false);
    }
  };

  const triggerRecoveryVerification = async () => {
    if (!selectedIncident) return;
    setIsActionLoading(true);
    setError(null);
    try {
      const rec = await apiClient.verifyRecovery(selectedIncident.incident_id);
      setRecovery(rec);
      // Also update latest remediation record
      try {
        const remData = await apiClient.getLatestRemediation(selectedIncident.incident_id);
        setRemediation(remData);
      } catch {
        // ignore
      }
      const auditList = await apiClient.getIncidentAuditTrail(selectedIncident.incident_id);
      setAudits(auditList);
    } catch (err: any) {
      setError(`Recovery verification failed: ${err.message}`);
    } finally {
      setIsActionLoading(false);
    }
  };

  const loadBenchmark = async () => {
    setIsActionLoading(true);
    setError(null);
    try {
      const data = await apiClient.getCorrelationBenchmark();
      setBenchmark(data);
    } catch (err: any) {
      setError(`Benchmark load failed: ${err.message}`);
    } finally {
      setIsActionLoading(false);
    }
  };

  const triggerReset = async () => {
    setIsActionLoading(true);
    setError(null);
    try {
      const resetResult = await apiClient.resetAll();
      activeIncidentId.current = null;
      setSelectedIncident(null);
      setSelectedIncidentDetails(null);
      setRca(null);
      setRemediation(null);
      setRecovery(null);
      setAudits([]);
      setIncidents([]);
      setAlerts([]);
      await refreshAll();
      if (resetResult.shopflow_reset === "unavailable") {
        setError("OpsPilot was reset, but ShopFlow could not be reached. Start ShopFlow and reset again to clear its chaos state.");
      }
    } catch (err: any) {
      setError(`Reset failed: ${err.message}`);
    } finally {
      setIsActionLoading(false);
    }
  };

  const togglePolling = () => {
    setIsPolling((prev) => !prev);
  };

  return (
    <OpsPilotContext.Provider
      value={{
        health,
        topology,
        services,
        alerts,
        incidents,
        selectedIncident,
        selectedIncidentDetails,
        rca,
        remediation,
        recovery,
        audits,
        benchmark,
        isLoading,
        isActionLoading,
        isPolling,
        error,
        lastUpdated,
        refreshAll,
        selectIncident,
        triggerSync,
        triggerCorrelation,
        triggerRca,
        triggerRemediation,
        triggerRecoveryVerification,
        loadBenchmark,
        triggerReset,
        togglePolling,
        clearError,
      }}
    >
      {children}
    </OpsPilotContext.Provider>
  );
};

export const useOpsPilot = () => {
  const context = useContext(OpsPilotContext);
  if (!context) {
    throw new Error("useOpsPilot must be used within an OpsPilotProvider");
  }
  return context;
};
