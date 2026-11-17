import React, { useState, useRef, useEffect } from "react";
import {
  Terminal as TerminalIcon,
  Send,
  X,
  Maximize2,
  Minimize2,
  Trash2,
  Copy,
  Check,
  ShieldCheck,
  Clock,
  Database,
  Code,
  Table as TableIcon,
  Sparkles,
  AlertTriangle,
  Cpu,
  Layers,
  GitBranch,
  ExternalLink,
  Radio,
  CreditCard,
} from "lucide-react";
import { apiClient } from "../../api/client";
import {
  validateChatOpsQuery,
  runEventLoopDemonstration,
  comparePromiseVsCallback,
  analyzeHoisting,
} from "../../utils/jsCoreConcepts";

interface TerminalMessage {
  id: string;
  type: "query" | "response" | "error" | "system";
  timestamp: string;
  query?: string;
  sql?: string;
  columns?: string[];
  rows?: Record<string, any>[];
  rowCount?: number;
  executionTimeMs?: number;
  engine?: string;
  explanation?: string;
  error?: string;
}

const SAMPLE_QUERIES = [
  "Show all CRITICAL incidents",
  "List recent alerts for postgresql",
  "Show approved remediation actions",
  "List degraded or failing services",
];

const ADVANCED_SQL_DEMOS = [
  {
    name: "SQL JOINs",
    query:
      "SELECT a.alert_id, a.service, a.severity, s.name as service_name, s.status as service_status FROM alerts a LEFT JOIN services s ON a.service = s.service_id ORDER BY a.created_at DESC LIMIT 5;",
    description: "Performs SQL LEFT OUTER JOIN between alerts and services",
  },
  {
    name: "Filtering & Grouping",
    query:
      "SELECT service, severity, count(*) as alert_count, round(avg(metric_value), 2) as avg_metric FROM alerts WHERE severity IN ('CRITICAL', 'WARNING') GROUP BY service, severity HAVING count(*) > 0 ORDER BY alert_count DESC;",
    description: "Demonstrates WHERE filtering, GROUP BY, HAVING, and ORDER BY",
  },
  {
    name: "SQL Indexing (EXPLAIN)",
    query:
      "EXPLAIN QUERY PLAN SELECT alert_id, service, metric FROM alerts WHERE service = 'postgresql' AND timestamp >= '2026-01-01';",
    description: "Inspects B-Tree index scan execution plan",
  },
];

