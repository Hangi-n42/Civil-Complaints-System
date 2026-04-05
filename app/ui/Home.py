import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import json
from pathlib import Path
from typing import Dict, List, Any
import re
import time
import random
import html
from urllib import error as urlerror
from urllib import request as urlrequest

from app.core.title_builder import build_case_title
from app.ui.components.search_ui import (
    render_search_filter,
    render_search_result_card,
    render_standard_status_banner,
    render_citations_block,
    render_limitations_block,
)
from app.ui.services.search_service import post_json, run_qa_via_api, search_cases_via_api_with_filters


def load_model_benchmark_report() -> Dict[str, Any]:
    """Week3 모델 벤치마크 최종 리포트(JSON)를 로드한다.

    - Path 기반 로드
    - 파일이 없거나 파싱 실패 시 Mock Dict 반환
    """

    default_mock: Dict[str, Any] = {
        "timestamp": "2026-03-27T18:00:00Z",
        "model_info": {"llm_model": "Qwen2.5-7B", "embedding_model": "BGE-m3"},
        "summary": {
            "average_f1_score": 0.91,
            "average_recall_at_5": 0.88,
            "average_latency_sec": 4.5,
        },
        "scenarios": [
            {"name": "도로안전 (포트홀)", "f1_score": 0.94, "recall_at_5": 0.90, "latency_sec": 4.2},
            {"name": "환경위생 (무단투기)", "f1_score": 0.88, "recall_at_5": 0.85, "latency_sec": 4.6},
            {"name": "주거복지 (층간소음)", "f1_score": 0.92, "recall_at_5": 0.89, "latency_sec": 4.8},
        ],
    }

    try:
        project_root = Path(__file__).resolve().parents[2]
        report_path = project_root / "logs" / "evaluation" / "week3" / "model_benchmark_report_final.json"
        if not report_path.exists():
            return default_mock
        raw = report_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else default_mock
    except Exception:
        return default_mock


# ============================================================================
# 1. PAGE CONFIG & STYLING
# ============================================================================

