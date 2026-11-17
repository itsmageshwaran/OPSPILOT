/**
 * ==============================================================================
 * JavaScript Core Concepts Demonstration & Utility Suite
 * ==============================================================================
 * This module provides demonstrable implementations of:
 * 1. JavaScript Event Loop (Microtask vs Macrotask vs Call Stack)
 * 2. Promises vs Callbacks (Error-first callbacks, Promises, Promisify, Async/Await)
 * 3. Hoisting (Variable hoisting with var vs let/const TDZ, Function declarations vs expressions)
 * 4. Client-side Form Validation with Regex and Sanitization
 * ==============================================================================
 */

// ------------------------------------------------------------------------------
// 1. JavaScript Event Loop Demonstration
// ------------------------------------------------------------------------------
export interface EventLoopLogEntry {
  step: number;
  phase: "Call Stack (Sync)" | "Microtask Queue" | "Macrotask Queue (Timer)";
  message: string;
  timestamp: number;
}

/**
 * Runs an asynchronous probe demonstrating the JavaScript Event Loop execution order:
 * 1. Synchronous Call Stack runs to completion.
 * 2. Microtask Queue (queueMicrotask, Promise.then) empties completely before next tick.
 * 3. Macrotask Queue (setTimeout, setInterval, I/O) executes on subsequent loop iterations.
 */
export async function runEventLoopDemonstration(): Promise<EventLoopLogEntry[]> {
  const logs: EventLoopLogEntry[] = [];
  let step = 1;

  // 1. Synchronous Call Stack
  logs.push({
    step: step++,
    phase: "Call Stack (Sync)",
    message: "1. Synchronous execution on main Call Stack begins",
    timestamp: performance.now(),
  });

  // Schedule Macrotask via setTimeout (0ms)
  setTimeout(() => {
    logs.push({
      step: step++,
      phase: "Macrotask Queue (Timer)",
      message: "5. Macrotask callback (setTimeout 0ms) executes from task queue",
      timestamp: performance.now(),
    });
  }, 0);

  // Schedule Microtask via Promise.resolve().then()
  Promise.resolve().then(() => {
    logs.push({
      step: step++,
      phase: "Microtask Queue",
      message: "3. Microtask callback (Promise.resolve().then) executes immediately after Call Stack",
      timestamp: performance.now(),
    });
  });

  // Schedule Microtask via queueMicrotask API
  if (typeof queueMicrotask === "function") {
    queueMicrotask(() => {
      logs.push({
        step: step++,
        phase: "Microtask Queue",
        message: "4. Microtask callback (queueMicrotask) executes before macrotask queue",
        timestamp: performance.now(),
      });
    });
  }

  // Synchronous Call Stack completion
  logs.push({
    step: step++,
    phase: "Call Stack (Sync)",
    message: "2. Synchronous Call Stack execution finishes",
    timestamp: performance.now(),
  });

  // Await one tick so macrotasks resolve
  await new Promise((resolve) => setTimeout(resolve, 20));

  return logs;
}

// ------------------------------------------------------------------------------
// 2. Promises vs Callbacks Demonstration & Utilities
// ------------------------------------------------------------------------------
export type NodeCallback<T> = (err: Error | null, result?: T) => void;

/**
 * Higher-order utility: Promisify
 * Converts a legacy error-first callback function `(arg, callback) => void`
 * into a modern Promise-returning function.
 */
export function promisify<T, A>(
  fn: (arg: A, callback: NodeCallback<T>) => void
): (arg: A) => Promise<T> {
  return (arg: A) => {
    return new Promise<T>((resolve, reject) => {
      fn(arg, (err, result) => {
        if (err) {
          reject(err);
        } else {
          resolve(result as T);
        }
      });
    });
  };
}

/**
 * Demonstrates comparison between Callback style and Promise/Async-Await style.
 */
