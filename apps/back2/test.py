import os
import logging
import sys
import argparse

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('test_pdf')

def test_pdfplumber(pdf_path: str):
    try:
        import pdfplumber
    except Exception as e:
        logger.error('pdfplumber not installed: %s', e)
        return

    if not os.path.exists(pdf_path):
        logger.warning('PDF not found: %s', pdf_path)
        return

    logger.info('Opening PDF: %s', pdf_path)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            num_pages = len(pdf.pages)
            logger.info('Total pages: %d', num_pages)

            # Read pages 1-5 (or all if fewer than 5)
            max_pages = min(5, num_pages)
            logger.info('Reading pages 1 to %d', max_pages)

            for page_idx in range(max_pages):
                page = pdf.pages[page_idx]
                text = page.extract_text() or ''

                # รวมทุกบรรทัดเป็นข้อความเดียว
                clean_text = text.strip()

                logger.info("\n=== PAGE %d ===\n%s\n", page_idx + 1, clean_text)

    except Exception as e:
        logger.exception('Error reading PDF: %s', e)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test PDF reading with pdfplumber')
    parser.add_argument('--pdf', help='Path to PDF file', default='sample.pdf')
    args = parser.parse_args()
    
    test_pdfplumber(args.pdf)