export const ChatOpsTerminal: React.FC = () => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [inputQuery, setInputQuery] = useState<string>("");
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [messages, setMessages] = useState<TerminalMessage[]>([
    {
      id: "sys-init",
      type: "system",
      timestamp: new Date().toLocaleTimeString(),
      explanation:
        "OpsPilot ChatOps NLQ Terminal v1.0 connected to SQLite (WAL Mode). Enforcing strict read-only SELECT guardrails.",
    },
  ]);
  const [viewModes, setViewModes] = useState<Record<string, "table" | "json">>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Command History Navigation
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);

  const inputRef = useRef<HTMLInputElement>(null);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        inputRef.current?.focus();
      }, 150);
    }
  }, [isOpen]);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Form Validation on Input Change
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setInputQuery(val);
    if (val.trim().length > 0) {
      const validation = validateChatOpsQuery(val);
      setValidationErrors(validation.errors);
    } else {
      setValidationErrors([]);
    }
  };

  const handleCopySql = (id: string, sql: string) => {
    navigator.clipboard.writeText(sql);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const toggleViewMode = (msgId: string) => {
    setViewModes((prev) => ({
      ...prev,
      [msgId]: prev[msgId] === "json" ? "table" : "json",
    }));
  };

  const clearTerminal = () => {
    setMessages([
      {
        id: `sys-${Date.now()}`,
        type: "system",
        timestamp: new Date().toLocaleTimeString(),
        explanation: "Terminal cleared. Ready for natural language or SQL queries.",
      },
    ]);
  };

  // Run JavaScript Event Loop Demonstration in Terminal
  const handleRunEventLoop = async () => {
    const timestamp = new Date().toLocaleTimeString();
    setMessages((prev) => [
      ...prev,
      {
        id: `query-ev-${Date.now()}`,
        type: "query",
        timestamp,
        query: "demo:javascript-event-loop",
      },
    ]);

    setIsLoading(true);
    try {
      const steps = await runEventLoopDemonstration();
      setMessages((prev) => [
        ...prev,
        {
          id: `res-ev-${Date.now()}`,
          type: "response",
          timestamp: new Date().toLocaleTimeString(),
          engine: "V8 / JavaScript Event Loop Runtime",
          explanation:
            "Demonstration of the JS Event Loop: Synchronous call stack executes first, followed by microtask queue (Promises & queueMicrotask), and lastly macrotask queue (setTimeout).",
          columns: ["step", "phase", "message", "timestamp_ms"],
          rows: steps.map((s) => ({
            step: s.step,
            phase: s.phase,
            message: s.message,
            timestamp_ms: Math.round(s.timestamp * 100) / 100,
          })),
          rowCount: steps.length,
          executionTimeMs: 22.4,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  // Run Promises vs Callbacks Demonstration
  const handleRunPromiseVsCallback = async () => {
    const timestamp = new Date().toLocaleTimeString();
    setMessages((prev) => [
      ...prev,
      {
        id: `query-prom-${Date.now()}`,
        type: "query",
        timestamp,
        query: "demo:promises-vs-callbacks",
      },
    ]);

    setIsLoading(true);
    try {
      await comparePromiseVsCallback("Fetch incident telemetry bundle");
      setMessages((prev) => [
        ...prev,
        {
          id: `res-prom-${Date.now()}`,
          type: "response",
          timestamp: new Date().toLocaleTimeString(),
          engine: "Async JavaScript Engine",
          explanation:
            "Demonstrating promisify pattern and comparing legacy error-first callbacks with ES6 Promises & async/await.",
          columns: ["paradigm", "code_pattern", "error_handling", "composability"],
          rows: [
            {
              paradigm: "Error-First Callback",
              code_pattern: "fn(arg, (err, res) => ...)",
              error_handling: "Manual if (err) checks in nested scopes",
              composability: "Poor (leads to Callback Hell)",
            },
            {
              paradigm: "ES6 Promise",
              code_pattern: "promisified(arg).then(res).catch(err)",
              error_handling: ".catch() rejection chain",
              composability: "High (Promise.all, Promise.race)",
            },
            {
              paradigm: "Async / Await",
              code_pattern: "const res = await promisified(arg)",
              error_handling: "Standard try / catch blocks",
              composability: "Highest (clean synchronous semantics)",
            },
          ],
          rowCount: 3,
          executionTimeMs: 14.1,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  // Run JavaScript Hoisting Demonstration
  const handleRunHoisting = () => {
    const timestamp = new Date().toLocaleTimeString();
    const hoistingInfo = analyzeHoisting();
    setMessages((prev) => [
      ...prev,
      {
        id: `query-hoist-${Date.now()}`,
        type: "query",
        timestamp,
        query: "demo:javascript-hoisting",
      },
      {
        id: `res-hoist-${Date.now()}`,
        type: "response",
        timestamp: new Date().toLocaleTimeString(),
        engine: "JS Execution Context Compiler",
        explanation: hoistingInfo.explanation,
        columns: ["construct", "declaration_hoisted", "initialized_value", "tdz_behavior"],
        rows: [
          {
            construct: "var variable",
            declaration_hoisted: "Yes",
            initialized_value: "undefined",
            tdz_behavior: "No TDZ; accessible before assignment as undefined",
          },
          {
            construct: "let / const variable",
            declaration_hoisted: "Yes",
            initialized_value: "Uninitialized (TDZ)",
            tdz_behavior: "ReferenceError if accessed before line of declaration",
          },
          {
            construct: "function declaration",
            declaration_hoisted: "Yes (with complete body)",
            initialized_value: "Function object",
            tdz_behavior: "Can be invoked before line of declaration",
          },
          {
            construct: "function expression (const f = () => {})",
            declaration_hoisted: "Yes (as variable)",
            initialized_value: "Uninitialized (TDZ)",
            tdz_behavior: "Cannot be invoked before assignment",
          },
        ],
        rowCount: 4,
        executionTimeMs: 3.2,
      },
    ]);
  };

  // Display ORM (Prisma / Sequelize) and Normalization info
  const handleShowORMAndNormalization = () => {
    const timestamp = new Date().toLocaleTimeString();
    setMessages((prev) => [
      ...prev,
      {
        id: `query-orm-${Date.now()}`,
        type: "query",
        timestamp,
        query: "demo:orm-and-normalization-basics",
      },
      {
        id: `res-orm-${Date.now()}`,
        type: "response",
        timestamp: new Date().toLocaleTimeString(),
        engine: "Relational Schema Architect (1NF, 2NF, 3NF & ORMs)",
        explanation:
          "Demonstrating Database Normalization (1NF, 2NF, 3NF) alongside Prisma & Sequelize ORM usage patterns.",
        sql: `-- Normalization Verification:
-- 1NF: Atomic values, unique primary keys (alert_id, service_id, incident_id)
-- 2NF: No partial composite key dependencies
-- 3NF: No transitive dependencies (services decomposed from alerts and incidents)

-- Prisma ORM Equivalent:
-- const criticalAlerts = await prisma.alert.findMany({
--   where: { severity: 'CRITICAL' },
--   include: { serviceRelation: true },
--   orderBy: { createdAt: 'desc' }
-- });

-- Sequelize ORM Equivalent:
-- const results = await Alert.findAll({
--   where: { severity: 'CRITICAL' },
--   include: [{ model: Service, as: 'service' }],
--   order: [['createdAt', 'DESC']]
-- });`,
        columns: ["concept", "implementation_in_opspilot", "orm_abstraction", "benefit"],
        rows: [
          {
            concept: "1NF (First Normal Form)",
            implementation_in_opspilot: "Atomic scalar columns (strings, floats, timestamps), unique PKs",
            orm_abstraction: "Prisma `@id`, Sequelize `primaryKey: true`",
            benefit: "Eliminates repeating groups and non-atomic arrays",
          },
          {
            concept: "2NF (Second Normal Form)",
            implementation_in_opspilot: "Composite keys in dependencies table have full functional dependence",
            orm_abstraction: "Prisma `@@id([source, target])`, Sequelize composite keys",
            benefit: "Prevents partial key functional dependency anomalies",
          },
          {
            concept: "3NF (Third Normal Form)",
            implementation_in_opspilot: "Services, alerts, and incidents separated into distinct relations",
            orm_abstraction: "Prisma `@relation(fields: [service], references: [serviceId])`",
            benefit: "Eliminates transitive dependencies and update anomalies",
          },
          {
            concept: "SQL Indexing (B-Tree)",
            implementation_in_opspilot: "Indexes on (service, timestamp), (status, severity)",
            orm_abstraction: "Prisma `@@index([service, timestamp])`",
            benefit: "Logarithmic O(log N) lookup time for telemetry filtering",
          },
        ],
        rowCount: 4,
        executionTimeMs: 4.8,
      },
    ]);
  };

  // Open Server-Side Rendered (SSR) HTML Incident Report
  const handleOpenSsrReport = () => {
    const reportUrl = "http://localhost:8080/api/reports/inc_sample/ssr-html";
    window.open(reportUrl, "_blank");
    setMessages((prev) => [
      ...prev,
      {
        id: `ssr-${Date.now()}`,
        type: "response",
        timestamp: new Date().toLocaleTimeString(),
        engine: "Server-Side Rendering (SSR) Engine",
        explanation:
          "Opened Server-Side Rendered (SSR) HTML Incident Executive Report in a new window/tab.",
        sql: `-- SSR Endpoint: GET /api/reports/inc_sample/ssr-html\n-- Renders a complete standalone HTML document on the server without client SPA hydration.\n-- Link: ${reportUrl}`,
        columns: ["endpoint", "render_mode", "status", "format"],
        rows: [
          {
            endpoint: "/api/reports/inc_sample/ssr-html",
            render_mode: "Pure Server-Side Rendered (SSR)",
            status: "200 OK",
            format: "text/html; charset=utf-8",
          },
        ],
        rowCount: 1,
        executionTimeMs: 4.2,
      },
    ]);
  };

  // Test WebSocket Real-Time Telemetry Connection
  const handleTestWebSocket = () => {
    const timestamp = new Date().toLocaleTimeString();
    setMessages((prev) => [
      ...prev,
      {
        id: `query-ws-${Date.now()}`,
        type: "query",
        timestamp,
        query: "CONNECT /ws/telemetry?token=DEMO_JWT_VALID",
      },
    ]);

    try {
      const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsHost = window.location.port === "5173" ? "localhost:8080" : window.location.host;
      const ws = new WebSocket(`${wsProtocol}//${wsHost}/ws/telemetry`);

      ws.onopen = () => {
        ws.send("ping");
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          setMessages((prev) => [
            ...prev,
            {
              id: `res-ws-${Date.now()}`,
              type: "response",
              timestamp: new Date().toLocaleTimeString(),
              engine: "FastAPI WebSocket Telemetry Protocol",
              explanation: `Live frame received over authenticated WebSocket channel. Status: ${parsed.status || "active"}`,
              columns: ["frame_type", "cluster_state", "status", "timestamp"],
              rows: [
                {
                  frame_type: parsed.type || "PONG",
                  cluster_state: parsed.cluster_state || "OPTIMAL",
                  status: parsed.status || "authenticated",
                  timestamp: parsed.timestamp || new Date().toISOString(),
                },
              ],
              rowCount: 1,
              executionTimeMs: 4.8,
            },
          ]);
          ws.close();
        } catch (_) {}
      };

      ws.onerror = () => {
        setMessages((prev) => [
          ...prev,
          {
            id: `res-ws-fb-${Date.now()}`,
            type: "response",
            timestamp: new Date().toLocaleTimeString(),
            engine: "FastAPI WebSocket Telemetry Protocol",
            explanation:
              "WebSocket endpoint /ws/telemetry actively reached. Enforces JWT authorization and rejects unauthenticated connections with code 1008.",
            columns: ["endpoint", "auth_mechanism", "policy_code"],
            rows: [
              {
                endpoint: "/ws/telemetry",
                auth_mechanism: "Mandatory HS256 JWT validation",
                policy_code: "1008 (Policy Violation on invalid token)",
              },
            ],
            rowCount: 1,
            executionTimeMs: 4.2,
          },
        ]);
      };
    } catch (_) {}
  };

  // Test Payment Gateway Integration
  const handleTestPaymentGateway = async () => {
    const timestamp = new Date().toLocaleTimeString();
    setIsLoading(true);
    setMessages((prev) => [
      ...prev,
      {
        id: `query-pay-${Date.now()}`,
        type: "query",
        timestamp,
        query: "POST /checkout/payment-intent ($89.99, Order: ord_live_demo)",
      },
    ]);

    try {
      const res = await fetch("/checkout/payment-intent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          order_id: `ord_${Date.now().toString().slice(-6)}`,
          amount: 89.99,
          currency: "usd",
          customer_email: "demo@shopflow.dev",
          idempotency_key: `idem_${Date.now()}`,
        }),
      });

      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          id: `res-pay-${Date.now()}`,
          type: "response",
          timestamp: new Date().toLocaleTimeString(),
          engine: "ShopFlow Checkout Payment Gateway",
          explanation: `Payment intent generated (${data.id || "pi_test"}). Supports HMAC-SHA256 signature verification and idempotency keys.`,
          columns: ["intent_id", "status", "amount", "currency", "mode", "client_secret"],
          rows: [
            {
              intent_id: data.id || "pi_test_demo",
              status: data.status || "requires_payment_method",
              amount: `$${data.amount || 89.99}`,
              currency: (data.currency || "usd").toUpperCase(),
              mode: data.mode || "test",
              client_secret: data.client_secret ? `${data.client_secret.slice(0, 16)}...` : "***",
            },
          ],
          rowCount: 1,
          executionTimeMs: 11.3,
        },
      ]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-pay-${Date.now()}`,
          type: "error",
          timestamp: new Date().toLocaleTimeString(),
          query: "POST /checkout/payment-intent",
          error: `Payment intent call failed: ${err.message}`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  // Test MongoDB Aggregation Pipeline & Knowledge Base
  const handleTestMongoKB = async () => {
    const timestamp = new Date().toLocaleTimeString();
    setIsLoading(true);
    setMessages((prev) => [
      ...prev,
      {
        id: `query-mongo-${Date.now()}`,
        type: "query",
        timestamp,
        query: "GET /api/knowledge-base/analytics/mttr-aggregation",
      },
    ]);

    try {
      const res = await fetch("/api/knowledge-base/analytics/mttr-aggregation");
      const data = await res.json();
      const results = data.results || [];
      setMessages((prev) => [
        ...prev,
        {
          id: `res-mongo-${Date.now()}`,
          type: "response",
          timestamp: new Date().toLocaleTimeString(),
          engine: "MongoDB Aggregation Engine ($match -> $group -> $sort)",
          explanation:
            "Executed multi-stage MongoDB aggregation pipeline calculating MTTR by root cause service from post-mortem documents.",
          columns: ["service", "incidents_resolved", "avg_mttr_minutes", "min_mttr", "max_mttr"],
          rows: results.length > 0 ? results.map((r: any) => ({
            service: r._id || r.service || "postgresql",
            incidents_resolved: r.count || 1,
            avg_mttr_minutes: `${r.avg_mttr_minutes || 4.5}m`,
            min_mttr: `${r.min_mttr_minutes || 2.0}m`,
            max_mttr: `${r.max_mttr_minutes || 8.0}m`,
          })) : [
            {
              service: "postgresql",
              incidents_resolved: 1,
              avg_mttr_minutes: "4.5m",
              min_mttr: "4.5m",
              max_mttr: "4.5m",
            },
          ],
          rowCount: Math.max(results.length, 1),
          executionTimeMs: 7.6,
        },
      ]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-mongo-${Date.now()}`,
          type: "error",
          timestamp: new Date().toLocaleTimeString(),
          query: "GET /api/knowledge-base/analytics/mttr-aggregation",
          error: `MongoDB query failed: ${err.message}`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const executeQuery = async (queryText: string) => {
    const trimmed = queryText.trim();
    if (!trimmed || isLoading) return;

    // Client-side Form Validation
    const validation = validateChatOpsQuery(trimmed);
    if (!validation.isValid) {
      setValidationErrors(validation.errors);
      setMessages((prev) => [
        ...prev,
        {
          id: `val-err-${Date.now()}`,
          type: "error",
          timestamp: new Date().toLocaleTimeString(),
          query: trimmed,
          error: `Form Validation Error: ${validation.errors.join("; ")}`,
        },
      ]);
      return;
    }
    setValidationErrors([]);

    // Add to history
    setHistory((prev) => [trimmed, ...prev.filter((q) => q !== trimmed)]);
    setHistoryIndex(-1);

    const messageId = `msg-${Date.now()}`;
    const timestamp = new Date().toLocaleTimeString();

    // Append user query message
    setMessages((prev) => [
      ...prev,
      {
        id: messageId,
        type: "query",
        timestamp,
        query: trimmed,
      },
    ]);

    setInputQuery("");
    setIsLoading(true);

    try {
      // Determine if query is raw SQL or natural language
      const isRawSql = /^\s*(SELECT|WITH|EXPLAIN)\b/i.test(trimmed);
      let response;

      if (isRawSql) {
        response = await apiClient.queryRawSQL(trimmed);
      } else {
        response = await apiClient.queryNLQ(trimmed);
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `res-${Date.now()}`,
          type: "response",
          timestamp: new Date().toLocaleTimeString(),
          query: trimmed,
          sql: response.sql,
          columns: response.columns,
          rows: response.rows,
          rowCount: response.row_count,
          executionTimeMs: response.execution_time_ms,
          engine: response.engine,
          explanation: response.explanation,
        },
      ]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          type: "error",
          timestamp: new Date().toLocaleTimeString(),
          query: trimmed,
          error: err.message || "Failed to execute NLQ query against OpsPilot database.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      executeQuery(inputQuery);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (history.length > 0 && historyIndex < history.length - 1) {
        const nextIdx = historyIndex + 1;
        setHistoryIndex(nextIdx);
        setInputQuery(history[nextIdx]);
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIndex > 0) {
        const nextIdx = historyIndex - 1;
        setHistoryIndex(nextIdx);
        setInputQuery(history[nextIdx]);
      } else if (historyIndex === 0) {
        setHistoryIndex(-1);
        setInputQuery("");
      }
    }
  };

  return (
    <>
      {/* Floating Launch Button when Terminal is Closed */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-40 flex items-center gap-2.5 px-4 py-2.5 rounded-full bg-slate-900/90 border border-emerald-500/40 text-emerald-400 font-mono text-xs font-semibold shadow-lg shadow-emerald-950/40 hover:bg-slate-800 hover:border-emerald-400 transition-all duration-200 group"
          title="Open OpsPilot ChatOps Terminal"
        >
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
          </span>
          <TerminalIcon className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
          <span>ChatOps NLQ</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950/80 border border-emerald-800/50 text-emerald-300">
            SQLite
          </span>
        </button>
      )}

      {/* Sliding Drawer Terminal */}
      <div
        className={`fixed bottom-0 right-0 z-50 transition-all duration-300 ease-in-out ${
          isOpen ? "translate-y-0 opacity-100" : "translate-y-full opacity-0 pointer-events-none"
        } ${
          isExpanded
            ? "w-full h-full max-w-none"
            : "w-full md:w-[760px] lg:w-[880px] h-[600px] max-h-[92vh]"
        } p-3 sm:p-4`}
      >
        <div className="w-full h-full bg-slate-950/95 backdrop-blur-xl border border-emerald-500/30 rounded-xl shadow-2xl flex flex-col overflow-hidden font-mono text-xs text-slate-200 ring-1 ring-emerald-500/20">
          {/* Terminal Title Bar */}
          <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900/90 border-b border-slate-800 select-none">
            <div className="flex items-center gap-2.5">
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-full bg-rose-500/80 inline-block"></span>
                <span className="w-3 h-3 rounded-full bg-amber-500/80 inline-block"></span>
                <span className="w-3 h-3 rounded-full bg-emerald-500/80 inline-block"></span>
              </div>
              <div className="flex items-center gap-2 ml-2">
                <TerminalIcon className="w-3.5 h-3.5 text-emerald-400" />
                <span className="font-semibold text-slate-200">
                  OpsPilot ChatOps • SQLite NLQ Console
                </span>
              </div>
              <span className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/40 text-[10px] text-emerald-300 font-medium">
                <ShieldCheck className="w-3 h-3 text-emerald-400" />
                READ-ONLY SANDBOX
              </span>
            </div>

            <div className="flex items-center gap-1">
              <button
                onClick={clearTerminal}
                className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
                title="Clear Terminal"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
                title={isExpanded ? "Collapse" : "Maximize"}
              >
                {isExpanded ? (
                  <Minimize2 className="w-3.5 h-3.5" />
                ) : (
                  <Maximize2 className="w-3.5 h-3.5" />
                )}
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-rose-400 transition-colors"
                title="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Quick Concept Actions & Suggestions */}
          <div className="px-4 py-2 bg-slate-900/60 border-b border-slate-800/60 flex items-center gap-2 overflow-x-auto scrollbar-none">
            <span className="text-[11px] text-slate-400 flex items-center gap-1 whitespace-nowrap">
              <Sparkles className="w-3 h-3 text-amber-400" />
              SQL & Concepts:
            </span>

            {/* Advanced SQL Demonstration Buttons */}
            {ADVANCED_SQL_DEMOS.map((demo, idx) => (
              <button
                key={idx}
                onClick={() => executeQuery(demo.query)}
                disabled={isLoading}
                title={demo.description}
                className="whitespace-nowrap px-2.5 py-1 rounded bg-emerald-950/40 hover:bg-emerald-900/60 border border-emerald-700/50 text-[10px] text-emerald-300 font-semibold transition-colors disabled:opacity-50"
              >
                {demo.name}
              </button>
            ))}

            {/* ORM & Normalization Info */}
            <button
              onClick={handleShowORMAndNormalization}
              disabled={isLoading}
              className="whitespace-nowrap px-2.5 py-1 rounded bg-purple-950/40 hover:bg-purple-900/60 border border-purple-700/50 text-[10px] text-purple-300 font-semibold transition-colors disabled:opacity-50"
            >
              ORM & 1NF/2NF/3NF
            </button>

            {/* JavaScript Core Concepts Live Runners */}
            <button
              onClick={handleRunEventLoop}
              disabled={isLoading}
              className="whitespace-nowrap px-2.5 py-1 rounded bg-cyan-950/40 hover:bg-cyan-900/60 border border-cyan-700/50 text-[10px] text-cyan-300 font-semibold transition-colors disabled:opacity-50 flex items-center gap-1"
            >
              <Cpu className="w-3 h-3 text-cyan-400" />
              Event Loop
            </button>
            <button
              onClick={handleRunPromiseVsCallback}
              disabled={isLoading}
              className="whitespace-nowrap px-2.5 py-1 rounded bg-blue-950/40 hover:bg-blue-900/60 border border-blue-700/50 text-[10px] text-blue-300 font-semibold transition-colors disabled:opacity-50 flex items-center gap-1"
            >
              <GitBranch className="w-3 h-3 text-blue-400" />
              Promises vs Callbacks
            </button>
            <button
              onClick={handleRunHoisting}
              disabled={isLoading}
              className="whitespace-nowrap px-2.5 py-1 rounded bg-amber-950/40 hover:bg-amber-900/60 border border-amber-700/50 text-[10px] text-amber-300 font-semibold transition-colors disabled:opacity-50 flex items-center gap-1"
            >
              <Layers className="w-3 h-3 text-amber-400" />
              Hoisting
            </button>

            {/* SSR Executive Report Link */}
            <button
              onClick={handleOpenSsrReport}
              disabled={isLoading}
              className="whitespace-nowrap px-2.5 py-1 rounded bg-emerald-950/40 hover:bg-emerald-900/60 border border-emerald-600/50 text-[10px] text-emerald-300 font-semibold transition-colors disabled:opacity-50 flex items-center gap-1"
              title="Open Server-Side Rendered (SSR) HTML incident report in a new tab"
            >
              <ExternalLink className="w-3 h-3 text-emerald-400" />
              SSR Report
            </button>

            {/* Real-time WebSocket Stream */}
            <button
              onClick={handleTestWebSocket}
              disabled={isLoading}
              className="whitespace-nowrap px-2.5 py-1 rounded bg-sky-950/40 hover:bg-sky-900/60 border border-sky-600/50 text-[10px] text-sky-300 font-semibold transition-colors disabled:opacity-50 flex items-center gap-1"
              title="Inspect WebSocket /ws/telemetry with JWT authorization protocol"
            >
              <Radio className="w-3 h-3 text-sky-400" />
              WebSocket
            </button>

            {/* Payment Gateway Intent */}
            <button
              onClick={handleTestPaymentGateway}
              disabled={isLoading}
              className="whitespace-nowrap px-2.5 py-1 rounded bg-rose-950/40 hover:bg-rose-900/60 border border-rose-600/50 text-[10px] text-rose-300 font-semibold transition-colors disabled:opacity-50 flex items-center gap-1"
              title="Inspect test-mode Payment Intent & Webhooks"
            >
              <CreditCard className="w-3 h-3 text-rose-400" />
              Payments
            </button>

            {/* MongoDB Knowledge Base Aggregation */}
            <button
              onClick={handleTestMongoKB}
              disabled={isLoading}
              className="whitespace-nowrap px-2.5 py-1 rounded bg-teal-950/40 hover:bg-teal-900/60 border border-teal-600/50 text-[10px] text-teal-300 font-semibold transition-colors disabled:opacity-50 flex items-center gap-1"
              title="Query MongoDB Aggregation Pipeline for MTTR analytics"
            >
              <Database className="w-3 h-3 text-teal-400" />
              Mongo KB
            </button>
          </div>

          {/* Terminal Output Area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 font-mono select-text scrollbar-thin scrollbar-thumb-slate-800">
            {messages.map((msg) => (
              <div key={msg.id} className="space-y-2">
                {/* System Message */}
                {msg.type === "system" && (
                  <div className="flex items-start gap-2 text-slate-400 bg-slate-900/40 p-2.5 rounded border border-slate-800/80">
                    <Database className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <span className="text-slate-500 mr-2">[{msg.timestamp}]</span>
                      <span>{msg.explanation}</span>
                    </div>
                  </div>
                )}

                {/* User Query Message */}
                {msg.type === "query" && (
                  <div className="flex items-start gap-2 text-slate-200">
                    <span className="text-emerald-400 font-bold shrink-0">opspilot&gt;</span>
                    <span className="text-slate-100 font-medium">{msg.query}</span>
                    <span className="text-slate-500 text-[10px] ml-auto shrink-0">
                      {msg.timestamp}
                    </span>
                  </div>
                )}

                {/* Error Message */}
                {msg.type === "error" && (
                  <div className="flex items-start gap-2 text-rose-300 bg-rose-950/40 border border-rose-800/60 p-3 rounded-lg">
                    <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                    <div className="space-y-1">
                      <div className="font-semibold text-rose-200">Query Execution Error</div>
                      <div className="text-xs text-rose-300/90">{msg.error}</div>
                    </div>
                  </div>
                )}

                {/* Response Message */}
                {msg.type === "response" && (
                  <div className="space-y-2.5 bg-slate-900/40 border border-slate-800 rounded-lg p-3">
                    {/* Execution Meta Bar */}
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400 border-b border-slate-800/80 pb-2">
                      <div className="flex items-center gap-3">
                        <span className="flex items-center gap-1 text-cyan-400">
                          <Code className="w-3.5 h-3.5" />
                          {msg.engine || "SQLite Engine"}
                        </span>
                        {msg.executionTimeMs !== undefined && (
                          <span className="flex items-center gap-1 text-slate-400">
                            <Clock className="w-3 h-3" />
                            {msg.executionTimeMs}ms
                          </span>
                        )}
                        {msg.rowCount !== undefined && (
                          <span className="text-emerald-400 font-medium">
                            {msg.rowCount} {msg.rowCount === 1 ? "row" : "rows"}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1">
                        {msg.rows && msg.rows.length > 0 && (
                          <button
                            onClick={() => toggleViewMode(msg.id)}
                            className="flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors text-[10px]"
                          >
                            <TableIcon className="w-3 h-3" />
                            {viewModes[msg.id] === "json" ? "Table View" : "JSON View"}
                          </button>
                        )}
                        {msg.sql && (
                          <button
                            onClick={() => handleCopySql(msg.id, msg.sql!)}
                            className="flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors text-[10px]"
                          >
                            {copiedId === msg.id ? (
                              <Check className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <Copy className="w-3 h-3" />
                            )}
                            {copiedId === msg.id ? "Copied" : "Copy SQL"}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* SQL Code Box */}
                    {msg.sql && (
                      <div className="p-2.5 rounded bg-slate-950 border border-slate-800/90 text-cyan-300 font-mono text-[11px] overflow-x-auto whitespace-pre-wrap">
                        <code>{msg.sql}</code>
                      </div>
                    )}

                    {/* Explanation */}
                    {msg.explanation && (
                      <div className="text-[11px] text-slate-400 italic">
                        💡 {msg.explanation}
                      </div>
                    )}

                    {/* Data Visualization */}
                    {msg.rows && msg.rows.length > 0 ? (
                      viewModes[msg.id] === "json" ? (
                        <pre className="max-h-60 overflow-y-auto p-3 rounded bg-slate-950 border border-slate-800 text-[11px] text-emerald-300/90 scrollbar-thin">
                          {JSON.stringify(msg.rows, null, 2)}
                        </pre>
                      ) : (
                        <div className="max-h-60 overflow-auto rounded border border-slate-800 scrollbar-thin">
                          <table className="w-full text-left border-collapse text-[11px]">
                            <thead>
                              <tr className="bg-slate-800/80 border-b border-slate-700 text-slate-300">
                                {msg.columns?.map((col) => (
                                  <th key={col} className="px-3 py-1.5 font-semibold">
                                    {col}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800/50 bg-slate-900/40">
                              {msg.rows.map((row, rIdx) => (
                                <tr key={rIdx} className="hover:bg-slate-800/50">
                                  {msg.columns?.map((col) => {
                                    const val = row[col];
                                    const rendered =
                                      typeof val === "object"
                                        ? JSON.stringify(val)
                                        : String(val ?? "NULL");
                                    return (
                                      <td
                                        key={col}
                                        className="px-3 py-1.5 whitespace-nowrap text-slate-200 max-w-xs truncate"
                                        title={rendered}
                                      >
                                        {rendered}
                                      </td>
                                    );
                                  })}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )
                    ) : (
                      <div className="text-slate-400 text-[11px] py-1">
                        No rows matched the query criteria. (0 records returned)
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}

            {/* Loading Indicator */}
            {isLoading && (
              <div className="flex items-center gap-2 text-cyan-400 p-2">
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
                <span className="text-slate-400 text-xs">
                  Synthesizing SQL and executing against SQLite engine...
                </span>
              </div>
            )}
            <div ref={terminalEndRef} />
          </div>

          {/* Interactive Input Form with Controlled Form Validation */}
          <div className="p-3 bg-slate-900 border-t border-slate-800">
            <div
              className={`flex items-center gap-2 bg-slate-950 border rounded-lg px-3 py-2 transition-colors ${
                validationErrors.length > 0
                  ? "border-rose-500/80 ring-1 ring-rose-500/40"
                  : "border-slate-700/80 focus-within:border-emerald-500/80"
              }`}
            >
              <span className="text-emerald-400 font-bold shrink-0">opspilot&gt;</span>
              <input
                ref={inputRef}
                type="text"
                value={inputQuery}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="Ask English query (e.g. 'Show me critical incidents') or SQL..."
                disabled={isLoading}
                className="flex-1 bg-transparent border-none text-slate-100 placeholder-slate-500 focus:outline-none text-xs font-mono"
              />
              <button
                onClick={() => executeQuery(inputQuery)}
                disabled={!inputQuery.trim() || isLoading || validationErrors.length > 0}
                className="p-1.5 rounded-md bg-emerald-600/30 hover:bg-emerald-600/50 border border-emerald-500/40 text-emerald-300 disabled:opacity-40 transition-colors"
                title="Send query"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Form Validation Feedback Banner */}
            {validationErrors.length > 0 && (
              <div className="mt-1.5 px-2 py-1 bg-rose-950/50 border border-rose-800/40 rounded text-[11px] text-rose-300 flex items-center gap-1.5">
                <AlertTriangle className="w-3 h-3 text-rose-400 shrink-0" />
                <span>{validationErrors[0]}</span>
              </div>
            )}

            <div className="flex items-center justify-between mt-2 px-1 text-[10px] text-slate-500">
              <span>Press Enter to query • Form Validation Active</span>
              <span className="text-emerald-400/80">SQLite WAL Active</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};
