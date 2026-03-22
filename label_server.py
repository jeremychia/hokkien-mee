#!/usr/bin/env python3
"""
Simple HTTP server for the image labeler with direct CSV editing.
Serves the labeling interface and provides API endpoints to load/save CSV.
"""

import json
import csv
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import sys

CSV_PATH = "output/image_labels.csv"
DOCS_DIR = "."  # Serve from project root to allow ../output/images/ paths

class LabelingHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        """Override to add timestamps"""
        print(f"[{self.log_date_time_string()}] {format % args}")
    
    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            
            if parsed_path.path == "/api/load-csv":
                self.load_csv()
            else:
                # Serve static files from docs directory
                self.path = self.path.replace("/docs/", "/")
                if self.path == "/":
                    self.path = "/label_images.html"
                super().do_GET()
        except Exception as e:
            print(f"❌ Error in do_GET: {e}")
            self.send_error(500, str(e))
    
    def do_POST(self):
        try:
            parsed_path = urlparse(self.path)
            
            if parsed_path.path == "/api/save-csv":
                self.save_csv()
            else:
                self.send_error(404)
        except Exception as e:
            print(f"❌ Error in do_POST: {e}")
            self.send_error(500, str(e))
    
    def load_csv(self):
        """Load CSV data and return as JSON"""
        try:
            if not os.path.exists(CSV_PATH):
                print(f"❌ CSV file not found at {CSV_PATH}")
                response = json.dumps({"success": False, "error": "CSV file not found"}).encode('utf-8')
                self.send_response(404)
            else:
                data = []
                with open(CSV_PATH, 'r', encoding='utf-8', newline='') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        data.append(row)
                
                response = json.dumps({"success": True, "data": data}).encode('utf-8')
                print(f"✅ Loaded {len(data)} images from CSV")
                self.send_response(200)
            
            self.send_header('Content-type', 'application/json')
            self.send_header('Content-Length', len(response))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response)
        except Exception as e:
            print(f"❌ Error loading CSV: {e}")
            response = json.dumps({"success": False, "error": str(e)}).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(response)
    
    def save_csv(self):
        """Save CSV data from JSON"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode('utf-8'))
            
            rows = payload.get("data", [])
            headers = payload.get("headers", [])
            
            if not rows:
                print(f"❌ Invalid CSV data format: no rows")
                response = json.dumps({"success": False, "error": "Invalid data format"}).encode('utf-8')
                self.send_response(400)
            else:
                # Use only these three fields
                fieldnames = ['local_path', 'image_type', 'is_manual']
                
                # Write to CSV with only these fields
                with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, restval='')
                    writer.writeheader()
                    for row in rows:
                        # Keep only these fields
                        filtered_row = {k: row.get(k, '') for k in fieldnames}
                        writer.writerow(filtered_row)
                
                print(f"✅ Saved {len(rows)} images to CSV")
                response = json.dumps({"success": True, "message": "CSV saved"}).encode('utf-8')
                self.send_response(200)
            
            self.send_header('Content-type', 'application/json')
            self.send_header('Content-Length', len(response))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response)
        except Exception as e:
            print(f"❌ Error saving CSV: {e}")
            response = json.dumps({"success": False, "error": str(e)}).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(response)
    
    def translate_path(self, path):
        """Override to serve from project root and handle docs/ access"""
        if path.startswith("/api/"):
            return path
        # Redirect root to label_images.html
        if path == "/" or path == "/label_images.html":
            path = "/docs/label_images.html"
        # Remove leading slash and join with root
        return os.path.join(DOCS_DIR, path.lstrip("/"))
    
    def end_headers(self):
        """Add CORS headers"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        try:
            self.send_response(200)
            self.end_headers()
        except Exception as e:
            print(f"❌ Error in do_OPTIONS: {e}")

if __name__ == '__main__':
    PORT = 8000
    handler = LabelingHandler
    server = HTTPServer(('127.0.0.1', PORT), handler)
    
    print(f"🚀 Label server running at http://localhost:{PORT}/label_images.html")
    print(f"📁 CSV path: {CSV_PATH}")
    print(f"📂 Docs directory: {DOCS_DIR}")
    print("Press Ctrl+C to stop\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n✅ Server stopped")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        sys.exit(1)
