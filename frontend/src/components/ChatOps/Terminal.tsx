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
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  Clock,
  Database,
  Code,
  Table as TableIcon,
  Sparkles,
  AlertTriangle,
} from "lucide-react";
import { apiClient } from "../../api/client";

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
  "Show error logs with high latency",
];

export const ChatOpsTerminal: React.FC = () => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [inputQuery, setInputQuery] = useState<string>("");
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
        explanation: "Terminal screen cleared. Read-only SQLite sandbox active.",
      },
    ]);
  };

  const executeQuery = async (queryText: string) => {
    const trimmed = queryText.trim();
    if (!trimmed || isLoading) return;

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
      const isRawSql = /^\s*(SELECT|WITH)\b/i.test(trimmed);
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
            : "w-full md:w-[720px] lg:w-[840px] h-[580px] max-h-[90vh]"
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

          {/* Quick Suggestion Chips */}
          <div className="px-4 py-2 bg-slate-900/50 border-b border-slate-800/60 flex items-center gap-2 overflow-x-auto scrollbar-none">
            <span className="text-[11px] text-slate-400 flex items-center gap-1 whitespace-nowrap">
              <Sparkles className="w-3 h-3 text-amber-400" />
              Suggestions:
            </span>
            {SAMPLE_QUERIES.map((sample, idx) => (
              <button
                key={idx}
                onClick={() => executeQuery(sample)}
                disabled={isLoading}
                className="whitespace-nowrap px-2.5 py-1 rounded bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 text-[11px] text-slate-300 hover:text-emerald-300 transition-colors disabled:opacity-50"
              >
                {sample}
              </button>
            ))}
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

                {/* User Query */}
                {msg.type === "query" && (
                  <div className="flex items-start gap-2 text-emerald-400">
                    <span className="text-slate-500 font-bold">opspilot@aiops:~$</span>
                    <span className="text-slate-100 font-medium">{msg.query}</span>
                  </div>
                )}

                {/* Error Output */}
                {msg.type === "error" && (
                  <div className="bg-rose-950/30 border border-rose-800/50 p-3 rounded-lg space-y-1 text-rose-300">
                    <div className="flex items-center gap-2 font-semibold">
                      <AlertTriangle className="w-4 h-4 text-rose-400" />
                      <span>Execution Error / Guardrail Blocked</span>
                    </div>
                    <div className="text-rose-200/90 text-[11px] pl-6">{msg.error}</div>
                  </div>
                )}

                {/* Query Result Output */}
                {msg.type === "response" && (
                  <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-3 space-y-3">
                    {/* SQL Banner & Meta */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-slate-800/70">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/70 border border-emerald-700/50 text-emerald-300 font-semibold uppercase">
                          SQL Executed
                        </span>
                        {msg.executionTimeMs !== undefined && (
                          <span className="flex items-center gap-1 text-[11px] text-slate-400">
                            <Clock className="w-3 h-3 text-cyan-400" />
                            {msg.executionTimeMs}ms
                          </span>
                        )}
                        {msg.rowCount !== undefined && (
                          <span className="text-[11px] text-slate-400">
                            • {msg.rowCount} {msg.rowCount === 1 ? "row" : "rows"}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => toggleViewMode(msg.id)}
                          className="flex items-center gap-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] transition-colors"
                        >
                          {viewModes[msg.id] === "json" ? (
                            <>
                              <TableIcon className="w-3 h-3 text-cyan-400" />
                              Table View
                            </>
                          ) : (
                            <>
                              <Code className="w-3 h-3 text-amber-400" />
                              JSON View
                            </>
                          )}
                        </button>
                        {msg.sql && (
                          <button
                            onClick={() => handleCopySql(msg.id, msg.sql!)}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] transition-colors"
                            title="Copy SQL query"
                          >
                            {copiedId === msg.id ? (
                              <Check className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <Copy className="w-3 h-3 text-slate-400" />
                            )}
                            {copiedId === msg.id ? "Copied" : "Copy SQL"}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* SQL Code Box */}
                    {msg.sql && (
                      <div className="p-2.5 rounded bg-slate-950 border border-slate-800/90 text-cyan-300 font-mono text-[11px] overflow-x-auto">
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

          {/* Interactive Input Form */}
          <div className="p-3 bg-slate-900 border-t border-slate-800">
            <div className="flex items-center gap-2 bg-slate-950 border border-slate-700/80 focus-within:border-emerald-500/80 rounded-lg px-3 py-2 transition-colors">
              <span className="text-emerald-400 font-bold shrink-0">opspilot&gt;</span>
              <input
                ref={inputRef}
                type="text"
                value={inputQuery}
                onChange={(e) => setInputQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask English query (e.g. 'Show me all critical database incidents') or direct SQL..."
                disabled={isLoading}
                className="flex-1 bg-transparent border-none text-slate-100 placeholder-slate-500 focus:outline-none text-xs font-mono"
              />
              <button
                onClick={() => executeQuery(inputQuery)}
                disabled={!inputQuery.trim() || isLoading}
                className="p-1.5 rounded-md bg-emerald-600/30 hover:bg-emerald-600/50 border border-emerald-500/40 text-emerald-300 disabled:opacity-40 transition-colors"
                title="Send query"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="flex items-center justify-between mt-2 px-1 text-[10px] text-slate-500">
              <span>Press Enter to query • Up/Down arrows for command history</span>
              <span className="text-emerald-400/80">SQLite WAL Active</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};
