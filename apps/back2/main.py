import os
import logging
import sys

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('back2')

MODEL_DIR_ENV = 'KHANOMTAN_MODEL_DIR'

def demo_pdfplumber(pdf_path: str):
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
            logger.info('Number of pages: %d', num_pages)
            if num_pages > 0:
                first_page = pdf.pages[0]
                text = first_page.extract_text() or ''
                snippet = text.strip().split('\n')[:5]
                logger.info('First page text (first 5 lines):')
                for i, line in enumerate(snippet, start=1):
                    logger.info('  %d: %s', i, line)
    except Exception as e:
        logger.exception('Error reading PDF: %s', e)


def main():
    # Default sample PDF path (look in project for sample.pdf)
    default_pdf = os.path.join(os.path.dirname(__file__), 'sample.pdf')
    model_dir = os.environ.get(MODEL_DIR_ENV)
    if model_dir:
        logger.info('KHANOMTAN_MODEL_DIR is set to: %s', model_dir)
    else:
        logger.info('KHANOMTAN_MODEL_DIR not set; continuing without model path')

    pdf_path = default_pdf
    # if a pdf path argument provided, use it
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--pdf', help='Path to pdf to inspect', default=pdf_path)
    args = parser.parse_args()
    demo_pdfplumber(args.pdf)


if __name__ == '__main__':
    main()
from fastapi import FastAPI

app= FastAPI()

@app.get("/")
def root():
    return "server is worked 111"


@app.get("/test")
def root():
    return "test test 222"

@app.post("/")
def root():
    return "test post 333"