export async function comparePromiseVsCallback(queryText: string): Promise<{
  callbackResult: string;
  promiseResult: string;
  comparisonNotes: string[];
}> {
  // Legacy Callback Simulation
  const simulateCallbackQuery = (query: string, cb: NodeCallback<string>) => {
    setTimeout(() => {
      if (!query || query.trim().length === 0) {
        cb(new Error("Query text is required"));
      } else {
        cb(null, `[Callback Style] Executed query: "${query}"`);
      }
    }, 10);
  };

  // Convert to Promise using our promisify utility
  const promisifiedQuery = promisify(simulateCallbackQuery);

  // 1. Run using Callback
  const callbackPromise = new Promise<string>((resolve) => {
    simulateCallbackQuery(queryText, (err, res) => {
      if (err) resolve(`Error: ${err.message}`);
      else resolve(res || "");
    });
  });

  // 2. Run using Promise / async-await
  const promiseResult = await promisifiedQuery(queryText);
  const callbackResult = await callbackPromise;

  return {
    callbackResult,
    promiseResult,
    comparisonNotes: [
      "Callbacks lead to inversion of control and deeply nested 'Callback Hell' / pyramid of doom.",
      "Promises provide composability (.then, .catch, Promise.all) and explicit state (pending, fulfilled, rejected).",
      "Async/Await provides synchronous-looking control flow with standard try/catch error handling over Promises.",
    ],
  };
}

// ------------------------------------------------------------------------------
// 3. JavaScript Hoisting Demonstration
// ------------------------------------------------------------------------------
export interface HoistingAnalysis {
  concept: string;
  explanation: string;
  varBehavior: string;
  letConstBehavior: string;
  functionDeclarationVsExpression: string;
}

export function analyzeHoisting(): HoistingAnalysis {
  // Demonstration of Hoisting Mechanism:
  // In JavaScript's Creation Phase, declarations are hoisted into memory before execution.
  // - 'var' is hoisted and initialized with undefined.
  // - 'let' and 'const' are hoisted but remain in the 'Temporal Dead Zone' (TDZ) until evaluation.
  // - Function declarations are hoisted with their complete implementation.
  // - Function expressions assigned to variables follow variable hoisting rules.

  let varExample = "Before declaration, var exists as undefined";
  let letExample = "Before declaration, let throws ReferenceError (TDZ)";
  let fnDeclarationExample = "Function declarations can be invoked before their definition in code";
  let fnExpressionExample = "Function expressions cannot be invoked before assignment";

  return {
    concept: "JavaScript Hoisting (Execution Context Creation Phase)",
    explanation:
      "Hoisting is JavaScript's default behavior of moving declarations to the top of their containing scope during compilation.",
    varBehavior:
      "var declarations are hoisted and initialized to undefined: accessing them before assignment yields undefined without throwing an error.",
    letConstBehavior:
      "let and const declarations are hoisted into block scope but placed in the Temporal Dead Zone (TDZ). Accessing them before initialization throws ReferenceError.",
    functionDeclarationVsExpression:
      "Function declarations (function foo() {}) are hoisted with their full body. Function expressions (const bar = () => {}) are treated as variable assignments and cannot be called prior to declaration.",
  };
}

// ------------------------------------------------------------------------------
// 4. Form Validation Suite (Client-Side Input Validation)
// ------------------------------------------------------------------------------
export interface FormValidationResult {
  isValid: boolean;
  sanitizedValue: string;
  errors: string[];
}

export function validateChatOpsQuery(input: string): FormValidationResult {
  const errors: string[] = [];
  const trimmed = (input || "").trim();

  // 1. Required / Non-empty check
  if (!trimmed) {
    errors.push("Query input cannot be empty.");
  }

  // 2. Minimum & Maximum Length
  if (trimmed.length > 0 && trimmed.length < 3) {
    errors.push("Query must be at least 3 characters long.");
  }
  if (trimmed.length > 500) {
    errors.push("Query exceeds maximum allowed length of 500 characters.");
  }

  // 3. Destructive Command Mitigation (Input Sanitization)
  const forbiddenPatterns = [
    { pattern: /\b(DROP\s+TABLE|DROP\s+DATABASE)\b/i, label: "DROP statements are prohibited" },
    { pattern: /\b(DELETE\s+FROM)\b/i, label: "DELETE statements are prohibited" },
    { pattern: /\b(TRUNCATE)\b/i, label: "TRUNCATE statements are prohibited" },
    { pattern: /<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, label: "Script tags / XSS patterns are prohibited" },
  ];

  for (const { pattern, label } of forbiddenPatterns) {
    if (pattern.test(trimmed)) {
      errors.push(`Security validation error: ${label}.`);
    }
  }

  // 4. Sanitization: strip dangerous HTML characters
  const sanitized = trimmed
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  return {
    isValid: errors.length === 0,
    sanitizedValue: sanitized,
    errors,
  };
}
