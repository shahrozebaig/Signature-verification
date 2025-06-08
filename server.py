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

    def generate_pdf_report(self, report_data):
        pdf = FPDF()
        pdf.add_page()
        
        # Set up fonts
        pdf.set_font("Arial", "B", 24)
        pdf.cell(0, 20, "Signature Verification Report", ln=True, align="C")
        
        # Report details
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"Report ID: {report_data['id']}", ln=True)
        pdf.cell(0, 10, f"Generated on: {datetime.fromisoformat(report_data['date']).strftime('%Y-%m-%d %H:%M:%S')}", ln=True)
        pdf.ln(10)
        
        # Results
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Verification Results", ln=True)
        pdf.set_font("Arial", "", 12)
        
        # Status with color
        status = "Verified" if report_data['result']['match'] else "Not Verified"
        pdf.set_text_color(0, 128, 0) if report_data['result']['match'] else pdf.set_text_color(255, 0, 0)
        pdf.cell(0, 10, f"Status: {status}", ln=True)
        pdf.set_text_color(0, 0, 0)  # Reset color
        
        # Metrics
        pdf.cell(0, 10, f"Confidence Level: {report_data['result']['confidence']}%", ln=True)
        pdf.cell(0, 10, f"Stroke Similarity: {report_data['result']['strokeSimilarity']}%", ln=True)
        pdf.cell(0, 10, f"Pressure Analysis: {report_data['result']['pressureAnalysis']}%", ln=True)
        pdf.ln(10)
        
        # Analysis
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Detailed Analysis", ln=True)
        pdf.set_font("Arial", "", 12)
        for item in report_data['result']['analysis']:
            if item.startswith('\n'):
                pdf.ln(5)
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, item.strip(), ln=True)
                pdf.set_font("Arial", "", 12)
            else:
                pdf.cell(0, 10, item, ln=True)
        
        return pdf.output(dest='S').encode('latin1')

    def do_GET(self):
        try:
            if self.path == '/':
                self.path = '/index.html'
            
            # Handle PDF report download
            if self.path.startswith('/download_report'):
                query = parse_qs(urlparse(self.path).query)
                report_id = query.get('report_id', ['1'])[0]
                
                # Get the report data from the request
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    post_data = self.rfile.read(content_length)
                    report_data = json.loads(post_data.decode('utf-8'))
                else:
                    # If no data sent, use query parameters to get report details
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

                # Generate PDF with the actual report data
                pdf_content = self.generate_pdf_report(report_data)
                
                # Send the PDF
                self.send_response(200)
                self.send_header('Content-Type', 'application/pdf')
                self.send_header('Content-Disposition', f'attachment; filename="signature_report_{report_id}.pdf"')
                self.end_headers()
                self.wfile.write(pdf_content)
                return
            
            # Prevent directory traversal
            safe_path = os.path.normpath(self.path).lstrip(os.sep)
            if '..' in safe_path or safe_path.startswith('/'):
                self.send_error(403, "Forbidden")
                return
            # Detect file extension and content type
            file_extension = self.path.split('.')[-1].lower()
            content_types = {
                'html': 'text/html',
                'css': 'text/css',
                'js': 'application/javascript',
                'png': 'image/png',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'gif': 'image/gif',
                'ico': 'image/x-icon'
            }
            content_type = content_types.get(file_extension, 'text/html')  # Default to HTML
            # Load and return file
            file_path = '.' + self.path
            print(f"Serving file: {file_path}")
            with open(file_path, 'rb') as file:
                content = file.read()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', content_type)
            self.end_headers()
            self.wfile.write(content)

        except FileNotFoundError:
            self.send_error(404, "File not found")
        except Exception as e:
            self.send_error(500, str(e))

    def do_POST(self):
        """Handle POST requests"""
        try:
            print(f"\nReceived POST request to: {self.path}")
            
            if self.path == '/download_report':
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    post_data = self.rfile.read(content_length)
                    report_data = json.loads(post_data.decode('utf-8'))
                else:
                    report_data = None

                query_components = parse_qs(urlparse(self.path).query)
                report_id = query_components.get('report_id', [None])[0]

                if not report_id:
                    self.send_error(400, "Report ID is required")
                    return

                try:
                    pdf_data = self.generate_pdf_report(report_data)
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/pdf')
                    self.send_header('Content-Disposition', f'attachment; filename=signature_report_{report_id}.pdf')
                    self.send_header('Content-Length', str(len(pdf_data)))
                    self.end_headers()
                    self.wfile.write(pdf_data)
                    return
                except Exception as e:
                    print(f"Error generating PDF: {str(e)}")
                    self.send_error(500, f"Error generating PDF: {str(e)}")
                    return
            elif self.path == '/verify':
                try:
                    content_length = int(self.headers['Content-Length'])
                    if content_length == 0:
                        self.send_error(400, "No content provided")
                        return
                    content_type = self.headers.get('Content-Type', '')
                    if not content_type.startswith('multipart/form-data'):
                        self.send_error(400, "Invalid content type")
                        return
                    post_data = self.rfile.read(content_length)
                    boundary_match = re.search(r'boundary=(.+)', content_type)
                    if not boundary_match:
                        self.send_error(400, "No boundary found in content type")
                        return
                    boundary = boundary_match.group(1).encode()
                    parts = post_data.split(b'--' + boundary)
                    files = []
                    for part in parts:
                        if b'Content-Type: image/' in part:
                            image_data = part.split(b'\r\n\r\n')[1].split(b'\r\n')[0]
                            files.append(image_data)
                    if len(files) != 2:
                        self.send_error(400, "Exactly two signature images are required")
                        return
                    reference_img = self.process_image(files[0])
                    verification_img = self.process_image(files[1])
                    result = self.verify_signatures(reference_img, verification_img)
                    self.send_response(200)
                    self.send_cors_headers()
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    response = {
                        'success': True,
                        'result': result,
                        'timestamp': datetime.now().isoformat()
                    }
                    self.wfile.write(json.dumps(response).encode())
                except Exception as e:
                    self.send_error(500, str(e))
            else:
                self.send_error(404, "Not found")
        except Exception as e:
            self.send_error(500, str(e))

    def process_image(self, image_data):
        image = Image.open(io.BytesIO(image_data))
        img_array = np.array(image)
        if len(img_array.shape) == 3:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        img_array = self.preprocess_image(img_array)
        return img_array

    def preprocess_image(self, img):
        img = img.astype(np.float32) / 255.0
        img = cv2.adaptiveThreshold(
            (img * 255).astype(np.uint8),
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11,
            2
        )
        img = cv2.medianBlur(img, 3)
        img = img.astype(np.float32) / 255.0
        return img

    def verify_signatures(self, reference_img, verification_img):
        if reference_img.shape != verification_img.shape:
            verification_img = cv2.resize(verification_img, (reference_img.shape[1], reference_img.shape[0]))
        structural_similarity = self.calculate_structural_similarity(reference_img, verification_img)
        stroke_similarity = self.analyze_strokes(reference_img, verification_img)
        pressure_similarity = self.analyze_pressure(reference_img, verification_img)
        contour_similarity = self.analyze_contours(reference_img, verification_img)
        weights = {
            'structural': 0.3,
            'stroke': 0.3,
            'pressure': 0.2,
            'contour': 0.2
        }
        overall_confidence = (
            structural_similarity * weights['structural'] +
            stroke_similarity * weights['stroke'] +
            pressure_similarity * weights['pressure'] +
            contour_similarity * weights['contour']
        ) * 100
        is_match = (
            structural_similarity > 0.75 and
            stroke_similarity > 0.70 and
            pressure_similarity > 0.60 and
            contour_similarity > 0.65 and
            overall_confidence > 70
        )
        analysis = [
            f"Structural Similarity: {round(structural_similarity * 100, 2)}%",
            f"Stroke Analysis: {round(stroke_similarity * 100, 2)}%",
            f"Pressure Analysis: {round(pressure_similarity * 100, 2)}%",
            f"Contour Analysis: {round(contour_similarity * 100, 2)}%",
            f"Overall Confidence: {round(overall_confidence, 2)}%",
            "\nMatch Criteria:",
            "- High structural similarity (>75%)",
            "- High stroke similarity (>70%)",
            "- Good pressure similarity (>60%)",
            "- Good contour similarity (>65%)",
            "- High overall confidence (>70%)"
        ]
        return {
            'match': is_match,
            'confidence': round(overall_confidence, 2),
            'strokeSimilarity': round(stroke_similarity * 100, 2),
            'pressureAnalysis': round(pressure_similarity * 100, 2),
            'analysis': analysis
        }

    def calculate_structural_similarity(self, img1, img2):
        mse = np.mean((img1 - img2) ** 2)
        similarity = 1 / (1 + mse)
        return similarity

    def analyze_strokes(self, img1, img2):
        edges1 = cv2.Canny((img1 * 255).astype(np.uint8), 50, 150)
        edges2 = cv2.Canny((img2 * 255).astype(np.uint8), 50, 150)
        contours1, _ = cv2.findContours(edges1, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours2, _ = cv2.findContours(edges2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        angle_similarity = self.compare_stroke_angles(contours1, contours2)
        count_similarity = min(len(contours1), len(contours2)) / max(len(contours1), len(contours2)) if max(len(contours1), len(contours2)) > 0 else 0
        return 0.6 * angle_similarity + 0.4 * count_similarity

    def compare_stroke_angles(self, contours1, contours2):
        def get_angles(contours):
            angles = []
            for cnt in contours:
                if len(cnt) >= 2:
                    dx = cnt[-1][0][0] - cnt[0][0][0]
                    dy = cnt[-1][0][1] - cnt[0][0][1]
                    angle = np.arctan2(dy, dx)
                    angles.append(angle)
            return angles
        angles1 = get_angles(contours1)
        angles2 = get_angles(contours2)
        if not angles1 or not angles2:
            return 0
        min_len = min(len(angles1), len(angles2))
        if min_len == 0:
            return 0
        angles1 = angles1[:min_len]
        angles2 = angles2[:min_len]
        diff = np.abs(np.array(angles1) - np.array(angles2))
        diff = np.minimum(diff, 2 * np.pi - diff)
        similarity = 1 - np.mean(diff) / np.pi
        return similarity

    def analyze_contours(self, img1, img2):
        edges1 = cv2.Canny((img1 * 255).astype(np.uint8), 50, 150)
        edges2 = cv2.Canny((img2 * 255).astype(np.uint8), 50, 150)
        contours1, _ = cv2.findContours(edges1, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours2, _ = cv2.findContours(edges2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        area_similarity = self.compare_contour_features(contours1, contours2, 'area')
        length_similarity = self.compare_contour_features(contours1, contours2, 'length')
        return 0.5 * area_similarity + 0.5 * length_similarity

    def analyze_pressure(self, img1, img2):
        def get_pressure_map(img):
            blur = cv2.GaussianBlur(img, (5, 5), 0)
            return np.mean(blur)
        pressure1 = get_pressure_map((img1 * 255).astype(np.uint8))
        pressure2 = get_pressure_map((img2 * 255).astype(np.uint8))
        diff = abs(pressure1 - pressure2) / 255.0
        similarity = 1 - diff
        return similarity

    def compare_contour_features(self, contours1, contours2, feature_type):
        def get_feature(contours, feature_type):
            features = []
            for cnt in contours:
                if feature_type == 'area':
                    features.append(cv2.contourArea(cnt))
                elif feature_type == 'length':
                    features.append(cv2.arcLength(cnt, True))
            return features
        features1 = get_feature(contours1, feature_type)
        features2 = get_feature(contours2, feature_type)
        if not features1 or not features2:
            return 0
        min_len = min(len(features1), len(features2))
        if min_len == 0:
            return 0
        features1 = features1[:min_len]
        features2 = features2[:min_len]
        diff = np.abs(np.array(features1) - np.array(features2))
        max_val = np.maximum(np.array(features1), np.array(features2))
        max_val[max_val == 0] = 1
        similarity = 1 - np.mean(diff / max_val)
        return similarity

def run_server():
    ports = [8000, 8080, 3000, 5000, 9000, 9999]
    server = None
    for PORT in ports:
        try:
            server = socketserver.TCPServer(("", PORT), SignatureVerificationHandler)
            print(f"\nServer started successfully!")
            print(f"Open your browser and visit: http://localhost:{PORT}")
            print("Press Ctrl+C to stop the server")
            server.serve_forever()
            break
        except OSError as e:
            if "already in use" in str(e):
                print(f"Port {PORT} is in use, trying another port...")
                continue
            else:
                print(f"Error starting server: {str(e)}")
                break
        except KeyboardInterrupt:
            print("\nShutting down server...")
            if server:
                server.server_close()
            break
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            break

if __name__ == "__main__":
    run_server()
