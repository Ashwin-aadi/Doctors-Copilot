"""One-off generator for the CP1 V1.2 lab-report fixtures.

Run standalone: `python ml/generate_fixtures.py`. Builds 5 realistic Indian
diagnostic-lab reports (Dr. Lal PathLabs / Metropolis / SRL style layout,
British spellings, SI units as printed on Indian lab reports) as text-layer
PDFs, plus one deliberately skewed/noisy scan variant (rasterised, rotated,
noise-injected, saved with no embedded text layer) into `ml/fixtures/`.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import numpy as np
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

LAB_HEADER = {
    "name": "PathCare Diagnostics Pvt. Ltd.",
    "address": "12, MG Road, Bengaluru - 560001, Karnataka, India",
    "reg": "NABL Accredited Laboratory | Reg. No. KA/PC/2019/00417",
}

PATIENT = {
    "Patient Name": "Ramesh Kumar",
    "Age/Sex": "45 Y / Male",
    "Ref. Doctor": "Dr. Anita Sharma, MD",
    "Sample Date": "12-Aug-2026",
}


def _report(filename: str, title: str, rows: list[list[str]]) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        str(FIXTURES_DIR / filename), pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm
    )
    elements = [
        Paragraph(f"<b>{LAB_HEADER['name']}</b>", styles["Title"]),
        Paragraph(LAB_HEADER["address"], styles["Normal"]),
        Paragraph(LAB_HEADER["reg"], styles["Normal"]),
        Spacer(1, 8 * mm),
        Paragraph(f"<b>{title}</b>", styles["Heading2"]),
    ]
    for k, v in PATIENT.items():
        elements.append(Paragraph(f"<b>{k}:</b> {v}", styles["Normal"]))
    elements.append(Spacer(1, 6 * mm))

    table_data = [["Investigation", "Result", "Unit", "Reference Range"]] + rows
    table = Table(table_data, colWidths=[70 * mm, 25 * mm, 30 * mm, 45 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3864")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 10 * mm))
    elements.append(Paragraph("-- End of Report --", styles["Italic"]))
    doc.build(elements)


def build_cbc() -> None:
    rows = [
        ["Haemoglobin", "10.2", "g/dL", "13.0 - 17.0"],
        ["Total Leukocyte Count (TLC)", "11800", "cells/cu mm", "4000 - 11000"],
        ["Platelet Count", "1.42", "lakhs/cu mm", "1.50 - 4.10"],
        ["RBC Count", "4.1", "mill/cu mm", "4.5 - 5.5"],
        ["Packed Cell Volume (PCV)", "33.5", "%", "40 - 50"],
        ["MCV", "81.7", "fL", "83 - 101"],
        ["MCH", "24.9", "pg", "27 - 32"],
        ["MCHC", "30.4", "g/dL", "31.5 - 34.5"],
        ["Neutrophils", "68", "%", "40 - 80"],
        ["Lymphocytes", "24", "%", "20 - 40"],
        ["Eosinophils", "3", "%", "1 - 6"],
        ["ESR", "28", "mm/hr", "0 - 15"],
    ]
    _report("cbc.pdf", "Complete Blood Count (CBC)", rows)


def build_lft() -> None:
    rows = [
        ["Bilirubin (Total)", "1.8", "mg/dL", "0.3 - 1.2"],
        ["Bilirubin (Direct)", "0.5", "mg/dL", "0.0 - 0.3"],
        ["Bilirubin (Indirect)", "1.3", "mg/dL", "0.2 - 0.8"],
        ["SGOT (AST)", "62", "U/L", "5 - 40"],
        ["SGPT (ALT)", "75", "U/L", "7 - 56"],
        ["Alkaline Phosphatase (ALP)", "142", "U/L", "44 - 147"],
        ["Total Protein", "6.8", "g/dL", "6.0 - 8.3"],
        ["Albumin", "3.9", "g/dL", "3.5 - 5.2"],
        ["Globulin", "2.9", "g/dL", "2.0 - 3.5"],
        ["A/G Ratio", "1.34", "ratio", "1.1 - 2.5"],
        ["GGT", "58", "U/L", "9 - 48"],
    ]
    _report("lft.pdf", "Liver Function Test (LFT)", rows)


def build_kft() -> None:
    rows = [
        ["Urea", "42", "mg/dL", "15 - 40"],
        ["Blood Urea Nitrogen (BUN)", "19.6", "mg/dL", "7 - 20"],
        ["Creatinine", "1.3", "mg/dL", "0.6 - 1.3"],
        ["Uric Acid", "6.8", "mg/dL", "3.4 - 7.0"],
        ["Sodium", "138", "mEq/L", "135 - 145"],
        ["Potassium", "4.6", "mEq/L", "3.5 - 5.1"],
        ["Chloride", "101", "mEq/L", "98 - 107"],
        ["eGFR", "68", "mL/min/1.73m2", ">60"],
    ]
    _report("kft.pdf", "Kidney Function Test (KFT)", rows)


def build_lipid() -> None:
    rows = [
        ["Total Cholesterol", "218", "mg/dL", "< 200"],
        ["Triglycerides", "168", "mg/dL", "< 150"],
        ["HDL Cholesterol", "38", "mg/dL", "> 40"],
        ["LDL Cholesterol", "146", "mg/dL", "< 100"],
        ["VLDL Cholesterol", "33.6", "mg/dL", "5 - 40"],
        ["Total Cholesterol/HDL Ratio", "5.7", "ratio", "< 5.0"],
    ]
    _report("lipid.pdf", "Lipid Profile", rows)


def build_thyroid() -> None:
    rows = [
        ["TSH (Thyroid Stimulating Hormone)", "6.8", "uIU/mL", "0.35 - 4.94"],
        ["Free T3", "2.4", "pg/mL", "1.71 - 3.71"],
        ["Free T4", "0.9", "ng/dL", "0.70 - 1.48"],
        ["Total T3", "108", "ng/dL", "80 - 200"],
        ["Total T4", "7.1", "ug/dL", "5.1 - 14.1"],
    ]
    _report("thyroid.pdf", "Thyroid Profile", rows)


def build_noisy_scan() -> None:
    """Rasterise cbc.pdf, rotate + inject noise, save with no text layer."""
    src = FIXTURES_DIR / "cbc.pdf"
    doc = fitz.open(str(src))
    pix = doc[0].get_pixmap(dpi=300)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()

    rng = np.random.default_rng(7)
    arr = np.array(img).astype(np.int16)
    noise = rng.normal(0, 18, arr.shape).astype(np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    noisy = Image.fromarray(arr).rotate(7.5, expand=True, fillcolor=(255, 255, 255))
    noisy.save(FIXTURES_DIR / "cbc_noisy_scan.pdf", "PDF", resolution=300.0)


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    build_cbc()
    build_lft()
    build_kft()
    build_lipid()
    build_thyroid()
    build_noisy_scan()
    print(f"fixtures written to {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
