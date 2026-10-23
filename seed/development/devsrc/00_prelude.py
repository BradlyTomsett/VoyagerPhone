#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voyager Fleet deterministic game engine infrastructure v2.72.0 (native authority + cold evidence archives).

Game facts are stored and executed directly in the eight-component authority set.
Normal boot, query, deterministic settlement, domain commands and commit paths do not
materialize legacy INDEX/WORLD/STATE/TASKS/HISTORY compatibility files.
"""
from __future__ import annotations

import argparse
import ast
import base64
import copy
import collections
import datetime as dt
import hashlib
import json
import importlib.util
import math
import os
import re
import shutil
import stat
import sys
import tempfile
import time
import zipfile
import zlib
import gzip
import lzma
import fcntl
import sqlite3
import subprocess
import uuid
import resource
import signal
import contextvars
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ENGINE_VERSION = "2.74.0"
ENGINE_PROTOCOL = "4"
RUNTIME_SCHEMA = "VOYAGER_RUNTIME_V2"
TASK_RUNTIME_SCHEMA = "TASK_RUNTIME_V3"
PATCH_FORMAT = "VOYAGER_PATCH_V1"
REVIEW_ACK_FORMAT = "VOYAGER_TASK_REVIEW_ACK_V1"
TASK_REVIEW_MAX_WINDOW_SECONDS = 7 * 24 * 60 * 60
RUNTIME_RULES_MARKER = "VOYAGER_RUNTIME_RULES_V1"
STATIC_CATALOG_MARKER = "VOYAGER_STATIC_CATALOG_V1"
STATIC_CATALOG_SCHEMA = "WORLD_STATIC_CATALOG_V1"
MONEY_MODEL_SCHEMA = "FIXED_POINT_FINANCE_V2"
MONEY_SCALE = 10000
MONEY_DECIMAL_PLACES = {"gold":4,"grey":2}
MONEY_QUANTUM_UNITS = {"gold":1,"grey":100}
DOMAIN_COMMAND_RUNTIME_SCHEMA = "DOMAIN_COMMAND_RUNTIME_V1"
DOMAIN_COMMAND_MAX_RECEIPTS = 256
ASSET_SEMANTIC_MAP_SCHEMA = "ASSET_SEMANTIC_MAP_V2"
GUARD_PROTOCOL = "4"
BUNDLED_GUARD_VERSION = "2.23.0"
ENGINE_MAGIC = "VOYAGER_FLEET_GAME_ENGINE"
COMMIT_FORMAT = "VOYAGER_COMMIT_V1"
BUNDLED_GUARD_SHA256 = "88993600617ea206f9a06d683da78d9be3189d829e3b5f0711e4149b6e1e3180"
NATIVE_COMMIT_JOURNAL_SCHEMA = "VOYAGER_NATIVE_COMMIT_JOURNAL_V1"
NATIVE_COMMIT_JOURNAL_FILENAME = "native_commit_journal.json"
SUPPORTED_SCHEMA_VERSIONS = {"V6.0", "V7.0"}
STRICT_GAME_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
COMPONENT_ROOT = Path(globals().get("_HOST_ENGINE_ROOT") or os.environ.get("VOYAGER_ROOT", str(Path(__file__).resolve().parent))).resolve()
COMPONENT_MODE = (COMPONENT_ROOT / "manifest.json").is_file()
ROOT = COMPONENT_ROOT
AUTH_FILES = ["manifest.json", "rules.json", "catalog.json", "events.jsonl", "tasks.json", "state.json"]
SRC_ORDER = ["rules.json", "catalog.json", "events.jsonl", "tasks.json", "state.json"]
SNAP_RE = re.compile(r"^V(\d+)\.(\d+)_SAVESET_([0-9a-f]{16})$")
EXPORT_RE = re.compile(r"^V(\d+)\.(\d+)_EXPORT_([0-9a-f]{16})$")
PROJECT_SOURCE_RE = re.compile(r"^V(\d+)\.(\d+)_PROJECT_SOURCE_([0-9a-f]{16})$")
AB_SLOT_FORMAT = "VOYAGER_AB_SLOT_V1"
AB_ACTIVE_FORMAT = "VOYAGER_AB_ACTIVE_V1"
AB_ACTIVE_FILE = "SAVE_ACTIVE.json"
AB_SLOT_FILES = {"A":"SAVE_SLOT_A.voyager", "B":"SAVE_SLOT_B.voyager"}
AB_REQUIRED_MEMBERS = tuple(AUTH_FILES) + ("SLOT.json",)
ABS_TIME_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::(\d{2}))?(?!\d)")
SHORT_TIME_RE = re.compile(r"(?<![\d-])(\d{2}-\d{2})[T ](\d{2}:\d{2})(?::(\d{2}))?(?!\d)")
HAZARD_RATE_SCALE = 10**12
HAZARD_YEAR_SECONDS = 31557600  # 365.25 days, integer seconds
HAZARD_DENOMINATOR = HAZARD_RATE_SCALE * HAZARD_YEAR_SECONDS
SECONDHAND_ROLL_SCALE = 10000
SECONDHAND_GATE_VERSION = "SECONDHAND_HIDDEN_ISSUE_GATE_V1"
AUDIT_REGISTRY_SCHEMA = "STATE_AUDIT_REGISTRY_V2"
TASK_OBJECT_SCHEMA = "TASK_OBJECT_V4"
WATCH_CONDITION_SCHEMA = "WATCH_CONDITION_V1"
TASK_AI_BARRIER_KINDS = {"task_overdue_reconciliation","task_ai_review","task_ai_review_now","task_watch_condition","task_player_decision_gate"}
WORLD_PURIFY_SCHEMA="WORLD_PURIFY_V1"
DERIVED_VIEW_RULE_SCHEMA = "DERIVED_VIEW_RULE_V1"
DERIVED_RUNTIME_SCHEMA = "DERIVED_RUNTIME_V1"
TRANSACTION_CHANGESET_SCHEMA = "TRANSACTION_CHANGESET_V1"
WORLD_PROCESS_RULE_SCHEMA = "WORLD_PROCESS_RULE_V1"
PROGRESS_RULE_SCHEMA = "PROGRESS_RULE_V1"
CONTINUOUS_PROGRESS_CONTRACT_SCHEMA = "CONTINUOUS_PROGRESS_CONTRACT_V1"
CONTINUOUS_PROGRESS_LEGACY_EXEMPTION_SCHEMA = "CONTINUOUS_PROGRESS_LEGACY_EXEMPTION_V1"
CONTINUOUS_PROGRESS_LEGACY_SAVE_FALLBACK = (10,148)
PROGRESS_NUMERIC_FIELD_RE = re.compile(r"(?:^|_)(?:progress|completion)(?:_pct|_percent|_percentage)?$", re.I)
CONTINUOUS_PROGRESS_TASK_HINT_RE = re.compile(r"research|science|explor|construct|train|decod|recover|restor|repair|refit|manufactur|build|科研|探索|建设|训练|解码|恢复|修复|改装|制造", re.I)
COLD_START_PACKET_SCHEMA = "COLD_START_PACKET_V5"
ROW_REGISTRY_FORMAT = "ROW_REGISTRY_V2"
CALDER_552_COMPONENT_REF = "CALDER_552_COMPONENT"
CALDER_552_CANONICAL_PATH = "world_state_overrides.multinational_industry_current"
DETERMINISTIC_RESOLVERS = {"passive_event_v1","jinchuan_daily_settlement_v1","research_sales_daily_v1","settlement_rule_v1","automation_rule_v1","world_process_rule_v1","progress_rule_v1","training_progress_v1","repair_completion_v1","delivery_v1","inventory_transfer_v1","authorized_sale_v1","authorized_purchase_v1","authorized_intel_purchase_v1","travel_progress_v1","research_progress_v1","construction_progress_v1","resource_operation_v1","market_refresh_v1"}
FINANCE_LEDGER_FORMAT = "VOYAGER_FINANCE_LEDGER_V1"
SHIPBOARD_ASSET_CROSSPATH_RULE_ID = "RULE-SHIPBOARD-ASSET-CROSSPATH-01"
VPACK_TRANSPORT_FORMAT = 'VOYAGER_SOURCE_VPACK_V1'
VPACK_BOOTSTRAP_FORMAT = 'VOYAGER_VPACK_BOOTSTRAP_V1'
VPACK_BOOTSTRAP_FILENAME = 'SAVE_GUARD_v2.4.1.py'


TEXT_POLICY_RULE_ID = "RULE-TEXT-CHARSET-01"
TEXT_POLICY_EVENT_TYPE = "text_charset_migration"
# Canonical one-time replacements used to migrate legacy game text into the allowed text set.
# ASCII digits are permitted as numeric notation; ASCII punctuation and Unicode punctuation are permitted.
TEXT_CANONICAL_REPLACEMENTS = {
    chr(0x03A3): "Sigma",   # legacy Greek capital sigma in proper-name text
}

# Proper names may use ASCII English letters/digits, Han ideographs, punctuation/spacing,
# and mathematical operators. Emoji, circled numerals, currency/decorative symbols and
# non-ASCII alphabetic scripts are not valid proper-name characters.
NAME_FIELD_KEYS = {"name", "canonical_name", "class_name", "former_name", "ship_name", "person_name", "location_name", "organization_name", "equipment_name", "model_name", "fleet_name", "display_name"}
WORLD_NAME_TABLE_HEADERS = {"名称", "人物", "组织", "舰级", "舰名", "地点", "装备", "型号", "当前正式名称", "旧称/易混名称"}

