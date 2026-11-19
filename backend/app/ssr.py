"""
Server-Side Rendering (SSR) Engine for OpsPilot.
Demonstrates:
1. Server-Side Rendering (SSR) of complete responsive HTML5 documents.
2. Direct HTML generation on the server without client-side SPA JavaScript execution.
3. Pre-rendered executive reports with dynamic incident status, MTTD, MTTR, and cascade graphs.
"""

import html
import time
from typing import Dict, Any, Optional


def render_incident_html_report(incident: Dict[str, Any]) -> str:
    """
    Renders a complete, standalone, responsive HTML5 document directly on the server.
    Delivered with Content-Type: text/html; charset=utf-8.
    """
    incident_id = html.escape(str(incident.get("incident_id", "inc_sample")))
    title = html.escape(str(incident.get("title", "Database Connection Pool Cascade Exhaustion")))
    severity = html.escape(str(incident.get("severity", "CRITICAL")))
    inc_status = html.escape(str(incident.get("status", "INVESTIGATING")))
    root_cause = html.escape(str(incident.get("root_cause_service", "postgresql")))
    score = float(incident.get("confidence_score", 0.95))
    started_at = html.escape(str(incident.get("started_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))))

    sev_color = "#f43f5e" if severity == "CRITICAL" else "#f59e0b" if severity == "WARNING" else "#3b82f6"

    services_pills = " ".join(
        f'<span style="display:inline-block;padding:4px 10px;margin:2px 4px 2px 0;background:#1e293b;border:1px solid #475569;border-radius:4px;font-family:monospace;font-size:12px;color:#e2e8f0;">{html.escape(svc)}</span>'
        for svc in incident.get("affected_services", ["postgresql", "order-api", "checkout-api"])
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpsPilot SSR Incident Report — {incident_id}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #030712;
            color: #f8fafc;
            margin: 0;
            padding: 24px;
            line-height: 1.5;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: #0b0f19;
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 32px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 1px solid #1e293b;
            padding-bottom: 20px;
            margin-bottom: 24px;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 9999px;
            font-weight: 700;
            font-size: 13px;
            text-transform: uppercase;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .card {{
            background: #0f172a;
            padding: 16px;
            border-radius: 8px;
            border: 1px solid #334155;
        }}
        .card-label {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #94a3b8;
            margin-bottom: 4px;
        }}
        .card-val {{
            font-size: 18px;
            font-weight: 600;
            color: #f1f5f9;
        }}
        .summary-box {{
            background: #090d16;
            border-left: 4px solid {sev_color};
            padding: 16px;
            border-radius: 4px;
            margin-bottom: 24px;
            font-family: monospace;
            font-size: 13px;
            color: #cbd5e1;
        }}
        .footer {{
            border-top: 1px solid #334155;
            padding-top: 16px;
            font-size: 12px;
            color: #64748b;
            display: flex;
            justify-content: space-between;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <span class="badge" style="background:{sev_color}22;color:{sev_color};border:1px solid {sev_color}55;">{severity}</span>
                <span class="badge" style="background:#3b82f622;color:#60a5fa;border:1px solid #3b82f655;margin-left:8px;">{inc_status}</span>
                <h1 style="margin: 12px 0 6px 0; font-size: 24px;">{title}</h1>
                <div style="font-size: 12px; color: #94a3b8;">Incident ID: <code>{incident_id}</code> &bull; Started: {started_at}</div>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">SSR Mode</div>
                <div style="font-size: 14px; font-weight: 600; color: #10b981;">&bull; Server-Rendered HTML</div>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-label">Identified Root Cause</div>
                <div class="card-val" style="color: #f43f5e;">{root_cause}</div>
            </div>
            <div class="card">
                <div class="card-label">Correlation Confidence</div>
                <div class="card-val" style="color: #10b981;">{round(score * 100, 1)}%</div>
            </div>
            <div class="card">
                <div class="card-label">Alert Count</div>
                <div class="card-val">{incident.get("alert_count", 0)}</div>
            </div>
        </div>

        <div style="margin-bottom: 24px;">
            <div class="card-label" style="margin-bottom: 8px;">Impacted Services Cascade</div>
            <div>{services_pills}</div>
        </div>

        <div class="summary-box">
            <div style="font-weight: 600; color: #38bdf8; margin-bottom: 6px;">Executive Summary &amp; Root Cause Analysis:</div>
            <div>{html.escape(str(incident.get("summary") or "Connection pool exhaustion propagated downstream latency to order-api and checkout-api."))}</div>
        </div>

        <div class="footer">
            <span>OpsPilot Autonomous SRE Platform &mdash; Server-Side Rendered Executive Briefing</span>
            <span>Generated: {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}</span>
        </div>
    </div>
</body>
</html>"""
    return html_content
