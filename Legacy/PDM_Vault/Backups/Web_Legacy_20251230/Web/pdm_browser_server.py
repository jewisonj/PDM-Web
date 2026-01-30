#!/usr/bin/env python3
"""
PDM Browser Server
Simple HTTP server that serves the PDM browser interface and provides API access to SQLite database
"""

import sqlite3
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
import mimetypes

# Configuration
DB_PATH = r"D:\PDM_Vault\pdm.sqlite"
PORT = 8080

class PDMBrowserHandler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # API endpoint - get all items and files
        if path == '/api/items':
            self.serve_api_items()
        
        # File viewing endpoint
        elif path.startswith('/file/'):
            file_path = unquote(path[6:])  # Remove '/file/' prefix
            self.serve_file(file_path)
        
        # Serve the main HTML page
        elif path == '/' or path == '/index.html':
            self.serve_html()
        
        else:
            self.send_error(404, "File not found")
    
    def serve_html(self):
        """Serve the main HTML interface"""
        html_path = os.path.join(os.path.dirname(__file__), 'pdm_browser.html')
        
        if not os.path.exists(html_path):
            self.send_error(500, "HTML file not found")
            return
        
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))
    
    def serve_api_items(self):
        """Query database and return items + files as JSON"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Get all items
            cursor.execute("""
                SELECT item_number, name, revision, iteration, lifecycle_state, 
                       description, created_at, modified_at
                FROM items
                ORDER BY item_number
            """)
            
            items = []
            for row in cursor.fetchall():
                items.append({
                    'item_number': row[0],
                    'name': row[1],
                    'revision': row[2],
                    'iteration': row[3],
                    'lifecycle_state': row[4],
                    'description': row[5],
                    'created_at': row[6],
                    'modified_at': row[7]
                })
            
            # Get all files grouped by item
            cursor.execute("""
                SELECT item_number, file_path, file_type, revision, iteration, added_at
                FROM files
                ORDER BY item_number, file_type, added_at DESC
            """)
            
            files = {}
            for row in cursor.fetchall():
                item_num = row[0]
                if item_num not in files:
                    files[item_num] = []
                
                files[item_num].append({
                    'file_path': row[1],
                    'file_type': row[2],
                    'revision': row[3],
                    'iteration': row[4],
                    'added_at': row[5]
                })
            
            conn.close()
            
            # Send JSON response
            response = {
                'items': items,
                'files': files
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        
        except Exception as e:
            print(f"Error querying database: {e}")
            self.send_error(500, f"Database error: {str(e)}")
    
    def serve_file(self, file_path):
        """Serve a file from the vault for viewing"""
        # Security check - make sure file is within PDM_Vault
        vault_root = r"D:\PDM_Vault"
        abs_path = os.path.abspath(file_path)
        
        if not abs_path.startswith(os.path.abspath(vault_root)):
            self.send_error(403, "Access denied - file outside vault")
            return
        
        if not os.path.exists(file_path):
            self.send_error(404, "File not found")
            return
        
        try:
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = 'application/octet-stream'
            
            # Read and serve file
            with open(file_path, 'rb') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', mime_type)
            self.send_header('Content-Length', len(content))
            
            # For PDFs and images, allow inline viewing
            if mime_type in ['application/pdf', 'image/svg+xml', 'image/png', 'image/jpeg']:
                self.send_header('Content-Disposition', 'inline')
            
            self.end_headers()
            self.wfile.write(content)
        
        except Exception as e:
            print(f"Error serving file: {e}")
            self.send_error(500, f"Error reading file: {str(e)}")
    
    def log_message(self, format, *args):
        """Custom logging"""
        print(f"{self.address_string()} - {format % args}")


def main():
    # Check if database exists
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Please update DB_PATH in the script")
        return
    
    print(f"PDM Browser Server")
    print(f"Database: {DB_PATH}")
    print(f"Starting server on http://localhost:{PORT}")
    print(f"Press Ctrl+C to stop")
    print()
    
    server = HTTPServer(('', PORT), PDMBrowserHandler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()


if __name__ == '__main__':
    main()