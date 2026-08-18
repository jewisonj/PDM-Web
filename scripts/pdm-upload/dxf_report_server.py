#!/usr/bin/env python3
"""
DXF Processing Report Server

A simple web server that provides:
1. Real-time view of the DXF work queue
2. Search for items with STEP files
3. Ability to trigger DXF generation

Run with: python dxf_report_server.py
Opens on http://localhost:8080
"""

import os
import json
import http.server
import socketserver
import urllib.parse
from datetime import datetime
from pathlib import Path

# Load environment or use defaults
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')
BACKEND_URL = os.environ.get('BACKEND_URL', 'http://localhost:8001')
PORT = int(os.environ.get('REPORT_PORT', 8080))

# Try to load from config file if env vars not set
config_file = Path(__file__).parent / 'report_config.json'
if config_file.exists() and not SUPABASE_URL:
    try:
        with open(config_file) as f:
            config = json.load(f)
            SUPABASE_URL = config.get('supabase_url', SUPABASE_URL)
            SUPABASE_KEY = config.get('supabase_key', SUPABASE_KEY)
            BACKEND_URL = config.get('backend_url', BACKEND_URL)
    except:
        pass


def query_supabase(table, select='*', filters=None, order=None, limit=100):
    """Query Supabase REST API directly."""
    import urllib.request
    import ssl

    if not SUPABASE_URL or not SUPABASE_KEY:
        return {'error': 'Supabase not configured'}

    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}"
    if filters:
        url += f"&{filters}"
    if order:
        url += f"&order={order}"
    url += f"&limit={limit}"

    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {'error': str(e)}


def get_work_queue():
    """Get current work queue tasks."""
    return query_supabase(
        'work_queue',
        select='*,items(item_number,name)',
        order='created_at.desc',
        limit=50
    )


def get_items_with_step(search=''):
    """Get items that have STEP files."""
    filters = "file_type=eq.STEP"
    if search:
        # Search in item_number via join
        pass  # Will filter client-side for simplicity

    files = query_supabase(
        'files',
        select='id,file_name,file_path,created_at,items(id,item_number,name)',
        filters=filters,
        order='created_at.desc',
        limit=200
    )

    if isinstance(files, dict) and 'error' in files:
        return files

    # Filter by search term if provided
    if search and isinstance(files, list):
        search_lower = search.lower()
        files = [f for f in files if
                 search_lower in f.get('file_name', '').lower() or
                 (f.get('items') and search_lower in f['items'].get('item_number', '').lower()) or
                 (f.get('items') and search_lower in (f['items'].get('name') or '').lower())]

    return files


def trigger_dxf_generation(item_number):
    """Trigger DXF generation via backend API."""
    import urllib.request

    url = f"{BACKEND_URL}/api/tasks/generate-dxf/{item_number}"

    try:
        req = urllib.request.Request(url, method='POST')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {'error': f'HTTP {e.code}: {e.reason}'}
    except Exception as e:
        return {'error': str(e)}


