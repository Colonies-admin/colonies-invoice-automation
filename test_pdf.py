import os
from modules.pdf_extractor import extract_invoice_data
data = extract_invoice_data("test1.pdf")
for k, v in data.items():
    print(k, v)
