#!/usr/bin/env python3
import http.server
import socketserver
import json
import base64
import random
import re
from urllib.parse import parse_qs, urlparse
import numpy as np
from PIL import Image
import io
import cv2
from datetime import datetime
import os
from fpdf import FPDF

class SignatureVerificationHandler(http.server.BaseHTTPRequestHandler):
    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path == '/':
                self.path = '/index.html'

            if parsed.path.startswith('/download_report'):
                query = parse_qs(parsed.query)
                report_id = query.get('report_id', ['1'])[0]
                report_data = {
                    'id': report_id,
                    'result': {
                        'match': query.get('match', ['true'])[0].lower() == 'true',
                        'confidence': float(query.get('confidence', ['0'])[0]),
                        'strokeSimilarity': float(query.get('strokeSimilarity', ['0'])[0]),
                        'pressureAnalysis': float(query.get('pressureAnalysis', ['0'])[0]),
                        'analysis': query.get('analysis', [''])[0].split('|')
                    },
                    'date': query.get('date', [datetime.now().isoformat()])[0]
                }
                pdf_content = self.generate_pdf_report(report_data)
                self.send_response(200)
                self.send_header('Content-Type', 'application/pdf')
                self.send_header('Content-Disposition', f'attachment; filename="signature_report_{report_id}.pdf"')
                self.end_headers()
                self.wfile.write(pdf_content)
                return

            safe_path = os.path.normpath(self.path.lstrip("/"))
            if '..' in safe_path or safe_path.startswith('/'):
                self.send_error(403, "Forbidden")
                return

            content_types = {
                'html': 'text/html',
                'css': 'text/css',
                'js': 'application/javascript',
                'png': 'image/png',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'gif': 'image/gif',
                'ico': 'image/x-icon',
                'pdf': 'application/pdf'
            }
            ext = safe_path.split('.')[-1].lower()
            content_type = content_types.get(ext, 'application/octet-stream')

            with open(safe_path, 'rb') as file:
                content = file.read()
                self.send_response(200)
                self.send_cors_headers()
                self.send_header('Content-Type', content_type)
                self.end_headers()
                self.wfile.write(content)

        except FileNotFoundError:
            self.send_error(404, "File not found")
        except Exception as e:
            self.send_error(500, f"Server error: {str(e)}")

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path == '/verify':
                self.handle_signature_verification()
            elif parsed.path == '/download_report':
                self.handle_pdf_generation(parsed)
            else:
                self.send_error(404, "Endpoint not found")
        except Exception as e:
            self.send_error(500, str(e))

    def handle_signature_verification(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_error(400, "No content provided")
                return

            content_type = self.headers.get('Content-Type', '')
            boundary = re.search(r'boundary=(.+)', content_type)
            if not boundary:
                self.send_error(400, "Invalid multipart/form-data")
                return

            boundary_bytes = boundary.group(1).encode()
            post_data = self.rfile.read(content_length)
            parts = post_data.split(b'--' + boundary_bytes)

            images = []
            for part in parts:
                if b'Content-Type: image/' in part:
                    image = part.split(b'\r\n\r\n')[1].rsplit(b'\r\n', 1)[0]
                    images.append(image)

            if len(images) != 2:
                self.send_error(400, "Exactly two images are required")
                return

            reference = self.process_image(images[0])
            verification = self.process_image(images[1])
            result = self.verify_signatures(reference, verification)

            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'result': result,
                'timestamp': datetime.now().isoformat()
            }).encode())

        except Exception as e:
            self.send_error(500, str(e))

    def handle_pdf_generation(self, parsed):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self.send_error(400, "No report data provided")
            return

        report_data = json.loads(self.rfile.read(content_length).decode())
        report_id = parse_qs(parsed.query).get('report_id', ['report'])[0]
        pdf = self.generate_pdf_report(report_data)

        self.send_response(200)
        self.send_header('Content-Type', 'application/pdf')
        self.send_header('Content-Disposition', f'attachment; filename="report_{report_id}.pdf"')
        self.send_header('Content-Length', str(len(pdf)))
        self.end_headers()
        self.wfile.write(pdf)

    def generate_pdf_report(self, report):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 24)
        pdf.cell(0, 20, "Signature Verification Report", ln=True, align="C")
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"Report ID: {report['id']}", ln=True)
        pdf.cell(0, 10, f"Generated on: {datetime.fromisoformat(report['date']).strftime('%Y-%m-%d %H:%M:%S')}", ln=True)
        pdf.ln(10)

        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Verification Results", ln=True)
        pdf.set_font("Arial", "", 12)
        status = "Verified" if report['result']['match'] else "Not Verified"
        pdf.set_text_color(0, 128, 0) if report['result']['match'] else pdf.set_text_color(255, 0, 0)
        pdf.cell(0, 10, f"Status: {status}", ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 10, f"Confidence Level: {report['result']['confidence']}%", ln=True)
        pdf.cell(0, 10, f"Stroke Similarity: {report['result']['strokeSimilarity']}%", ln=True)
        pdf.cell(0, 10, f"Pressure Analysis: {report['result']['pressureAnalysis']}%", ln=True)
        pdf.ln(10)

        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Detailed Analysis", ln=True)
        pdf.set_font("Arial", "", 12)
        for line in report['result']['analysis']:
            if line.startswith('\n'):
                pdf.ln(5)
            pdf.cell(0, 10, line.strip(), ln=True)
        return pdf.output(dest='S').encode('latin1')

    def process_image(self, data):
        image = Image.open(io.BytesIO(data)).convert('L')
        arr = np.array(image).astype(np.float32) / 255.0
        thresh = cv2.adaptiveThreshold((arr * 255).astype(np.uint8), 255,
                                       cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 11, 2)
        blur = cv2.medianBlur(thresh, 3).astype(np.float32) / 255.0
        return blur

    def verify_signatures(self, img1, img2):
        if img1.shape != img2.shape:
            img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

        structural = self.calculate_structural_similarity(img1, img2)
        stroke = self.analyze_strokes(img1, img2)
        pressure = self.analyze_pressure(img1, img2)
        contour = self.analyze_contours(img1, img2)

        weights = {'structural': 0.3, 'stroke': 0.3, 'pressure': 0.2, 'contour': 0.2}
        confidence = (structural * weights['structural'] + stroke * weights['stroke'] +
                      pressure * weights['pressure'] + contour * weights['contour']) * 100
        match = structural > 0.75 and stroke > 0.70 and pressure > 0.60 and contour > 0.65 and confidence > 70

        return {
            'match': match,
            'confidence': round(confidence, 2),
            'strokeSimilarity': round(stroke * 100, 2),
            'pressureAnalysis': round(pressure * 100, 2),
            'analysis': [
                f"Structural Similarity: {round(structural * 100, 2)}%",
                f"Stroke Analysis: {round(stroke * 100, 2)}%",
                f"Pressure Analysis: {round(pressure * 100, 2)}%",
                f"Contour Analysis: {round(contour * 100, 2)}%",
                f"Overall Confidence: {round(confidence, 2)}%",
                "\nMatch Criteria:",
                "- Structural Similarity > 75%",
                "- Stroke Similarity > 70%",
                "- Pressure Similarity > 60%",
                "- Contour Similarity > 65%",
                "- Confidence > 70%"
            ]
        }

    def calculate_structural_similarity(self, img1, img2):
        mse = np.mean((img1 - img2) ** 2)
        return 1 / (1 + mse)

    def analyze_strokes(self, img1, img2):
        edges1 = cv2.Canny((img1 * 255).astype(np.uint8), 50, 150)
        edges2 = cv2.Canny((img2 * 255).astype(np.uint8), 50, 150)
        contours1, _ = cv2.findContours(edges1, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours2, _ = cv2.findContours(edges2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        angle_similarity = self.compare_stroke_angles(contours1, contours2)
        count_similarity = min(len(contours1), len(contours2)) / max(len(contours1), len(contours2)) if max(len(contours1), len(contours2)) else 0
        return 0.6 * angle_similarity + 0.4 * count_similarity

    def compare_stroke_angles(self, c1, c2):
        def angles(contours):
            return [np.arctan2(cnt[-1][0][1] - cnt[0][0][1], cnt[-1][0][0] - cnt[0][0][0])
                    for cnt in contours if len(cnt) >= 2]

        a1 = angles(c1)
        a2 = angles(c2)
        if not a1 or not a2:
            return 0
        diff = np.abs(np.array(a1[:len(a2)]) - np.array(a2[:len(a1)]))
        diff = np.minimum(diff, 2 * np.pi - diff)
        return 1 - np.mean(diff) / np.pi

    def analyze_contours(self, img1, img2):
        def extract(img):
            edges = cv2.Canny((img * 255).astype(np.uint8), 50, 150)
            return cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]

        c1 = extract(img1)
        c2 = extract(img2)

        def feature_similarity(f_type):
            f1 = [cv2.contourArea(cnt) if f_type == 'area' else cv2.arcLength(cnt, True) for cnt in c1]
            f2 = [cv2.contourArea(cnt) if f_type == 'area' else cv2.arcLength(cnt, True) for cnt in c2]
            if not f1 or not f2:
                return 0
            min_len = min(len(f1), len(f2))
            f1 = f1[:min_len]
            f2 = f2[:min_len]
            return 1 - np.mean(np.abs(np.array(f1) - np.array(f2)) / np.maximum(np.array(f1), np.array(f2)))

        return 0.5 * feature_similarity('area') + 0.5 * feature_similarity('length')

    def analyze_pressure(self, img1, img2):
        def pressure(img): return np.mean(cv2.GaussianBlur(img, (5, 5), 0))
        diff = abs(pressure(img1) - pressure(img2)) / 255.0
        return 1 - diff

def run_server():
    ports = [8000, 8080, 3000, 5000, 9000]
    for port in ports:
        try:
            with socketserver.TCPServer(("", port), SignatureVerificationHandler) as httpd:
                print(f"\n✅ Server running at http://localhost:{port}")
                print("🔴 Press Ctrl+C to stop")
                httpd.serve_forever()
        except OSError:
            print(f"Port {port} in use, trying another...")
        except KeyboardInterrupt:
            print("\nServer stopped.")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            break

if __name__ == "__main__":
    run_server()