def generate_html(queue_data, search_results=None, search_term='', message=''):
    """Generate the HTML report page."""

    # Process queue data
    queue_rows = []
    if isinstance(queue_data, list):
        for task in queue_data:
            item = task.get('items') or {}
            item_number = item.get('item_number', 'N/A')
            item_name = item.get('name', '')
            status = task.get('status', 'unknown')
            task_type = task.get('task_type', 'unknown')
            created = task.get('created_at', '')[:19].replace('T', ' ')
            error = task.get('error_message', '') or ''

            status_class = {
                'pending': 'status-pending',
                'processing': 'status-processing',
                'completed': 'status-completed',
                'failed': 'status-failed'
            }.get(status, '')

            queue_rows.append(f'''
            <tr class="{status_class}">
                <td>{item_number}</td>
                <td>{item_name[:30]}</td>
                <td>{task_type}</td>
                <td class="status">{status.upper()}</td>
                <td>{created}</td>
                <td class="error">{error[:50]}</td>
            </tr>''')

    # Process search results
    search_rows = []
    if search_results and isinstance(search_results, list):
        for f in search_results[:50]:  # Limit display
            item = f.get('items') or {}
            item_number = item.get('item_number', 'N/A')
            item_name = item.get('name', '')
            file_name = f.get('file_name', '')
            created = f.get('created_at', '')[:19].replace('T', ' ')

            search_rows.append(f'''
            <tr>
                <td>{item_number}</td>
                <td>{item_name[:30]}</td>
                <td>{file_name}</td>
                <td>{created}</td>
                <td>
                    <button onclick="triggerDxf('{item_number}')" class="btn-generate">
                        Generate DXF
                    </button>
                </td>
            </tr>''')

    # Count stats
    if isinstance(queue_data, list):
        pending = sum(1 for t in queue_data if t.get('status') == 'pending')
        processing = sum(1 for t in queue_data if t.get('status') == 'processing')
        completed = sum(1 for t in queue_data if t.get('status') == 'completed')
        failed = sum(1 for t in queue_data if t.get('status') == 'failed')
    else:
        pending = processing = completed = failed = 0

    message_html = f'<div class="message">{message}</div>' if message else ''

    return f'''<!DOCTYPE html>
<html>
<head>
    <title>DXF Processing Dashboard</title>
    <meta http-equiv="refresh" content="15">
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            padding: 20px;
            margin: 0;
        }}
        h1 {{ color: #4ade80; margin-bottom: 5px; }}
        h2 {{ color: #38bdf8; margin-top: 30px; }}
        .subtitle {{ color: #64748b; margin-bottom: 20px; }}

        .summary {{ display: flex; gap: 15px; margin-bottom: 25px; flex-wrap: wrap; }}
        .stat {{
            background: #1e293b;
            padding: 15px 25px;
            border-radius: 8px;
            min-width: 120px;
        }}
        .stat-value {{ font-size: 28px; font-weight: bold; }}
        .stat-label {{ color: #64748b; font-size: 12px; text-transform: uppercase; }}

        table {{
            width: 100%;
            border-collapse: collapse;
            background: #1e293b;
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 20px;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #334155;
        }}
        th {{
            background: #0f172a;
            color: #4ade80;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
        }}

        .status {{ font-weight: bold; }}
        .status-pending .status {{ color: #fbbf24; }}
        .status-processing .status {{ color: #38bdf8; }}
        .status-completed .status {{ color: #4ade80; }}
        .status-failed .status {{ color: #f87171; }}
        .status-failed {{ background: rgba(248, 113, 113, 0.1); }}

        .error {{ color: #f87171; font-size: 11px; }}

        .search-box {{
            background: #1e293b;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .search-box input {{
            padding: 10px 15px;
            border: 1px solid #334155;
            border-radius: 6px;
            background: #0f172a;
            color: #e2e8f0;
            font-size: 14px;
            width: 300px;
        }}
        .search-box button {{
            padding: 10px 20px;
            background: #3b82f6;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            margin-left: 10px;
        }}
        .search-box button:hover {{ background: #2563eb; }}

        .btn-generate {{
            padding: 6px 12px;
            background: #22c55e;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }}
        .btn-generate:hover {{ background: #16a34a; }}
        .btn-generate:disabled {{ background: #4b5563; cursor: not-allowed; }}

        .message {{
            padding: 15px;
            background: #1e3a5f;
            border-left: 4px solid #3b82f6;
            border-radius: 4px;
            margin-bottom: 20px;
        }}

        .no-data {{
            color: #64748b;
            text-align: center;
            padding: 40px;
            background: #1e293b;
            border-radius: 8px;
        }}

        .config-warning {{
            background: #422006;
            border-left: 4px solid #f59e0b;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <h1>DXF Processing Dashboard</h1>
    <p class="subtitle">Auto-refreshes every 15 seconds | Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

    {message_html}

    {f'<div class="config-warning">Supabase not configured. Create report_config.json with supabase_url and supabase_key.</div>' if not SUPABASE_URL else ''}

    <div class="summary">
        <div class="stat">
            <div class="stat-value" style="color: #fbbf24;">{pending}</div>
            <div class="stat-label">Pending</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color: #38bdf8;">{processing}</div>
            <div class="stat-label">Processing</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color: #4ade80;">{completed}</div>
            <div class="stat-label">Completed</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color: #f87171;">{failed}</div>
            <div class="stat-label">Failed</div>
        </div>
    </div>

    <h2>Work Queue</h2>
    <table>
        <tr>
            <th>Item #</th>
            <th>Name</th>
            <th>Task Type</th>
            <th>Status</th>
            <th>Created</th>
            <th>Error</th>
        </tr>
        {''.join(queue_rows) if queue_rows else '<tr><td colspan="6" class="no-data">No tasks in queue</td></tr>'}
    </table>

    <h2>Search STEP Files</h2>
    <div class="search-box">
        <form method="GET" action="/">
            <input type="text" name="search" placeholder="Search by item number or name..." value="{search_term}">
            <button type="submit">Search</button>
        </form>
    </div>

    {f'''<table>
        <tr>
            <th>Item #</th>
            <th>Name</th>
            <th>STEP File</th>
            <th>Uploaded</th>
            <th>Action</th>
        </tr>
        {''.join(search_rows)}
    </table>''' if search_rows else (f'<div class="no-data">{"Enter a search term to find STEP files" if not search_term else "No STEP files found matching: " + search_term}</div>' if search_term or not search_results else '')}

    <script>
    function triggerDxf(itemNumber) {{
        if (!confirm('Generate DXF for ' + itemNumber + '?')) return;

        const btn = event.target;
        btn.disabled = true;
        btn.textContent = 'Queuing...';

        fetch('/trigger?item=' + encodeURIComponent(itemNumber), {{method: 'POST'}})
            .then(r => r.json())
            .then(data => {{
                if (data.error) {{
                    alert('Error: ' + data.error);
                    btn.disabled = false;
                    btn.textContent = 'Generate DXF';
                }} else {{
                    btn.textContent = 'Queued!';
                    setTimeout(() => location.reload(), 1000);
                }}
            }})
            .catch(e => {{
                alert('Error: ' + e);
                btn.disabled = false;
                btn.textContent = 'Generate DXF';
            }});
    }}
    </script>
</body>
</html>'''


class ReportHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the report server."""

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def do_GET(self):
        """Handle GET requests."""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        search_term = params.get('search', [''])[0]

        # Get data
        queue_data = get_work_queue()
        search_results = get_items_with_step(search_term) if search_term else None

        # Generate HTML
        html = generate_html(queue_data, search_results, search_term)

        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def do_POST(self):
        """Handle POST requests (trigger DXF generation)."""
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/trigger':
            params = urllib.parse.parse_qs(parsed.query)
            item_number = params.get('item', [''])[0]

            if item_number:
                result = trigger_dxf_generation(item_number)
            else:
                result = {'error': 'No item number provided'}

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()


def main():
    """Run the report server."""
    print(f"=" * 60)
    print("DXF Processing Dashboard")
    print(f"=" * 60)
    print(f"Server starting on http://localhost:{PORT}")
    print(f"Supabase: {'Configured' if SUPABASE_URL else 'NOT CONFIGURED'}")
    print(f"Backend: {BACKEND_URL}")
    print(f"Press Ctrl+C to stop")
    print(f"=" * 60)

    with socketserver.TCPServer(("", PORT), ReportHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")


if __name__ == '__main__':
    main()
