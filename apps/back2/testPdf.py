from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os

out_path = os.path.join(os.path.dirname(__file__), 'sample.pdf')

def make_pdf(path):
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter
    c.setFont('Helvetica', 12)
    lines = [
        'This is a sample PDF generated for testing pdfplumber.',
        'Line 2: The quick brown fox jumps over the lazy dog.',
        'Line 3: สวัสดีครับ นี่คือไฟล์ทดสอบภาษาไทย.',
        'Line 4: Testing PDF extraction.',
        'Line 5: End of sample.'
    ]
    y = height - 72
    for line in lines:
        c.drawString(72, y, line)
        y -= 18
    c.showPage()
    c.save()

if __name__ == '__main__':
    make_pdf(out_path)
    print('Wrote sample PDF to', out_path)
