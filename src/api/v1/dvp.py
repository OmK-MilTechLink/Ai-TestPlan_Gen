"""
Endpoint 5 & 6: PTP Document Generation and Download
Generates Excel and Word PTP matching industry standards
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from typing import List, Dict, Any
import uuid
from datetime import datetime
from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from src.models.api_models import (
    DVPGenerationRequest,
    DVPGenerationResponse,
    JobStatus,
    JobStatusResponse
)
from src.config import settings
from loguru import logger

router = APIRouter()

# In-memory job storage
dvp_jobs = {}
generated_dvps = {}  # Store DVP metadata

class PTPGenerator:
    """
    Generates PTP documents matching reference format
    """

    def __init__(self):
        self.workbook = None

    def generate_ptp(self, component_profile: Dict[str, Any],
                    test_cases: List[Dict[str, Any]],
                    include_traceability: bool = True) -> str:
        """
        Generate complete PTP Excel document
        """
        logger.info(f"Generating PTP for: {component_profile.get('name')}")

        # Create workbook
        self.workbook = Workbook()

        # Remove default sheet
        if 'Sheet' in self.workbook.sheetnames:
            del self.workbook['Sheet']

        # Sheet 1: PTP - Test Matrix
        logger.debug("Generating Sheet 1: Test Matrix")
        self._create_test_matrix_sheet(component_profile, test_cases)

        # Sheet 2: Test Sequence
        logger.debug("Generating Sheet 2: Test Sequence")
        self._create_test_sequence_sheet(test_cases)

        # Sheet 3: Traceability Matrix (if requested)
        if include_traceability:
            logger.debug("Generating Sheet 3: Traceability Matrix")
            self._create_traceability_sheet(test_cases)

        # Sheet 4: Source References
        logger.debug("Generating Sheet 4: Source References")
        self._create_references_sheet(test_cases)

        # Save file
        output_filename = f"PTP_{component_profile.get('name', 'Component').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        output_path = Path(settings.output_dir) / output_filename

        self.workbook.save(str(output_path))
        file_size = output_path.stat().st_size
        logger.info(f"PTP saved to: {output_path} (Size: {file_size/1024:.2f} KB)")

        return str(output_path)

    def generate_ptp_docx_v1(self, component_profile: Dict[str, Any],
                         test_cases: List[Dict[str, Any]],
                         include_traceability: bool = True) -> str:
        """
        V1: Generate a PTP Word document.
        Kept for backward compatibility. Callers now use generate_ptp_docx (V2).
        """
        logger.info(f"Generating PTP Docx for: {component_profile.get('name')}")

        def _shade_cell(cell, hex_color: str):
            """Apply background shading to a table cell."""
            tc_pr = cell._tc.get_or_add_tcPr()
            shd = OxmlElement('w:shd')
            shd.set(qn('w:fill'), hex_color)
            tc_pr.append(shd)

        def _set_cell_text(cell, text: str, bold: bool = False, size: int = 10):
            """Set cell text with formatting."""
            cell.text = ""
            p = cell.paragraphs[0]
            run = p.add_run(str(text))
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.name = 'Calibri'

        def _add_test_case_table(doc, tc_data: dict, index: int):
            """Add an individual test case as a structured 2-column table."""
            tc_name = tc_data.get('test_name', tc_data.get('test_description', f'Test Case {index}'))
            tc_id = tc_data.get('source_requirement', tc_data.get('requirement_id', f'TC-{index:03d}'))

            doc.add_heading(f"{index}. {tc_name}", level=3)

            rows_data = []
            rows_data.append(("Test Case ID", str(tc_id)))
            rows_data.append(("Test Name", str(tc_name)))

            # Purpose
            desc = tc_data.get('test_description', tc_data.get('test_name', ''))
            if desc:
                rows_data.append(("Purpose", str(desc)))

            # Test Procedure
            procedure = tc_data.get('detailed_procedure', tc_data.get('test_procedure', ''))
            if procedure:
                if isinstance(procedure, list):
                    proc_lines = [f"{i+1}. {step}" for i, step in enumerate(procedure)]
                    rows_data.append(("Test Procedure", "\n".join(proc_lines)))
                else:
                    rows_data.append(("Test Procedure", str(procedure)))

            # Acceptance Criteria
            criteria = tc_data.get('acceptance_criteria', '')
            if criteria:
                rows_data.append(("Acceptance Criteria", str(criteria)))

            # Traceability
            traceability = tc_data.get('traceability', {})
            if traceability:
                source_std = traceability.get('source_standard', '')
                if source_std:
                    rows_data.append(("Source Standard", str(source_std)))

            # Build table
            table = doc.add_table(rows=len(rows_data), cols=2)
            table.style = 'Table Grid'
            table.columns[0].width = Inches(2.0)
            table.columns[1].width = Inches(4.5)

            for row_idx, (label, value) in enumerate(rows_data):
                cell_label = table.rows[row_idx].cells[0]
                cell_value = table.rows[row_idx].cells[1]
                _set_cell_text(cell_label, label, bold=True, size=10)
                _shade_cell(cell_label, 'D9E2F3')
                _set_cell_text(cell_value, value, bold=False, size=10)

            doc.add_paragraph("")

        # ================================================================
        # MAIN DOCUMENT GENERATION
        # ================================================================
        document = Document()

        HEADER_COLOR = '1F4E79'
        HEADER_TEXT_COLOR = RGBColor(255, 255, 255)

        # Default font
        style = document.styles['Normal']
        font = style.font
        font.name = 'Calibri'
        font.size = Pt(11)

        # Page margins
        section = document.sections[0]
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

        # ---- HEADER with Logo ----
        header = section.header
        header.is_linked_to_previous = False
        header_para = header.paragraphs[0]

        logo_path = Path(__file__).resolve().parent.parent.parent / "assets" / "Logo_TechLink_new.png"
        if logo_path.exists():
            run_logo = header_para.add_run()
            run_logo.add_picture(str(logo_path), width=Inches(1.5))
        else:
            run_logo = header_para.add_run("Millennium TechLink")
            run_logo.font.size = Pt(12)
            run_logo.font.bold = True
            run_logo.font.color.rgb = RGBColor(75, 0, 130)

        run_spacer = header_para.add_run("\t\t")
        run_title = header_para.add_run("Test Plan & Test Case Document")
        run_title.font.size = Pt(9)
        run_title.font.color.rgb = RGBColor(100, 100, 100)

        # ---- FOOTER ----
        footer = section.footer
        footer.is_linked_to_previous = False
        footer_para = footer.paragraphs[0]
        footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_f = footer_para.add_run("Millennium TechLink - Confidential & Proprietary")
        run_f.font.size = Pt(8)
        run_f.font.color.rgb = RGBColor(128, 128, 128)

        # ---- COVER PAGE ----
        comp_name = component_profile.get('name', 'Component')
        comp_type = component_profile.get('type', '')
        comp_app = component_profile.get('application', '')

        if logo_path.exists():
            logo_para = document.add_paragraph()
            logo_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = logo_para.add_run()
            run.add_picture(str(logo_path), width=Inches(2.5))

        document.add_paragraph("\n\n")

        title = document.add_heading("Test Plan & Test Case Document", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in title.runs:
            run.font.color.rgb = RGBColor(31, 78, 121)

        subtitle = document.add_paragraph()
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_sub = subtitle.add_run(comp_name)
        run_sub.font.size = Pt(18)
        run_sub.font.bold = True
        run_sub.font.color.rgb = RGBColor(54, 96, 146)

        document.add_paragraph("\n")

        cover_table = document.add_table(rows=4, cols=2)
        cover_table.style = 'Table Grid'
        cover_table.columns[0].width = Inches(2.5)
        cover_table.columns[1].width = Inches(4.0)

        cover_data = [
            ("Product Name", comp_name),
            ("Application", comp_app),
            ("Document Version", "1.0"),
            ("Date", datetime.now().strftime('%d %B %Y')),
        ]
        for i, (label, val) in enumerate(cover_data):
            _set_cell_text(cover_table.rows[i].cells[0], label, bold=True, size=12)
            _shade_cell(cover_table.rows[i].cells[0], 'D9E2F3')
            _set_cell_text(cover_table.rows[i].cells[1], val, bold=False, size=12)

        document.add_paragraph("\n\n")

        notice = document.add_paragraph()
        notice.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_notice = notice.add_run("CONFIDENTIAL & PROPRIETARY")
        run_notice.font.size = Pt(10)
        run_notice.font.bold = True
        run_notice.font.color.rgb = RGBColor(192, 0, 0)

        document.add_page_break()

        # ---- REVISION HISTORY ----
        document.add_heading("Revision History", level=1)
        rev_table = document.add_table(rows=2, cols=4)
        rev_table.style = 'Table Grid'
        rev_headers = ["Version", "Date", "Changes Made", "Author"]
        for i, h in enumerate(rev_headers):
            _set_cell_text(rev_table.rows[0].cells[i], h, bold=True, size=10)
            _shade_cell(rev_table.rows[0].cells[i], HEADER_COLOR)
            rev_table.rows[0].cells[i].paragraphs[0].runs[0].font.color.rgb = HEADER_TEXT_COLOR

        _set_cell_text(rev_table.rows[1].cells[0], "1.0", size=10)
        _set_cell_text(rev_table.rows[1].cells[1], datetime.now().strftime('%d/%m/%Y'), size=10)
        _set_cell_text(rev_table.rows[1].cells[2], "Initial AI-generated test plan", size=10)
        _set_cell_text(rev_table.rows[1].cells[3], "AI System", size=10)

        document.add_page_break()

        # ---- TABLE OF CONTENTS ----
        document.add_heading("Table of Contents", level=1)
        sec = 1
        toc_items = [f"{sec}. Introduction"]
        sec += 1
        if test_cases:
            toc_items.append(f"{sec}. Test Cases")
            for idx, tc in enumerate(test_cases, 1):
                tc_name = tc.get('test_name', tc.get('test_description', f'Test Case {idx}'))
                toc_items.append(f"   {sec}.{idx} {tc_name}")
            sec += 1
        if include_traceability:
            toc_items.append(f"{sec}. Requirement Traceability")
            sec += 1
        toc_items.append(f"{sec}. References")
        document.add_paragraph("\n".join(toc_items))

        document.add_page_break()

        # ---- INTRODUCTION ----
        cur_section = 1
        document.add_heading(f"{cur_section}. Introduction", level=1)

        document.add_heading(f"{cur_section}.1 Objectives", level=2)
        document.add_paragraph(
            f"This document provides the detailed test planning and test procedures "
            f"for verification of {comp_name}. This is a living document and will be "
            f"updated as needed."
        )

        document.add_heading(f"{cur_section}.2 Scope", level=2)
        document.add_paragraph(
            f"This document identifies the test equipment, procedures, expected results, "
            f"and traceability to requirements for the {comp_name} ({comp_app} application)."
        )

        document.add_heading(f"{cur_section}.3 Equipment Under Test (EUT)", level=2)

        details_map = {
            "Product Name": comp_name,
            "Type": comp_type,
            "Application": comp_app,
            "Test Level": component_profile.get('test_level', 'Component'),
        }
        specs = component_profile.get('specifications', {})
        for spec_name, spec_value in specs.items():
            if spec_value and str(spec_value) != 'N/A':
                details_map[spec_name.capitalize()] = str(spec_value)

        variants = component_profile.get('variants', [])
        if variants:
            details_map["Variants"] = ", ".join(variants)

        table_pd = document.add_table(rows=0, cols=2)
        table_pd.style = 'Table Grid'
        table_pd.columns[0].width = Inches(2.5)
        table_pd.columns[1].width = Inches(4.0)
        for k, v in details_map.items():
            row_cells = table_pd.add_row().cells
            _set_cell_text(row_cells[0], k, bold=True, size=10)
            _shade_cell(row_cells[0], 'D9E2F3')
            _set_cell_text(row_cells[1], str(v), size=10)

        document.add_paragraph("")
        cur_section += 1

        # ---- TEST CASES (Individual Tables) ----
        if test_cases:
            document.add_heading(f"{cur_section}. Test Cases", level=1)
            document.add_paragraph(
                f"The following section details {len(test_cases)} test case(s). "
                f"Each test case includes its purpose, procedure, and acceptance criteria."
            )

            for idx, tc in enumerate(test_cases, 1):
                _add_test_case_table(document, tc, idx)

            cur_section += 1

        # ---- TRACEABILITY ----
        if include_traceability:
            document.add_page_break()
            document.add_heading(f"{cur_section}. Requirement Traceability", level=1)
            document.add_paragraph("This section maps test cases to source requirements.")

            headers = ['#', 'Requirement ID', 'Source Standard', 'Confidence', 'Relevance']
            table = document.add_table(rows=1, cols=len(headers))
            table.style = 'Table Grid'

            table.columns[0].width = Inches(0.4)
            table.columns[1].width = Inches(1.5)
            table.columns[2].width = Inches(2.0)
            table.columns[3].width = Inches(1.5)
            table.columns[4].width = Inches(1.0)

            hdr_cells = table.rows[0].cells
            for i, h in enumerate(headers):
                _set_cell_text(hdr_cells[i], h, bold=True, size=10)
                _shade_cell(hdr_cells[i], HEADER_COLOR)
                hdr_cells[i].paragraphs[0].runs[0].font.color.rgb = HEADER_TEXT_COLOR

            for idx, test_case in enumerate(test_cases, start=1):
                traceability = test_case.get('traceability', {})
                row_cells = table.add_row().cells
                row_cells[0].text = str(idx)
                row_cells[1].text = str(traceability.get('requirement_id', ''))
                source = f"{traceability.get('source_standard', '')} {traceability.get('source_clause', '')}"
                row_cells[2].text = source.strip()
                row_cells[3].text = str(traceability.get('confidence_reasoning', 'N/A'))
                row_cells[4].text = str(traceability.get('relevance_score', 'N/A'))

            cur_section += 1

        # ---- REFERENCES ----
        document.add_page_break()
        document.add_heading(f"{cur_section}. References", level=1)

        references = set()
        for test_case in test_cases:
            traceability = test_case.get('traceability', {})
            source_std = traceability.get('source_standard', '')
            if source_std:
                references.add(source_std)

        if references:
            for ref in sorted(references):
                document.add_paragraph(ref, style='List Bullet')
        else:
            document.add_paragraph("No references available.", style='List Bullet')

        # Save file
        output_filename = f"PTP_Doc_{component_profile.get('name', 'Component').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        output_path = Path(settings.output_dir) / output_filename

        document.save(str(output_path))
        logger.info(f"PTP Document saved to: {output_path}")

        return str(output_path)

    def generate_ptp_docx(self, component_profile: Dict[str, Any],
                         test_cases: List[Dict[str, Any]],
                         include_traceability: bool = True) -> str:
        """
        V2: Generate a highly detailed, professional PTP Word document
        closely matching the NC2 Functional TestPlan reference format.
        """
        logger.info(f"Generating PTP Docx V2 for: {component_profile.get('name')}")

        def _shade(cell, hex_color: str):
            tc_pr = cell._tc.get_or_add_tcPr()
            shd = OxmlElement('w:shd')
            shd.set(qn('w:fill'), hex_color)
            tc_pr.append(shd)

        def _cell(cell, text: str, bold: bool = False, size: int = 10, color: RGBColor = None):
            cell.text = ""
            p = cell.paragraphs[0]
            run = p.add_run(str(text))
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.name = 'Calibri'
            if color:
                run.font.color.rgb = color

        def _header_row(table, headers, color, txt_color):
            for i, h in enumerate(headers):
                _cell(table.rows[0].cells[i], h, bold=True, size=10, color=txt_color)
                _shade(table.rows[0].cells[i], color)

        def _kv_row(table, label, value):
            row = table.add_row().cells
            _cell(row[0], label, bold=True, size=10)
            _shade(row[0], LABEL_BG)
            _cell(row[1], value, size=10)

        # Constants
        HDR = '1F4E79'
        HDR_TXT = RGBColor(255, 255, 255)
        LABEL_BG = 'D9E2F3'
        RED = RGBColor(192, 0, 0)
        GRAY = RGBColor(128, 128, 128)
        TITLE_BLUE = RGBColor(31, 78, 121)

        document = Document()
        style = document.styles['Normal']
        style.font.name = 'Calibri'
        style.font.size = Pt(11)

        sec = document.sections[0]
        sec.top_margin = Inches(1.0)
        sec.bottom_margin = Inches(0.75)
        sec.left_margin = Inches(1.0)
        sec.right_margin = Inches(1.0)

        logo_path = Path(__file__).resolve().parent.parent.parent / "assets" / "Logo_TechLink_new.png"

        # ---- HEADER ----
        header = sec.header
        header.is_linked_to_previous = False
        hp = header.paragraphs[0]
        if logo_path.exists():
            hp.add_run().add_picture(str(logo_path), width=Inches(1.4))
        else:
            r = hp.add_run("Millennium TechLink")
            r.font.size = Pt(11)
            r.font.bold = True
            r.font.color.rgb = RGBColor(75, 0, 130)
        hp.add_run("\t\t")
        rt = hp.add_run("Test Plan & Test Case Document")
        rt.font.size = Pt(8)
        rt.font.italic = True
        rt.font.color.rgb = GRAY

        # ---- FOOTER ----
        footer = sec.footer
        footer.is_linked_to_previous = False
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fr = fp.add_run("Millennium TechLink  \u00b7  Confidential & Proprietary")
        fr.font.size = Pt(8)
        fr.font.color.rgb = GRAY

        # ---- EXTRACT DATA ----
        comp_name = component_profile.get('name', 'Component')
        comp_type = component_profile.get('type', '')
        comp_app = component_profile.get('application', '')

        # ================================================================
        #  COVER PAGE
        # ================================================================
        if logo_path.exists():
            lp = document.add_paragraph()
            lp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            lp.add_run().add_picture(str(logo_path), width=Inches(2.8))

        document.add_paragraph("\n")
        title = document.add_heading("Test Plan & Test Case Document", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for r in title.runs:
            r.font.color.rgb = TITLE_BLUE

        sub = document.add_paragraph()
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sr = sub.add_run(comp_name)
        sr.font.size = Pt(20)
        sr.font.bold = True
        sr.font.color.rgb = RGBColor(54, 96, 146)

        document.add_paragraph("")

        ct = document.add_table(rows=5, cols=2)
        ct.style = 'Table Grid'
        ct.columns[0].width = Inches(2.5)
        ct.columns[1].width = Inches(4.0)
        for i, (lbl, val) in enumerate([
            ("Document Title", f"Test Plan & Test Case Document \u2014 {comp_name}"),
            ("Product / EUT", comp_name),
            ("Application", comp_app),
            ("Document Version", "1.0"),
            ("Date", datetime.now().strftime('%d %B %Y')),
        ]):
            _cell(ct.rows[i].cells[0], lbl, bold=True, size=11)
            _shade(ct.rows[i].cells[0], LABEL_BG)
            _cell(ct.rows[i].cells[1], val, size=11)

        document.add_paragraph("\n")
        cn = document.add_paragraph()
        cn.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cr = cn.add_run("CONFIDENTIAL & PROPRIETARY")
        cr.font.size = Pt(11)
        cr.font.bold = True
        cr.font.color.rgb = RED

        document.add_page_break()

        # ================================================================
        #  REVISION HISTORY
        # ================================================================
        document.add_heading("Revision History", level=1)
        rh = document.add_table(rows=2, cols=5)
        rh.style = 'Table Grid'
        _header_row(rh, ["Version", "Date", "Changes Made", "Author", "Reviewed By"], HDR, HDR_TXT)
        _cell(rh.rows[1].cells[0], "1.0", size=10)
        _cell(rh.rows[1].cells[1], datetime.now().strftime('%d/%m/%Y'), size=10)
        _cell(rh.rows[1].cells[2], "Initial AI-generated test plan", size=10)
        _cell(rh.rows[1].cells[3], "AI System", size=10)
        _cell(rh.rows[1].cells[4], "", size=10)

        document.add_page_break()

        # ================================================================
        #  TABLE OF CONTENTS
        # ================================================================
        document.add_heading("Table of Contents", level=1)
        sn = 1
        toc = []
        toc.append(f"{sn}. Introduction")
        toc.append(f"   {sn}.1 Objectives")
        toc.append(f"   {sn}.2 Scope")
        toc.append(f"   {sn}.3 Abbreviations")
        toc.append(f"   {sn}.4 Reference Documents")
        toc.append(f"   {sn}.5 Equipment Under Test")
        sn += 1

        if test_cases:
            toc.append(f"{sn}. Test Strategy")
            sn += 1
            toc.append(f"{sn}. Test Cases")
            for idx, tc in enumerate(test_cases, 1):
                tc_name = tc.get('test_name', tc.get('test_description', f'Test Case {idx}'))
                toc.append(f"   {sn}.{idx} {tc_name}")
            sn += 1

        if include_traceability:
            toc.append(f"{sn}. Requirement Traceability")
            sn += 1
        toc.append(f"{sn}. References")
        document.add_paragraph("\n".join(toc))
        document.add_page_break()

        # ================================================================
        #  SECTION 1 — INTRODUCTION
        # ================================================================
        cs = 1
        document.add_heading(f"{cs}. Introduction", level=1)

        document.add_heading(f"{cs}.1 Objectives", level=2)
        document.add_paragraph(
            f"The objective of this test artifact is to provide detailed test planning "
            f"and test procedures for functional verification of {comp_name}. This document "
            f"is a live document and will be updated as and when need arises."
        )

        document.add_heading(f"{cs}.2 Scope", level=2)
        document.add_paragraph(
            f"This document identifies the test equipment required for functional "
            f"verification of {comp_name}. It also lists the test procedures, expected "
            f"results, and traceability to requirements."
        )

        document.add_heading(f"{cs}.3 Definitions / Acronyms / Abbreviations", level=2)
        ab_tbl = document.add_table(rows=1, cols=2)
        ab_tbl.style = 'Table Grid'
        ab_tbl.columns[0].width = Inches(2.0)
        ab_tbl.columns[1].width = Inches(4.5)
        _header_row(ab_tbl, ["Abbreviation", "Description"], HDR, HDR_TXT)
        for abbr, desc in [("EUT", "Equipment Under Test"), ("PTP", "Product Test Plan"),
                           ("DVP", "Design Verification Plan"), ("EMC", "Electromagnetic Compatibility"),
                           ("ESD", "Electrostatic Discharge")]:
            row = ab_tbl.add_row().cells
            _cell(row[0], abbr, bold=True, size=10)
            _cell(row[1], desc, size=10)
        document.add_paragraph("")

        document.add_heading(f"{cs}.4 Reference Documents", level=2)
        ref_tbl = document.add_table(rows=1, cols=3)
        ref_tbl.style = 'Table Grid'
        ref_tbl.columns[0].width = Inches(3.0)
        ref_tbl.columns[1].width = Inches(1.5)
        ref_tbl.columns[2].width = Inches(2.0)
        _header_row(ref_tbl, ["Document Title", "Revision", "Remarks"], HDR, HDR_TXT)

        references = set()
        for tc in test_cases:
            tr = tc.get('traceability', {})
            src = tr.get('source_standard', '')
            if src:
                references.add(src)

        if references:
            for ref in sorted(references):
                row = ref_tbl.add_row().cells
                _cell(row[0], ref, size=10)
                _cell(row[1], "\u2014", size=10)
                _cell(row[2], "Applicable Standard", size=10)
        else:
            row = ref_tbl.add_row().cells
            _cell(row[0], "No reference documents", size=10)
            _cell(row[1], "\u2014", size=10)
            _cell(row[2], "\u2014", size=10)
        document.add_paragraph("")

        document.add_heading(f"{cs}.5 Equipment Under Test (EUT)", level=2)
        eut_tbl = document.add_table(rows=0, cols=2)
        eut_tbl.style = 'Table Grid'
        eut_tbl.columns[0].width = Inches(2.5)
        eut_tbl.columns[1].width = Inches(4.0)
        _kv_row(eut_tbl, "Product Name", comp_name)
        _kv_row(eut_tbl, "Type", comp_type)
        _kv_row(eut_tbl, "Application", comp_app)
        _kv_row(eut_tbl, "Test Level", component_profile.get('test_level', 'Component'))
        specs = component_profile.get('specifications', {})
        for spec_name, spec_value in specs.items():
            if spec_value and str(spec_value) != 'N/A':
                _kv_row(eut_tbl, spec_name.capitalize(), str(spec_value))
        variants = component_profile.get('variants', [])
        if variants:
            _kv_row(eut_tbl, "Variants", ", ".join(variants))
        document.add_paragraph("")
        cs += 1

        # ================================================================
        #  SECTION 2 — TEST STRATEGY
        # ================================================================
        if test_cases:
            document.add_page_break()
            document.add_heading(f"{cs}. Test Strategy", level=1)

            document.add_heading(f"{cs}.1 Testing Approach", level=2)
            document.add_paragraph(
                f"The testing approach for {comp_name} follows a systematic methodology:\n\n"
                f"1. Review applicable standards and requirements.\n"
                f"2. Prepare test setups and equipment.\n"
                f"3. Execute test procedures as documented below.\n"
                f"4. Record observations and compare against acceptance criteria.\n"
                f"5. Document results and generate compliance reports."
            )

            document.add_heading(f"{cs}.2 Test Summary", level=2)
            st = document.add_table(rows=1, cols=3)
            st.style = 'Table Grid'
            st.columns[0].width = Inches(1.0)
            st.columns[1].width = Inches(4.0)
            st.columns[2].width = Inches(1.5)
            _header_row(st, ["#", "Test Case Name", "Status"], HDR, HDR_TXT)
            for idx, tc in enumerate(test_cases, 1):
                row = st.add_row().cells
                _cell(row[0], str(idx), size=10)
                _cell(row[1], tc.get('test_name', tc.get('test_description', f'Test Case {idx}')), size=10)
                _cell(row[2], "Planned", size=10)
            document.add_paragraph("")
            cs += 1

        # ================================================================
        #  SECTION 3 — TEST CASES (individual tables)
        # ================================================================
        if test_cases:
            document.add_page_break()
            document.add_heading(f"{cs}. Test Cases", level=1)
            document.add_paragraph(
                f"This section contains {len(test_cases)} detailed test case(s). Each test "
                f"case includes purpose, required equipment, procedure, and acceptance criteria."
            )

            for idx, tc in enumerate(test_cases, 1):
                tc_name = tc.get('test_name', tc.get('test_description', f'Test Case {idx}'))
                tc_id = tc.get('source_requirement', tc.get('requirement_id', f'TC-{idx:03d}'))

                document.add_heading(f"{cs}.{idx} {tc_name}", level=2)

                rows = []
                rows.append(("Requirements Tag", str(tc.get('traceability', {}).get('requirement_id', 'N/A'))))
                rows.append(("Test Case ID", str(tc_id)))
                rows.append(("Purpose", str(tc.get('test_description', tc.get('test_name', '')))))

                setup = tc.get('setup', tc.get('equipment', ''))
                if setup:
                    rows.append(("Set-up / Equipment", str(setup)))

                procedure = tc.get('detailed_procedure', tc.get('test_procedure', ''))
                if procedure:
                    if isinstance(procedure, list):
                        proc_lines = [f"{i+1}. {s}" for i, s in enumerate(procedure)]
                        rows.append(("Test Procedure", "\n".join(proc_lines)))
                    else:
                        rows.append(("Test Procedure", str(procedure)))

                criteria = tc.get('acceptance_criteria', '')
                if criteria:
                    rows.append(("Expected Result", str(criteria)))

                qty = tc.get('quantity', '')
                if qty:
                    rows.append(("Number of Samples", str(qty)))

                rows.append(("Comments", str(tc.get('comments', ''))))

                tbl = document.add_table(rows=len(rows), cols=2)
                tbl.style = 'Table Grid'
                tbl.columns[0].width = Inches(2.0)
                tbl.columns[1].width = Inches(4.5)

                for ri, (label, value) in enumerate(rows):
                    _cell(tbl.rows[ri].cells[0], label, bold=True, size=10)
                    _shade(tbl.rows[ri].cells[0], LABEL_BG)
                    _cell(tbl.rows[ri].cells[1], value, size=10)

                document.add_paragraph("")

            cs += 1

        # ================================================================
        #  TRACEABILITY
        # ================================================================
        if include_traceability:
            document.add_page_break()
            document.add_heading(f"{cs}. Requirement Traceability", level=1)
            document.add_paragraph(
                "The following matrix traces each test case back to its source "
                "requirement and applicable standard."
            )

            tr_hdrs = ['#', 'Test Case', 'Requirement ID', 'Source Standard', 'Confidence', 'Relevance']
            tr_tbl = document.add_table(rows=1, cols=len(tr_hdrs))
            tr_tbl.style = 'Table Grid'
            tr_tbl.columns[0].width = Inches(0.3)
            tr_tbl.columns[1].width = Inches(1.5)
            tr_tbl.columns[2].width = Inches(1.2)
            tr_tbl.columns[3].width = Inches(1.5)
            tr_tbl.columns[4].width = Inches(1.0)
            tr_tbl.columns[5].width = Inches(0.8)
            _header_row(tr_tbl, tr_hdrs, HDR, HDR_TXT)

            for idx, tc in enumerate(test_cases, 1):
                tr_data = tc.get('traceability', {})
                row = tr_tbl.add_row().cells
                row[0].text = str(idx)
                row[1].text = tc.get('test_name', tc.get('test_description', f'TC-{idx}'))
                row[2].text = str(tr_data.get('requirement_id', ''))
                source = f"{tr_data.get('source_standard', '')} {tr_data.get('source_clause', '')}"
                row[3].text = source.strip()
                row[4].text = str(tr_data.get('confidence_reasoning', 'N/A'))
                row[5].text = str(tr_data.get('relevance_score', 'N/A'))

            cs += 1

        # ================================================================
        #  REFERENCES
        # ================================================================
        document.add_page_break()
        document.add_heading(f"{cs}. References", level=1)
        if references:
            for ref in sorted(references):
                document.add_paragraph(ref, style='List Bullet')
        else:
            document.add_paragraph("No references available.", style='List Bullet')

        # Save
        output_filename = f"PTP_Doc_{component_profile.get('name', 'Component').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        output_path = Path(settings.output_dir) / output_filename
        document.save(str(output_path))
        logger.info(f"PTP Document V2 saved to: {output_path}")
        return str(output_path)

    def _create_test_matrix_sheet(self, component_profile: Dict[str, Any],
                                  test_cases: List[Dict[str, Any]]):
        """
        Create main test matrix sheet
        """
        ws = self.workbook.create_sheet("PTP - Test Matrix", 0)

        # Header section
        ws['A1'] = f"PROJECT NAME: {component_profile.get('name', 'Component')}"
        ws['A1'].font = Font(bold=True, size=14)

        ws['A2'] = f"Component Type: {component_profile.get('type', '')}"
        ws['A3'] = f"Application: {component_profile.get('application', '')}"
        ws['A4'] = f"Test Level: {component_profile.get('test_level', '')}"

        # Column headers (row 6)
        headers = [
            'Sl.No.',
            'Test Standard',
            'Test Description',
            'Test Procedure',
            'Acceptance Criteria',
            'Test Responsibility',
            'Test Stage',
            'Qty',
            'Test Days',
            'Start date',
            'End date',
            'Test Inference',
            'PCB/LAMP ASSEMBLY',
            'Remarks'
        ]

        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=6, column=col_idx)
            cell.value = header
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        # Data rows
        for row_idx, test_case in enumerate(test_cases, start=7):
            ws.cell(row=row_idx, column=1).value = test_case.get('test_id', f'B{row_idx-6}')
            ws.cell(row=row_idx, column=2).value = test_case.get('test_standard', '')
            ws.cell(row=row_idx, column=3).value = test_case.get('test_description', '')
            ws.cell(row=row_idx, column=4).value = test_case.get('test_procedure', '')
            ws.cell(row=row_idx, column=5).value = test_case.get('acceptance_criteria', '')
            ws.cell(row=row_idx, column=6).value = test_case.get('test_responsibility', 'Supplier')
            ws.cell(row=row_idx, column=7).value = test_case.get('test_stage', 'PTP')
            ws.cell(row=row_idx, column=8).value = test_case.get('quantity', '5')
            ws.cell(row=row_idx, column=9).value = test_case.get('estimated_days', 5)
            ws.cell(row=row_idx, column=10).value = ''  # Start date
            ws.cell(row=row_idx, column=11).value = ''  # End date
            ws.cell(row=row_idx, column=12).value = ''  # Test Inference
            ws.cell(row=row_idx, column=13).value = test_case.get('pcb_or_lamp', component_profile.get('test_level', ''))
            ws.cell(row=row_idx, column=14).value = test_case.get('remarks', '')

            # Wrap text for procedure and criteria
            ws.cell(row=row_idx, column=4).alignment = Alignment(wrap_text=True, vertical='top')
            ws.cell(row=row_idx, column=5).alignment = Alignment(wrap_text=True, vertical='top')

        # Adjust column widths
        column_widths = {
            'A': 10, 'B': 15, 'C': 25, 'D': 40, 'E': 40,
            'F': 15, 'G': 12, 'H': 20, 'I': 10, 'J': 12,
            'K': 12, 'L': 15, 'M': 25, 'N': 20
        }

        for col, width in column_widths.items():
            ws.column_dimensions[col].width = width

        # Set row heights
        for row_idx in range(7, 7 + len(test_cases)):
            ws.row_dimensions[row_idx].height = 60

    def _create_test_sequence_sheet(self, test_cases: List[Dict[str, Any]]):
        """
        Create test sequence sheet
        """
        ws = self.workbook.create_sheet("TEST SEQUENCE", 1)

        ws['A1'] = "TEST SEQUENCE"
        ws['A1'].font = Font(bold=True, size=14)

        # Group tests by category
        thermal_tests = [tc for tc in test_cases if 'thermal' in tc.get('test_description', '').lower()]
        mechanical_tests = [tc for tc in test_cases if 'mechanical' in tc.get('test_description', '').lower()]
        env_tests = [tc for tc in test_cases if 'environment' in tc.get('test_description', '').lower() or 'humidity' in tc.get('test_description', '').lower()]

        row = 3
        ws.cell(row=row, column=1).value = "ENVIRONMENTAL TESTS"
        ws.cell(row=row, column=1).font = Font(bold=True)

        row += 1
        for idx, test in enumerate(env_tests + thermal_tests, start=1):
            ws.cell(row=row, column=1).value = f"Leg {idx}"
            ws.cell(row=row, column=2).value = test.get('test_id', '')
            ws.cell(row=row, column=3).value = test.get('test_description', '')
            row += 1

        row += 2
        ws.cell(row=row, column=1).value = "MECHANICAL TESTS"
        ws.cell(row=row, column=1).font = Font(bold=True)

        row += 1
        for idx, test in enumerate(mechanical_tests, start=1):
            ws.cell(row=row, column=1).value = f"Leg {idx}"
            ws.cell(row=row, column=2).value = test.get('test_id', '')
            ws.cell(row=row, column=3).value = test.get('test_description', '')
            row += 1

    def _create_traceability_sheet(self, test_cases: List[Dict[str, Any]]):
        """
        Create traceability matrix sheet
        """
        ws = self.workbook.create_sheet("Traceability Matrix", 2)

        # Headers
        headers = [
            'ID',
            'Test Description',
            'Requirement ID',
            'Source Clause',
            'Source Standard',
            'Requirement Type',
            'Confidence Score',
            'Linking Method'
        ]

        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx)
            cell.value = header
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid")

        # Data rows
        row_idx = 2
        for idx, test_case in enumerate(test_cases, start=1):
            traceability = test_case.get('traceability', {})

            ws.cell(row=row_idx, column=1).value = f"B{idx}"
            ws.cell(row=row_idx, column=2).value = test_case.get('test_description', '')
            ws.cell(row=row_idx, column=3).value = traceability.get('requirement_id', '')
            ws.cell(row=row_idx, column=4).value = traceability.get('source_clause', '')
            ws.cell(row=row_idx, column=5).value = traceability.get('source_standard', '')
            ws.cell(row=row_idx, column=6).value = traceability.get('requirement_type', '')
            ws.cell(row=row_idx, column=7).value = traceability.get('confidence_score', '')
            ws.cell(row=row_idx, column=8).value = 'Hybrid (Semantic + Graph)'

            row_idx += 1

        # Adjust column widths
        for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']:
            ws.column_dimensions[col].width = 20

    def _create_references_sheet(self, test_cases: List[Dict[str, Any]]):
        """
        Create source references sheet
        """
        ws = self.workbook.create_sheet("Source References", 3)

        ws['A1'] = "SOURCE STANDARDS AND CLAUSES REFERENCED"
        ws['A1'].font = Font(bold=True, size=12)

        # Collect unique references
        references = set()
        for test_case in test_cases:
            traceability = test_case.get('traceability', {})
            source_std = traceability.get('source_standard', '')
            source_clause = traceability.get('source_clause', '')

            if source_std and source_clause:
                references.add(f"{source_std} - Clause {source_clause}")

        # List references
        row = 3
        for ref in sorted(references):
            ws.cell(row=row, column=1).value = ref
            row += 1

async def process_dvp_generation(job_id: str, request: DVPGenerationRequest):
    """
    Background task for PTP generation
    """
    try:
        dvp_jobs[job_id]['status'] = JobStatus.PROCESSING
        dvp_jobs[job_id]['current_step'] = 'Generating PTP document'
        dvp_jobs[job_id]['progress_percent'] = 20.0

        generator = PTPGenerator()
        
        output_format = request.output_format.lower()
        if output_format == 'docx' or output_format == 'doc':
             output_path = generator.generate_ptp_docx(
                component_profile=request.component_profile.model_dump(),
                test_cases=request.test_cases,
                include_traceability=request.include_traceability_sheet
            )
        else:
            # Default to xlsx
            output_path = generator.generate_ptp(
                component_profile=request.component_profile.model_dump(),
                test_cases=request.test_cases,
                include_traceability=request.include_traceability_sheet
            )

        # Get file size
        file_size = Path(output_path).stat().st_size

        # Create PTP ID
        dvp_id = Path(output_path).stem

        # Store PTP metadata
        generated_dvps[dvp_id] = {
            'dvp_id': dvp_id,
            'file_path': output_path,
            'component_name': request.component_profile.name,
            'test_cases_count': len(request.test_cases),
            'file_size_bytes': file_size,
            'created_at': datetime.utcnow()
        }

        # Update job status
        dvp_jobs[job_id]['status'] = JobStatus.COMPLETED
        dvp_jobs[job_id]['current_step'] = 'Completed'
        dvp_jobs[job_id]['progress_percent'] = 100.0
        dvp_jobs[job_id]['result'] = {
            'dvp_id': dvp_id,
            'file_path': output_path,
            'file_size_bytes': file_size,
            'test_cases_count': len(request.test_cases)
        }

        logger.info(f"PTP generation job {job_id} completed: {dvp_id}")

    except Exception as e:
        logger.exception(f"PTP generation job {job_id} failed: {e}")
        dvp_jobs[job_id]['status'] = JobStatus.FAILED
        dvp_jobs[job_id]['error'] = str(e)

# ==================== ENDPOINTS ====================

@router.post("/generate", response_model=DVPGenerationResponse)
async def generate_dvp_document(
    request: DVPGenerationRequest,
    background_tasks: BackgroundTasks
):
    """
    **Endpoint 5: Generate PTP Document**

    Creates complete PTP document (Excel or Word) matching industry standards.

    **Sheets Generated (Excel):**
    1. PTP - Test Matrix (main test matrix)
    2. EMC & ENV TEST SEQUENCE (test grouping)
    3. Traceability Matrix (requirement → test mapping)
    4. Source References (standards cited)

    **Format:**
    - Excel .xlsx format
    - Word .docx format (Product Testing Plan)
    - Matches industrial PTP layout
    - Includes styling and formatting
    - Ready for use by quality engineers

    **Parameters:**
    - component_profile: Component specifications
    - test_cases: Generated test cases from LLM
    - output_format: xlsx or docx
    - include_traceability_sheet: Include traceability

    **Example:**
    ```json
    {
        "component_profile": {...},
        "test_cases": [...],
        "output_format": "docx",
        "include_traceability_sheet": true
    }
    ```
    """
    job_id = str(uuid.uuid4())

    # Validate test cases
    if not request.test_cases:
        raise HTTPException(
            status_code=400,
            detail="No test cases provided. Please generate test cases first using /llm/generate"
        )

    # Create job entry
    dvp_jobs[job_id] = {
        'job_id': job_id,
        'status': JobStatus.PENDING,
        'current_step': 'Initializing',
        'progress_percent': 0.0,
        'created_at': datetime.utcnow()
    }

    # Start background processing
    background_tasks.add_task(
        process_dvp_generation,
        job_id,
        request
    )

    return DVPGenerationResponse(
        job_id=job_id,
        dvp_id="",  # Will be set when completed
        status=JobStatus.PENDING,
        message="PTP generation started. Use /dvp/status/{job_id} to check progress.",
        download_url="",
        file_size_bytes=0,
        test_cases_count=len(request.test_cases),
        requirements_covered=0,
        traceability_complete=request.include_traceability_sheet,
        timestamp=datetime.utcnow()
    )

@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_dvp_generation_status(job_id: str):
    """
    **Check PTP generation job status**
    """
    if job_id not in dvp_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = dvp_jobs[job_id]

    return JobStatusResponse(
        job_id=job_id,
        status=job['status'],
        progress_percent=job.get('progress_percent', 0.0),
        current_step=job.get('current_step', 'Unknown'),
        message=f"PTP generation: {job.get('current_step', 'Processing')}",
        result=job.get('result') if job['status'] == JobStatus.COMPLETED else None,
        error=job.get('error')
    )

@router.get("/download/{dvp_id}")
async def download_dvp(dvp_id: str):
    """
    **Endpoint 6: Download Generated PTP**

    Download the Excel or Word PTP document.
    """
    if dvp_id not in generated_dvps:
        raise HTTPException(status_code=404, detail=f"PTP {dvp_id} not found")

    dvp_metadata = generated_dvps[dvp_id]
    file_path = dvp_metadata['file_path']

    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="PTP file not found on disk")

    return FileResponse(
        path=file_path,
        filename=Path(file_path).name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document" if str(file_path).endswith('.docx') else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@router.get("/list")
async def list_generated_dvps():
    """
    **List all generated PTPs**
    """
    return {
        "total_ptps": len(generated_dvps),
        "ptps": [
            {
                "ptp_id": dvp_id,
                "component_name": metadata['component_name'],
                "test_cases_count": metadata['test_cases_count'],
                "file_size_bytes": metadata['file_size_bytes'],
                "created_at": metadata['created_at'].isoformat(),
                "download_url": f"/api/v1/dvp/download/{dvp_id}"
            }
            for dvp_id, metadata in generated_dvps.items()
        ]
    }

@router.delete("/delete/{dvp_id}")
async def delete_dvp(dvp_id: str):
    """
    **Delete a generated PTP**
    """
    if dvp_id not in generated_dvps:
        raise HTTPException(status_code=404, detail=f"PTP {dvp_id} not found")

    dvp_metadata = generated_dvps[dvp_id]
    file_path = Path(dvp_metadata['file_path'])

    # Delete file
    if file_path.exists():
        file_path.unlink()

    # Remove from metadata
    del generated_dvps[dvp_id]

    return {
        "message": f"PTP {dvp_id} deleted successfully",
        "ptp_id": dvp_id
    }