st.set_page_config(
    page_title="공공 민원 AI 처리 시스템",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    :root {
        --primary: #1e3a8a;
        --primary-light: #3b82f6;
        --success: #10b981;
        --warning: #f59e0b;
        --danger: #ef4444;
        --gray-bg: #f8fafc;
        --gray-border: #e2e8f0;
        --gray-text: #64748b;
        --white: #ffffff;
    }

    .stApp {
        background: var(--gray-bg);
        color: #0f172a;
    }

    /* Hide Streamlit top-right Deploy (robust across Streamlit versions) */
    header [data-testid="stHeaderActionElements"],
    header [data-testid="stToolbar"],
    [data-testid="stToolbar"],
    [data-testid="stToolbarActions"],
    [data-testid="stToolbarActionElements"] {
        display: none !important;
        visibility: hidden !important;
    }

    /* Remove hyperlink look (black text, no underline) */
    .stApp a, .stApp a:visited {
        color: #0f172a !important;
        text-decoration: none !important;
    }
    .stApp a:hover, .stApp a:active, .stApp a:focus {
        color: #0f172a !important;
        text-decoration: none !important;
    }
    /* Preserve button-like anchors */
    .stApp a.wb-action-done { color: #ffffff !important; }
    .stApp a.wb-action-review { color: #0b0b0b !important; }

    /* ===== Week3 Demo: Workbench screenshot replica ===== */
    [data-testid="stSidebar"] {
        background: #e9eef6;
        border-right: 1px solid #cbd5e1;
    }

    .sb-brand {
        padding: 12px 10px 8px 10px;
        margin-bottom: 8px;
    }
    .sb-brand-title {
        font-size: 1.05rem;
        font-weight: 900;
        color: #0f172a;
        letter-spacing: 0.02em;
        line-height: 1.1;
    }
    .sb-brand-sub {
        font-size: 0.72rem;
        font-weight: 700;
        color: #64748b;
        margin-top: 3px;
    }
    .sb-menu {
        margin-top: 8px;
    }
    .sb-item {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 11px 10px;
        border-radius: 10px;
        color: #0f172a;
        text-decoration: none;
        font-size: 0.92rem;
        font-weight: 800;
        position: relative;
        margin-bottom: 6px;
    }
    .sb-item:hover {
        background: rgba(255, 255, 255, 0.55);
        border: 1px solid rgba(148, 163, 184, 0.45);
    }
    .sb-item.active {
        background: rgba(255, 255, 255, 0.80);
        border: 1px solid rgba(148, 163, 184, 0.55);
    }
    .sb-item.active::before {
        content: "";
        position: absolute;
        left: -10px;
        top: 10px;
        height: calc(100% - 20px);
        width: 4px;
        border-radius: 999px;
        background: #0f172a;
    }

    .wb-topnav {
        display: flex;
        align-items: center;
        gap: 14px;
        padding: 6px 0 8px 0;
    }
    .wb-topnav .wb-topnav-spacer {
        margin-left: auto;
    }
    .wb-topnav .wb-topnav-status {
        font-weight: 900;
        font-size: 0.88rem;
        color: #0f172a;
        white-space: nowrap;
    }
    .wb-topnav a {
        color: #0f172a;
        text-decoration: none;
        font-weight: 800;
        font-size: 0.92rem;
    }
    .wb-topnav a:hover {
        text-decoration: none;
    }
    .wb-topline {
        border-bottom: 1px solid #cbd5e1;
        margin-bottom: 10px;
    }

    .wb-panel {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 0px;
        padding: 10px 10px;
        min-height: 640px;
    }

    .wb-section-title {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 8px;
    }

    .wb-section-title .title {
        font-size: 0.95rem;
        font-weight: 900;
        color: #0f172a;
    }

    .wb-mini-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 4px 10px;
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        background: #f8fafc;
        color: #0f172a;
        font-size: 0.78rem;
        font-weight: 800;
        text-decoration: none;
        line-height: 1.2;
        white-space: nowrap;
    }
    .wb-mini-btn:hover {
        background: #f1f5f9;
        border-color: #94a3b8;
    }

    /* Make the Workbench '초안' Streamlit button look like wb-mini-btn */
    .wb-draft-mini-btn-anchor {
        display: none !important;
    }
    div[data-testid="stElementContainer"]:has(.wb-draft-mini-btn-anchor) + div[data-testid="stElementContainer"] div[data-testid="stButton"] {
        display: flex;
        justify-content: flex-end;
        align-items: center;
    }
    div[data-testid="stElementContainer"]:has(.wb-draft-mini-btn-anchor) + div[data-testid="stElementContainer"] div[data-testid="stButton"] button {
        padding: 4px 10px !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 4px !important;
        background: #f8fafc !important;
        color: #0f172a !important;
        font-size: 0.78rem !important;
        font-weight: 800 !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
        height: auto !important;
        box-shadow: none !important;
    }
    div[data-testid="stElementContainer"]:has(.wb-draft-mini-btn-anchor) + div[data-testid="stElementContainer"] div[data-testid="stButton"] button:hover {
        background: #f1f5f9 !important;
        border-color: #94a3b8 !important;
    }

    /* Workbench: style Streamlit buttons as existing wb-mini-btn */
    .wb-mini-btn-anchor {
        display: none !important;
    }
    div[data-testid="stElementContainer"]:has(.wb-mini-btn-anchor) + div[data-testid="stElementContainer"] div[data-testid="stButton"] button {
        padding: 4px 10px !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 4px !important;
        background: #f8fafc !important;
        color: #0f172a !important;
        font-size: 0.78rem !important;
        font-weight: 800 !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
        height: auto !important;
        box-shadow: none !important;
    }
    div[data-testid="stElementContainer"]:has(.wb-mini-btn-anchor) + div[data-testid="stElementContainer"] div[data-testid="stButton"] button:hover {
        background: #f1f5f9 !important;
        border-color: #94a3b8 !important;
    }

    /* Wrapper-based styling (robust inside columns) */
    .wb-mini-btn-wrap div[data-testid="stButton"] > button {
        padding: 4px 10px !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 4px !important;
        background: #f8fafc !important;
        color: #0f172a !important;
        font-size: 0.78rem !important;
        font-weight: 800 !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
        height: auto !important;
        box-shadow: none !important;
    }
    .wb-mini-btn-wrap div[data-testid="stButton"] > button:hover {
        background: #f1f5f9 !important;
        border-color: #94a3b8 !important;
    }

    .wb-topnav-link-wrap div[data-testid="stButton"] > button {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        color: #0f172a !important;
        font-weight: 800 !important;
        font-size: 0.92rem !important;
        box-shadow: none !important;
        height: auto !important;
    }

    .wb-queue-link-wrap div[data-testid="stButton"] > button {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        color: #0f172a !important;
        font-weight: 800 !important;
        font-size: 0.86rem !important;
        text-align: left !important;
        box-shadow: none !important;
        height: auto !important;
        justify-content: flex-start !important;
        width: 100% !important;
    }

    .wb-action-done-wrap div[data-testid="stButton"] > button {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        height: 46px !important;
        width: 100% !important;
        border-radius: 4px !important;
        font-size: 0.92rem !important;
        font-weight: 900 !important;
        letter-spacing: 0.01em !important;
        background: #0b0b0b !important;
        color: #ffffff !important;
        border: 2px solid #0b0b0b !important;
        box-shadow: none !important;
    }
    .wb-action-review-wrap div[data-testid="stButton"] > button {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        height: 46px !important;
        width: 100% !important;
        border-radius: 4px !important;
        font-size: 0.92rem !important;
        font-weight: 900 !important;
        letter-spacing: 0.01em !important;
        background: #ffffff !important;
        color: #0b0b0b !important;
        border: 2px solid #0b0b0b !important;
        box-shadow: none !important;
    }

    /* Workbench: style Streamlit buttons as existing wb-action-btn (done/review) */
    .wb-action-done-anchor, .wb-action-review-anchor {
        display: none !important;
    }
    div[data-testid="stElementContainer"]:has(.wb-action-done-anchor) + div[data-testid="stElementContainer"] div[data-testid="stButton"] button {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        height: 46px !important;
        width: 100% !important;
        border-radius: 4px !important;
        font-size: 0.92rem !important;
        font-weight: 900 !important;
        letter-spacing: 0.01em !important;
        background: #0b0b0b !important;
        color: #ffffff !important;
        border: 2px solid #0b0b0b !important;
        box-shadow: none !important;
    }
    div[data-testid="stElementContainer"]:has(.wb-action-review-anchor) + div[data-testid="stElementContainer"] div[data-testid="stButton"] button {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        height: 46px !important;
        width: 100% !important;
        border-radius: 4px !important;
        font-size: 0.92rem !important;
        font-weight: 900 !important;
        letter-spacing: 0.01em !important;
        background: #ffffff !important;
        color: #0b0b0b !important;
        border: 2px solid #0b0b0b !important;
        box-shadow: none !important;
    }

    /* Workbench: style Streamlit buttons as topnav links */
    .wb-topnav-link-anchor {
        display: none !important;
    }
    div[data-testid="stElementContainer"]:has(.wb-topnav-link-anchor) + div[data-testid="stElementContainer"] div[data-testid="stButton"] button {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        color: #0f172a !important;
        font-weight: 800 !important;
        font-size: 0.92rem !important;
        box-shadow: none !important;
        height: auto !important;
    }
    div[data-testid="stElementContainer"]:has(.wb-topnav-link-anchor) + div[data-testid="stElementContainer"] div[data-testid="stButton"] button:hover {
        background: transparent !important;
        border: none !important;
        text-decoration: none !important;
    }

    /* Workbench: case title buttons in left queue should look like plain links */
    .wb-queue-link-anchor {
        display: none !important;
    }
    div[data-testid="stElementContainer"]:has(.wb-queue-link-anchor) + div[data-testid="stElementContainer"] div[data-testid="stButton"] button {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        color: #0f172a !important;
        font-weight: 800 !important;
        font-size: 0.86rem !important;
        text-align: left !important;
        box-shadow: none !important;
        height: auto !important;
        justify-content: flex-start !important;
        width: 100% !important;
    }
    div[data-testid="stElementContainer"]:has(.wb-queue-link-anchor) + div[data-testid="stElementContainer"] div[data-testid="stButton"] button:hover {
        background: transparent !important;
        border: none !important;
    }

    .wb-table {
        width: 100%;
        border-collapse: collapse;
        border: 1px solid #cbd5e1;
        font-size: 0.82rem;
        table-layout: fixed;
    }
    .wb-table thead th {
        background: #f1f5f9;
        color: #0f172a;
        font-weight: 900;
        text-align: left;
        padding: 8px 8px;
        border-bottom: 1px solid #cbd5e1;
    }
    .wb-table tbody td {
        padding: 8px 8px;
        border-bottom: 1px solid #e2e8f0;
        color: #0f172a;
        vertical-align: top;
    }
    .wb-table tbody tr:hover {
        background: #f8fafc;
    }
    .wb-table tbody tr.wb-row-active {
        background: #f1f5f9;
    }
    .wb-table tbody tr.wb-row-active:hover {
        background: #f1f5f9;
    }
    .wb-table tbody tr.wb-row-active td:first-child a {
        font-weight: 900;
    }
    .wb-table a {
        color: #0f172a;
        text-decoration: none;
        font-weight: 800;
    }
    .wb-table a:hover {
        text-decoration: none;
    }

    /* Column widths + truncation similar to screenshot */
    .wb-table th:nth-child(1), .wb-table td:nth-child(1) { width: 26%; }
    .wb-table th:nth-child(2), .wb-table td:nth-child(2) { width: 44%; }
    .wb-table th:nth-child(3), .wb-table td:nth-child(3) { width: 17%; }
    .wb-table th:nth-child(4), .wb-table td:nth-child(4) { width: 13%; }
    .wb-table td:nth-child(2) {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    /* Workbench queue table (left) */
    .wb-table-queue th:nth-child(1), .wb-table-queue td:nth-child(1) { width: 46%; }
    .wb-table-queue th:nth-child(2), .wb-table-queue td:nth-child(2) { width: 22%; }
    .wb-table-queue th:nth-child(3), .wb-table-queue td:nth-child(3) { width: 16%; }
    .wb-table-queue th:nth-child(4), .wb-table-queue td:nth-child(4) { width: 16%; }
    .wb-table-queue td:nth-child(1) {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .status-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 900;
        letter-spacing: 0.02em;
    }
    .status-urgent {
        background: #0b0b0b;
        color: #ffffff;
    }
    .status-pending {
        background: #e5e7eb;
        color: #6b7280;
    }
    .status-completed {
        background: #ffffff;
        color: #6b7280;
        border: 1px solid #9ca3af;
    }

    .wb-card {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 0px;
        padding: 10px 10px;
        margin-bottom: 10px;
    }
    .wb-card-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 8px;
    }
    .wb-card-header-right {
        margin-left: auto;
        display: flex;
        align-items: center;
    }
    .wb-card-header-right div[data-testid="stButton"] > button {
        padding: 4px 10px !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 4px !important;
        background: #f8fafc !important;
        color: #0f172a !important;
        font-size: 0.78rem !important;
        font-weight: 800 !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
        height: auto !important;
        box-shadow: none !important;
    }
    .wb-card-header-right div[data-testid="stButton"] > button:hover {
        background: #f1f5f9 !important;
        border-color: #94a3b8 !important;
    }
    .wb-card-title {
        font-size: 0.9rem;
        font-weight: 900;
        color: #0f172a;
    }
    .wb-conf-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 3px 10px;
        border-radius: 999px;
        background: #f1f5f9;
        border: 1px solid #cbd5e1;
        color: #0f172a;
        font-size: 0.72rem;
        font-weight: 900;
        white-space: nowrap;
    }

    .wb-textbox {
        background: #f1f5f9;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 10px 10px;
        font-size: 0.84rem;
        color: #0f172a;
        line-height: 1.45;
        white-space: pre-wrap;
    }

    .wb-card-title-tight {
        margin: 0;
        padding: 0;
        line-height: 1.2;
    }
    .wb-textbox-scroll {
        max-height: 120px;
        overflow-y: auto;
    }

    /* Collapsible details used by 원문 텍스트 */
    .wb-details {
        border: 0;
        padding: 0;
        margin: 0;
    }

    .wb-details summary {
        list-style: none;
        cursor: pointer;
        user-select: none;
    }
    .wb-details summary::-webkit-details-marker {
        display: none;
    }
    .wb-details summary::marker {
        content: "";
    }

    .wb-details-summary {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 8px;
    }

    .wb-details-caret {
        font-weight: 900;
        color: #6b7280;
        line-height: 1;
    }

    .wb-details[open] .wb-details-caret {
        transform: rotate(180deg);
        display: inline-block;
    }

    .wb-actions {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
        margin-top: 10px;
    }

    /* Workbench similar-cases collapsible list */
    .wb-similar-list {
        max-height: 360px;
        overflow-y: auto;
        border: 1px solid #cbd5e1;
        background: #ffffff;
    }
    .wb-similar-item {
        border-bottom: 1px solid #e2e8f0;
        padding: 0;
        margin: 0;
    }
    .wb-similar-item:last-child {
        border-bottom: 0;
    }
    .wb-similar-item summary {
        list-style: none;
        cursor: pointer;
        user-select: none;
        padding: 10px 10px;
    }
    .wb-similar-item summary::-webkit-details-marker {
        display: none;
    }
    .wb-similar-item summary::marker {
        content: "";
    }
    .wb-similar-summary {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 10px;
    }
    .wb-similar-title {
        font-weight: 900;
        font-size: 0.86rem;
        color: #0f172a;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 58%;
    }
    .wb-similar-meta {
        font-size: 0.78rem;
        font-weight: 800;
        color: #64748b;
        white-space: nowrap;
    }
    .wb-similar-body {
        padding: 0 10px 10px 10px;
        display: grid;
        gap: 8px;
        max-height: 240px;
        overflow-y: auto;
    }
    .wb-similar-block {
        border: 1px solid #e2e8f0;
        background: #f8fafc;
        padding: 8px 8px;
    }
    .wb-similar-dept-list {
        display: grid;
        gap: 8px;
    }
    .wb-similar-dept-item {
        border: 1px solid #e2e8f0;
        background: #ffffff;
        padding: 8px 8px;
    }
    .wb-similar-dept-name {
        font-size: 0.78rem;
        font-weight: 900;
        color: #0f172a;
        margin-bottom: 6px;
    }
    .wb-similar-dept-answer {
        font-size: 0.84rem;
        line-height: 1.45;
        color: #0f172a;
        white-space: pre-wrap;
    }
    .wb-similar-label {
        font-size: 0.78rem;
        font-weight: 900;
        color: #0f172a;
        margin-bottom: 6px;
    }
    .wb-similar-text {
        max-height: none;
        overflow: visible;
        font-size: 0.84rem;
        line-height: 1.45;
        color: #0f172a;
        white-space: pre-wrap;
    }
    .wb-action-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        height: 46px;
        border-radius: 4px;
        font-size: 0.92rem;
        font-weight: 900;
        text-decoration: none;
        letter-spacing: 0.01em;
    }
    .wb-action-done {
        background: #0b0b0b;
        color: #ffffff;
        border: 2px solid #0b0b0b;
    }
    .wb-action-review {
        background: #ffffff;
        color: #0b0b0b;
        border: 2px solid #0b0b0b;
    }

    /* TextArea styling for draft box */
    [data-testid="stTextArea"] textarea {
        background: #f8fafc !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 6px !important;
        font-size: 0.9rem !important;
    }

    .card {
        background: var(--white);
        border: 1px solid var(--gray-border);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
    }

    .card-success {
        background: #ecfdf5;
        border: 1px solid #a7f3d0;
        border-left: 4px solid var(--success);
    }

    .card-warning {
        background: #fffbeb;
        border: 1px solid #fcd34d;
        border-left: 4px solid var(--warning);
    }

    .card-danger {
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-left: 4px solid var(--danger);
    }

    .badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 16px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-right: 6px;
        margin-bottom: 6px;
    }

    .badge-entity {
        background: #dbeafe;
        color: #1e40af;
    }

    .badge-valid {
        background: #dcfce7;
        color: #166534;
    }

    .badge-invalid {
        background: #fee2e2;
        color: #991b1b;
    }

    .badge-hazard {
        background: #fed7aa;
        color: #92400e;
    }

    .citation {
        background: #fef08a;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 0.85rem;
        font-weight: 600;
        cursor: help;
    }

    .case-list-item {
        background: var(--white);
        border: 1px solid var(--gray-border);
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 8px;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .case-list-item:hover {
        border-color: var(--primary-light);
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
    }

    .case-list-item.active {
        border-color: var(--primary-light);
        background: #eff6ff;
    }

    .metric-card {
        background: var(--white);
        border: 1px solid var(--gray-border);
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    }

    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
        color: var(--primary);
        margin: 8px 0;
    }

    .metric-label {
        color: var(--gray-text);
        font-size: 0.95rem;
        font-weight: 500;
    }

    .queue-kpi-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }

    .queue-kpi-label {
        font-size: 0.82rem;
        font-weight: 700;
        color: #64748b;
        letter-spacing: .01em;
        margin-bottom: 4px;
    }

    .queue-kpi-value {
        font-size: 1.6rem;
        line-height: 1.15;
        font-weight: 800;
        color: #0f172a;
    }

    .queue-kpi-open {
        border-left: 4px solid #2563eb;
    }

    .queue-kpi-urgent {
        border-left: 4px solid #dc2626;
    }

    .queue-kpi-done {
        border-left: 4px solid #059669;
    }

    .queue-filter-title {
        font-size: 0.9rem;
        font-weight: 700;
        color: #334155;
        margin-bottom: 8px;
    }

    .queue-filter-label {
        font-size: 0.76rem;
        font-weight: 700;
        color: #64748b;
        letter-spacing: .01em;
        margin-bottom: 2px;
    }

    .chat-message-user {
        background: var(--primary-light);
        color: white;
        border-radius: 12px;
        padding: 12px 16px;
        margin-bottom: 8px;
        margin-left: 40px;
        text-align: right;
    }

    .chat-message-assistant {
        background: #f3f4f6;
        color: #0f172a;
        border-radius: 12px;
        padding: 12px 16px;
        margin-bottom: 8px;
        margin-right: 40px;
    }

    .entity-label {
        font-weight: 600;
        color: var(--primary);
    }

    .confidence-high {
        color: var(--success);
        font-weight: 600;
    }

    .confidence-medium {
        color: var(--warning);
        font-weight: 600;
    }

    .confidence-low {
        color: var(--danger);
        font-weight: 600;
    }

    @keyframes slideInFade {
        from {
            opacity: 0;
            transform: translateY(8px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .detail-header-animate {
        background: linear-gradient(90deg, #eff6ff 0%, #f8fafc 100%);
        border: 1px solid #bfdbfe;
        border-left: 4px solid #2563eb;
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 12px;
        animation: slideInFade 220ms ease-out;
    }

    .detail-header-title {
        font-size: 1rem;
        font-weight: 700;
        color: #1e3a8a;
        margin-bottom: 2px;
    }

    .detail-header-sub {
        color: #475569;
        font-size: 0.9rem;
        font-weight: 600;
    }

    @keyframes fadeNoticeOut {
        0% { opacity: 1; transform: translateY(0); }
        80% { opacity: 1; }
        100% { opacity: 0; transform: translateY(-3px); }
    }

    .transition-inline-notice {
        margin-top: 10px;
        padding: 10px 12px;
        border-radius: 10px;
        border: 1px solid #bfdbfe;
        background: #eff6ff;
        color: #1e3a8a;
        font-size: 0.86rem;
        font-weight: 700;
        animation: fadeNoticeOut 1s ease forwards;
    }

    .detail-header-animate.detail-header-done {
        background: linear-gradient(90deg, #ecfdf5 0%, #f0fdf4 100%);
        border: 1px solid #86efac;
        border-left: 4px solid #16a34a;
    }

    .detail-header-animate.detail-header-review {
        background: linear-gradient(90deg, #fffbeb 0%, #fefce8 100%);
        border: 1px solid #fcd34d;
        border-left: 4px solid #f59e0b;
    }

    /* Queue table UX: row hover emphasis for one-click selection */
    [data-testid="stDataFrame"] tbody tr:hover {
        background-color: #eff6ff !important;
        cursor: pointer;
    }

    [data-testid="stDataFrame"] thead th {
        background: #f8fafc !important;
        color: #334155 !important;
        font-size: 0.78rem !important;
        font-weight: 700 !important;
        border-bottom: 1px solid #e2e8f0 !important;
    }

    [data-testid="stDataFrame"] tbody td {
        font-size: 0.84rem !important;
        color: #0f172a !important;
        line-height: 1.25 !important;
        padding-top: 8px !important;
        padding-bottom: 8px !important;
        border-bottom: 1px solid #f1f5f9 !important;
    }

    .queue-table-wrap [data-testid="stDataFrame"] {
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        overflow: hidden;
    }

    .workbench-toolbar-title {
        font-size: 0.9rem;
        font-weight: 700;
        color: #334155;
        margin-bottom: 8px;
    }

    .workbench-panel {
        background: #f8fafc;
        border: 1px solid #dbe3ef;
        border-radius: 12px;
        padding: 12px 14px;
    }

    .workbench-panel-title {
        font-size: 0.92rem;
        font-weight: 800;
        color: #1e3a8a;
        margin-bottom: 8px;
    }

    .workbench-result-item {
        border-bottom: 1px solid #f1f5f9;
        padding: 8px 0;
        margin-bottom: 2px;
    }

    .workbench-result-item:last-child {
        border-bottom: none;
    }

    .workbench-citation-line {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 6px 8px;
        margin-bottom: 6px;
        font-size: 0.82rem;
        color: #334155;
    }

    .structured-card {
        background: #f8fafc;
        border: 1px solid #dbe3ef;
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 10px;
    }

    .structured-card-title {
        font-size: 0.9rem;
        font-weight: 800;
        color: #1e3a8a;
    }

    .structured-card-text {
        font-size: 0.94rem;
        font-weight: 600;
        color: #0f172a;
        margin: 8px 0 4px;
    }

    .structured-card-evidence {
        font-size: 0.82rem;
        color: #64748b;
    }

    .workbench-notice {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-left: 4px solid #2563eb;
        color: #1e3a8a;
        border-radius: 10px;
        padding: 9px 12px;
        font-size: 0.86rem;
        font-weight: 600;
        margin-bottom: 10px;
    }

    .entity-mini-card {
        background: #f8fafc;
        border: 1px solid #dbe3ef;
        border-radius: 12px;
        padding: 10px 12px;
        min-height: 84px;
    }

    .workbench-side-title {
        font-size: 0.88rem;
        font-weight: 800;
        color: #1e3a8a;
        margin-bottom: 8px;
    }

    .workbench-side-meta {
        font-size: 0.82rem;
        color: #475569;
        margin-bottom: 8px;
    }

    .workbench-entity-pill {
        display: inline-block;
        border-radius: 999px;
        border: 1px solid #bfdbfe;
        background: #eff6ff;
        color: #1e3a8a;
        font-size: 0.76rem;
        font-weight: 700;
        padding: 3px 8px;
        margin: 2px 4px 2px 0;
    }

    .entity-mini-label {
        font-size: 0.76rem;
        font-weight: 800;
        color: #1e3a8a;
        letter-spacing: .02em;
        margin-bottom: 6px;
    }

    .entity-mini-text {
        font-size: 0.92rem;
        font-weight: 600;
        color: #0f172a;
    }

    .workbench-action-title {
        font-size: 0.9rem;
        font-weight: 800;
        color: #1e3a8a;
        margin-bottom: 8px;
    }

    .workbench-action-help {
        font-size: 0.78rem;
        color: #64748b;
        margin-top: 4px;
    }

    .admin-panel-title {
        font-size: 0.9rem;
        font-weight: 700;
        color: #334155;
        margin-bottom: 8px;
    }

    .admin-kpi-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }

    .admin-kpi-label {
        font-size: 0.78rem;
        font-weight: 700;
        color: #64748b;
        margin-bottom: 4px;
    }

    .admin-kpi-value {
        font-size: 1.35rem;
        line-height: 1.2;
        font-weight: 800;
        color: #0f172a;
    }

    .admin-kpi-delta {
        font-size: 0.78rem;
        font-weight: 700;
        margin-top: 4px;
    }

    .admin-kpi-up {
        color: #059669;
    }

    .admin-kpi-down {
        color: #2563eb;
    }

    .admin-section-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 12px 14px;
    }

    .admin-section-title {
        font-size: 1rem;
        font-weight: 800;
        color: #1e3a8a;
        margin-bottom: 8px;
    }

    .app-hero {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
        color: #ffffff;
        border-radius: 12px;
        padding: 22px 20px;
        margin-bottom: 14px;
        border: 1px solid rgba(255, 255, 255, 0.12);
    }

    .app-hero-title {
        margin: 0;
        font-size: 2rem;
        line-height: 1.2;
        font-weight: 800;
    }

    .app-hero-sub {
        margin-top: 6px;
        font-size: 0.95rem;
        opacity: 0.95;
        font-weight: 500;
    }

    .app-info-inline {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        color: #1e3a8a;
        border-radius: 10px;
        padding: 9px 12px;
        font-size: 0.86rem;
        font-weight: 600;
        margin-bottom: 12px;
    }

    .app-footer {
        text-align: center;
        color: #64748b;
        font-size: 0.86rem;
        padding: 14px 0 8px;
    }

    .app-footer p {
        margin: 0;
        line-height: 1.5;
    }

    .queue-select-hint {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-left: 4px solid #2563eb;
        color: #1e3a8a;
        border-radius: 10px;
        padding: 10px 12px;
        font-weight: 600;
        margin-bottom: 10px;
    }

    .queue-list-wrap {
        margin-top: 10px;
    }

    .queue-row-link {
        display: block;
        text-decoration: none;
        color: #0f172a;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 8px;
        transition: all .18s ease;
    }

    .queue-row-link:hover {
        border-color: #3b82f6;
        background: #eff6ff;
        box-shadow: 0 2px 8px rgba(30, 58, 138, 0.08);
    }

    .queue-row-selected {
        border-color: #3b82f6 !important;
        background: #eff6ff !important;
    }

    .queue-row-title {
        font-weight: 800;
        color: #1e3a8a;
        margin-bottom: 4px;
    }

    .queue-title-link {
        display: inline-block !important;
        color: #000000 !important;
        font-size: 0.80rem !important;
        font-weight: 700 !important;
        line-height: 1.15 !important;
        text-decoration: none !important;
        max-width: 100% !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        white-space: nowrap !important;
    }

    .queue-title-link:hover {
        text-decoration: none !important;
        color: #000000 !important;
    }

    .queue-title-button {
        background: none !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 4px !important;
        color: #000000 !important;
        font-size: 0.65rem !important;
        font-weight: 600 !important;
        padding: 2px 5px !important;
        cursor: pointer !important;
        text-decoration: none !important;
        font-family: inherit !important;
        line-height: 1 !important;
    }

    .queue-title-button:hover {
        background: #f1f5f9 !important;
        border-color: #94a3b8 !important;
    }

    .queue-row-meta {
        color: #475569;
        font-size: 0.9rem;
        margin-bottom: 6px;
    }

    .queue-pill {
        display: inline-block;
        border-radius: 999px;
        padding: 2px 10px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-right: 6px;
    }

    .queue-pill-priority-high {
        background: #fee2e2;
        color: #991b1b;
    }

    .queue-pill-priority-mid {
        background: #fef3c7;
        color: #92400e;
    }

    .queue-pill-priority-low {
        background: #dbeafe;
        color: #1e40af;
    }

    .queue-pill-status-open {
        background: #dcfce7;
        color: #166534;
    }

    .queue-pill-status-review {
        background: #e0f2fe;
        color: #075985;
    }

    .queue-pill-status-hold {
        background: #e5e7eb;
        color: #374151;
    }

    .queue-pill-status-done {
        background: #ede9fe;
        color: #5b21b6;
    }

    /* Hide Streamlit default chrome/navigation in favor of app-defined controls */
    #MainMenu {
        visibility: hidden;
    }

    /* Keep header container (needed for sidebar re-open control) but visually minimize it */
    header[data-testid="stHeader"] {
        background: transparent;
        height: 0px;
    }

    header[data-testid="stHeader"] [data-testid="collapsedControl"] {
        position: fixed;
        top: 0.35rem;
        left: 0.35rem;
        z-index: 1000;
    }

    [data-testid="stToolbarActions"] {
        display: none;
    }

    [data-testid="stSidebarNav"] {
        display: none;
    }

    /* Reduce top whitespace across all pages/views */
    [data-testid="stMainBlockContainer"] {
        padding-top: 0.35rem !important;
    }

    [data-testid="stAppViewContainer"] .main .block-container {
        padding-top: 0.35rem !important;
        margin-top: 0 !important;
    }

    /* Sidebar nav tuning: place controls higher and make buttons larger */
    [data-testid="stSidebar"] .block-container {
        padding-top: 0 !important;
        margin-top: -0.45rem;
    }

    [data-testid="stSidebar"] .stButton > button {
        min-height: 48px;
        font-size: 0.98rem;
        font-weight: 700;
        border-radius: 12px;
        margin-bottom: 6px;
    }

    /* Always show sidebar collapse/expand arrow controls */
    [data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"] {
        opacity: 1 !important;
        visibility: visible !important;
        display: flex !important;
    }
</style>
""", unsafe_allow_html=True)


def _qp_first(name: str) -> str | None:
    value = st.query_params.get(name)
    if value is None:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def _consume_qp(name: str) -> str | None:
    value = _qp_first(name)
    if value is None:
        return None
    try:
        del st.query_params[name]
    except Exception:
        pass
    return value


def _case_status_cache_path() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    path = project_root / "logs" / "ui" / "case_statuses.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return path


def _load_case_statuses_from_cache(default_statuses: Dict[str, str]) -> Dict[str, str]:
    path = _case_status_cache_path()
    try:
        if not path.exists():
            return dict(default_statuses)
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw) if raw else {}
        if not isinstance(parsed, dict):
            return dict(default_statuses)
        allowed = {"미처리", "검토중", "처리완료"}
        merged = dict(default_statuses)
        for key, value in parsed.items():
            case_id = str(key)
            status = str(value or "").strip() or "미처리"
            if status not in allowed:
                continue
            merged[case_id] = status
        return merged
    except Exception:
        return dict(default_statuses)


def _save_case_statuses_to_cache(statuses: Dict[str, str]) -> None:
    path = _case_status_cache_path()
    try:
        allowed = {"미처리", "검토중", "처리완료"}
        payload: Dict[str, str] = {}
        for key, value in (statuses or {}).items():
            case_id = str(key)
            status = str(value or "").strip() or "미처리"
            if status in allowed:
                payload[case_id] = status
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            tmp_path.replace(path)
        except Exception:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        return


def _clear_case_status_cache_file() -> None:
    path = _case_status_cache_path()
    try:
        if path.exists():
            path.unlink(missing_ok=True)
    except Exception:
        pass


# ============================================================================
# 2. MOCK DATA DEFINITIONS
# ============================================================================

def _format_received_at(value: Any) -> str:
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", ""))
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value
    return "-"


def _safe_index(options: List[str], value: Any, default: int = 0) -> int:
    try:
        text = "" if value is None else str(value)
        return options.index(text)
    except ValueError:
        return default


def get_case_category(case: Dict[str, Any]) -> str:
    return str(case.get("category_norm") or case.get("category") or "기타")


def get_case_region(case: Dict[str, Any]) -> str:
    region = str(case.get("region_norm") or case.get("region") or "-")
    if region in ("unknown", "Unknown", "UNK", ""):
        return "-"
    return region


def build_category_options(cases: List[Dict[str, Any]]) -> List[str]:
    base = ["도로안전", "환경위생", "주거복지", "교통행정"]
    seen: set[str] = set()
    extras: List[str] = []
    for case in cases:
        cat = get_case_category(case)
        if not cat or cat == "기타":
            continue
        if cat not in base and cat not in seen:
            seen.add(cat)
            extras.append(cat)
    return ["전체", *base, *sorted(extras)]


def build_region_options(cases: List[Dict[str, Any]]) -> List[str]:
    base = ["강남구", "서초구", "송파구", "강동구", "영등포구"]
    seen: set[str] = set()
    extras: List[str] = []
    for case in cases:
        region = get_case_region(case)
        if not region or region == "-":
            continue
        if region not in base and region not in seen:
            seen.add(region)
            extras.append(region)
    return ["전체", *base, *sorted(extras)]


def get_case_admin_units(case: Dict[str, Any]) -> List[str]:
    """케이스에서 부서(ADMIN_UNIT) 후보를 추출한다.

    - 구조화 엔티티(label=ADMIN_UNIT) 우선
    - 데이터 소스별로 top-level 필드(admin_unit/department/dept)도 방어적으로 지원
    """
    units: List[str] = []

    for key in ("admin_unit", "department", "dept"):
        raw = case.get(key)
        if raw:
            text = str(raw).strip()
            if text and text not in units:
                units.append(text)

    entities = case.get("structured", {}).get("entities", [])
    if isinstance(entities, list):
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            if str(entity.get("label")) != "ADMIN_UNIT":
                continue
            text = str(entity.get("text") or "").strip()
            if text and text not in units:
                units.append(text)

    return units


def build_admin_unit_options(cases: List[Dict[str, Any]]) -> List[str]:
    seen: set[str] = set()
    extras: List[str] = []
    has_unassigned = False

    for case in cases:
        units = get_case_admin_units(case)
        if not units:
            has_unassigned = True
            continue
        for unit in units:
            if unit not in seen:
                seen.add(unit)
                extras.append(unit)

    options = ["전체", *sorted(extras)]
    if has_unassigned:
        options.append("미지정")
    return options


def filter_cases_by_admin_unit(cases: List[Dict[str, Any]], selected_unit: str) -> List[Dict[str, Any]]:
    if not selected_unit or selected_unit == "전체":
        return list(cases)
    if selected_unit == "미지정":
        return [case for case in cases if not get_case_admin_units(case)]
    return [case for case in cases if selected_unit in get_case_admin_units(case)]


def get_case_status_kr(case: Dict[str, Any], statuses: Dict[str, Any]) -> str:
    status_kr = statuses.get(case.get("case_id", ""), case.get("status", "미처리"))
    status_kr = str(status_kr or "").strip() or "미처리"
    if status_kr in ("미처리", "검토중", "보류", "처리완료"):
        return status_kr
    return "미처리"


def filter_cases_by_priority(cases: List[Dict[str, Any]], priority_value: str) -> List[Dict[str, Any]]:
    if not priority_value or priority_value == "전체":
        return list(cases)
    return [case for case in cases if str(case.get("priority") or "보통") == priority_value]


def filter_cases_by_status(cases: List[Dict[str, Any]], statuses: Dict[str, Any], status_value: str) -> List[Dict[str, Any]]:
    if not status_value or status_value == "전체":
        return list(cases)
    return [case for case in cases if get_case_status_kr(case, statuses) == status_value]


def _span_to_evidence_text(raw_text: str, span: Any) -> str:
    if isinstance(span, str):
        return span
    if (
        isinstance(span, (list, tuple))
        and len(span) == 2
        and isinstance(span[0], int)
        and isinstance(span[1], int)
    ):
        start, end = span
        if isinstance(raw_text, str) and 0 <= start < end <= len(raw_text):
            return raw_text[start:end]
        return f"{start}:{end}"
    return ""


def load_week2_structured_sample_cases() -> List[Dict[str, Any]]:
    """week2_structured_sample_10.json을 UI 케이스 포맷으로 변환해 로딩한다.

    - 파일이 없거나 파싱 실패 시 빈 리스트 반환 (기존 mock으로 폴백)
    """
    sample_path = (
        Path(__file__).resolve().parents[2]
        / "reports"
        / "week2_entity_audit"
        / "week2_structured_sample_10.json"
    )
    if not sample_path.exists():
        return []

    try:
        data = json.loads(sample_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    cases: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue

        raw_text = str(item.get("raw_text") or item.get("text") or "")

        # 입력이 UI-case(상위에 structured 포함) 형태로 들어올 수도 있어 방어적으로 처리
        structured_in = item.get("structured") if isinstance(item.get("structured"), dict) else None
        structured_src = structured_in if structured_in is not None else item

        validation = structured_src.get("validation") if isinstance(structured_src.get("validation"), dict) else {}
        is_valid = bool(validation.get("is_valid", True))

        def _pack_field(name: str) -> Dict[str, Any]:
            field = structured_src.get(name) if isinstance(structured_src.get(name), dict) else {}
            text = str(field.get("text", ""))
            confidence = float(field.get("confidence", 0.0) or 0.0)
            span = field.get("evidence_span")
            evidence_text = _span_to_evidence_text(raw_text, span)
            return {"text": text, "confidence": confidence, "evidence_span": evidence_text}

        entities_in = structured_src.get("entities") if isinstance(structured_src.get("entities"), list) else []
        entities: List[Dict[str, Any]] = []
        for e in entities_in:
            if not isinstance(e, dict):
                continue
            label = e.get("label")
            text = e.get("text")
            if not label or not text:
                continue
            entities.append({"label": str(label), "text": str(text)})

        case_id = str(item.get("case_id", "")) or f"SAMPLE-{len(cases) + 1:03d}"

        category = str(item.get("category_norm") or item.get("category") or "기타")
        region = str(item.get("region_norm") or item.get("region") or "-")
        if region in ("unknown", "Unknown", "UNK", ""):
            region = "-"

        assignee = str(item.get("assignee") or item.get("source") or "미지정")
        priority = str(item.get("priority") or "보통")
        status = str(item.get("status") or "미처리")
        received_at = item.get("received_at") or item.get("created_at")

        cases.append(
            {
                "case_id": case_id,
                "received_at": _format_received_at(received_at),
                "category": category,
                "category_norm": item.get("category_norm"),
                "region": region,
                "region_norm": item.get("region_norm"),
                "raw_text": raw_text,
                "assignee": assignee,
                "priority": priority,
                "status": status,
                "structured": {
                    "observation": _pack_field("observation"),
                    "result": _pack_field("result"),
                    "request": _pack_field("request"),
                    "context": _pack_field("context"),
                    "entities": entities,
                    "is_valid": is_valid,
                    "schema_version": "1.0",
                },
            }
        )

    return cases

def generate_mock_assigned_cases() -> List[Dict[str, Any]]:
    """신규 할당 민원 Mock Data (Tab 1)"""
    return [
        {
            "case_id": "CASE-2026-0301-001",
            "received_at": "2026-03-21 14:30",
            "category": "도로안전",
            "region": "강남구",
            "raw_text": "중앙로 10m 지점에서 포트홀이 발생했습니다. 어제 폭우 이후 배수가 불량해 아스팔트가 패여있습니다. 이륜차 사고가 발생할 위험이 있으니 긴급 복구를 부탁드립니다.",
            "assignee": "김민철",
            "priority": "급함",
            "status": "미처리",
            "structured": {
                "observation": {
                    "text": "중앙로 10m 지점에 포트홀이 발생함",
                    "confidence": 0.94,
                    "evidence_span": "중앙로 10m 지점에서 포트홀이 발생했습니다"
                },
                "result": {
                    "text": "폭우로 인한 배수 불량이 원인",
                    "confidence": 0.89,
                    "evidence_span": "어제 폭우 이후 배수가 불량해 아스팔트가 패여있습니다"
                },
                "request": {
                    "text": "긴급 복구 요청",
                    "confidence": 0.97,
                    "evidence_span": "긴급 복구를 부탁드립니다"
                },
                "context": {
                    "text": "이륜차 사고 위험 상황",
                    "confidence": 0.91,
                    "evidence_span": "이륜차 사고가 발생할 위험이 있으니"
                },
                "entities": [
                    {"label": "LOCATION", "text": "중앙로", "start": 0, "end": 3},
                    {"label": "HAZARD", "text": "포트홀", "start": 5, "end": 7},
                    {"label": "TIME", "text": "어제", "start": 22, "end": 24},
                    {"label": "HAZARD", "text": "배수 불량", "start": 25, "end": 30},
                    {"label": "FACILITY", "text": "아스팔트", "start": 31, "end": 34},
                ],
                "is_valid": True,
                "schema_version": "1.0"
            }
        },
        {
            "case_id": "CASE-2026-0301-002",
            "received_at": "2026-03-21 13:15",
            "category": "환경위생",
            "region": "서초구",
            "raw_text": "아파트 뒷골목에서 지속적으로 악취가 나고 있습니다. 해당 지역에는 무단 쓰레기 투기가 많이 일어나고 있으며, CCTV 설치가 시급합니다. 주민 민원이 많이 접수되고 있습니다.",
            "assignee": "이정미",
            "priority": "매우급함",
            "status": "미처리",
            "structured": {
                "observation": {
                    "text": "아파트 뒷골목에서 지속적인 악취 발생",
                    "confidence": 0.93,
                    "evidence_span": "아파트 뒷골목에서 지속적으로 악취가 나고 있습니다"
                },
                "result": {
                    "text": "무단 쓰레기 투기가 원인",
                    "confidence": 0.88,
                    "evidence_span": "해당 지역에는 무단 쓰레기 투기가 많이 일어나고 있으며"
                },
                "request": {
                    "text": "CCTV 설치 요청",
                    "confidence": 0.96,
                    "evidence_span": "CCTV 설치가 시급합니다"
                },
                "context": {
                    "text": "다수 주민 민원 접수",
                    "confidence": 0.92,
                    "evidence_span": "주민 민원이 많이 접수되고 있습니다"
                },
                "entities": [
                    {"label": "LOCATION", "text": "아파트 뒷골목", "start": 0, "end": 6},
                    {"label": "HAZARD", "text": "악취", "start": 9, "end": 11},
                    {"label": "HAZARD", "text": "무단 쓰레기 투기", "start": 18, "end": 26},
                    {"label": "FACILITY", "text": "CCTV", "start": 33, "end": 37},
                ],
                "is_valid": True,
                "schema_version": "1.0"
            }
        },
        {
            "case_id": "CASE-2026-0301-003",
            "received_at": "2026-03-20 16:45",
            "category": "주거복지",
            "region": "송파구",
            "raw_text": "위층 주민이 밤 11시 이후에도 계속 시끄러운 소음을 냅니다. 짐을 옮기고 바닥을 쿵쿵거리는 소리가 매일 들립니다. 층간소음 분쟁 중재를 요청합니다.",
            "assignee": "박수환",
            "priority": "보통",
            "status": "미처리",
            "structured": {
                "observation": {
                    "text": "위층 주민의 야간 소음 발생",
                    "confidence": 0.95,
                    "evidence_span": "위층 주민이 밤 11시 이후에도 계속 시끄러운 소음을 냅니다"
                },
                "result": {
                    "text": "짐 이동과 바닥 쿵쿵거림이 원인",
                    "confidence": 0.90,
                    "evidence_span": "짐을 옮기고 바닥을 쿵쿵거리는 소리가 매일 들립니다"
                },
                "request": {
                    "text": "층간소음 분쟁 중재 요청",
                    "confidence": 0.98,
                    "evidence_span": "층간소음 분쟁 중재를 요청합니다"
                },
                "context": {
                    "text": "야간 시간대 문제 (23:00 이후)",
                    "confidence": 0.93,
                    "evidence_span": "밤 11시 이후에도 계속"
                },
                "entities": [
                    {"label": "TIME", "text": "밤 11시 이후", "start": 10, "end": 17},
                    {"label": "HAZARD", "text": "소음", "start": 24, "end": 26},
                    {"label": "FACILITY", "text": "바닥", "start": 43, "end": 45},
                ],
                "is_valid": True,
                "schema_version": "1.0"
            }
        },
        {
            "case_id": "CASE-2026-0301-004",
            "received_at": "2026-03-21 10:40",
            "category": "교통행정",
            "region": "강동구",
            "raw_text": "사거리 신호등이 주말부터 점멸 상태로 방치되어 차량 정체가 심합니다. 출근 시간대 접촉사고가 2건 발생했습니다. 신호제어기 점검과 긴급 복구를 요청합니다.",
            "assignee": "최서연",
            "priority": "매우급함",
            "status": "미처리",
            "structured": {
                "observation": {
                    "text": "사거리 신호등이 점멸 상태로 지속됨",
                    "confidence": 0.95,
                    "evidence_span": "사거리 신호등이 주말부터 점멸 상태로 방치되어"
                },
                "result": {
                    "text": "출근 시간대 정체 심화 및 접촉사고 2건 발생",
                    "confidence": 0.90,
                    "evidence_span": "출근 시간대 접촉사고가 2건 발생했습니다"
                },
                "request": {
                    "text": "신호제어기 점검 및 긴급 복구 요청",
                    "confidence": 0.97,
                    "evidence_span": "신호제어기 점검과 긴급 복구를 요청합니다"
                },
                "context": {
                    "text": "주말부터 지속된 교차로 안전 이슈",
                    "confidence": 0.89,
                    "evidence_span": "주말부터 점멸 상태로 방치되어"
                },
                "entities": [
                    {"label": "LOCATION", "text": "사거리", "start": 0, "end": 2},
                    {"label": "FACILITY", "text": "신호등", "start": 4, "end": 6},
                    {"label": "TIME", "text": "주말부터", "start": 8, "end": 11},
                    {"label": "HAZARD", "text": "접촉사고", "start": 39, "end": 43},
                ],
                "is_valid": True,
                "schema_version": "1.0"
            }
        },
        {
            "case_id": "CASE-2026-0301-005",
            "received_at": "2026-03-21 09:55",
            "category": "환경위생",
            "region": "영등포구",
            "raw_text": "하천 산책로 인근 쓰레기 적치로 악취가 심하고 해충이 증가했습니다. 야간 무단투기가 반복되며 주민 불편이 커지고 있습니다. 이동식 단속 카메라 설치 검토를 요청합니다.",
            "assignee": "이정미",
            "priority": "급함",
            "status": "미처리",
            "structured": {
                "observation": {
                    "text": "하천 산책로 주변 쓰레기 적치 및 악취 발생",
                    "confidence": 0.92,
                    "evidence_span": "하천 산책로 인근 쓰레기 적치로 악취가 심하고"
                },
                "result": {
                    "text": "해충 증가와 주민 불편 심화",
                    "confidence": 0.88,
                    "evidence_span": "해충이 증가했습니다. 주민 불편이 커지고 있습니다"
                },
                "request": {
                    "text": "이동식 단속 카메라 설치 검토 요청",
                    "confidence": 0.96,
                    "evidence_span": "이동식 단속 카메라 설치 검토를 요청합니다"
                },
                "context": {
                    "text": "야간 무단투기 반복 지역",
                    "confidence": 0.91,
                    "evidence_span": "야간 무단투기가 반복되며"
                },
                "entities": [
                    {"label": "LOCATION", "text": "하천 산책로", "start": 0, "end": 5},
                    {"label": "HAZARD", "text": "악취", "start": 16, "end": 18},
                    {"label": "HAZARD", "text": "해충", "start": 23, "end": 25},
                    {"label": "TIME", "text": "야간", "start": 31, "end": 33},
                    {"label": "FACILITY", "text": "단속 카메라", "start": 57, "end": 62},
                ],
                "is_valid": True,
                "schema_version": "1.0"
            }
        },
        {
            "case_id": "CASE-2026-0301-006",
            "received_at": "2026-03-20 15:20",
            "category": "도로안전",
            "region": "서초구",
            "raw_text": "지하차도 진입부 가로등 3개가 고장 나 야간 시야가 매우 어둡습니다. 비가 오면 도로 경계가 보이지 않아 사고 위험이 큽니다. 조명 복구와 안전 표지 설치를 요청합니다.",
            "assignee": "김민철",
            "priority": "급함",
            "status": "검토중",
            "structured": {
                "observation": {
                    "text": "지하차도 진입부 가로등 3개 고장",
                    "confidence": 0.93,
                    "evidence_span": "지하차도 진입부 가로등 3개가 고장 나"
                },
                "result": {
                    "text": "야간 시야 저하로 사고 위험 증가",
                    "confidence": 0.90,
                    "evidence_span": "야간 시야가 매우 어둡습니다. 사고 위험이 큽니다"
                },
                "request": {
                    "text": "조명 복구 및 안전 표지 설치 요청",
                    "confidence": 0.95,
                    "evidence_span": "조명 복구와 안전 표지 설치를 요청합니다"
                },
                "context": {
                    "text": "강우 시 시인성 급격히 악화",
                    "confidence": 0.87,
                    "evidence_span": "비가 오면 도로 경계가 보이지 않아"
                },
                "entities": [
                    {"label": "LOCATION", "text": "지하차도 진입부", "start": 0, "end": 7},
                    {"label": "FACILITY", "text": "가로등", "start": 8, "end": 10},
                    {"label": "TIME", "text": "야간", "start": 20, "end": 22},
                    {"label": "HAZARD", "text": "시야 저하", "start": 23, "end": 27},
                ],
                "is_valid": True,
                "schema_version": "1.0"
            }
        },
        {
            "case_id": "CASE-2026-0301-007",
            "received_at": "2026-03-20 11:05",
            "category": "주거복지",
            "region": "강남구",
            "raw_text": "노후 임대아파트 엘리베이터가 한 달 내 두 차례 멈춰 고령 입주민 이동이 어렵습니다. 관리사무소 긴급 점검과 예비부품 교체 계획 안내를 요청합니다.",
            "assignee": "박수환",
            "priority": "보통",
            "status": "미처리",
            "structured": {
                "observation": {
                    "text": "엘리베이터 고장 반복 발생",
                    "confidence": 0.91,
                    "evidence_span": "엘리베이터가 한 달 내 두 차례 멈춰"
                },
                "result": {
                    "text": "고령 입주민 이동 불편 심화",
                    "confidence": 0.89,
                    "evidence_span": "고령 입주민 이동이 어렵습니다"
                },
                "request": {
                    "text": "긴급 점검 및 예비부품 교체 계획 안내 요청",
                    "confidence": 0.94,
                    "evidence_span": "긴급 점검과 예비부품 교체 계획 안내를 요청합니다"
                },
                "context": {
                    "text": "노후 임대아파트 시설 안전 문제",
                    "confidence": 0.88,
                    "evidence_span": "노후 임대아파트"
                },
                "entities": [
                    {"label": "FACILITY", "text": "엘리베이터", "start": 9, "end": 14},
                    {"label": "TIME", "text": "한 달 내", "start": 16, "end": 20},
                    {"label": "HAZARD", "text": "고장", "start": 15, "end": 17},
                    {"label": "ADMIN_UNIT", "text": "관리사무소", "start": 38, "end": 43},
                ],
                "is_valid": True,
                "schema_version": "1.0"
            }
        },
    ]


def generate_mock_search_results(query: str, cases_db: List[Dict]) -> List[Dict[str, Any]]:
    """유사 민원 검색 결과 Mock Data (Tab 2)"""
    # 테스트용 검색 코퍼스 확장 + 간단한 유사도 시뮬레이션
    all_results = [
        {
            "doc_id": "DOC-2025-1024",
            "case_id": "CASE-2025-1024",
            "title": "중앙로 포트홀 긴급 복구 완료",
            "category": "도로안전",
            "region": "강남구",
            "received_at": "2025-10-15",
            "similarity_score": 0.94,
            "snippet": "...폭우 이후 배수 불량으로 발생한 포트홀에 대해 해당일 오후 긴급 아스팔트 타설 완료. 예방차원에서 해당 지점 배수로 점검 및 보수 계획 수립... [더보기]",
        },
        {
            "doc_id": "DOC-2025-0988",
            "case_id": "CASE-2025-0988",
            "title": "이륜차 전도사고 발생 (노면 불량)",
            "category": "도로안전",
            "region": "서초구",
            "received_at": "2025-09-02",
            "similarity_score": 0.89,
            "snippet": "...야간 주행 중 도로 파인 곳을 발견하지 못하고 배달 오토바이가 전도되어 운전자 경상. 현장 사진 첨부. 도로관리팀에 즉시 보수 지시... [더보기]",
        },
        {
            "doc_id": "DOC-2025-0876",
            "case_id": "CASE-2025-0876",
            "title": "도로 침하로 통행 주의",
            "category": "도로안전",
            "region": "송파구",
            "received_at": "2025-08-20",
            "similarity_score": 0.81,
            "snippet": "...선거로 도로 침하가 발생하여 차량 통행 지장 발생. 해당 구간 우회 경로 안내 및 긴급 복구... [더보기]",
        },
        {
            "doc_id": "DOC-2025-1102",
            "case_id": "CASE-2025-1102",
            "title": "상습 무단투기 구역 이동식 CCTV 운영 성과",
            "category": "환경위생",
            "region": "영등포구",
            "received_at": "2025-11-01",
            "similarity_score": 0.92,
            "snippet": "...이동식 CCTV 도입 후 무단투기 신고 건수가 62% 감소. 야간 단속 병행으로 악취 민원 동시 감소... [더보기]",
        },
        {
            "doc_id": "DOC-2025-1045",
            "case_id": "CASE-2025-1045",
            "title": "하천변 악취 민원 집중 정비 사례",
            "category": "환경위생",
            "region": "강동구",
            "received_at": "2025-10-11",
            "similarity_score": 0.86,
            "snippet": "...하천변 쓰레기 적치 구간에 대해 일괄 수거 및 방역 실시. 주 2회 순찰 체계로 악취 재발률 감소... [더보기]",
        },
        {
            "doc_id": "DOC-2025-0931",
            "case_id": "CASE-2025-0931",
            "title": "교차로 신호등 점멸 긴급 복구",
            "category": "교통행정",
            "region": "강동구",
            "received_at": "2025-09-19",
            "similarity_score": 0.91,
            "snippet": "...신호제어기 오류로 점멸 운전 발생. 3시간 내 제어기 교체 후 정상 신호 복구, 사고 예방 조치 완료... [더보기]",
        },
        {
            "doc_id": "DOC-2025-0814",
            "case_id": "CASE-2025-0814",
            "title": "지하차도 가로등 고장 야간 사고 예방 조치",
            "category": "도로안전",
            "region": "서초구",
            "received_at": "2025-08-14",
            "similarity_score": 0.87,
            "snippet": "...가로등 2개 고장으로 시야 저하 민원 접수. 임시 조명차 투입 후 영업일 2일 내 복구 완료... [더보기]",
        },
        {
            "doc_id": "DOC-2025-0720",
            "case_id": "CASE-2025-0720",
            "title": "층간소음 분쟁 중재 및 소음 측정 연계",
            "category": "주거복지",
            "region": "송파구",
            "received_at": "2025-07-20",
            "similarity_score": 0.88,
            "snippet": "...이웃사이센터와 연계해 소음 측정 및 중재 회의 진행. 야간 소음 민원 재접수율 감소... [더보기]",
        },
        {
            "doc_id": "DOC-2025-1011",
            "case_id": "CASE-2025-1011",
            "title": "노후 아파트 엘리베이터 반복 고장 대응",
            "category": "주거복지",
            "region": "강남구",
            "received_at": "2025-10-05",
            "similarity_score": 0.84,
            "snippet": "...고령층 이동권 보호를 위해 긴급 점검과 핵심 부품 선교체 시행, 입주민 안내문 즉시 배포... [더보기]",
        },
    ]

    query_tokens = [t.strip().lower() for t in re.split(r"[,\s]+", query or "") if t.strip()]
    selected_category = str(st.session_state.get("ui_filter_category", "전체"))
    selected_region = str(st.session_state.get("ui_filter_region", "전체"))

    scored_results: List[Dict[str, Any]] = []
    for item in all_results:
        if selected_category != "전체" and item.get("category") != selected_category:
            continue
        if selected_region != "전체" and item.get("region") != selected_region:
            continue

        haystack = " ".join([
            str(item.get("title", "")).lower(),
            str(item.get("snippet", "")).lower(),
            str(item.get("category", "")).lower(),
        ])
        matched = sum(1 for token in query_tokens if token and token in haystack)
        boost = min(0.08, matched * 0.02)

        result = dict(item)
        result["similarity_score"] = min(0.99, float(item.get("similarity_score", 0.0)) + boost)
        scored_results.append(result)

    if not scored_results:
        scored_results = list(all_results)

    sorted_results = sorted(scored_results, key=lambda x: x["similarity_score"], reverse=True)

    # 계약(SearchResult) 필드가 항상 존재하도록 mock 결과를 정규화
    normalized_results: List[Dict[str, Any]] = []
    for rank, item in enumerate(sorted_results, start=1):
        case_id = str(item.get("case_id", "") or "")
        received_at = item.get("received_at")
        score = float(item.get("similarity_score", 0.0) or 0.0)

        existing_metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else None
        entity_labels = item.get("entity_labels") if isinstance(item.get("entity_labels"), list) else None
        metadata = existing_metadata or {
            "created_at": received_at,
            "category": item.get("category"),
            "region": item.get("region"),
            "entity_labels": entity_labels or [],
        }

        normalized_results.append(
            {
                **item,
                "rank": int(item.get("rank", rank) or rank),
                "score": float(item.get("score", score) or score),
                "chunk_id": str(item.get("chunk_id") or (f"{case_id}__chunk-0" if case_id else "")),
                "summary": item.get("summary") if isinstance(item.get("summary"), dict) else None,
                "metadata": metadata,
                # UI 편의/호환 필드
                "created_at": item.get("created_at") or metadata.get("created_at") or received_at,
                "entity_labels": entity_labels or metadata.get("entity_labels") or [],
                "similarity_score": float(item.get("similarity_score", score) or score),
            }
        )

    return normalized_results


def search_cases_via_api(query: str, top_k: int = 5) -> tuple[List[Dict[str, Any]], str | None]:
    """현재 필터 상태를 이용해 /api/v1/search를 호출한다."""
    date_range = st.session_state.get("ui_filter_date_range")
    return search_cases_via_api_with_filters(
        query=query,
        top_k=top_k,
        date_range=date_range,
        region=st.session_state.get("ui_filter_region", "전체"),
        category=st.session_state.get("ui_filter_category", "전체"),
        entity_labels=st.session_state.get("ui_filter_entity_labels", []),
    )
def build_search_results_payload_from_session() -> List[Dict[str, Any]]:
    """현재 검색 결과를 /api/v1/qa의 search_results 포맷으로 변환한다."""
    payload: List[Dict[str, Any]] = []
    for item in st.session_state.search_results:
        payload.append(
            {
                "doc_id": item.get("doc_id"),
                "chunk_id": item.get("chunk_id", ""),
                "case_id": item.get("case_id", ""),
                "snippet": item.get("snippet", ""),
                "score": float(item.get("similarity_score", item.get("score", 0.0)) or 0.0),
            }
        )
    return payload


def run_workbench_qa(prompt: str, case: Dict[str, Any]) -> None:
    """통합 워크벤치에서 검색결과 기반 QA를 실행한다."""
    search_results_payload = build_search_results_payload_from_session()
    qa_payload = {
        "query": prompt,
        "top_k": 5,
        "use_search_results": bool(search_results_payload),
        "search_results": search_results_payload,
        "filters": {
            "region": case.get("region"),
            "category": case.get("category"),
            "entity_labels": ["FACILITY", "HAZARD"],
        },
    }

    st.session_state.chat_history.append({"role": "user", "content": prompt})

    with st.spinner("AI 어시스턴트가 답변을 생성 중입니다... (약 8~12초)"):
        start_ts = time.time()
        qa_data, qa_err = run_qa_via_api(
            query=str(qa_payload.get("query") or ""),
            top_k=int(qa_payload.get("top_k") or 5),
            use_search_results=bool(qa_payload.get("use_search_results")),
            search_results=qa_payload.get("search_results") or [],
            filters=qa_payload.get("filters") if isinstance(qa_payload.get("filters"), dict) else None,
            timeout=35.0,
        )
        elapsed = time.time() - start_ts
        if elapsed < 8.0:
            time.sleep(8.0 - elapsed)

    if qa_err and not qa_data:
        fallback_answer = (
            "서버 지연으로 샘플 초안을 표시합니다. 현장 안전조치, 원인 점검, 후속 일정 공유 순으로 대응하세요. [출처 1]"
        )
        fallback_citations = [
            {
                "ref_id": 1,
                "case_id": "CASE-2025-1024",
                "chunk_id": "CASE-2025-1024__chunk-0",
                "doc_id": "DOC-2025-1024",
                "snippet": "포트홀 긴급 복구 및 후속 배수 개선 사례",
            }
        ]
        st.session_state.chat_history.append(
            {
                "role": "assistant",
                "content": render_answer_with_citations(fallback_answer, fallback_citations),
                "citations": fallback_citations,
                "meta": {"processing_time": 8.0, "model": "fallback-sample"},
            }
        )
        st.session_state.single_call_notice = f"QA API 폴백 사용: {qa_err}"
        return

    if qa_data.get("success") is True:
        citations = qa_data.get("citations", [])
        rendered_answer = render_answer_with_citations(str(qa_data.get("answer", "")), citations)
        st.session_state.chat_history.append(
            {
                "role": "assistant",
                "content": rendered_answer,
                "citations": citations,
                "meta": qa_data.get("meta", {}),
                "limitations": qa_data.get("limitations"),
                "confidence": qa_data.get("confidence"),
                "qa_validation": qa_data.get("qa_validation"),
            }
        )
        st.session_state.single_call_notice = "통합 워크벤치에서 답변 생성이 완료되었습니다."
        return

    error_message = str(qa_err or (qa_data.get("error", {}) or {}).get("message") or "QA 응답 생성 실패")
    st.session_state.chat_history.append(
        {
            "role": "assistant",
            "content": f"<div style='background:#fee2e2; color:#991b1b; border:1px solid #fecaca; border-radius:8px; padding:12px;'>{html.escape(error_message)}</div>",
            "citations": [],
            "meta": {},
        }
    )
    st.session_state.single_call_notice = error_message


def generate_mock_hazard_statistics() -> Dict[str, Any]:
    """위험요소 통계 Mock Data (Tab 3)"""
    return {
        "total_cases": 1243,
        "cases_this_month": 287,
        "cases_this_week": 64,
        "category_stats": {
            "category": ["도로안전", "환경위생", "주거복지", "교통행정", "안전총괄"],
            "count": [342, 289, 198, 156, 108],
            "change_pct": [12.5, -3.2, 8.1, -5.4, 2.1],
        },
        "hazard_top5": [
            {"hazard": "포트홀", "count": 124, "percentage": 15.2},
            {"hazard": "무단투기/악취", "count": 98, "percentage": 12.1},
            {"hazard": "층간소음", "count": 87, "percentage": 10.7},
            {"hazard": "가로등 고장", "count": 76, "percentage": 9.3},
            {"hazard": "도로 함몰", "count": 65, "percentage": 8.0},
        ],
        "region_stats": {
            "region": ["강남구", "서초구", "송파구", "강동구", "영등포구"],
            "count": [256, 203, 198, 176, 165],
        }
    }


# ============================================================================
# 3. HELPER FUNCTIONS
# ============================================================================

def render_entity_badge() -> str:
    """엔티티 배지 렌더링"""
    return """
    <span class="badge badge-entity">LOCATION</span>
    <span class="badge badge-entity">HAZARD</span>
    <span class="badge badge-entity">TIME</span>
    """


def render_confidence_score(score: float) -> str:
    """신뢰도 점수 렌더링"""
    if score >= 0.90:
        css_class = "confidence-high"
        label = "높음"
    elif score >= 0.75:
        css_class = "confidence-medium"
        label = "중간"
    else:
        css_class = "confidence-low"
        label = "낮음"
    return f"<span class='{css_class}'>{score:.0%} ({label})</span>"


def render_citation(ref_id: int, snippet: str) -> str:
    """Citation 배지 렌더링 (hover 추가 정보)"""
    escaped_snippet = snippet.replace('"', '&quot;')
    return f'<span class="citation" title="{escaped_snippet}">[출처 {ref_id}]</span>'


def render_answer_with_citations(answer: str, citations: List[Dict[str, Any]]) -> str:
    """[[CITE:n]] 또는 [출처 n] 토큰을 시각 배지로 변환한다."""
    citation_map: Dict[int, Dict[str, Any]] = {}
    for citation in citations:
        try:
            ref_id = int(citation.get("ref_id", 0))
        except (TypeError, ValueError):
            continue
        citation_map[ref_id] = citation

    def _replace(match: re.Match[str]) -> str:
        ref_id = int(match.group(1))
        snippet = str(citation_map.get(ref_id, {}).get("snippet", "근거 스니펫 없음"))
        return render_citation(ref_id=ref_id, snippet=snippet)

    rendered = re.sub(r"\[\[CITE:(\d+)\]\]", _replace, answer or "")
    rendered = re.sub(r"\[출처\s*(\d+)\]", _replace, rendered)
    return rendered


def get_selected_case() -> Dict[str, Any] | None:
    for case in st.session_state.mock_cases:
        if case["case_id"] == st.session_state.selected_case_id:
            return case
    return None


def move_to_next_open_case(current_case_id: str) -> str | None:
    """현재 민원 다음 순서의 열린 민원(미처리/검토중)으로 이동한다."""
    open_case_ids = [
        c["case_id"]
        for c in st.session_state.mock_cases
        if st.session_state.case_statuses.get(c["case_id"], c.get("status", "미처리")) in ("미처리", "검토중")
    ]
    if not open_case_ids:
        return None

    all_case_ids = [c["case_id"] for c in st.session_state.mock_cases]
    if current_case_id not in all_case_ids:
        return open_case_ids[0]

    start_idx = all_case_ids.index(current_case_id)
    total = len(all_case_ids)
    for offset in range(1, total + 1):
        candidate = all_case_ids[(start_idx + offset) % total]
        if candidate in open_case_ids:
            return candidate

    return None


def apply_auto_filters_from_case(case: Dict[str, Any]) -> None:
    """Tab1에서 선택된 민원 정보를 Tab2 필터 상태로 동기화한다."""
    entities = case.get("structured", {}).get("entities", [])
    hazards = [e.get("text", "") for e in entities if e.get("label") == "HAZARD" and e.get("text")]
    facilities = [e.get("text", "") for e in entities if e.get("label") == "FACILITY" and e.get("text")]
    keywords = [*hazards[:2], *facilities[:1], case.get("category", "")]
    query = ", ".join([k for k in keywords if k])

    st.session_state.search_query_text = query if query else case.get("category", "")
    st.session_state.auto_filter_payload = {
        "ui_search_query": st.session_state.search_query_text,
        "ui_filter_region": get_case_region(case) if get_case_region(case) != "-" else "전체",
        "ui_filter_category": get_case_category(case) if get_case_category(case) else "전체",
        "ui_filter_date_range": (
            datetime.now() - timedelta(days=90),
            datetime.now(),
        ),
        "ui_filter_entity_labels": ["FACILITY", "HAZARD"],
    }


def build_single_call_qa_payload(case: Dict[str, Any]) -> Dict[str, Any]:
    """내부 검색 모드 /api/v1/qa payload 생성."""
    entities = case.get("structured", {}).get("entities", [])
    hazards = [e.get("text", "") for e in entities if e.get("label") == "HAZARD" and e.get("text")]
    facilities = [e.get("text", "") for e in entities if e.get("label") == "FACILITY" and e.get("text")]
    query_terms = [*hazards[:2], *facilities[:1], case.get("category", "")]
    query = " ".join([t for t in query_terms if t]).strip() or case.get("raw_text", "")[:60]

    return {
        "query": f"{query} 민원에 대한 대응 방안을 공문체로 작성해줘.",
        "top_k": 5,
        "use_search_results": False,
        "filters": {
            "region": case.get("region"),
            "category": case.get("category"),
            "entity_labels": ["FACILITY", "HAZARD"],
        },
    }


def run_single_call_qa(case: Dict[str, Any]) -> None:
    """Tab1 원클릭에서 QA를 호출하고 Tab2 챗 히스토리를 갱신한다."""
    payload = build_single_call_qa_payload(case)
    st.session_state.chat_history = []
    query_for_search = st.session_state.get("search_query_text", case.get("category", ""))
    api_results, api_err = search_cases_via_api(query=query_for_search, top_k=5)
    if api_results:
        st.session_state.search_results = api_results
    else:
        st.session_state.search_results = generate_mock_search_results(query_for_search, st.session_state.mock_cases)
        if api_err:
            st.session_state.single_call_notice = f"검색 API 폴백 사용: {api_err}"

    user_msg = {
        "role": "user",
        "content": f"{case['case_id']} 기반으로 유사 사례와 대응 방안을 작성해줘.",
    }
    st.session_state.chat_history.append(user_msg)

    delay_seconds = random.uniform(8.0, 12.0)
    with st.spinner("내부 검색 모드로 /api/v1/qa 호출 중... (약 8~12초)"):
        start_ts = time.time()
        qa_data, qa_err = run_qa_via_api(
            query=str(payload.get("query") or ""),
            top_k=int(payload.get("top_k") or 5),
            use_search_results=bool(payload.get("use_search_results")),
            search_results=payload.get("search_results") or [],
            filters=payload.get("filters") if isinstance(payload.get("filters"), dict) else None,
            timeout=35.0,
        )
        elapsed = time.time() - start_ts
        if elapsed < delay_seconds:
            time.sleep(delay_seconds - elapsed)

    if qa_err and not qa_data:
        fallback_answer = (
            "내부망 QA 서버 연결이 지연되어 샘플 대응안을 표시합니다. "
            "현장 안전조치 및 임시복구를 우선 진행하고, 후속 정비계획을 3일 이내 제출하세요. [출처 1]"
        )
        citations = [
            {
                "ref_id": 1,
                "case_id": "CASE-2025-1024",
                "chunk_id": "CASE-2025-1024__chunk-0",
                "doc_id": "DOC-2025-1024",
                "snippet": "폭우 이후 배수 불량으로 발생한 포트홀 긴급 복구 사례",
            }
        ]
        st.session_state.chat_history.append(
            {
                "role": "assistant",
                "content": render_answer_with_citations(fallback_answer, citations),
                "citations": citations,
                "meta": {"model": "fallback-sample", "processing_time": round(delay_seconds, 2)},
            }
        )
        st.session_state.single_call_notice = f"QA API 연결 실패: {qa_err}"
        return

    if qa_data.get("success") is True:
        citations = qa_data.get("citations", [])
        rendered_answer = render_answer_with_citations(str(qa_data.get("answer", "")), citations)
        st.session_state.chat_history.append(
            {
                "role": "assistant",
                "content": rendered_answer,
                "citations": citations,
                "meta": qa_data.get("meta", {}),
                "limitations": qa_data.get("limitations"),
                "confidence": qa_data.get("confidence"),
                "qa_validation": qa_data.get("qa_validation"),
            }
        )
        st.session_state.single_call_notice = "유사 사례 검색 + 대응안 생성이 완료되었습니다. 2번 탭 우측 챗 패널을 확인하세요."
        return

    error_message = str(qa_err or (qa_data.get("error", {}) or {}).get("message") or "QA 응답 생성 실패")
    st.session_state.chat_history.append(
        {
            "role": "assistant",
            "content": f"<div style='background:#fee2e2; color:#991b1b; border:1px solid #fecaca; border-radius:8px; padding:12px;'>{html.escape(error_message)}</div>",
            "citations": [],
            "meta": {},
        }
    )
    st.session_state.single_call_notice = error_message


def highlight_evidence_in_text(text: str, evidence: str) -> str:
    """원문에서 근거 부분 강조"""
    return text.replace(
        evidence,
        f"<mark style='background-color: #fef08a; font-weight:600;'>{evidence}</mark>"
    )


# ============================================================================
# 4. SESSION STATE INITIALIZATION
# ============================================================================

if "mock_cases" not in st.session_state:
    use_week2_sample = os.getenv("UI_USE_WEEK2_SAMPLE", "false").lower() == "true"
    if use_week2_sample:
        sample_cases = load_week2_structured_sample_cases()
        st.session_state.mock_cases = sample_cases if sample_cases else generate_mock_assigned_cases()
    else:
        st.session_state.mock_cases = generate_mock_assigned_cases()

if "selected_case_id" not in st.session_state:
    st.session_state.selected_case_id = st.session_state.mock_cases[0]["case_id"] if st.session_state.mock_cases else None

if "search_results" not in st.session_state:
    st.session_state.search_results = []

if "wb_search_state" not in st.session_state:
    st.session_state.wb_search_state = None

if "wb_last_api_err" not in st.session_state:
    st.session_state.wb_last_api_err = None

if "wb_pending_search" not in st.session_state:
    st.session_state.wb_pending_search = None

if "wb_query" not in st.session_state:
    st.session_state.wb_query = ""

if "wb_region" not in st.session_state:
    st.session_state.wb_region = "전체"

if "wb_category" not in st.session_state:
    st.session_state.wb_category = "전체"

if "wb_admin_unit" not in st.session_state:
    st.session_state.wb_admin_unit = "전체"

if "wb_priority_value" not in st.session_state:
    st.session_state.wb_priority_value = "전체"

if "wb_status_value" not in st.session_state:
    st.session_state.wb_status_value = "전체"

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "search_query_text" not in st.session_state:
    st.session_state.search_query_text = "포트홀, 도로 파손"

if "selected_date_range" not in st.session_state:
    st.session_state.selected_date_range = (
        datetime.now() - timedelta(days=30),
        datetime.now(),
    )

# 데모 안정성을 위해 기본값은 mock 강제(백엔드 응답 변동/계약 불일치 방어)
if "ui_force_mock" not in st.session_state:
    st.session_state.ui_force_mock = os.getenv("UI_FORCE_MOCK", "true").lower() == "true"

if "api_base_url" not in st.session_state:
    st.session_state.api_base_url = "http://localhost:8000"

if "ui_search_query" not in st.session_state:
    st.session_state.ui_search_query = st.session_state.search_query_text

if "ui_filter_region" not in st.session_state:
    st.session_state.ui_filter_region = "전체"

if "ui_filter_category" not in st.session_state:
    st.session_state.ui_filter_category = "전체"

if "ui_filter_date_range" not in st.session_state:
    st.session_state.ui_filter_date_range = (
        datetime.now() - timedelta(days=30),
        datetime.now(),
    )

if "ui_filter_entity_labels" not in st.session_state:
    st.session_state.ui_filter_entity_labels = []

if "single_call_notice" not in st.session_state:
    st.session_state.single_call_notice = ""

if "filter_synced_case_id" not in st.session_state:
    st.session_state.filter_synced_case_id = ""

if "auto_filter_payload" not in st.session_state:
    st.session_state.auto_filter_payload = None

if "wb_prompt_input" not in st.session_state:
    st.session_state.wb_prompt_input = ""

if "app_view" not in st.session_state:
    st.session_state.app_view = "queue"

if "pending_transition_toast" not in st.session_state:
    st.session_state.pending_transition_toast = ""

if "scroll_to_top_on_workbench" not in st.session_state:
    st.session_state.scroll_to_top_on_workbench = False

if "scroll_to_integrated_workbench" not in st.session_state:
    st.session_state.scroll_to_integrated_workbench = False

if "status_transition_notice" not in st.session_state:
    st.session_state.status_transition_notice = ""

if "status_transition_notice_seq" not in st.session_state:
    st.session_state.status_transition_notice_seq = 0

if "status_transition_notice_rendered_seq" not in st.session_state:
    st.session_state.status_transition_notice_rendered_seq = 0


def render_selected_case_detail_and_workbench(selected_case: Dict[str, Any]) -> None:
    """선택 민원 상세 + 통합 워크벤치(단일 화면)"""
    current_status = st.session_state.case_statuses.get(selected_case["case_id"], selected_case.get("status", "미처리"))
    header_status_class = ""
    if current_status == "처리완료":
        header_status_class = " detail-header-done"
    elif current_status == "검토중":
        header_status_class = " detail-header-review"

    status_label_map = {
        "처리완료": "처리 완료",
        "검토중": "검토중",
        "미처리": "미처리",
        "보류": "보류",
    }
    display_status = status_label_map.get(current_status, current_status)

    structured = selected_case.get("structured") if isinstance(selected_case.get("structured"), dict) else {}
    case_title = build_case_title(
        explicit_title=selected_case.get("title"),
        observation=(structured.get("observation") or {}).get("text"),
        request=(structured.get("request") or {}).get("text"),
        raw_text=selected_case.get("raw_text"),
        category=selected_case.get("category"),
    )
    case_title_esc = html.escape(case_title)
    case_id_esc = html.escape(str(selected_case.get("case_id") or "-"))

    st.markdown(
        f"""
        <div class="detail-header-animate{header_status_class}">
            <div class="detail-header-title">선택 민원: {case_title_esc} <span style="font-size:0.78rem;font-weight:800;color:#64748b;">({case_id_esc})</span></div>
            <div class="detail-header-sub">카테고리: {selected_case['category']} | 우선순위: {selected_case['priority']} | 상태: {display_status}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.single_call_notice:
        st.markdown(f"<div class='workbench-notice'>{html.escape(st.session_state.single_call_notice)}</div>", unsafe_allow_html=True)
        st.session_state.single_call_notice = ""
    structured = selected_case["structured"]
    entities = structured.get("entities", [])

    main_col, side_col = st.columns([2.2, 1], gap="large")

    with main_col:
        with st.expander("원문 텍스트", expanded=False):
            st.write(selected_case["raw_text"])

        st.markdown("### 민원 요약 (AI 분석)")
        st.caption("담당자가 빠르게 파악할 수 있도록 핵심 3개 항목만 표시합니다.")

        summary_cols = st.columns(3, gap="small")
        
        # 관찰(상황)
        with summary_cols[0]:
            with st.container(border=True):
                st.markdown("<div style='font-weight: 600; margin-bottom: 0.5rem;'>상황</div>", unsafe_allow_html=True)
                st.markdown(structured["observation"]["text"], unsafe_allow_html=False)
                st.markdown(
                    render_confidence_score(structured["observation"]["confidence"]), 
                    unsafe_allow_html=True
                )
        
        # 요청
        with summary_cols[1]:
            with st.container(border=True):
                st.markdown("<div style='font-weight: 600; margin-bottom: 0.5rem;'>민원인 요청</div>", unsafe_allow_html=True)
                st.markdown(structured["request"]["text"], unsafe_allow_html=False)
                st.markdown(
                    render_confidence_score(structured["request"]["confidence"]), 
                    unsafe_allow_html=True
                )
        
        # 원인/분석
        with summary_cols[2]:
            with st.container(border=True):
                st.markdown("<div style='font-weight: 600; margin-bottom: 0.5rem;'>문제점/원인</div>", unsafe_allow_html=True)
                st.markdown(structured["result"]["text"], unsafe_allow_html=False)
                st.markdown(
                    render_confidence_score(structured["result"]["confidence"]), 
                    unsafe_allow_html=True
                )

        # 상세 구조화 정보 (Context 포함)
        with st.expander("상세 구조화 정보 (근거/맥락)", expanded=False):
            detail_left, detail_right = st.columns(2)
            with detail_left:
                st.markdown("**상황 근거**")
                st.caption(f"\"{structured['observation']['evidence_span']}\"")
            with detail_right:
                st.markdown("**요청 근거**")
                st.caption(f"\"{structured['request']['evidence_span']}\"")
            
            st.divider()
            st.markdown("**처리 결과 근거**")
            st.caption(f"\"{structured['result']['evidence_span']}\"")
            
            st.divider()
            st.markdown("**배경/맥락**")
            with st.container(border=True):
                st.markdown(structured["context"]["text"])
                st.markdown(render_confidence_score(structured["context"]["confidence"]), unsafe_allow_html=True)
                st.caption(f"근거: \"{structured['context']['evidence_span']}\"")
            
            if not structured["is_valid"]:
                st.warning("이 구조화 결과는 스키마 검증을 통과하지 못했습니다.")

        st.markdown("<div class='workbench-action-title'>처리 액션</div>", unsafe_allow_html=True)
        action_cols = st.columns(3)
        with action_cols[0]:
            if st.button("처리완료", use_container_width=True, key=f"workbench_done_{selected_case['case_id']}"):
                st.session_state.case_statuses[selected_case["case_id"]] = "처리완료"
                _save_case_statuses_to_cache(st.session_state.case_statuses)
                next_case_id = move_to_next_open_case(selected_case["case_id"])
                if next_case_id:
                    st.session_state.selected_case_id = next_case_id
                    next_case = next((c for c in st.session_state.mock_cases if c["case_id"] == next_case_id), None)
                    if next_case:
                        apply_auto_filters_from_case(next_case)
                    st.session_state.status_transition_notice = f"다음 민원 {next_case_id}로 이동했습니다."
                else:
                    st.session_state.status_transition_notice = "다음 민원이 없습니다."
                st.session_state.status_transition_notice_seq += 1
                st.session_state.scroll_to_top_on_workbench = True
                st.session_state.scroll_to_integrated_workbench = False
                st.rerun()
            st.markdown("<div class='workbench-action-help'>현재 민원 상태를 처리 완료로 변경합니다.</div>", unsafe_allow_html=True)
        with action_cols[1]:
            if st.button("검토중", use_container_width=True, key=f"workbench_inreview_{selected_case['case_id']}"):
                st.session_state.case_statuses[selected_case["case_id"]] = "검토중"
                _save_case_statuses_to_cache(st.session_state.case_statuses)
                next_case_id = move_to_next_open_case(selected_case["case_id"])
                if next_case_id:
                    st.session_state.selected_case_id = next_case_id
                    next_case = next((c for c in st.session_state.mock_cases if c["case_id"] == next_case_id), None)
                    if next_case:
                        apply_auto_filters_from_case(next_case)
                    st.session_state.status_transition_notice = f"다음 민원 {next_case_id}로 이동했습니다."
                else:
                    st.session_state.status_transition_notice = "다음 민원이 없습니다."
                st.session_state.status_transition_notice_seq += 1
                st.session_state.scroll_to_top_on_workbench = True
                st.session_state.scroll_to_integrated_workbench = False
                st.rerun()
            st.markdown("<div class='workbench-action-help'>내부 검토 단계로 상태를 변경해 큐 우선순위를 조정합니다.</div>", unsafe_allow_html=True)
        with action_cols[2]:
            if st.button("AI 유사 사례 및 대응 방안 생성", use_container_width=True, type="primary", key=f"workbench_single_call_{selected_case['case_id']}"):
                apply_auto_filters_from_case(selected_case)
                run_single_call_qa(selected_case)
                st.rerun()
            st.markdown("<div class='workbench-action-help'>유사 사례 검색과 답변 초안을 한 번에 실행합니다.</div>", unsafe_allow_html=True)

    with side_col:
        st.markdown("<div class='workbench-side-title'>보조 정보</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='workbench-side-meta'>민원 ID: {selected_case['case_id']}<br>지역: {get_case_region(selected_case)}<br>담당: {selected_case.get('assignee', '-')}</div>",
            unsafe_allow_html=True,
        )

        with st.expander("핵심 엔티티", expanded=False):
            if entities:
                for entity in entities:
                    st.markdown(
                        f"<span class='workbench-entity-pill'>{entity.get('label', '-')}: {entity.get('text', '-')}</span>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("추출된 엔티티가 없습니다.")

        with st.expander("추출/검증 정보", expanded=False):
            if structured["is_valid"]:
                st.markdown('<span class="badge badge-valid">✓ 스키마 검증 통과</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge badge-invalid">✗ 스키마 검증 실패</span>', unsafe_allow_html=True)
            st.caption(f"Schema v{structured['schema_version']}")

        if (
            st.session_state.status_transition_notice
            and st.session_state.status_transition_notice_seq > st.session_state.status_transition_notice_rendered_seq
        ):
            st.markdown(
                f"<div class='transition-inline-notice' data-seq='{st.session_state.status_transition_notice_seq}'>{html.escape(st.session_state.status_transition_notice)}</div>",
                unsafe_allow_html=True,
            )
            st.session_state.status_transition_notice_rendered_seq = st.session_state.status_transition_notice_seq

    st.divider()
    st.markdown("<div id='integrated-workbench-anchor'></div>", unsafe_allow_html=True)
    if st.session_state.scroll_to_integrated_workbench:
        components.html(
            """
            <script>
                const target = window.parent.document.getElementById('integrated-workbench-anchor');
                if (target) {
                    target.scrollIntoView({behavior: 'instant', block: 'start'});
                }
            </script>
            """,
            height=0,
            width=0,
        )
        st.session_state.scroll_to_integrated_workbench = False

    st.markdown("### 통합 민원 처리 워크벤치")
    st.caption("선택 민원의 검색/답변 작성 도구를 한 화면에서 실행합니다.")

    wb_entities = selected_case.get("structured", {}).get("entities", [])
    wb_hazards = [e.get("text", "") for e in wb_entities if e.get("label") == "HAZARD" and e.get("text")]
    wb_facilities = [e.get("text", "") for e in wb_entities if e.get("label") == "FACILITY" and e.get("text")]
    default_wb_query = ", ".join([*wb_hazards[:2], *wb_facilities[:1], selected_case.get("category", "")]).strip(", ")

    if st.session_state.get("wb_selected_case_id") != selected_case["case_id"]:
        st.session_state.wb_selected_case_id = selected_case["case_id"]
        st.session_state.wb_query = default_wb_query or selected_case.get("category", "")

    region_options = build_region_options(st.session_state.mock_cases)
    category_options = build_category_options(st.session_state.mock_cases)

    default_region = get_case_region(selected_case)
    default_category = get_case_category(selected_case)
    if st.session_state.wb_region not in region_options:
        st.session_state.wb_region = default_region if default_region in region_options else region_options[0]
    if st.session_state.wb_category not in category_options:
        st.session_state.wb_category = default_category if default_category in category_options else category_options[0]

    test_cols = st.columns([1, 6])
    with test_cols[0]:
        if st.button("오류 테스트", key=f"wb_error_test_{selected_case['case_id']}"):
            st.session_state.wb_search_state = "error_fallback"
            st.session_state.wb_last_api_err = "검색 서버에 일시적인 장애가 발생했습니다. 관리자에게 문의하세요."
            st.session_state.wb_pending_search = None
            st.session_state.search_results = []
            st.rerun()

    with st.container():
        query, region, category, is_search_clicked = render_search_filter(
            default_query=st.session_state.wb_query,
            default_region=st.session_state.wb_region,
            default_category=st.session_state.wb_category,
            region_options=region_options,
            category_options=category_options,
        )

        # 상태 머신: 클릭 -> loading 세팅 -> rerun -> (loading 상태에서 실제 호출)
        if is_search_clicked:
            st.session_state.wb_search_state = "loading"
            st.session_state.wb_last_api_err = None
            st.session_state.search_results = []
            st.session_state.wb_pending_search = {
                "query": query,
                "region": region,
                "category": category,
                "date_range": st.session_state.ui_filter_date_range,
                "entity_labels": ["FACILITY", "HAZARD"],
                "top_k": 5,
            }
            st.rerun()

        if st.session_state.wb_search_state == "loading" and st.session_state.wb_pending_search:
            pending = dict(st.session_state.wb_pending_search)
            with st.spinner("유사 민원 및 지식 베이스를 검색 중입니다..."):
                api_results, api_err = search_cases_via_api_with_filters(
                    query=str(pending.get("query", "")),
                    top_k=int(pending.get("top_k", 5)),
                    date_range=pending.get("date_range"),
                    region=str(pending.get("region", "전체")),
                    category=str(pending.get("category", "전체")),
                    entity_labels=list(pending.get("entity_labels", [])),
                )

            st.session_state.wb_pending_search = None
            st.session_state.wb_last_api_err = api_err
            if api_err and not api_results:
                api_err_text = str(api_err)
                if st.session_state.ui_force_mock or "UI_FORCE_MOCK" in api_err_text:
                    st.session_state.wb_search_state = "mock_mode"
                else:
                    st.session_state.wb_search_state = "error_fallback"
                st.session_state.search_results = generate_mock_search_results(str(pending.get("query", "")), st.session_state.mock_cases)
            elif api_results is not None and len(api_results) == 0:
                st.session_state.wb_search_state = "empty"
                st.session_state.search_results = []
            else:
                st.session_state.wb_search_state = "success"
                st.session_state.search_results = api_results or []
            st.rerun()

    with st.container(border=True):
        result_count = len(st.session_state.search_results)
        st.markdown(f"<div class='workbench-panel-title'>유사 사례 검색 결과 ({result_count}건)</div>", unsafe_allow_html=True)
        st.caption("워크벤치 검색 필터를 실행하면 아래에 유사 사례가 표시됩니다.")
        banner_state = st.session_state.wb_search_state
        banner_err = st.session_state.wb_last_api_err
        if (banner_state or "").strip().lower() in ("error_fallback", "error") and banner_err:
            banner_err = f"{banner_err} (Mock 데이터를 표시합니다.)"

        render_standard_status_banner(
            state=banner_state,
            result_count=result_count,
            error_message=banner_err,
            idle_message="검색 조건을 입력한 뒤 ‘워크벤치 검색’을 실행하세요.",
            loading_message="검색 요청을 처리 중입니다...",
            empty_message="조건에 맞는 유사 민원이 없습니다. 검색어나 필터를 변경해 보세요.",
            success_message=(
                f"총 {result_count}건의 유사 사례를 찾았습니다." if (banner_state == "success") else None
            ),
            mock_message="Mock 모드(UI_FORCE_MOCK)로 샘플 데이터를 표시합니다.",
        )

        if st.session_state.search_results:
            for idx, item in enumerate(st.session_state.search_results[:5], start=1):
                render_search_result_card(idx, item)
        else:
            if st.session_state.wb_search_state is None:
                st.info("검색 버튼을 눌러 유사 사례를 불러오세요.")

    st.divider()

    with st.container(border=True):
        st.markdown("<div class='workbench-panel-title'>AI 어시스턴트</div>", unsafe_allow_html=True)
        st.caption("유사 사례 검색과 별개로, 선택 민원 기준 지시사항을 입력해 답변 초안을 생성합니다.")

        quick_cols = st.columns(4)
        with quick_cols[0]:
            if st.button("답변 초안", key=f"wb_quick_reply_{selected_case['case_id']}", use_container_width=True):
                st.session_state.wb_prompt_input = "선택 민원을 기준으로 민원인 안내용 답변 초안을 작성해줘."
                st.rerun()
        with quick_cols[1]:
            if st.button("부서 전달", key=f"wb_quick_dept_{selected_case['case_id']}", use_container_width=True):
                st.session_state.wb_prompt_input = "선택 민원을 기준으로 유관부서 전달문을 작성해줘."
                st.rerun()
        with quick_cols[2]:
            if st.button("일정 요약", key=f"wb_quick_plan_{selected_case['case_id']}", use_container_width=True):
                st.session_state.wb_prompt_input = "선택 민원의 처리 일정과 조치 항목을 3줄로 요약해줘."
                st.rerun()
        with quick_cols[3]:
            if st.button("대화 초기화", key=f"wb_quick_clear_{selected_case['case_id']}", use_container_width=True):
                st.session_state.chat_history = []
                st.session_state.single_call_notice = "워크벤치 대화를 초기화했습니다."
                st.rerun()

        st.markdown("<div class='queue-filter-label'>지시사항</div>", unsafe_allow_html=True)
        st.text_area(
            "지시사항",
            key="wb_prompt_input",
            height=90,
            placeholder="예: 선택 민원을 기준으로 담당부서 전달문과 민원인 안내문을 작성해줘.",
            label_visibility="collapsed",
        )

        if st.button("워크벤치 답변 생성", use_container_width=True, type="primary", key=f"workbench_qa_{selected_case['case_id']}"):
            prompt = st.session_state.wb_prompt_input.strip()
            if not prompt:
                st.warning("지시사항을 입력해주세요.")
            else:
                run_workbench_qa(prompt=prompt, case=selected_case)
                st.rerun()

        for message in st.session_state.chat_history[-8:]:
            if message.get("role") == "user":
                st.markdown(f"<div class='chat-message-user'>{message.get('content', '')}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='chat-message-assistant'>{message.get('content', '')}</div>", unsafe_allow_html=True)
                qa_validation = message.get("qa_validation")
                if isinstance(qa_validation, dict) and qa_validation.get("is_valid") is False:
                    st.warning("QA 응답 검증에서 문제가 감지되었습니다. (qa_validation.is_valid=false)")
                citations = message.get("citations", [])
                render_citations_block(citations if isinstance(citations, list) else [], expanded=False)

                limitations = message.get("limitations")
                has_limitations = bool(str(limitations).strip()) if isinstance(limitations, str) else bool(limitations)
                render_limitations_block(limitations, expanded=has_limitations)

                meta = message.get("meta", {})
                if isinstance(meta, dict) and meta.get("validation_warning"):
                    st.caption(str(meta.get("validation_warning")))


def render_queue_entry_screen() -> None:
    """민원 선택 전용 화면"""
    open_case_param = st.query_params.get("open_case")
    if open_case_param:
        open_case_id = open_case_param[0] if isinstance(open_case_param, list) else str(open_case_param)
        selected_case = next((c for c in st.session_state.mock_cases if c["case_id"] == open_case_id), None)
        if selected_case:
            st.session_state.selected_case_id = open_case_id
            apply_auto_filters_from_case(selected_case)
            st.session_state.scroll_to_top_on_workbench = True
            st.session_state.scroll_to_integrated_workbench = False
            st.session_state.app_view = "workbench"
        if "open_case" in st.query_params:
            del st.query_params["open_case"]
        st.rerun()

    st.markdown("## 처리 대상 민원 선택")
    st.caption("민원 목록에서 항목을 클릭하면 현재 화면에서 바로 워크벤치로 전환됩니다.")

    def _shorten_for_display(value: Any, max_len: int) -> str:
        text = "" if value is None else str(value)
        if max_len <= 0:
            return ""
        if len(text) <= max_len:
            return text
        if max_len == 1:
            return "…"
        return text[: max_len - 1] + "…"

    open_count = sum(1 for c in st.session_state.mock_cases if st.session_state.case_statuses.get(c["case_id"], "미처리") in ("미처리", "검토중"))
    urgent_count = sum(1 for c in st.session_state.mock_cases if c.get("priority") == "매우급함" and st.session_state.case_statuses.get(c["case_id"], "미처리") in ("미처리", "검토중"))
    done_count = sum(1 for c in st.session_state.mock_cases if st.session_state.case_statuses.get(c["case_id"], "미처리") == "처리완료")

    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(
            f"""
            <div class="queue-kpi-card queue-kpi-open">
                <div class="queue-kpi-label">열린 건</div>
                <div class="queue-kpi-value">{open_count}건</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"""
            <div class="queue-kpi-card queue-kpi-urgent">
                <div class="queue-kpi-label">매우급함</div>
                <div class="queue-kpi-value">{urgent_count}건</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"""
            <div class="queue-kpi-card queue-kpi-done">
                <div class="queue-kpi-label">오늘 완료</div>
                <div class="queue-kpi-value">{done_count}건</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    def _reset_queue_filters() -> None:
        st.session_state.queue_priority_value = "전체"
        st.session_state.queue_status_value = "전체"
        st.session_state.queue_sort_by = "우선순위"
        st.session_state.queue_keyword = ""

    with st.container(border=True):
        st.markdown("<div class='queue-filter-title'>빠른 필터</div>", unsafe_allow_html=True)

        r1c1, r1c2, r1c3 = st.columns([1, 1, 1])
        with r1c1:
            st.markdown("<div class='queue-filter-label'>우선순위</div>", unsafe_allow_html=True)
            priority_value = st.selectbox(
                "우선순위",
                ["전체", "매우급함", "급함", "보통"],
                key="queue_priority_value",
                label_visibility="collapsed",
            )
        with r1c2:
            st.markdown("<div class='queue-filter-label'>상태</div>", unsafe_allow_html=True)
            status_value = st.selectbox(
                "상태",
                ["전체", "미처리", "검토중", "보류", "처리완료"],
                key="queue_status_value",
                label_visibility="collapsed",
            )
        with r1c3:
            st.markdown("<div class='queue-filter-label'>정렬</div>", unsafe_allow_html=True)
            st.selectbox(
                "정렬",
                ["우선순위", "최신 접수"],
                key="queue_sort_by",
                label_visibility="collapsed",
            )

        r2c1, r2c2 = st.columns([4.2, 1])
        with r2c1:
            st.markdown("<div class='queue-filter-label'>빠른 검색</div>", unsafe_allow_html=True)
            st.text_input(
                "빠른 검색",
                key="queue_keyword",
                placeholder="case_id, 카테고리, 담당자, 지역",
                label_visibility="collapsed",
            )
        with r2c2:
            st.markdown("<div class='queue-filter-label'>도구</div>", unsafe_allow_html=True)
            st.button("초기화", key="queue_reset_filters_top", use_container_width=True, on_click=_reset_queue_filters)

    priority_rank = {"매우급함": 0, "급함": 1, "보통": 2}
    queue_rows: List[Dict[str, Any]] = []
    filtered_cases: List[Dict[str, Any]] = []
    for case in st.session_state.mock_cases:
        status = st.session_state.case_statuses.get(case["case_id"], case.get("status", "미처리"))
        if priority_value != "전체" and case.get("priority") != priority_value:
            continue
        if status_value != "전체" and status != status_value:
            continue

        keyword = st.session_state.queue_keyword.strip().lower()
        if keyword:
            haystack = " ".join([
                case.get("case_id", ""),
                case.get("category", ""),
                case.get("assignee", ""),
                case.get("region", ""),
            ]).lower()
            if keyword not in haystack:
                continue

        filtered_cases.append(case)
        title_text = build_case_title(
            explicit_title=case.get("title"),
            observation=(case.get("structured", {}).get("observation", {}) or {}).get("text"),
            request=(case.get("structured", {}).get("request", {}) or {}).get("text"),
            raw_text=case.get("raw_text", ""),
            category=get_case_category(case),
        )
        queue_rows.append(
            {
                "제목": title_text,
                "case_id": case["case_id"],
                "접수": case.get("received_at", "-"),
                "카테고리": get_case_category(case),
                "지역": get_case_region(case),
                "우선순위": case.get("priority", "보통"),
                "담당": case.get("assignee", "-") ,
                "상태": status,
            }
        )

    if st.session_state.queue_sort_by == "우선순위":
        queue_rows.sort(key=lambda x: (priority_rank.get(x.get("우선순위", "보통"), 9), x.get("접수", "")), reverse=False)
    else:
        queue_rows.sort(key=lambda x: x.get("접수", ""), reverse=True)

    if queue_rows:
        case_ids = [row["case_id"] for row in queue_rows]
        if st.session_state.selected_case_id not in case_ids:
            st.session_state.selected_case_id = case_ids[0]

        st.markdown(f"#### 민원 목록 ({len(queue_rows)}건)")
        priority_badge = {"매우급함": "매우급함", "급함": "급함", "보통": "보통"}
        status_badge = {
            "미처리": "미처리",
            "검토중": "검토중",
            "보류": "보류",
            "처리완료": "처리완료",
        }

        header_cols = st.columns([1.3, 0.7, 1.1, 0.9, 0.9, 1.1, 1.0], gap="small")
        header_labels = ["민원 제목", "케이스ID", "접수일", "카테고리", "지역", "우선순위", "상태"]
        for col, label in zip(header_cols, header_labels):
            with col:
                st.markdown(f"<div class='queue-filter-label'>{label}</div>", unsafe_allow_html=True)

        for idx, row in enumerate(queue_rows):
            row_cols = st.columns([1.3, 0.7, 1.1, 0.9, 0.9, 1.1, 1.0], gap="small")
            with row_cols[0]:
                full_title = str(row.get("제목", ""))
                display_title = _shorten_for_display(full_title, 34)
                st.markdown(
                    f"<a class='queue-title-link' href='?open_case={row['case_id']}' target='_self' title='{html.escape(full_title)}'>{html.escape(display_title)}</a>",
                    unsafe_allow_html=True,
                )
            with row_cols[1]:
                full_case_id = str(row.get("case_id", ""))
                display_case_id = _shorten_for_display(full_case_id, 16)
                st.markdown(
                    f"<div style='font-size:0.75rem;line-height:1.0;color:#94a3b8;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' title='{html.escape(full_case_id)}'>{html.escape(display_case_id)}</div>",
                    unsafe_allow_html=True,
                )
            with row_cols[2]:
                st.markdown(f"<div style='font-size:0.85rem;line-height:1.15;color:#475569;'>{row['접수']}</div>", unsafe_allow_html=True)
            with row_cols[3]:
                st.markdown(f"<div style='font-size:0.85rem;line-height:1.15;color:#475569;'>{row['카테고리']}</div>", unsafe_allow_html=True)
            with row_cols[4]:
                st.markdown(f"<div style='font-size:0.85rem;line-height:1.15;color:#475569;'>{row['지역']}</div>", unsafe_allow_html=True)
            with row_cols[5]:
                st.markdown(f"<div style='font-size:0.85rem;line-height:1.15;color:#475569;'>{priority_badge.get(row['우선순위'], row['우선순위'])}</div>", unsafe_allow_html=True)
            with row_cols[6]:
                st.markdown(f"<div style='font-size:0.85rem;line-height:1.15;color:#475569;'>{status_badge.get(row['상태'], row['상태'])}</div>", unsafe_allow_html=True)
            if idx < len(queue_rows) - 1:
                st.markdown(
                    "<div style='height:1px;background:#e2e8f0;margin:2px 0 3px 0;'></div>",
                    unsafe_allow_html=True,
                )
    else:
        st.warning("필터 조건에 맞는 민원이 없습니다.")


def render_case_workbench_screen() -> None:
    """선택 민원 전용 처리 화면"""
    # Workbench-only: screenshot-like layout (queue/admin views remain unchanged)
    open_case_id = _qp_first("open_case")
    if open_case_id:
        sel_case = next((c for c in st.session_state.mock_cases if c.get("case_id") == open_case_id), None)
        if sel_case:
            st.session_state.selected_case_id = open_case_id
            apply_auto_filters_from_case(sel_case)

    selected_case = get_selected_case()
    if not selected_case:
        st.warning("선택된 민원이 없습니다. 목록 화면으로 이동합니다.")
        st.session_state.app_view = "queue"
        st.rerun()
        return

    # Query-param driven actions (HTML buttons)
    wb_action = _qp_first("wb_action")
    wb_mark = _qp_first("wb_mark")
    if wb_mark in ("done", "review"):
        if wb_mark == "done":
            st.session_state.case_statuses[selected_case["case_id"]] = "처리완료"
        else:
            st.session_state.case_statuses[selected_case["case_id"]] = "검토중"
        _save_case_statuses_to_cache(st.session_state.case_statuses)

        display_cases = list(st.session_state.mock_cases)
        display_cases = filter_cases_by_admin_unit(display_cases, str(st.session_state.get("wb_admin_unit", "전체")))
        display_cases = filter_cases_by_priority(display_cases, str(st.session_state.get("wb_priority_value", "전체")))
        display_cases = filter_cases_by_status(display_cases, st.session_state.case_statuses, str(st.session_state.get("wb_status_value", "전체")))
        display_cases = list(display_cases[:7])
        ordered_ids = [str(c.get("case_id")) for c in display_cases if c.get("case_id")]

        current_id = str(selected_case.get("case_id") or "")
        next_case_id = current_id
        if ordered_ids:
            if current_id in ordered_ids:
                next_case_id = ordered_ids[(ordered_ids.index(current_id) + 1) % len(ordered_ids)]
            else:
                next_case_id = ordered_ids[0]

        if next_case_id:
            st.session_state.selected_case_id = next_case_id
            st.query_params["open_case"] = next_case_id
            next_case = next((c for c in st.session_state.mock_cases if c.get("case_id") == next_case_id), None)
            if next_case:
                apply_auto_filters_from_case(next_case)

        _consume_qp("wb_mark")
        st.rerun()

    if wb_action == "similar":
        from app.ui.services.search_service import search_similar_cases_for_workbench

        rows, _err = search_similar_cases_for_workbench(query=selected_case.get("raw_text", ""), top_k=5)
        st.session_state.wb_similar_rows = rows
        _consume_qp("wb_action")
        st.rerun()

    if wb_action == "refresh":
        _clear_case_status_cache_file()
        try:
            for case in st.session_state.mock_cases:
                case_id = str(case.get("case_id") or "")
                if case_id:
                    st.session_state.case_statuses[case_id] = "미처리"
        except Exception:
            st.session_state.case_statuses = {str(c.get("case_id")): "미처리" for c in st.session_state.mock_cases if c.get("case_id")}
        _save_case_statuses_to_cache(st.session_state.case_statuses)
        _consume_qp("wb_action")
        st.rerun()

    if wb_action == "draft":
        st.session_state.wb_draft_text = "".join(
            [
                "안녕하세요. 문의 주신 내용 확인했습니다.\n",
                "현장 확인 후 조치 예정이며, 진행 상황은 추가로 안내드리겠습니다.\n",
                "감사합니다.",
            ]
        )
        _consume_qp("wb_action")
        st.rerun()

    st.markdown(
        """
        <div class="wb-topnav">
            <a href="?view=queue" target="_self" onclick="window.location.assign('?view=queue'); return false;">민원 목록으로</a>
            <a href="?view=admin" target="_self" onclick="window.location.assign('?view=admin'); return false;">관리자 통계</a>
            <div class="wb-topnav-spacer"></div>
        </div>
        <div class="wb-topline"></div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([1, 1], gap="small")

    # ----------------------------
    # LEFT: 민원 목록 (7개)
    # ----------------------------
    with col1:
        current_case_id = html.escape(str(selected_case.get("case_id", "")))

        def _reset_wb_queue_filters() -> None:
            st.session_state.wb_admin_unit = "전체"
            st.session_state.wb_priority_value = "전체"
            st.session_state.wb_status_value = "전체"

        filter_row = st.columns([1.2, 1.0, 1.0, 0.7])
        with filter_row[0]:
            admin_unit_options = build_admin_unit_options(list(st.session_state.mock_cases))
            if st.session_state.wb_admin_unit not in admin_unit_options:
                st.session_state.wb_admin_unit = "전체"
            st.selectbox(
                "부서",
                options=admin_unit_options,
                index=_safe_index(admin_unit_options, st.session_state.wb_admin_unit, default=0),
                key="wb_admin_unit",
            )
        with filter_row[1]:
            priority_options = ["전체", "매우급함", "급함", "보통"]
            if st.session_state.wb_priority_value not in priority_options:
                st.session_state.wb_priority_value = "전체"
            st.selectbox(
                "우선순위",
                options=priority_options,
                index=_safe_index(priority_options, st.session_state.wb_priority_value, default=0),
                key="wb_priority_value",
            )
        with filter_row[2]:
            status_options = ["전체", "미처리", "검토중", "보류", "처리완료"]
            if st.session_state.wb_status_value not in status_options:
                st.session_state.wb_status_value = "전체"
            st.selectbox(
                "상태",
                options=status_options,
                index=_safe_index(status_options, st.session_state.wb_status_value, default=0),
                key="wb_status_value",
            )

        with filter_row[3]:
            st.markdown("<div style='height: 1.75rem'></div>", unsafe_allow_html=True)
            st.button("초기화", key="wb_reset_filters", use_container_width=True, on_click=_reset_wb_queue_filters)

        def _title_for_case(case: Dict[str, Any]) -> str:
            return build_case_title(
                explicit_title=case.get("title"),
                observation=(case.get("structured", {}).get("observation", {}) or {}).get("text"),
                request=(case.get("structured", {}).get("request", {}) or {}).get("text"),
                raw_text=case.get("raw_text", ""),
                category=case.get("category"),
            )

        def _priority_for_case(case: Dict[str, Any]) -> str:
            return str(case.get("priority") or "보통")

        def _status_kr_for_case(case: Dict[str, Any]) -> str:
            status_kr = st.session_state.case_statuses.get(case.get("case_id", ""), case.get("status", "미처리"))
            status_kr = str(status_kr or "").strip() or "미처리"
            if status_kr in ("미처리", "검토중", "처리완료"):
                return status_kr
            return "미처리"

        list_cases_all = list(st.session_state.mock_cases)
        list_cases_all = filter_cases_by_admin_unit(list_cases_all, str(st.session_state.get("wb_admin_unit", "전체")))
        list_cases_all = filter_cases_by_priority(list_cases_all, str(st.session_state.get("wb_priority_value", "전체")))
        list_cases_all = filter_cases_by_status(list_cases_all, st.session_state.case_statuses, str(st.session_state.get("wb_status_value", "전체")))
        list_cases = list(list_cases_all[:7])

        rows_html: list[str] = []
        for case in list_cases:
            cid = str(case.get("case_id", "-"))
            is_active = str(selected_case.get("case_id", "")) == cid
            tr_class_attr = " class='wb-row-active'" if is_active else ""
            title = html.escape(_title_for_case(case))
            received = html.escape(str(case.get("received_at", "-")))
            priority = html.escape(_priority_for_case(case))
            status_kr = _status_kr_for_case(case)
            if status_kr == "처리완료":
                badge = "<span class='status-badge status-completed'>처리완료</span>"
            elif status_kr == "검토중":
                badge = "<span class='status-badge status-pending'>검토중</span>"
            else:
                badge = "<span class='status-badge status-urgent'>미처리</span>"
            rows_html.append(
                (
                    f"<tr{tr_class_attr}>"
                    f"<td><a href='?view=workbench&open_case={html.escape(cid)}' target='_self' "
                    f"onclick=\"window.location.assign('?view=workbench&open_case={html.escape(cid)}'); return false;\" "
                    f"title='{title}'>{title}</a></td>"
                    f"<td>{received}</td>"
                    f"<td>{priority}</td>"
                    f"<td>{badge}</td>"
                    "</tr>"
                )
            )

        table_html = (
            "<div class='wb-empty'>표시할 민원이 없습니다.</div>"
            if not rows_html
            else "<table class='wb-table wb-table-queue'>"
            "<thead><tr><th>제목</th><th>접수일</th><th>우선순위</th><th>상태</th></tr></thead>"
            f"<tbody>{''.join(rows_html)}</tbody>"
            "</table>"
        )

        left_panel_html = (
            "<div class='wb-panel'>"
            "<div class='wb-section-title'>"
            "<div class='title'>민원 목록</div>"
            f"<a class='wb-mini-btn' href='?view=workbench&wb_action=refresh&open_case={current_case_id}' "
            f"target='_self' onclick=\"window.location.assign('?view=workbench&wb_action=refresh&open_case={current_case_id}'); return false;\">갱신</a>"
            "</div>"
            f"{table_html}"
            "</div>"
        )
        st.markdown(left_panel_html, unsafe_allow_html=True)

    # ----------------------------
    # RIGHT: 상세/처리
    # ----------------------------
    with col2:
        raw_text = selected_case.get("raw_text") or "[상수도사업본부] 안녕하세요..."
        raw_html = (
            "<div class='wb-card'>"
            "<details class='wb-details'>"
            "<summary>"
            "<div class='wb-details-summary'>"
            "<div class='wb-card-title'>원문 텍스트</div>"
            "<div class='wb-details-caret'>▾</div>"
            "</div>"
            "</summary>"
            f"<div class='wb-textbox wb-textbox-scroll'>{html.escape(str(raw_text))}</div>"
            "</details>"
            "</div>"
        )
        st.markdown(raw_html, unsafe_allow_html=True)

        observation = str(selected_case.get("structured", {}).get("observation", {}).get("text") or "-")
        problem = str(selected_case.get("structured", {}).get("result", {}).get("text") or "-")
        request = str(selected_case.get("structured", {}).get("request", {}).get("text") or "-")
        st.markdown(
            """
            <div class="wb-card">
                <div class="wb-card-header">
                    <div class="wb-card-title">민원 요약 (AI 분석)</div>
                        <div class="wb-conf-badge">신뢰도: 98.4%</div>
                </div>
                <table class="wb-table" style="border:none;table-layout:fixed;">
                    <colgroup>
                        <col style="width: 33%;" />
                        <col style="width: 20%;" />
                        <col style="width: 47%;" />
                    </colgroup>
                    <thead><tr>
                            <th style="border-top:1px solid #cbd5e1;">관찰</th>
                            <th style="border-top:1px solid #cbd5e1;">결과</th>
                            <th style="border-top:1px solid #cbd5e1;">요청</th>
                    </tr></thead>
                    <tbody><tr>
                        <td>{obs}</td>
                        <td>{prob}</td>
                        <td>{req}</td>
                    </tr></tbody>
                </table>
            </div>
            """.format(obs=html.escape(observation), prob=html.escape(problem), req=html.escape(request)),
            unsafe_allow_html=True,
        )

        from app.ui.components.search_ui import render_similar_cases_collapsible

        cid = html.escape(str(selected_case.get("case_id", "")))
        similar_rows = st.session_state.get("wb_similar_rows")
        table_html = ""
        if isinstance(similar_rows, list) and similar_rows:
            table_html = render_similar_cases_collapsible(similar_rows, return_html=True) or ""

        similar_card_html = (
            "<div class='wb-card'>"
            "<div class='wb-card-header'>"
            "<div class='wb-card-title'>유사 민원 검색</div>"
            f"<a class='wb-mini-btn' href='?view=workbench&wb_action=similar&open_case={cid}' target='_self' "
            f"onclick=\"window.location.assign('?view=workbench&wb_action=similar&open_case={cid}'); return false;\">유사민원검색</a>"
            "</div>"
            f"{table_html}"
            "</div>"
        )
        st.markdown(similar_card_html, unsafe_allow_html=True)

        st.markdown(
            f"""
            <div class="wb-card">
                <div class="wb-card-header">
                    <div class="wb-card-title">답변 초안 및 비교</div>
                    <a class="wb-mini-btn" href="?view=workbench&wb_action=draft&open_case={cid}" target="_self" onclick="window.location.assign('?view=workbench&wb_action=draft&open_case={cid}'); return false;">초안</a>
                </div>
            """,
            unsafe_allow_html=True,
        )

        if "wb_draft_text" not in st.session_state:
            st.session_state.wb_draft_text = ""

        st.text_area(
            "답변 초안 및 비교",
            key="wb_draft_text",
            height=240,
            placeholder="여기에 내용을 입력하거나 AI가 생성한 초안을 편집하세요...",
            label_visibility="collapsed",
        )

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(
            f"""
            <div class="wb-actions">
                <a class="wb-action-btn wb-action-done" href="?view=workbench&wb_mark=done&open_case={cid}" target="_self" onclick="window.location.assign('?view=workbench&wb_mark=done&open_case={cid}'); return false;">처리완료</a>
                <a class="wb-action-btn wb-action-review" href="?view=workbench&wb_mark=review&open_case={cid}" target="_self" onclick="window.location.assign('?view=workbench&wb_mark=review&open_case={cid}'); return false;">검토중</a>
            </div>
            """,
            unsafe_allow_html=True,
        )

if "case_statuses" not in st.session_state:
    default_statuses = {case["case_id"]: case.get("status", "미처리") for case in st.session_state.mock_cases}
    st.session_state.case_statuses = _load_case_statuses_from_cache(default_statuses)

if "queue_priority_filter" not in st.session_state:
    st.session_state.queue_priority_filter = ["매우급함", "급함", "보통"]

if "queue_status_filter" not in st.session_state:
    st.session_state.queue_status_filter = ["미처리", "검토중"]

if "queue_sort_by" not in st.session_state:
    st.session_state.queue_sort_by = "우선순위"

if "queue_keyword" not in st.session_state:
    st.session_state.queue_keyword = ""

if "queue_priority_value" not in st.session_state:
    st.session_state.queue_priority_value = "전체"

if "queue_status_value" not in st.session_state:
    st.session_state.queue_status_value = "전체"


# ============================================================================
# 5. TAB 1: 할당된 민원 및 자동 구조화
# ============================================================================

def render_tab1_assigned_cases():
    """
    Tab 1: 담당자가 자신에게 할당된 신규 민원을 확인하고
           AI 구조화 결과를 검토하는 화면
    """
    st.markdown("## 할당된 민원 및 자동 구조화")
    st.markdown("오늘 처리해야 할 신규 기일 민원을 확인하고, AI가 분석한 구조화 결과를 검토합니다.")
    st.caption("처리 순서: 1) 왼쪽 큐에서 민원 선택  2) 오른쪽에서 구조화 확인  3) 하단 워크벤치에서 검색/답변 생성")

    col_left, col_right = st.columns([1.1, 1.3], gap="large")

    # 좌측: 민원 목록
    with col_left:
        st.markdown("### 신규 대기 민원 큐")
        m1, m2, m3 = st.columns(3)
        open_count = sum(1 for c in st.session_state.mock_cases if st.session_state.case_statuses.get(c["case_id"], "미처리") in ("미처리", "검토중"))
        urgent_count = sum(1 for c in st.session_state.mock_cases if c.get("priority") == "매우급함" and st.session_state.case_statuses.get(c["case_id"], "미처리") in ("미처리", "검토중"))
        done_count = sum(1 for c in st.session_state.mock_cases if st.session_state.case_statuses.get(c["case_id"], "미처리") == "처리완료")
        m1.metric("열린 건", f"{open_count}건")
        m2.metric("매우급함", f"{urgent_count}건")
        m3.metric("오늘 완료", f"{done_count}건")

        c1, c2, c3 = st.columns([1.2, 1.2, 1])
        with c1:
            st.multiselect(
                "우선순위 필터",
                ["매우급함", "급함", "보통"],
                key="queue_priority_filter",
            )
        with c2:
            st.multiselect(
                "상태 필터",
                ["미처리", "검토중", "보류", "처리완료"],
                key="queue_status_filter",
            )
        with c3:
            st.selectbox("정렬", ["우선순위", "최신 접수"], key="queue_sort_by")

        priority_rank = {"매우급함": 0, "급함": 1, "보통": 2}
        queue_rows: List[Dict[str, Any]] = []
        filtered_cases: List[Dict[str, Any]] = []
        for case in st.session_state.mock_cases:
            status = st.session_state.case_statuses.get(case["case_id"], case.get("status", "미처리"))
            if case.get("priority") not in st.session_state.queue_priority_filter:
                continue
            if status not in st.session_state.queue_status_filter:
                continue
            filtered_cases.append(case)
            queue_rows.append(
                {
                    "case_id": case["case_id"],
                    "접수": case["received_at"],
                    "카테고리": case["category"],
                    "우선순위": case["priority"],
                    "담당": case["assignee"],
                    "상태": status,
                }
            )

        if st.session_state.queue_sort_by == "우선순위":
            filtered_cases.sort(key=lambda x: (priority_rank.get(x.get("priority", "보통"), 9), x.get("received_at", "")), reverse=False)
            queue_rows.sort(key=lambda x: (priority_rank.get(x.get("우선순위", "보통"), 9), x.get("접수", "")), reverse=False)
        else:
            filtered_cases.sort(key=lambda x: x.get("received_at", ""), reverse=True)
            queue_rows.sort(key=lambda x: x.get("접수", ""), reverse=True)

        if queue_rows:
            queue_df = pd.DataFrame(queue_rows)
            selection_event = st.dataframe(
                queue_df,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
            )
            case_ids = [c["case_id"] for c in filtered_cases]
            if st.session_state.selected_case_id not in case_ids:
                st.session_state.selected_case_id = case_ids[0]

            selected_rows = selection_event.selection.get("rows", []) if hasattr(selection_event, "selection") else []
            if selected_rows:
                selected_case_id = queue_df.iloc[selected_rows[0]]["case_id"]
                st.session_state.selected_case_id = selected_case_id
                sel_case = next((c for c in st.session_state.mock_cases if c["case_id"] == selected_case_id), None)
                if sel_case:
                    apply_auto_filters_from_case(sel_case)
                st.rerun()
        else:
            st.warning("필터 조건에 맞는 민원이 없습니다.")

    # 우측: 구조화 결과
    with col_right:
        selected_case = None
        for case in st.session_state.mock_cases:
            if case["case_id"] == st.session_state.selected_case_id:
                selected_case = case
                break

        if selected_case:
            current_status = st.session_state.case_statuses.get(selected_case["case_id"], selected_case.get("status", "미처리"))
            st.markdown(
                f"""
                <div class="detail-header-animate">
                    <div class="detail-header-title">선택 민원: {selected_case['case_id']}</div>
                    <div class="detail-header-sub">카테고리: {get_case_category(selected_case)} | 우선순위: {selected_case.get('priority','보통')} | 상태: {current_status}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 원문 표시
            with st.expander("원문 텍스트", expanded=True):
                st.write(selected_case["raw_text"])

            # 4요소 구조화 결과
            st.markdown("### AI 구조화 결과")
            structured = selected_case["structured"]

            # 관찰 (Observation)
            with st.container(border=True):
                col_obs_label, col_obs_conf = st.columns([3, 1])
                with col_obs_label:
                    st.markdown("**관찰**")
                with col_obs_conf:
                    st.markdown(render_confidence_score(structured["observation"]["confidence"]), unsafe_allow_html=True)
                
                st.write(structured["observation"]["text"])
                st.caption(f"근거: \"{structured['observation']['evidence_span']}\"")

            # 결과 (Result)
            with st.container(border=True):
                col_res_label, col_res_conf = st.columns([3, 1])
                with col_res_label:
                    st.markdown("**결과**")
                with col_res_conf:
                    st.markdown(render_confidence_score(structured["result"]["confidence"]), unsafe_allow_html=True)
                
                st.write(structured["result"]["text"])
                st.caption(f"근거: \"{structured['result']['evidence_span']}\"")

            # 요청 (Request)
            with st.container(border=True):
                col_req_label, col_req_conf = st.columns([3, 1])
                with col_req_label:
                    st.markdown("**요청**")
                with col_req_conf:
                    st.markdown(render_confidence_score(structured["request"]["confidence"]), unsafe_allow_html=True)
                
                st.write(structured["request"]["text"])
                st.caption(f"근거: \"{structured['request']['evidence_span']}\"")

            # 맥락 (Context)
            with st.container(border=True):
                col_ctx_label, col_ctx_conf = st.columns([3, 1])
                with col_ctx_label:
                    st.markdown("**맥락**")
                with col_ctx_conf:
                    st.markdown(render_confidence_score(structured["context"]["confidence"]), unsafe_allow_html=True)
                
                st.write(structured["context"]["text"])
                st.caption(f"근거: \"{structured['context']['evidence_span']}\"")

            # 추출된 엔티티
            st.markdown("### 추출된 핵심 엔티티")
            entities = structured.get("entities", [])
            if entities:
                for entity in entities[:24]:
                    st.markdown(
                        f"<span class='workbench-entity-pill'>{entity.get('label','-')}: {entity.get('text','-')}</span>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("추출된 엔티티가 없습니다.")

            # 스키마 검증 배지
            col_valid, col_version = st.columns([1, 1])
            with col_valid:
                if structured["is_valid"]:
                    st.markdown(
                        '<span class="badge badge-valid">✓ 스키마 검증 통과</span>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<span class="badge badge-invalid">✗ 스키마 검증 실패</span>',
                        unsafe_allow_html=True,
                    )
            with col_version:
                st.caption(f"Schema v{structured['schema_version']}")

            action_cols = st.columns(3)
            with action_cols[0]:
                if st.button("처리완료", use_container_width=True):
                    st.session_state.case_statuses[selected_case["case_id"]] = "처리완료"
                    _save_case_statuses_to_cache(st.session_state.case_statuses)
                    open_cases = [
                        c["case_id"]
                        for c in st.session_state.mock_cases
                        if st.session_state.case_statuses.get(c["case_id"], c.get("status", "미처리")) in ("미처리", "검토중")
                    ]
                    if open_cases:
                        st.session_state.selected_case_id = open_cases[0]
                        next_case = next((c for c in st.session_state.mock_cases if c["case_id"] == open_cases[0]), None)
                        if next_case:
                            apply_auto_filters_from_case(next_case)
                    st.rerun()
            with action_cols[1]:
                if st.button("검토중", use_container_width=True):
                    st.session_state.case_statuses[selected_case["case_id"]] = "검토중"
                    _save_case_statuses_to_cache(st.session_state.case_statuses)
                    st.rerun()
            with action_cols[2]:
                if st.button("다음 미처리", use_container_width=True):
                    open_cases = [
                        c["case_id"]
                        for c in st.session_state.mock_cases
                        if st.session_state.case_statuses.get(c["case_id"], c.get("status", "미처리")) in ("미처리", "검토중")
                    ]
                    if selected_case["case_id"] in open_cases and len(open_cases) > 1:
                        next_idx = (open_cases.index(selected_case["case_id"]) + 1) % len(open_cases)
                        st.session_state.selected_case_id = open_cases[next_idx]
                    st.rerun()

            st.divider()
            st.markdown("### 빠른 실행")
            st.caption("선택 민원의 핵심 엔티티(FACILITY/HAZARD/카테고리)를 검색 필터에 자동 반영한 뒤 단일 호출을 실행합니다.")
            if st.button("AI 유사 사례 및 대응 방안 생성", use_container_width=True, type="primary"):
                apply_auto_filters_from_case(selected_case)
                run_single_call_qa(selected_case)
                st.rerun()

            if st.session_state.single_call_notice:
                st.info(st.session_state.single_call_notice)

            st.divider()
            st.markdown("### 통합 민원 처리 워크벤치")
            st.caption("선택 민원의 검색/답변 작성 도구를 한 화면에서 실행합니다.")

            wb_entities = selected_case.get("structured", {}).get("entities", [])
            wb_hazards = [e.get("text", "") for e in wb_entities if e.get("label") == "HAZARD" and e.get("text")]
            wb_facilities = [e.get("text", "") for e in wb_entities if e.get("label") == "FACILITY" and e.get("text")]
            default_wb_query = ", ".join([*wb_hazards[:2], *wb_facilities[:1], selected_case.get("category", "")]).strip(", ")

            if st.session_state.get("wb_selected_case_id") != selected_case["case_id"]:
                st.session_state.wb_selected_case_id = selected_case["case_id"]
                st.session_state.wb_query = default_wb_query or selected_case.get("category", "")

            region_options = build_region_options(st.session_state.mock_cases)
            category_options = build_category_options(st.session_state.mock_cases)

            default_region = get_case_region(selected_case)
            default_category = get_case_category(selected_case)
            if st.session_state.wb_region not in region_options:
                st.session_state.wb_region = default_region if default_region in region_options else region_options[0]
            if st.session_state.wb_category not in category_options:
                st.session_state.wb_category = default_category if default_category in category_options else category_options[0]

            test_cols = st.columns([1, 6])
            with test_cols[0]:
                if st.button("오류 테스트", key=f"wb_error_test_compact_{selected_case['case_id']}"):
                    st.session_state.wb_search_state = "error_fallback"
                    st.session_state.wb_last_api_err = "검색 서버에 일시적인 장애가 발생했습니다. 관리자에게 문의하세요."
                    st.session_state.wb_pending_search = None
                    st.session_state.search_results = []
                    st.rerun()

            query, region, category, is_search_clicked = render_search_filter(
                default_query=st.session_state.wb_query,
                default_region=st.session_state.wb_region,
                default_category=st.session_state.wb_category,
                region_options=region_options,
                category_options=category_options,
            )

            if is_search_clicked:
                st.session_state.wb_search_state = "loading"
                st.session_state.wb_last_api_err = None
                st.session_state.search_results = []
                st.session_state.wb_pending_search = {
                    "query": query,
                    "region": region,
                    "category": category,
                    "date_range": st.session_state.ui_filter_date_range,
                    "entity_labels": ["FACILITY", "HAZARD"],
                    "top_k": 5,
                }
                st.rerun()

            if st.session_state.wb_search_state == "loading" and st.session_state.wb_pending_search:
                pending = dict(st.session_state.wb_pending_search)
                with st.spinner("유사 민원 및 지식 베이스를 검색 중입니다..."):
                    api_results, api_err = search_cases_via_api_with_filters(
                        query=str(pending.get("query", "")),
                        top_k=int(pending.get("top_k", 5)),
                        date_range=pending.get("date_range"),
                        region=str(pending.get("region", "전체")),
                        category=str(pending.get("category", "전체")),
                        entity_labels=list(pending.get("entity_labels", [])),
                    )

                st.session_state.wb_pending_search = None
                st.session_state.wb_last_api_err = api_err
                if api_err and not api_results:
                    api_err_text = str(api_err)
                    if st.session_state.ui_force_mock or "UI_FORCE_MOCK" in api_err_text:
                        st.session_state.wb_search_state = "mock_mode"
                    else:
                        st.session_state.wb_search_state = "error_fallback"
                    st.session_state.search_results = generate_mock_search_results(str(pending.get("query", "")), st.session_state.mock_cases)
                elif api_results is not None and len(api_results) == 0:
                    st.session_state.wb_search_state = "empty"
                    st.session_state.search_results = []
                else:
                    st.session_state.wb_search_state = "success"
                    st.session_state.search_results = api_results or []
                st.rerun()

            left_tool, right_tool = st.columns([1, 1], gap="small")
            with left_tool:
                st.markdown("#### 유사 사례")
                result_count = len(st.session_state.search_results)
                banner_state = st.session_state.wb_search_state
                banner_err = st.session_state.wb_last_api_err
                if (banner_state or "").strip().lower() in ("error_fallback", "error") and banner_err:
                    banner_err = f"{banner_err} (Mock 데이터를 표시합니다.)"

                render_standard_status_banner(
                    state=banner_state,
                    result_count=result_count,
                    error_message=banner_err,
                    idle_message="검색 조건을 입력한 뒤 ‘워크벤치 검색’을 실행하세요.",
                    loading_message="검색 요청을 처리 중입니다...",
                    empty_message="조건에 맞는 유사 민원이 없습니다. 검색어나 필터를 변경해 보세요.",
                    success_message=(
                        f"총 {result_count}건의 유사 사례를 찾았습니다." if (banner_state == "success") else None
                    ),
                    mock_message="Mock 모드(UI_FORCE_MOCK)로 샘플 데이터를 표시합니다.",
                )

                if st.session_state.search_results:
                    for idx, item in enumerate(st.session_state.search_results[:5], start=1):
                        render_search_result_card(idx, item)
                else:
                    if st.session_state.wb_search_state is None:
                        st.info("검색 버튼을 눌러 유사 사례를 불러오세요.")

            with right_tool:
                st.markdown("#### AI 어시스턴트")
                st.text_area(
                    "지시사항",
                    key="wb_prompt_input",
                    height=90,
                    placeholder="예: 선택 민원을 기준으로 담당부서 전달문과 민원인 안내문을 작성해줘.",
                )
                if st.button("워크벤치 답변 생성", use_container_width=True, type="primary"):
                    prompt = st.session_state.wb_prompt_input.strip()
                    if not prompt:
                        st.warning("지시사항을 입력해주세요.")
                    else:
                        run_workbench_qa(prompt=prompt, case=selected_case)
                        st.rerun()

                for message in st.session_state.chat_history[-4:]:
                    if message.get("role") == "user":
                        st.markdown(f"<div class='chat-message-user'>{message.get('content', '')}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='chat-message-assistant'>{message.get('content', '')}</div>", unsafe_allow_html=True)
                        citations = message.get("citations", [])
                        render_citations_block(citations if isinstance(citations, list) else [], expanded=False)

                        qa_validation = message.get("qa_validation")
                        if isinstance(qa_validation, dict) and qa_validation.get("is_valid") is False:
                            st.warning("QA 응답 검증에서 문제가 감지되었습니다. (qa_validation.is_valid=false)")
                        limitations = message.get("limitations")
                        has_limitations = bool(str(limitations).strip()) if isinstance(limitations, str) else bool(limitations)
                        render_limitations_block(limitations, expanded=has_limitations)
                        meta = message.get("meta", {})
                        if isinstance(meta, dict) and meta.get("validation_warning"):
                            st.caption(str(meta.get("validation_warning")))


# ============================================================================
# 6. TAB 2: 유사 민원 검색 및 RAG 챗
# ============================================================================

def render_tab2_search_rag():
    """
    Tab 2: 특정 민원에 대해 과거 유사 사례를 검색하고
           AI가 제공하는 RAG 기반 답변을 작성하는 화면
    """
    st.markdown("## 유사 민원 검색 및 AI 조력자 (RAG-QA)")
    st.markdown("과거 비슷한 사례를 찾아 AI와 함께 답변 초안을 작성합니다.")
    st.caption("Tab1에서 민원을 선택하면 엔티티 기반 필터가 자동 세팅됩니다.")

    if "tab2_search_state" not in st.session_state:
        st.session_state.tab2_search_state = None
    if "tab2_pending_search" not in st.session_state:
        st.session_state.tab2_pending_search = None
    if "tab2_last_api_err" not in st.session_state:
        st.session_state.tab2_last_api_err = None

    # 현재 선택 민원을 기준으로 자동 필터 동기화
    selected_case = get_selected_case()
    if selected_case and st.session_state.filter_synced_case_id != selected_case.get("case_id", ""):
        apply_auto_filters_from_case(selected_case)
        st.session_state.filter_synced_case_id = selected_case.get("case_id", "")

    # 위젯 렌더 전 pending 필터를 반영해 Streamlit key 충돌을 피한다.
    if st.session_state.auto_filter_payload:
        payload = st.session_state.auto_filter_payload
        st.session_state.ui_search_query = payload.get("ui_search_query", st.session_state.ui_search_query)
        st.session_state.ui_filter_region = payload.get("ui_filter_region", st.session_state.ui_filter_region)
        st.session_state.ui_filter_category = payload.get("ui_filter_category", st.session_state.ui_filter_category)
        st.session_state.ui_filter_date_range = payload.get("ui_filter_date_range", st.session_state.ui_filter_date_range)
        st.session_state.ui_filter_entity_labels = payload.get("ui_filter_entity_labels", st.session_state.ui_filter_entity_labels)
        st.session_state.auto_filter_payload = None

    # -------- 필터 영역 --------
    with st.container():
        filter_cols = st.columns([2, 1.5, 1.5, 1.5])
        
        with filter_cols[0]:
            st.text_input(
                "검색어 입력",
                key="ui_search_query",
                placeholder="예: 포트홀, 도로 파손, 배수..."
            )
        
        with filter_cols[1]:
            st.date_input(
                "기간",
                key="ui_filter_date_range",
                label_visibility="visible",
            )
        
        with filter_cols[2]:
            region_options = build_region_options(st.session_state.mock_cases)
            if st.session_state.ui_filter_region not in region_options:
                st.session_state.ui_filter_region = "전체"
            st.selectbox(
                "행정구역",
                options=region_options,
                index=_safe_index(region_options, st.session_state.ui_filter_region, default=0),
                key="ui_filter_region",
            )
        
        with filter_cols[3]:
            category_options = build_category_options(st.session_state.mock_cases)
            if st.session_state.ui_filter_category not in category_options:
                st.session_state.ui_filter_category = "전체"
            st.selectbox(
                "카테고리",
                options=category_options,
                index=_safe_index(category_options, st.session_state.ui_filter_category, default=0),
                key="ui_filter_category",
            )

    # 위젯 값 -> 내부 상태 동기화
    st.session_state.search_query_text = st.session_state.ui_search_query

    st.text_input("API Base URL", key="api_base_url")

    st.divider()

    # -------- 검색 버튼 --------
    search_cols = st.columns([1, 1])
    with search_cols[0]:
        run_search = st.button("검색 시작", use_container_width=True, type="primary")
    with search_cols[1]:
        auto_search = st.button("자동 검색(선택 민원 기반)", use_container_width=True)

    if auto_search and selected_case:
        apply_auto_filters_from_case(selected_case)
        st.session_state.tab2_search_state = "loading"
        st.session_state.tab2_last_api_err = None
        st.session_state.tab2_pending_search = {
            "query": st.session_state.search_query_text,
            "top_k": 5,
        }
        st.session_state.single_call_notice = "선택 민원 기반 자동 검색을 실행합니다."
        st.rerun()

    if run_search:
        st.session_state.tab2_search_state = "loading"
        st.session_state.tab2_last_api_err = None
        st.session_state.tab2_pending_search = {
            "query": st.session_state.search_query_text,
            "top_k": 5,
        }
        st.session_state.single_call_notice = "검색을 실행합니다."
        st.session_state.chat_history = []  # 새로운 검색 시작하면 채팅 히스토리 초기화
        st.rerun()

    if st.session_state.tab2_search_state == "loading" and st.session_state.tab2_pending_search:
        pending = dict(st.session_state.tab2_pending_search)
        with st.spinner("유사 민원 및 지식 베이스를 검색 중입니다..."):
            api_results, api_err = search_cases_via_api(
                query=str(pending.get("query", "")),
                top_k=int(pending.get("top_k", 5)),
            )

        st.session_state.tab2_pending_search = None
        st.session_state.tab2_last_api_err = api_err

        if api_err and not api_results:
            st.session_state.tab2_search_state = "error_fallback"
            st.session_state.search_results = generate_mock_search_results(
                str(pending.get("query", "")),
                st.session_state.mock_cases,
            )
            st.session_state.single_call_notice = "검색 서버 오류로 인해 Mock 데이터로 대체합니다."
        elif api_results is not None and len(api_results) == 0:
            st.session_state.tab2_search_state = "empty"
            st.session_state.search_results = []
            st.session_state.single_call_notice = "검색 결과가 없습니다."
        else:
            st.session_state.tab2_search_state = "success"
            st.session_state.search_results = api_results or []
            st.session_state.single_call_notice = "검색 결과를 불러왔습니다."

        st.rerun()

    # -------- 검색 결과 + RAG 챗 (2열 분할) --------
    col_search, col_rag = st.columns([1.1, 1.3], gap="large")

    # 좌측: 검색 결과 리스트
    with col_search:
        st.markdown("### 검색 결과")

        banner_state = st.session_state.tab2_search_state
        banner_err = st.session_state.tab2_last_api_err
        if (banner_state or "").strip().lower() in ("error_fallback", "error") and banner_err:
            banner_err = f"{banner_err} (Mock 데이터를 표시합니다.)"

        render_standard_status_banner(
            state=banner_state,
            result_count=len(st.session_state.search_results),
            error_message=banner_err,
            idle_message="검색어를 입력하고 ‘검색 시작’을 클릭해주세요.",
            loading_message="검색 요청을 처리 중입니다...",
            empty_message="조건에 맞는 유사 민원이 없습니다. 검색어나 필터를 변경해 보세요.",
            success_message=None,
            mock_message="Mock 모드(UI_FORCE_MOCK)로 샘플 데이터를 표시합니다.",
        )
        
        if st.session_state.search_results:
            st.markdown(f"**{len(st.session_state.search_results)}개 결과 찾음**")
            
            for idx, result in enumerate(st.session_state.search_results):
                with st.container(border=True):
                    col_title, col_score = st.columns([4, 1])
                    
                    with col_title:
                        st.markdown(f"**유사민원 {idx + 1}**")
                        st.caption(f"{result['case_id']} | {result['received_at']}")
                    
                    with col_score:
                        st.markdown(
                            f"<div style='text-align: right; font-weight: 700; color: #10b981;'>"
                            f"{result['similarity_score']:.0%}</div>",
                            unsafe_allow_html=True,
                        )
                    
                    st.caption(result['snippet'])
                    
                    # 이 결과 기반으로 RAG 질문 버튼
                    if st.button(
                        f"이 사례로 답변 생성",
                        key=f"use_result_{idx}",
                        use_container_width=True,
                    ):
                        # 해당 문서 기반 RAG 채팅 시작 (Mock)
                        st.session_state.current_rag_doc = result
                        st.rerun()
        else:
            # 표준 배너가 idle/empty/error를 담당한다.
            pass

    # 우측: RAG QA 채팅 인터페이스
    with col_rag:
        st.markdown("### AI 어시스턴트 (RAG-QA)")
        quick_prompts = st.columns(3)
        with quick_prompts[0]:
            if st.button("답변 초안", use_container_width=True):
                st.session_state.chat_history.append({"role": "user", "content": "선택된 유사 사례 기반으로 민원 답변 초안을 작성해줘."})
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": render_answer_with_citations("민원 답변 초안을 생성했습니다. 사실관계 확인 후 발송하세요. [출처 1]", [{"ref_id": 1, "case_id": "CASE-2025-1024", "snippet": "유사 민원 처리 내역"}]),
                    "citations": [{"ref_id": 1, "case_id": "CASE-2025-1024", "snippet": "유사 민원 처리 내역"}],
                    "meta": {"processing_time": round(random.uniform(8.0, 12.0), 2), "model": "mock-rag"},
                })
                st.rerun()
        with quick_prompts[1]:
            if st.button("부서 전달문", use_container_width=True):
                st.session_state.chat_history.append({"role": "user", "content": "유관 부서 전달용 조치 요청문을 작성해줘."})
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": render_answer_with_citations("부서 전달문을 작성했습니다. 현장점검과 조치일정을 병행 요청합니다. [출처 1]", [{"ref_id": 1, "case_id": "CASE-2025-0988", "snippet": "이륜차 사고 예방 조치 사례"}]),
                    "citations": [{"ref_id": 1, "case_id": "CASE-2025-0988", "snippet": "이륜차 사고 예방 조치 사례"}],
                    "meta": {"processing_time": round(random.uniform(8.0, 12.0), 2), "model": "mock-rag"},
                })
                st.rerun()
        with quick_prompts[2]:
            if st.button("민원인 안내", use_container_width=True):
                st.session_state.chat_history.append({"role": "user", "content": "민원인 안내 메시지를 친절한 톤으로 작성해줘."})
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": render_answer_with_citations("민원인 안내문을 생성했습니다. 접수번호와 처리예정일을 함께 안내하세요. [출처 1]", [{"ref_id": 1, "case_id": "CASE-2025-0876", "snippet": "처리 지연 최소화 안내 문안"}]),
                    "citations": [{"ref_id": 1, "case_id": "CASE-2025-0876", "snippet": "처리 지연 최소화 안내 문안"}],
                    "meta": {"processing_time": round(random.uniform(8.0, 12.0), 2), "model": "mock-rag"},
                })
                st.rerun()

        # 채팅 히스토리 표시
        chat_container = st.container(border=True)
        
        with chat_container:
            for message in st.session_state.chat_history:
                if message["role"] == "user":
                    st.markdown(
                        f"""
                        <div class="chat-message-user">
                            {message['content']}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:  # assistant
                    # 답변에 citation이 포함되어 있으면 렌더링
                    answer = message['content']
                    
                    st.markdown(
                        f"""
                        <div class="chat-message-assistant">
                            {answer}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    
                    # Citation 목록
                    if "citations" in message and message["citations"]:
                        st.markdown("**참고 자료:**")
                        for cidx, citation in enumerate(message["citations"], start=1):
                            ref_id = citation.get("ref_id", cidx)
                            case_id = citation.get("case_id", "-")
                            chunk_id = citation.get("chunk_id", "-")
                            snippet = citation.get("snippet", "-")
                            st.caption(f"• [출처 {ref_id}] {case_id} | {chunk_id} | {snippet}")

                    meta = message.get("meta", {})
                    if meta:
                        st.caption(
                            f"처리시간: {meta.get('processing_time', '-')}s | 모델: {meta.get('model', '-')}"
                        )

        # 사용자 입력
        user_prompt = st.chat_input(
            placeholder="예: 이 사례를 바탕으로 도로보수팀 지시서를 작성해줄 수 있나?",
        )

        if user_prompt:
            # 사용자 메시지 추가
            st.session_state.chat_history.append({
                "role": "user",
                "content": user_prompt,
            })

            # Mock RAG 답변 생성
            mock_answer = f"""이 사례를 바탕으로 아래와 같이 작성을 제안드립니다:

**[도로보수팀 긴급 작업 지시서]**

**1. 작업 개요** [[CITE:1]]
- 위치: 중앙로 10m 지점
- 원인: 폭우로 인한 배수 불량
- 긴급도: 높음 (이륜차 사고 위험)

**2. 조치 방안**
- 당일 현장 확인 및 임시 응급 복구 [[CITE:1]]
- 아스팔트 타설 (2-3일 소요)
- 해당 지점 배수로 개선 계획 수립

**3. 예상 기간**
- 임시 복구: 당일 완료
- 본격 복구: 영업 3일 내 완료"""

            mock_citations = [
                {
                    "ref_id": 1,
                    "case_id": "CASE-2025-1024",
                    "doc_id": "DOC-2025-1024",
                    "snippet": "폭우 이후 배수 불량으로 발생한 포트홀에 대해 긴급 아스팔트 타설 완료...",
                }
            ]

            st.session_state.chat_history.append({
                "role": "assistant",
                "content": render_answer_with_citations(mock_answer, mock_citations),
                "citations": mock_citations,
                "meta": {"processing_time": round(random.uniform(8.0, 12.0), 2), "model": "mock-rag"},
            })

            st.rerun()


# ============================================================================
# 7. TAB 3: 관리자 통계 대시보드
# ============================================================================

def render_tab3_statistics():
    """
    Tab 3: 정책 관리자가 민원 트렌드와 위험요소 통계를 분석하는 화면
    """
    st.caption("민원 발생 현황, 카테고리별 추이, 위험요소 분포를 분석합니다.")

    # 기간 필터
    with st.container(border=True):
        st.markdown("<div class='admin-panel-title'>조회 설정</div>", unsafe_allow_html=True)
        col_date, col_refresh = st.columns([4, 1])
        with col_date:
            st.markdown("<div class='queue-filter-label'>조회 기간</div>", unsafe_allow_html=True)
            period = st.selectbox(
                "조회 기간",
                options=["지난 7일", "지난 30일", "지난 90일", "올해", "전체"],
                index=1,
                label_visibility="collapsed",
            )
        with col_refresh:
            st.markdown("<div class='queue-filter-label'>실행</div>", unsafe_allow_html=True)
            if st.button("새로고침", use_container_width=True):
                st.rerun()

    st.divider()

    stats = generate_mock_hazard_statistics()

    # -------- 차트 1: 카테고리별 발생 건수 (Bar Chart) --------
    chart_cols = st.columns([1.2, 1.0])

    with chart_cols[0]:
        st.markdown("<div class='admin-section-title'>카테고리별 발생 현황</div>", unsafe_allow_html=True)
        
        category_data = stats["category_stats"]
        df_category = pd.DataFrame({
            "카테고리": category_data["category"],
            "건수": category_data["count"],
        })

        fig_category = go.Figure(
            data=[
                go.Bar(
                    x=df_category["카테고리"],
                    y=df_category["건수"],
                    marker=dict(
                        color=["#1d4ed8", "#059669", "#d97706", "#7c3aed", "#334155"],
                    ),
                    text=df_category["건수"],
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="<b>%{x}</b><br>%{y}건<extra></extra>",
                )
            ]
        )

        fig_category.update_layout(
            height=350,
            margin=dict(l=40, r=20, t=20, b=60),
            xaxis_tickangle=-45,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(gridcolor="#e2e8f0"),
        )

        st.plotly_chart(fig_category, use_container_width=True)

    # -------- 차트 2: 위험요소 Top 5 (Horizontal Bar) --------
    with chart_cols[1]:
        st.markdown("<div class='admin-section-title'>위험요소 Top 5</div>", unsafe_allow_html=True)
        
        hazard_data = stats["hazard_top5"]
        df_hazard = pd.DataFrame({
            "위험요소": [h["hazard"] for h in hazard_data],
            "건수": [h["count"] for h in hazard_data],
            "비율": [h["percentage"] for h in hazard_data],
        })

        fig_hazard = go.Figure(
            data=[
                go.Bar(
                    y=df_hazard["위험요소"],
                    x=df_hazard["건수"],
                    orientation="h",
                    marker=dict(
                        color=["#ef4444", "#f97316", "#eab308", "#84cc16", "#22c55e"],
                    ),
                    text=[f"{count}건" for count in df_hazard["건수"]],
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="<b>%{y}</b><br>%{x}건<extra></extra>",
                )
            ]
        )

        fig_hazard.update_layout(
            height=350,
            margin=dict(l=120, r=120, t=20, b=20),
            xaxis=dict(
                gridcolor="#e2e8f0",
                range=[0, float(df_hazard["건수"].max()) * 1.25],
            ),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )

        st.plotly_chart(fig_hazard, use_container_width=True)

    st.divider()

    # -------- 지역별 발생 현황 (데이터테이블) --------
    st.markdown("<div class='admin-section-title'>지역별 민원 발생 현황</div>", unsafe_allow_html=True)

    region_data = stats["region_stats"]
    df_region = pd.DataFrame({
        "지역": region_data["region"],
        "건수": region_data["count"],
        "비율": [f"{(count / sum(region_data['count'])) * 100:.1f}%" for count in region_data["count"]],
    })

    st.dataframe(
        df_region,
        use_container_width=True,
        hide_index=True,
        column_config={
            "건수": st.column_config.NumberColumn(format="%d건"),
        },
    )

    # -------- 추가 분석 아이템 --------
    st.divider()
    st.markdown("<div class='admin-section-title'>주간 트렌드 (지난 4주)</div>", unsafe_allow_html=True)

    weeks = ["1주차", "2주차", "3주차", "4주차"]
    weekly_count = [58, 71, 94, 64]

    df_weekly = pd.DataFrame({
        "주차": weeks,
        "접수건수": weekly_count,
    })

    fig_weekly = go.Figure(
        data=[
            go.Scatter(
                x=df_weekly["주차"],
                y=df_weekly["접수건수"],
                mode="lines+markers",
                line=dict(color="#3b82f6", width=3),
                marker=dict(size=10),
                fill="tozeroy",
                fillcolor="rgba(59, 130, 246, 0.2)",
                hovertemplate="<b>%{x}</b><br>%{y}건<extra></extra>",
            )
        ]
    )

    fig_weekly.update_layout(
        height=280,
        margin=dict(l=40, r=20, t=0, b=20),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="rgba(0,0,0,0)"),
        yaxis=dict(gridcolor="#e2e8f0"),
        showlegend=False,
    )

    st.plotly_chart(fig_weekly, use_container_width=True)

    # =====================================================================
    # [Week 3] 모델 벤치마크 대시보드 시각화
    # =====================================================================

    st.divider()
    st.markdown("<div class='admin-section-title'>주간 AI 모델 성능 벤치마크</div>", unsafe_allow_html=True)

    benchmark_data = load_model_benchmark_report()
    summary = benchmark_data.get("summary", {}) if isinstance(benchmark_data, dict) else {}
    model_info = benchmark_data.get("model_info", {}) if isinstance(benchmark_data, dict) else {}
    scenarios = benchmark_data.get("scenarios", []) if isinstance(benchmark_data, dict) else []

    # [Step A] 요약 KPI 카드
    kpi_cols = st.columns(3)
    avg_f1 = float(summary.get("average_f1_score", 0.0) or 0.0)
    avg_recall = float(summary.get("average_recall_at_5", 0.0) or 0.0)
    avg_latency = float(summary.get("average_latency_sec", 0.0) or 0.0)

    def _kpi_card(label: str, value: str) -> str:
        return (
            "<div class='admin-kpi-card'>"
            f"<div class='admin-kpi-label'>{html.escape(label)}</div>"
            f"<div class='admin-kpi-value'>{html.escape(value)}</div>"
            "</div>"
        )

    with kpi_cols[0]:
        st.markdown(_kpi_card("구조화 F1", f"{avg_f1 * 100:.1f}%"), unsafe_allow_html=True)
    with kpi_cols[1]:
        st.markdown(_kpi_card("검색 명중률 (Recall@5)", f"{avg_recall * 100:.1f}%"), unsafe_allow_html=True)
    with kpi_cols[2]:
        st.markdown(_kpi_card("평균 추론 지연", f"{avg_latency:.2f}s"), unsafe_allow_html=True)

    llm_model = str(model_info.get("llm_model", "-"))
    emb_model = str(model_info.get("embedding_model", "-"))
    st.caption(f"모델: {llm_model} | 임베딩: {emb_model}")

    # [Step B] 시나리오별 성능 비교 차트 (Grouped Bar)
    df_scenarios = pd.DataFrame(scenarios) if isinstance(scenarios, list) else pd.DataFrame()
    chart_col, table_col = st.columns([1.6, 1.0], gap="large")
    with chart_col:
        if not df_scenarios.empty and "name" in df_scenarios.columns:
            df_scenarios = df_scenarios.copy()
            df_scenarios["f1_score"] = pd.to_numeric(df_scenarios.get("f1_score", 0), errors="coerce").fillna(0.0)
            df_scenarios["recall_at_5"] = pd.to_numeric(df_scenarios.get("recall_at_5", 0), errors="coerce").fillna(0.0)

            fig = go.Figure(
                data=[
                    go.Bar(
                        name="F1",
                        x=df_scenarios["name"],
                        y=df_scenarios["f1_score"],
                        marker_color="#2563eb",
                        hovertemplate="<b>%{x}</b><br>F1: %{y:.2f}<extra></extra>",
                    ),
                    go.Bar(
                        name="Recall@5",
                        x=df_scenarios["name"],
                        y=df_scenarios["recall_at_5"],
                        marker_color="#10b981",
                        hovertemplate="<b>%{x}</b><br>Recall@5: %{y:.2f}<extra></extra>",
                    ),
                ]
            )
            fig.update_layout(
                barmode="group",
                height=320,
                margin=dict(l=40, r=20, t=10, b=90),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(range=[0, 1.0], gridcolor="#e2e8f0"),
                xaxis=dict(tickangle=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("시나리오 데이터가 없어 차트를 표시할 수 없습니다.")

    # [Step C] 상세 데이터 테이블 및 출처
    with table_col:
        if not df_scenarios.empty:
            view_df = df_scenarios.rename(
                columns={
                    "name": "시나리오",
                    "f1_score": "F1",
                    "recall_at_5": "Recall@5",
                    "latency_sec": "지연(초)",
                }
            )
            st.dataframe(
                view_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "F1": st.column_config.NumberColumn(format="%.2f"),
                    "Recall@5": st.column_config.NumberColumn(format="%.2f"),
                    "지연(초)": st.column_config.NumberColumn(format="%.2f"),
                },
            )
        else:
            st.caption("표시할 시나리오 데이터가 없습니다.")

    project_root = Path(__file__).resolve().parents[2]
    source_path = project_root / "logs" / "evaluation" / "week3" / "model_benchmark_report_final.json"
    st.caption(f"출처: {source_path} (없거나 파싱 실패 시 Mock 데이터 표시)")



# ============================================================================
# 8. MAIN APP
# ============================================================================

def main():
    # Workbench deep-link safety: if action params exist, force workbench view.
    if _qp_first("wb_action") or _qp_first("wb_mark") or _qp_first("open_case"):
        if st.session_state.get("app_view") != "admin":
            st.session_state.app_view = "workbench"

    # Query param based view switching (HTML sidebar/topnav)
    requested_view = _qp_first("view")
    if requested_view in ("queue", "workbench", "admin"):
        st.session_state.app_view = requested_view
        _consume_qp("view")
        st.rerun()

    with st.sidebar:
        active_queue = "active" if st.session_state.app_view == "queue" else ""
        active_wb = "active" if st.session_state.app_view == "workbench" else ""
        active_admin = "active" if st.session_state.app_view == "admin" else ""
        st.markdown(
            f"""
            <div class="sb-brand">
                <div class="sb-brand-title">CRM SYSTEM</div>
                <div class="sb-brand-sub">ON-DEVICE AI V1.0</div>
            </div>
            <div class="sb-menu">
                <a class="sb-item {active_queue}" href="?view=queue" target="_self" onclick="window.location.assign('?view=queue'); return false;">민원 선택</a>
                <a class="sb-item {active_wb}" href="?view=workbench" target="_self" onclick="window.location.assign('?view=workbench'); return false;">처리 워크벤치</a>
                <a class="sb-item {active_admin}" href="?view=admin" target="_self" onclick="window.location.assign('?view=admin'); return false;">관리자 통계</a>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if st.session_state.app_view == "queue":
        render_queue_entry_screen()
    elif st.session_state.app_view == "workbench":
        render_case_workbench_screen()
    else:
        st.markdown("## 관리자 통계 대시보드")
        if st.button("⬅ 민원 선택으로", use_container_width=False, key="admin_back_to_queue"):
            st.session_state.app_view = "queue"
            st.rerun()
        render_tab3_statistics()

    # 푸터
    st.divider()
    st.markdown(
        """
        <div class="app-footer">
            <p><strong>보안 특화 On-Device AI 시스템</strong> | 로컬 환경 추론만 지원 | 외부 API 미사용</p>
            <p style="opacity: 0.85;">© 2026 공공기관 민원처리팀 | Mock Data 기반 데모</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()