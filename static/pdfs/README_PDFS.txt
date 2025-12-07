# PDF Files - TODO

This directory contains PDF files for onboarding and contracts.

## Files Needed:

1. onboarding_manager.pdf
   - Source: staticpages/content/onboarding_manager.md
   - TODO: Convert markdown to PDF using a tool like pandoc or wkhtmltopdf
   - Command: pandoc staticpages/content/onboarding_manager.md -o static/pdfs/onboarding_manager.pdf

2. onboarding_hq.pdf
   - Source: staticpages/content/onboarding_hq.md
   - TODO: Convert markdown to PDF
   - Command: pandoc staticpages/content/onboarding_hq.md -o static/pdfs/onboarding_hq.pdf

3. merchant_contract_template.pdf
   - Source: staticpages/content/merchant_contract_template.md
   - TODO: Convert markdown to PDF with proper legal formatting
   - Command: pandoc staticpages/content/merchant_contract_template.md -o static/pdfs/merchant_contract_template.pdf

## Generating PDFs

### Option 1: Using Pandoc
Install pandoc: https://pandoc.org/installing.html

Then run:
```
pandoc staticpages/content/onboarding_manager.md -o static/pdfs/onboarding_manager.pdf --pdf-engine=wkhtmltopdf
pandoc staticpages/content/onboarding_hq.md -o static/pdfs/onboarding_hq.pdf --pdf-engine=wkhtmltopdf
pandoc staticpages/content/merchant_contract_template.md -o static/pdfs/merchant_contract_template.pdf --pdf-engine=wkhtmltopdf
```

### Option 2: Using Python/Django
Create a management command that uses reportlab or weasyprint to generate PDFs from the markdown content.

### Option 3: Online Converters
Use services like markdown-pdf.com or similar to convert manually.

For now, placeholder text files are in place. Replace these with actual PDFs before deployment!

