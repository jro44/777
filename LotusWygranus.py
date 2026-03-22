import os
import re
import math
import json
import random
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Iterable
from collections import Counter, defaultdict
from itertools import combinations

import fitz  # PyMuPDF
import numpy as np
import pandas as pd
import streamlit as st


# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("lotto_app")


# =========================================================
# CONSTANTS
# =========================================================
APP_TITLE = "🏆 Victory Lotto Pro — 6/49"
PDF_CANDIDATES = ["wyniki.pdf", "wynik.pdf"]

NUM_MIN = 1
NUM_MAX = 49
PICK_COUNT = 6
DRAWNO_MIN = 1000

DEFAULT_SEED = 123456

LOW_HIGH_THRESHOLD = 24

WINDOWS_SHORT = 20
WINDOWS_MEDIUM = 50
WINDOWS_LONG = 100
WINDOWS_ULTRA = 250

MAX_RECENT_OVERLAP = 3

DEFAULT_CANDIDATES = 6000
DEFAULT_TICKETS = 30

INT_RE = re.compile(r"\d+")


# =========================================================
# CSS
# =========================================================
APP_CSS = """
<style>
:root{
  --bg0:#f3fbf7;
  --bg1:#ffffff;
  --card:#ffffff;
  --card2:#f7fffb;
  --txt:#000000;
  --mut:#111827;
  --green:#00a86b;
  --green2:#00c27a;
  --gold:#d4af37;
  --blue:#2d77d1;
  --danger:#cf3b3b;
  --border: rgba(0,168,107,0.22);
  --shadow: 0 10px 28px rgba(0,0,0,.08);
}

.stApp{
  background-color: var(--bg0) !important;
  background-image:
    radial-gradient(1100px 700px at 12% 10%, rgba(0, 194, 122, 0.10), transparent 58%),
    radial-gradient(900px 600px at 92% 18%, rgba(0, 168, 107, 0.08), transparent 55%),
    linear-gradient(180deg, var(--bg0), var(--bg1)) !important;
  color: var(--txt) !important;
}

[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] *{
  color: var(--txt) !important;
}

.v-card{
  background: linear-gradient(180deg, var(--card), var(--card2));
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  border-radius: 18px;
  padding: 16px;
  margin-bottom: 16px;
}

.v-pill{
  display:inline-block;
  padding:6px 10px;
  margin:3px 4px 0 0;
  border-radius:999px;
  border:1px solid rgba(0,168,107,0.28);
  background:rgba(0,168,107,0.10);
  font-weight:900;
  color:#000000 !important;
}

.v-muted{
  opacity:.86;
  font-size:.92rem;
  color:var(--mut) !important;
}

.rank-card{
  background: linear-gradient(180deg, #ffffff, #f8fffb);
  border: 1px solid rgba(0,168,107,0.18);
  border-radius: 16px;
  padding: 14px 14px 12px 14px;
  margin: 10px 0;
  box-shadow: 0 8px 18px rgba(0,0,0,.05);
}

.rank-title{
  font-size: 1.05rem;
  font-weight: 900;
  margin-bottom: 6px;
  color:#000000 !important;
}

.rank-main{
  font-size: 1.2rem;
  font-weight: 1000;
  letter-spacing: .8px;
  margin-bottom: 6px;
  color:#000000 !important;
}

.rank-meta{
  font-size: .95rem;
  line-height: 1.55;
  color:#000000 !important;
}

div.stButton > button[kind="primary"]{
  background: linear-gradient(90deg, var(--green) 0%, var(--green2) 100%) !important;
  color: #000000 !important;
  border: 0 !important;
  border-radius: 14px !important;
  padding: 0.80rem 1.10rem !important;
  font-weight: 1000 !important;
  letter-spacing: .6px !important;
  box-shadow: 0 10px 22px rgba(0, 168, 107, 0.18) !important;
}

.btn-gold > button{
  background: linear-gradient(90deg, #d4af37 0%, #ffdf00 100%) !important;
  color: #000 !important;
  box-shadow: 0 10px 22px rgba(212, 175, 55, 0.4) !important;
}

[data-testid="stDataFrame"]{
  border-radius: 16px !important;
  overflow: hidden !important;
  border: 1px solid rgba(0, 168, 107, 0.22) !important;
}
</style>
"""


# =========================================================
# DATA MODELS
# =========================================================
@dataclass
class DrawRecord:
    draw_no: Optional[int]
    nums: List[int]
    date_str: str = "—"
    date_iso: str = ""


@dataclass
class TicketMetrics:
    ticket: List[int]
    final_score: float
    freq_score: float
    momentum_score: float
    overdue_score: float
    pair_score: float
    triple_score: float
    shape_score: float
    diversity_penalty: float
    recent_overlap_penalty: float
    odd_even: str
    low_high: str
    spread: int
    consecutive_pairs: int
    sum_total: int
    source: str


@dataclass
class EngineConfig:
    analysis_window: int
    candidate_count: int
    n_tickets: int
    seed: int
    max_recent_overlap: int
    hot_pool_size: int
    elite_pool_size: int
    soft_pool_size: int
    enable_local_search: bool
    local_search_steps: int


# =========================================================
# GENERAL HELPERS
# =========================================================
def resolve_pdf_path() -> Path:
    cwd = Path(os.getcwd())
    for name in PDF_CANDIDATES:
        p = cwd / name
        if p.exists():
            return p
    return cwd / PDF_CANDIDATES[0]


def sanitize_txt_filename(name: str) -> str:
    name = (name or "").strip()
    if not name:
        name = "wyniki.txt"
    name = name.replace("\\", "_").replace("/", "_").replace("..", "_")
    if not name.lower().endswith(".txt"):
        name += ".txt"
    return name


def even_odd_split(nums: List[int]) -> Tuple[int, int]:
    ev = sum(1 for n in nums if n % 2 == 0)
    od = len(nums) - ev
    return ev, od


def count_adjacent_pairs(nums_sorted: List[int]) -> int:
    return sum(1 for a, b in zip(nums_sorted, nums_sorted[1:]) if b == a + 1)


def has_run_length(nums_sorted: List[int], run_len: int) -> bool:
    if run_len <= 1:
        return True
    current = 1
    for a, b in zip(nums_sorted, nums_sorted[1:]):
        if b == a + 1:
            current += 1
            if current >= run_len:
                return True
        else:
            current = 1
    return False


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def zscore_series(values: List[float]) -> List[float]:
    if not values:
        return []
    arr = np.array(values, dtype=float)
    mean = arr.mean()
    std = arr.std()
    if std == 0:
        return [0.0] * len(values)
    return ((arr - mean) / std).tolist()


def safe_mean(values: Iterable[float], default: float = 0.0) -> float:
    vals = list(values)
    if not vals:
        return default
    return float(sum(vals) / len(vals))


def normalize_scores(score_map: Dict[int, float]) -> Dict[int, float]:
    if not score_map:
        return {}
    vals = list(score_map.values())
    mn = min(vals)
    mx = max(vals)
    if mx == mn:
        return {k: 0.0 for k in score_map}
    return {k: (v - mn) / (mx - mn) for k, v in score_map.items()}


def weighted_unique_sample(
    rng: np.random.Generator,
    population: List[int],
    weights: List[float],
    k: int
) -> List[int]:
    arr_pop = np.array(population, dtype=int)
    arr_w = np.array(weights, dtype=float)
    if len(arr_pop) < k:
        raise ValueError("Population smaller than k.")
    if arr_w.sum() <= 0:
        arr_w = np.ones_like(arr_w, dtype=float)
    probs = arr_w / arr_w.sum()
    chosen = rng.choice(arr_pop, size=k, replace=False, p=probs)
    return sorted(chosen.tolist())


# =========================================================
# PDF PARSER
# =========================================================
def _validate_pdf_bytes(pdf_bytes: bytes) -> None:
    if not pdf_bytes.startswith(b"%PDF"):
        head = pdf_bytes[:240].decode("utf-8", errors="replace")
        raise ValueError(
            "Plik nie wygląda jak prawdziwy PDF (brak nagłówka %PDF).\n"
            f"Początek pliku:\n{head}"
        )


def _read_pdf_pages_text(pdf_bytes: bytes) -> List[str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page in doc:
        pages.append(page.get_text("text") or "")
    doc.close()
    return pages


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", (line or "").strip())


def _is_noise_line(line: str) -> bool:
    low = line.lower()
    noise_fragments = [
        "lotto 6/49",
        "www.",
        "©",
        "multipasko",
        "drukuj",
        "reklama",
    ]
    return any(fragment in low for fragment in noise_fragments)


def _split_numbers_from_lines(page_text: str) -> Tuple[List[int], List[int]]:
    """
    Parser dostosowany do PDF drukowanego z DuckDuckGo / print page:
    - część górna zawiera wyniki (liczby 1..49),
    - część dolna zawiera numery losowań (np. 7329).
    """
    lines = [_clean_line(x) for x in page_text.splitlines()]
    lines = [ln for ln in lines if ln and not _is_noise_line(ln)]

    result_tokens: List[int] = []
    draw_numbers: List[int] = []
    drawno_mode = False

    for ln in lines:
        ints = [int(x) for x in INT_RE.findall(ln)]
        if not ints:
            continue

        has_large = any(x >= DRAWNO_MIN for x in ints)
        has_small_lotto = any(NUM_MIN <= x <= NUM_MAX for x in ints)

        # jeżeli linia jest "czysto numerami losowań", przechodzimy do sekcji draw_no
        if has_large and not has_small_lotto:
            drawno_mode = True

        if not drawno_mode:
            for x in ints:
                if NUM_MIN <= x <= NUM_MAX:
                    result_tokens.append(x)
        else:
            for x in ints:
                if DRAWNO_MIN <= x < 100000:
                    draw_numbers.append(x)

    return result_tokens, draw_numbers


def _chunk_tokens_to_draws(tokens: List[int]) -> List[List[int]]:
    """
    Szuka najlepszego przesunięcia i buduje losowania po 6 liczb.
    """
    if len(tokens) < PICK_COUNT:
        return []

    best_draws: List[List[int]] = []
    best_score = -1

    for offset in range(PICK_COUNT):
        sliced = tokens[offset:]
        usable = (len(sliced) // PICK_COUNT) * PICK_COUNT
        sliced = sliced[:usable]
        draws: List[List[int]] = []
        score = 0

        for i in range(0, len(sliced), PICK_COUNT):
            draw = sorted(sliced[i:i + PICK_COUNT])
            draws.append(draw)

            unique_ok = len(set(draw)) == PICK_COUNT
            range_ok = all(NUM_MIN <= n <= NUM_MAX for n in draw)
            spread_ok = (draw[-1] - draw[0]) >= 8
            if unique_ok and range_ok:
                score += 3
            if spread_ok:
                score += 1

        if score > best_score:
            best_score = score
            best_draws = draws

    # finalna walidacja: bierzemy tylko sensowne zestawy
    validated = []
    for d in best_draws:
        if len(d) == PICK_COUNT and len(set(d)) == PICK_COUNT and all(NUM_MIN <= x <= NUM_MAX for x in d):
            validated.append(d)

    return validated


def _pair_draws_with_drawnos(draws: List[List[int]], drawnos: List[int]) -> List[DrawRecord]:
    n = min(len(draws), len(drawnos))
    records: List[DrawRecord] = []

    for i in range(n):
        records.append(DrawRecord(
            draw_no=drawnos[i],
            nums=draws[i],
            date_str="—",
            date_iso=""
        ))

    for j in range(n, len(draws)):
        records.append(DrawRecord(
            draw_no=None,
            nums=draws[j],
            date_str="—",
            date_iso=""
        ))

    # jeśli mamy sporo draw_no, sortujemy malejąco po numerach losowania
    with_numbers = [r for r in records if r.draw_no is not None]
    if len(with_numbers) > 10:
        records.sort(key=lambda r: (r.draw_no is None, r.draw_no or -1), reverse=True)

    return records


@st.cache_data(show_spinner=False)
def load_records_cached(pdf_bytes: bytes) -> List[DrawRecord]:
    _validate_pdf_bytes(pdf_bytes)
    pages = _read_pdf_pages_text(pdf_bytes)

    all_tokens: List[int] = []
    all_drawnos: List[int] = []

    for page_text in pages:
        tokens, drawnos = _split_numbers_from_lines(page_text)
        all_tokens.extend(tokens)
        all_drawnos.extend(drawnos)

    draws = _chunk_tokens_to_draws(all_tokens)
    if not draws:
        raise RuntimeError("Nie udało się wyciągnąć poprawnych losowań z PDF.")

    records = _pair_draws_with_drawnos(draws, all_drawnos)

    if len(records) < 20:
        raise RuntimeError(
            f"Wyciągnięto zbyt mało rekordów ({len(records)}). "
            "Sprawdź, czy PDF ma prawidłowy układ."
        )

    return records


# =========================================================
# ANALYSIS CORE
# =========================================================
@st.cache_data(show_spinner=False)
def compute_presence_df_cached(draws: List[List[int]]) -> pd.DataFrame:
    total = len(draws)
    counter = Counter()
    for draw in draws:
        for n in set(draw):
            counter[n] += 1

    rows = []
    for n in range(NUM_MIN, NUM_MAX + 1):
        hits = counter.get(n, 0)
        pct = (hits / total * 100.0) if total else 0.0
        rows.append({
            "Liczba": n,
            "Losowania_z_wystapieniem": hits,
            "Procent_losowan": pct
        })

    df = pd.DataFrame(rows).sort_values(
        ["Procent_losowan", "Losowania_z_wystapieniem", "Liczba"],
        ascending=[False, False, True]
    ).reset_index(drop=True)
    return df


@st.cache_data(show_spinner=False)
def compute_pair_triple_counters_cached(draws: List[List[int]]) -> Tuple[Counter, Counter]:
    pair_counter = Counter()
    triple_counter = Counter()

    for draw in draws:
        s = sorted(draw)
        for pair in combinations(s, 2):
            pair_counter[pair] += 1
        for triple in combinations(s, 3):
            triple_counter[triple] += 1

    return pair_counter, triple_counter


@st.cache_data(show_spinner=False)
def compute_last_seen_map_cached(draws: List[List[int]]) -> Dict[int, int]:
    result = {}
    for n in range(NUM_MIN, NUM_MAX + 1):
        result[n] = 999999
        for idx, draw in enumerate(draws):
            if n in draw:
                result[n] = idx
                break
    return result


@st.cache_data(show_spinner=False)
def compute_gap_stats_cached(draws: List[List[int]]) -> pd.DataFrame:
    chronological = list(reversed(draws))
    total = len(chronological)

    rows = []
    for num in range(NUM_MIN, NUM_MAX + 1):
        positions = []
        for idx, draw in enumerate(chronological):
            if num in draw:
                positions.append(idx)

        occurrences = len(positions)
        if occurrences >= 2:
            gaps = [b - a for a, b in zip(positions[:-1], positions[1:])]
            avg_gap = safe_mean(gaps, 0.0)
            current_gap = float((total - 1) - positions[-1])
            ratio = (current_gap / avg_gap) if avg_gap > 0 else 0.0
        elif occurrences == 1:
            avg_gap = 0.0
            current_gap = float((total - 1) - positions[-1])
            ratio = 0.0
        else:
            avg_gap = 0.0
            current_gap = float(total)
            ratio = 0.0

        rows.append({
            "Liczba": num,
            "Wystąpienia": occurrences,
            "Średni_gap": round(avg_gap, 3),
            "Aktualny_gap": round(current_gap, 3),
            "Gap_ratio": round(ratio, 3)
        })

    return pd.DataFrame(rows).sort_values(
        ["Gap_ratio", "Wystąpienia", "Liczba"],
        ascending=[False, False, True]
    ).reset_index(drop=True)


def build_shape_profile(draws: List[List[int]]) -> Dict:
    if not draws:
        return {
            "target_even_odd": (3, 3),
            "target_low_high": (3, 3),
            "target_sum": 150.0,
            "target_spread": 30.0,
            "target_adj_pairs": 0.8,
        }

    eo_counter = Counter()
    lh_counter = Counter()
    sums = []
    spreads = []
    adj_pairs = []

    for draw in draws:
        s = sorted(draw)
        ev, od = even_odd_split(s)
        low = sum(1 for x in s if x <= LOW_HIGH_THRESHOLD)
        high = PICK_COUNT - low

        eo_counter[(ev, od)] += 1
        lh_counter[(low, high)] += 1
        sums.append(sum(s))
        spreads.append(s[-1] - s[0])
        adj_pairs.append(count_adjacent_pairs(s))

    return {
        "target_even_odd": eo_counter.most_common(1)[0][0] if eo_counter else (3, 3),
        "target_low_high": lh_counter.most_common(1)[0][0] if lh_counter else (3, 3),
        "target_sum": safe_mean(sums, 150.0),
        "target_spread": safe_mean(spreads, 30.0),
        "target_adj_pairs": safe_mean(adj_pairs, 0.8),
    }


def build_frequency_windows(draws: List[List[int]]) -> Dict[str, Dict[int, float]]:
    """
    Liczy częstości na wielu oknach naraz.
    """
    def pct_map(sub_draws: List[List[int]]) -> Dict[int, float]:
        total = len(sub_draws)
        c = Counter()
        for d in sub_draws:
            for n in set(d):
                c[n] += 1
        return {n: (c.get(n, 0) / total if total else 0.0) for n in range(NUM_MIN, NUM_MAX + 1)}

    return {
        "w20": pct_map(draws[:min(WINDOWS_SHORT, len(draws))]),
        "w50": pct_map(draws[:min(WINDOWS_MEDIUM, len(draws))]),
        "w100": pct_map(draws[:min(WINDOWS_LONG, len(draws))]),
        "w250": pct_map(draws[:min(WINDOWS_ULTRA, len(draws))]),
        "wall": pct_map(draws),
    }


def build_number_feature_table(draws: List[List[int]]) -> pd.DataFrame:
    freq_windows = build_frequency_windows(draws)
    gap_df = compute_gap_stats_cached(draws)
    gap_map = dict(zip(gap_df["Liczba"], gap_df["Gap_ratio"]))
    last_seen_map = compute_last_seen_map_cached(draws)

    rows = []
    for n in range(NUM_MIN, NUM_MAX + 1):
        f20 = freq_windows["w20"].get(n, 0.0)
        f50 = freq_windows["w50"].get(n, 0.0)
        f100 = freq_windows["w100"].get(n, 0.0)
        f250 = freq_windows["w250"].get(n, 0.0)
        fall = freq_windows["wall"].get(n, 0.0)

        # momentum: większy nacisk na świeże okna, ale nie ignorujemy długiego tła
        momentum = (
            f20 * 0.42 +
            f50 * 0.28 +
            f100 * 0.16 +
            f250 * 0.08 +
            fall * 0.06
        )

        # overdue umiarkowanie: nie przesadzamy z "długo nie było = zaraz będzie"
        overdue_ratio = min(float(gap_map.get(n, 0.0)), 3.0) / 3.0

        # recency penalty: jeśli liczba padła bardzo niedawno, lekka kara
        last_seen = last_seen_map.get(n, 999999)
        if last_seen == 0:
            recency_penalty = 1.00
        elif last_seen == 1:
            recency_penalty = 0.65
        elif last_seen == 2:
            recency_penalty = 0.35
        else:
            recency_penalty = 0.0

        base_strength = (
            momentum * 0.72 +
            overdue_ratio * 0.28
        ) - (recency_penalty * 0.10)

        rows.append({
            "Liczba": n,
            "Freq20": f20,
            "Freq50": f50,
            "Freq100": f100,
            "Freq250": f250,
            "FreqAll": fall,
            "Momentum": momentum,
            "GapRatio": gap_map.get(n, 0.0),
            "LastSeenIdx": last_seen,
            "RecencyPenalty": recency_penalty,
            "BaseStrength": base_strength,
        })

    df = pd.DataFrame(rows)

    # normalizacja dodatkowych pól
    for col in ["Freq20", "Freq50", "Freq100", "Freq250", "FreqAll", "Momentum", "GapRatio", "BaseStrength"]:
        vals = df[col].tolist()
        df[col + "_Norm"] = normalize_scores(dict(zip(df["Liczba"], vals))).values()

    df = df.sort_values(["BaseStrength", "Momentum", "Liczba"], ascending=[False, False, True]).reset_index(drop=True)
    return df


def build_hot_cold_groups(feature_df: pd.DataFrame, hot_size: int, cold_size: int) -> Tuple[List[int], List[int], List[int]]:
    hot = feature_df.head(hot_size)["Liczba"].tolist()
    cold = feature_df.tail(cold_size)["Liczba"].tolist()
    neutral = [n for n in range(NUM_MIN, NUM_MAX + 1) if n not in hot and n not in cold]
    return hot, cold, neutral


def build_elite_and_soft_pools(feature_df: pd.DataFrame, elite_size: int, soft_size: int) -> Tuple[List[int], List[int]]:
    elite = feature_df.head(elite_size)["Liczba"].tolist()
    soft = feature_df.head(soft_size)["Liczba"].tolist()
    return elite, soft


# =========================================================
# SCORING
# =========================================================
def similarity_to_recent(ticket: List[int], recent_draws: List[List[int]]) -> int:
    tset = set(ticket)
    if not recent_draws:
        return 0
    return max(len(tset.intersection(set(d))) for d in recent_draws)


def ticket_shape_values(ticket: List[int]) -> Dict[str, object]:
    s = sorted(ticket)
    ev, od = even_odd_split(s)
    low = sum(1 for x in s if x <= LOW_HIGH_THRESHOLD)
    high = PICK_COUNT - low
    spread = s[-1] - s[0]
    adj_pairs = count_adjacent_pairs(s)
    total_sum = sum(s)
    return {
        "ev": ev,
        "od": od,
        "low": low,
        "high": high,
        "spread": spread,
        "adj_pairs": adj_pairs,
        "sum_total": total_sum,
    }


def build_pair_triple_strength_maps(
    pair_counter: Counter,
    triple_counter: Counter
) -> Tuple[Dict[Tuple[int, int], float], Dict[Tuple[int, int, int], float]]:
    pair_map = {}
    triple_map = {}

    if pair_counter:
        max_pair = max(pair_counter.values())
        for k, v in pair_counter.items():
            pair_map[k] = v / max_pair

    if triple_counter:
        max_triple = max(triple_counter.values())
        for k, v in triple_counter.items():
            triple_map[k] = v / max_triple

    return pair_map, triple_map


def score_ticket(
    ticket: List[int],
    feature_df: pd.DataFrame,
    pair_map: Dict[Tuple[int, int], float],
    triple_map: Dict[Tuple[int, int, int], float],
    profile: Dict,
    recent_draws: List[List[int]],
    max_recent_overlap: int,
    source: str
) -> TicketMetrics:
    s = sorted(ticket)
    feat_map = feature_df.set_index("Liczba").to_dict("index")

    shape = ticket_shape_values(s)

    # 1. siła liczb
    freq_score = sum(feat_map[n]["FreqAll_Norm"] for n in s) / PICK_COUNT
    momentum_score = sum(feat_map[n]["Momentum_Norm"] for n in s) / PICK_COUNT
    overdue_score = sum(feat_map[n]["GapRatio_Norm"] for n in s) / PICK_COUNT

    # 2. synergia par / trójek
    pair_score = safe_mean([pair_map.get(tuple(pair), 0.0) for pair in combinations(s, 2)], 0.0)
    triple_score = safe_mean([triple_map.get(tuple(triple), 0.0) for triple in combinations(s, 3)], 0.0)

    # 3. kształt kuponu
    target_ev, target_od = profile["target_even_odd"]
    target_low, target_high = profile["target_low_high"]

    even_odd_pen = abs(shape["ev"] - target_ev) + abs(shape["od"] - target_od)
    low_high_pen = abs(shape["low"] - target_low) + abs(shape["high"] - target_high)
    spread_pen = abs(shape["spread"] - profile["target_spread"]) / 25.0
    sum_pen = abs(shape["sum_total"] - profile["target_sum"]) / 45.0
    adj_pen = abs(shape["adj_pairs"] - profile["target_adj_pairs"]) / 2.0

    shape_score = max(0.0, 1.0 - (even_odd_pen * 0.10 + low_high_pen * 0.10 + spread_pen * 0.10 + sum_pen * 0.12 + adj_pen * 0.08))

    # 4. kara za zbyt podobne do ostatnich
    recent_overlap = similarity_to_recent(s, recent_draws)
    recent_overlap_penalty = 0.0
    if recent_overlap > max_recent_overlap:
        recent_overlap_penalty = (recent_overlap - max_recent_overlap) * 0.30
    else:
        recent_overlap_penalty = recent_overlap * 0.05

    # 5. kary za "dziwne" struktury
    diversity_penalty = 0.0
    if has_run_length(s, 4):
        diversity_penalty += 0.65
    elif has_run_length(s, 3):
        diversity_penalty += 0.28

    if shape["adj_pairs"] >= 3:
        diversity_penalty += 0.20

    if shape["ev"] in (0, 6) or shape["od"] in (0, 6):
        diversity_penalty += 0.40

    if shape["low"] in (0, 6) or shape["high"] in (0, 6):
        diversity_penalty += 0.35

    # 6. score końcowy — bardziej zdyscyplinowany niż stara wersja
    final_score = (
        freq_score * 1.65 +
        momentum_score * 2.20 +
        overdue_score * 0.85 +
        pair_score * 0.90 +
        triple_score * 1.10 +
        shape_score * 1.55
        - diversity_penalty
        - recent_overlap_penalty
    )

    return TicketMetrics(
        ticket=s,
        final_score=round(final_score, 6),
        freq_score=round(freq_score, 6),
        momentum_score=round(momentum_score, 6),
        overdue_score=round(overdue_score, 6),
        pair_score=round(pair_score, 6),
        triple_score=round(triple_score, 6),
        shape_score=round(shape_score, 6),
        diversity_penalty=round(diversity_penalty, 6),
        recent_overlap_penalty=round(recent_overlap_penalty, 6),
        odd_even=f"{shape['ev']}/{shape['od']}",
        low_high=f"{shape['low']}/{shape['high']}",
        spread=shape["spread"],
        consecutive_pairs=shape["adj_pairs"],
        sum_total=shape["sum_total"],
        source=source
    )


# =========================================================
# CANDIDATE GENERATION
# =========================================================
def build_generation_weights(feature_df: pd.DataFrame) -> Dict[int, float]:
    weights = {}
    feat_map = feature_df.set_index("Liczba").to_dict("index")

    for n in range(NUM_MIN, NUM_MAX + 1):
        rec = feat_map[n]

        # siła podstawowa
        w = (
            rec["BaseStrength_Norm"] * 0.55 +
            rec["Momentum_Norm"] * 0.25 +
            rec["Freq50_Norm"] * 0.10 +
            rec["Freq100_Norm"] * 0.05 +
            rec["GapRatio_Norm"] * 0.05
        )

        # twarde ograniczenie skrajnie świeżych liczb
        if rec["LastSeenIdx"] == 0:
            w *= 0.88
        elif rec["LastSeenIdx"] == 1:
            w *= 0.94

        weights[n] = max(w, 0.0001)

    return weights


def generate_weighted_candidate(
    rng: np.random.Generator,
    generation_weights: Dict[int, float],
    elite_pool: List[int],
    soft_pool: List[int]
) -> List[int]:
    """
    Generator hybrydowy:
    - 2 lub 3 liczby z elite,
    - reszta z szerszej puli ważonej.
    """
    elite_take = int(rng.choice([2, 3, 4], p=[0.30, 0.45, 0.25]))
    elite_take = min(elite_take, PICK_COUNT)

    elite_weights = [generation_weights[n] for n in elite_pool]
    elite_part = weighted_unique_sample(rng, elite_pool, elite_weights, elite_take)

    remaining_count = PICK_COUNT - elite_take
    remaining_population = [n for n in soft_pool if n not in elite_part]
    if len(remaining_population) < remaining_count:
        remaining_population = [n for n in range(NUM_MIN, NUM_MAX + 1) if n not in elite_part]

    remaining_weights = [generation_weights[n] for n in remaining_population]
    rest = weighted_unique_sample(rng, remaining_population, remaining_weights, remaining_count)

    return sorted(elite_part + rest)


def generate_diverse_candidate(
    rng: np.random.Generator,
    generation_weights: Dict[int, float],
    full_pool: List[int]
) -> List[int]:
    """
    Drugi generator: bardziej szeroki, by nie zamknąć się tylko w hotach.
    """
    weights = [generation_weights[n] for n in full_pool]
    return weighted_unique_sample(rng, full_pool, weights, PICK_COUNT)


def mutate_ticket(
    rng: np.random.Generator,
    ticket: List[int],
    generation_weights: Dict[int, float],
    soft_pool: List[int],
    replace_count: int
) -> List[int]:
    current = sorted(ticket)
    replace_count = min(replace_count, PICK_COUNT)

    to_remove = set(rng.choice(current, size=replace_count, replace=False).tolist())
    kept = [n for n in current if n not in to_remove]

    candidates = [n for n in soft_pool if n not in kept]
    if len(candidates) < (PICK_COUNT - len(kept)):
        candidates = [n for n in range(NUM_MIN, NUM_MAX + 1) if n not in kept]

    weights = [generation_weights[n] for n in candidates]
    added = weighted_unique_sample(rng, candidates, weights, PICK_COUNT - len(kept))

    return sorted(kept + added)


def local_search_improve(
    rng: np.random.Generator,
    ticket: List[int],
    generation_weights: Dict[int, float],
    soft_pool: List[int],
    score_fn,
    steps: int
) -> List[int]:
    best = sorted(ticket)
    best_score = score_fn(best).final_score

    for _ in range(steps):
        replace_count = int(rng.choice([1, 2], p=[0.75, 0.25]))
        candidate = mutate_ticket(rng, best, generation_weights, soft_pool, replace_count)
        candidate_score = score_fn(candidate).final_score
        if candidate_score > best_score:
            best = candidate
            best_score = candidate_score

    return best


def build_candidates(
    draws: List[List[int]],
    feature_df: pd.DataFrame,
    pair_map: Dict[Tuple[int, int], float],
    triple_map: Dict[Tuple[int, int, int], float],
    profile: Dict,
    cfg: EngineConfig
) -> List[TicketMetrics]:
    rng = np.random.default_rng(cfg.seed)

    recent_draws = draws[:10]
    generation_weights = build_generation_weights(feature_df)

    elite_pool, soft_pool = build_elite_and_soft_pools(
        feature_df,
        elite_size=cfg.elite_pool_size,
        soft_size=cfg.soft_pool_size
    )
    full_pool = list(range(NUM_MIN, NUM_MAX + 1))

    def score_fn(ticket: List[int], source: str = "gen") -> TicketMetrics:
        return score_ticket(
            ticket=ticket,
            feature_df=feature_df,
            pair_map=pair_map,
            triple_map=triple_map,
            profile=profile,
            recent_draws=recent_draws,
            max_recent_overlap=cfg.max_recent_overlap,
            source=source
        )

    uniq = set()
    results: List[TicketMetrics] = []

    target = cfg.candidate_count
    hard_limit = target * 5
    attempts = 0

    while len(results) < target and attempts < hard_limit:
        attempts += 1

        mode = rng.choice(
            ["weighted", "diverse", "mutated"],
            p=[0.56, 0.24, 0.20]
        )

        if mode == "weighted":
            ticket = generate_weighted_candidate(rng, generation_weights, elite_pool, soft_pool)
            source = "weighted"
        elif mode == "diverse":
            ticket = generate_diverse_candidate(rng, generation_weights, full_pool)
            source = "diverse"
        else:
            seed_ticket = generate_weighted_candidate(rng, generation_weights, elite_pool, soft_pool)
            ticket = mutate_ticket(rng, seed_ticket, generation_weights, soft_pool, replace_count=int(rng.choice([1, 2])))
            source = "mutated"

        key = tuple(ticket)
        if key in uniq:
            continue

        if cfg.enable_local_search:
            improved = local_search_improve(
                rng=rng,
                ticket=ticket,
                generation_weights=generation_weights,
                soft_pool=soft_pool,
                score_fn=lambda t: score_fn(t, source="local_search"),
                steps=cfg.local_search_steps
            )
            ticket = improved
            key = tuple(ticket)
            if key in uniq:
                continue

        uniq.add(key)
        results.append(score_fn(ticket, source=source))

    results.sort(key=lambda x: x.final_score, reverse=True)
    return results


# =========================================================
# SPECIAL ENGINES
# =========================================================
def build_momentum_master_ticket(feature_df: pd.DataFrame, seed: int) -> Dict:
    rng = np.random.default_rng(seed)

    top_df = feature_df.head(15).copy()
    population = top_df["Liczba"].tolist()

    weights = []
    for _, row in top_df.iterrows():
        w = (
            row["Momentum_Norm"] * 0.55 +
            row["BaseStrength_Norm"] * 0.25 +
            row["GapRatio_Norm"] * 0.20
        )
        weights.append(max(w, 0.001))

    ticket = weighted_unique_sample(rng, population, weights, PICK_COUNT)
    avg_strength = safe_mean(
        feature_df.set_index("Liczba").loc[ticket]["BaseStrength"].tolist(),
        0.0
    )

    return {
        "ticket": ticket,
        "avg_strength": round(avg_strength, 6),
        "details": top_df
    }


def build_hot6_ticket(feature_df: pd.DataFrame) -> List[int]:
    return sorted(feature_df.head(PICK_COUNT)["Liczba"].tolist())


def build_cycle_ticket(draws: List[List[int]]) -> Tuple[List[int], pd.DataFrame]:
    cycle_df = compute_gap_stats_cached(draws)
    ticket = sorted(cycle_df.head(PICK_COUNT)["Liczba"].tolist())
    return ticket, cycle_df


def build_daily_ticket(draws: List[List[int]], feature_df: pd.DataFrame, seed: int) -> Dict:
    rng = np.random.default_rng(seed)

    top_pool = feature_df.head(20)["Liczba"].tolist()
    top_weights = (
        feature_df.head(20)["Momentum_Norm"] * 0.55 +
        feature_df.head(20)["Freq20_Norm"] * 0.25 +
        feature_df.head(20)["GapRatio_Norm"] * 0.20
    ).tolist()

    history10 = draws[:10]
    flat10 = [x for d in history10 for x in d]

    ev = sum(1 for x in flat10 if x % 2 == 0)
    od = len(flat10) - ev
    parity_pref = "EVEN" if ev > od else ("ODD" if od > ev else "ANY")

    last2 = draws[:2]
    flat2 = [x for d in last2 for x in d]
    low = sum(1 for x in flat2 if x <= LOW_HIGH_THRESHOLD)
    high = len(flat2) - low
    level_pref = "HIGH" if low >= high + 2 else ("LOW" if high >= low + 2 else "ANY")

    best = None
    best_score = -999999.0

    for _ in range(600):
        cand = weighted_unique_sample(rng, top_pool, top_weights, PICK_COUNT)
        cand = sorted(cand)

        score = 0.0
        c_ev, c_od = even_odd_split(cand)
        c_low = sum(1 for x in cand if x <= LOW_HIGH_THRESHOLD)
        c_high = PICK_COUNT - c_low
        spread = cand[-1] - cand[0]

        if parity_pref == "EVEN":
            score += c_ev * 0.35
        elif parity_pref == "ODD":
            score += c_od * 0.35

        if level_pref == "HIGH":
            score += c_high * 0.30
        elif level_pref == "LOW":
            score += c_low * 0.30

        target_spread = safe_mean([(max(d) - min(d)) for d in history10], 30.0)
        score -= abs(spread - target_spread) * 0.08

        if score > best_score:
            best_score = score
            best = cand

    return {
        "ticket": best if best else build_hot6_ticket(feature_df),
        "parity_pref": parity_pref,
        "level_pref": level_pref,
    }


# =========================================================
# TXT EXPORTS
# =========================================================
def lines_to_txt_bytes(lines: List[str]) -> bytes:
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_txt_for_results(records: List[DrawRecord]) -> bytes:
    lines = []
    for r in records:
        nums = " ".join(f"{x:02d}" for x in r.nums)
        draw_str = str(r.draw_no) if r.draw_no is not None else "—"
        lines.append(f"Losowanie: {draw_str} | Data: {r.date_str} | Wynik: {nums}")
    return lines_to_txt_bytes(lines)


def make_txt_for_ticket_metrics(metrics: List[TicketMetrics]) -> bytes:
    lines = []
    for i, m in enumerate(metrics, start=1):
        nums = " ".join(f"{x:02d}" for x in m.ticket)
        lines.append(
            f"#{i:03d} | {nums} | Final={m.final_score:.6f} | "
            f"Freq={m.freq_score:.6f} | Momentum={m.momentum_score:.6f} | "
            f"Overdue={m.overdue_score:.6f} | Pair={m.pair_score:.6f} | "
            f"Triple={m.triple_score:.6f} | Shape={m.shape_score:.6f} | "
            f"Kary={m.diversity_penalty + m.recent_overlap_penalty:.6f} | "
            f"EO={m.odd_even} | LH={m.low_high} | Spread={m.spread} | "
            f"Adj={m.consecutive_pairs} | Sum={m.sum_total} | Source={m.source}"
        )
    return lines_to_txt_bytes(lines)


def make_txt_for_simple_ticket(title: str, ticket: List[int], extra_lines: Optional[List[str]] = None) -> bytes:
    lines = [title, f"Kupon: {' '.join(f'{x:02d}' for x in ticket)}"]
    if extra_lines:
        lines.extend([""] + extra_lines)
    return lines_to_txt_bytes(lines)


# =========================================================
# UI HELPERS
# =========================================================
def render_ticket_card(idx: int, metric: TicketMetrics) -> None:
    nums_str = " ".join(f"{x:02d}" for x in metric.ticket)
    st.markdown(
        f"""
<div class="rank-card">
  <div class="rank-title">Kupon #{idx:03d}</div>
  <div class="rank-main">{nums_str}</div>
  <div class="rank-meta">
    Final Score: <b>{metric.final_score:.4f}</b><br>
    Freq: <b>{metric.freq_score:.4f}</b> | Momentum: <b>{metric.momentum_score:.4f}</b> | Overdue: <b>{metric.overdue_score:.4f}</b><br>
    Pair: <b>{metric.pair_score:.4f}</b> | Triple: <b>{metric.triple_score:.4f}</b> | Shape: <b>{metric.shape_score:.4f}</b><br>
    Parzyste/Nieparzyste: <b>{metric.odd_even}</b> | Niskie/Wysokie: <b>{metric.low_high}</b><br>
    Rozstrzał: <b>{metric.spread}</b> | Pary kolejne: <b>{metric.consecutive_pairs}</b> | Suma: <b>{metric.sum_total}</b><br>
    Kara za różnorodność: <b>{metric.diversity_penalty:.4f}</b> | Kara za podobieństwo do ostatnich: <b>{metric.recent_overlap_penalty:.4f}</b><br>
    Źródło: <b>{metric.source}</b>
  </div>
</div>
        """,
        unsafe_allow_html=True
    )


def render_feature_table(feature_df: pd.DataFrame) -> None:
    display_df = feature_df.copy()
    cols_round = [
        "Freq20", "Freq50", "Freq100", "Freq250", "FreqAll",
        "Momentum", "GapRatio", "BaseStrength"
    ]
    for col in cols_round:
        display_df[col] = display_df[col].map(lambda x: round(float(x), 6))
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def session_init() -> None:
    defaults = {
        "generated_metrics": None,
        "daily_ticket": None,
        "hot6_ticket": None,
        "momentum_ticket": None,
        "cycle_ticket": None,
        "cycle_df": None,
        "show_results": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def settings_panel(max_records: int) -> Dict:
    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("⚙️ Ustawienia silnika")

    analysis_window = st.selectbox(
        "Ile ostatnich losowań analizować?",
        options=[50, 100, 250, 500, 750, 1000, max_records],
        index=5 if max_records >= 1000 else len([x for x in [50,100,250,500,750,1000,max_records] if x <= max_records]) - 1
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        candidate_count = st.slider("Kandydaci do oceny", 1000, 20000, DEFAULT_CANDIDATES, 500)
    with c2:
        n_tickets = st.slider("Ile finalnych kuponów", 1, 100, DEFAULT_TICKETS, 1)
    with c3:
        seed = st.number_input("Seed losowania", min_value=1, max_value=999999999, value=DEFAULT_SEED, step=1)

    c4, c5, c6 = st.columns(3)
    with c4:
        max_recent_overlap = st.slider("Maks. podobieństwo do ostatnich losowań", 1, 6, 3, 1)
    with c5:
        hot_pool_size = st.slider("Pula HOT", 10, 35, 20, 1)
    with c6:
        elite_pool_size = st.slider("Pula ELITE", 6, 20, 12, 1)

    soft_pool_size = st.slider("Pula SOFT (szersza pula premium)", 15, 49, 28, 1)

    enable_local_search = st.checkbox("Włącz dopieszczanie kuponu (local search)", value=True)
    local_search_steps = st.slider("Liczba kroków local search", 0, 20, 6, 1) if enable_local_search else 0

    st.markdown("</div>", unsafe_allow_html=True)

    return {
        "analysis_window": int(analysis_window),
        "candidate_count": int(candidate_count),
        "n_tickets": int(n_tickets),
        "seed": int(seed),
        "max_recent_overlap": int(max_recent_overlap),
        "hot_pool_size": int(hot_pool_size),
        "elite_pool_size": int(elite_pool_size),
        "soft_pool_size": int(soft_pool_size),
        "enable_local_search": bool(enable_local_search),
        "local_search_steps": int(local_search_steps),
    }


# =========================================================
# MAIN
# =========================================================
def main() -> None:
    st.set_page_config(
        page_title="Victory Lotto Pro",
        page_icon="🏆",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    st.markdown(APP_CSS, unsafe_allow_html=True)

    st.title(APP_TITLE)
    st.write(
        "Nowa wersja aplikacji do analizy historii losowań Lotto 6/49 z pliku "
        "**wyniki.pdf** / **wynik.pdf**. "
        "Parser jest przygotowany pod PDF zapisany przez funkcję **drukuj stronę**."
    )

    session_init()

    pdf_path = resolve_pdf_path()

    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("📄 Źródło danych")
    st.write(f"Plik wejściowy: `{pdf_path}`")
    st.write("Silnik odczytu PDF: **PyMuPDF (fitz)**")
    st.markdown(
        '<div class="v-muted">Aplikacja zakłada układ PDF podobny do tego, który zapisujesz przez „drukuj stronę” w aplikacji DuckDuckGo.</div>',
        unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)

    if not pdf_path.exists():
        st.error("❌ Nie znaleziono pliku `wyniki.pdf` ani `wynik.pdf` obok `app.py`.")
        st.stop()

    try:
        pdf_bytes = pdf_path.read_bytes()
        all_records = load_records_cached(pdf_bytes)
    except Exception as e:
        logger.exception("Błąd podczas odczytu PDF")
        st.error("❌ Nie udało się odczytać lub sparsować PDF.")
        st.code(str(e))
        st.stop()

    cfg_raw = settings_panel(max_records=len(all_records))
    cfg = EngineConfig(**cfg_raw)

    used_window = min(cfg.analysis_window, len(all_records))
    used_records = all_records[:used_window]
    draws = [r.nums for r in used_records]

    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("📊 Diagnostyka danych")
    st.success(f"✅ Odczytano rekordów z PDF: **{len(all_records)}**")
    st.info(f"✅ Do analizy użyto: **{used_window}** najnowszych losowań")
    st.markdown("</div>", unsafe_allow_html=True)

    feature_df = build_number_feature_table(draws)
    pair_counter, triple_counter = compute_pair_triple_counters_cached(draws)
    pair_map, triple_map = build_pair_triple_strength_maps(pair_counter, triple_counter)
    shape_profile = build_shape_profile(draws)

    hot, cold, neutral = build_hot_cold_groups(
        feature_df=feature_df,
        hot_size=cfg.hot_pool_size,
        cold_size=min(cfg.hot_pool_size, 49 - cfg.hot_pool_size)
    )

    left, right = st.columns([1.25, 0.75], gap="large")

    with left:
        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("📈 Tabela siły liczb 1–49")
        render_feature_table(feature_df)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🔥 HOT / ❄️ COLD")
        st.markdown("**HOT**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in hot]), unsafe_allow_html=True)
        st.markdown("**COLD**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in cold]), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🎯 Profil typowego losowania")
        st.write(f"Parzyste/Nieparzyste: **{shape_profile['target_even_odd'][0]}/{shape_profile['target_even_odd'][1]}**")
        st.write(f"Niskie/Wysokie: **{shape_profile['target_low_high'][0]}/{shape_profile['target_low_high'][1]}**")
        st.write(f"Średni rozstrzał: **{shape_profile['target_spread']:.2f}**")
        st.write(f"Średnia suma: **{shape_profile['target_sum']:.2f}**")
        st.write(f"Średnia liczba par kolejnych: **{shape_profile['target_adj_pairs']:.2f}**")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("🎟️ Narzędzia")

    c1, c2, c3, c4 = st.columns(4, gap="large")
    with c1:
        generate_btn = st.button("🏆 GENERUJ KU PONY PRO", type="primary", use_container_width=True)
        daily_btn = st.button("🌿 KU PON DNIA", type="primary", use_container_width=True)
    with c2:
        hot6_btn = st.button("🔥 HOT 6", type="primary", use_container_width=True)
        show_results_btn = st.button("📋 POKAŻ WYNIKI", type="primary", use_container_width=True)
    with c3:
        cycle_btn = st.button("🔄 CYKLE", type="primary", use_container_width=True)
        feature_export_btn = st.button("📊 TOP / LOW", type="primary", use_container_width=True)
    with c4:
        st.markdown('<div class="btn-gold">', unsafe_allow_html=True)
        momentum_btn = st.button("🌟 MOMENTUM MASTER", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    if show_results_btn:
        st.session_state["show_results"] = not st.session_state["show_results"]

    if generate_btn:
        progress = st.progress(0)
        status = st.empty()

        with st.spinner("Buduję kandydatów, punktuję i wybieram najlepsze kupony..."):
            metrics = build_candidates(
                draws=draws,
                feature_df=feature_df,
                pair_map=pair_map,
                triple_map=triple_map,
                profile=shape_profile,
                cfg=cfg
            )
            st.session_state["generated_metrics"] = metrics[:cfg.n_tickets]
            progress.progress(100)
            status.write(f"Wygenerowano i oceniono {len(metrics)} unikalnych kandydatów.")

        progress.empty()
        status.empty()

    if daily_btn:
        st.session_state["daily_ticket"] = build_daily_ticket(draws, feature_df, seed=cfg.seed + 7)

    if hot6_btn:
        st.session_state["hot6_ticket"] = build_hot6_ticket(feature_df)

    if momentum_btn:
        st.session_state["momentum_ticket"] = build_momentum_master_ticket(feature_df, seed=cfg.seed + 11)

    if cycle_btn:
        cycle_ticket, cycle_df = build_cycle_ticket(draws)
        st.session_state["cycle_ticket"] = cycle_ticket
        st.session_state["cycle_df"] = cycle_df

    # =====================================================
    # OUTPUTS
    # =====================================================
    if st.session_state["show_results"]:
        st.markdown("### 📋 Ostatnie wyniki z PDF")
        show_n = st.selectbox("Ile rekordów pokazać?", [10, 50, 100, 200], index=1)
        view_records = all_records[:min(show_n, len(all_records))]
        df_results = pd.DataFrame({
            "Numer losowania": [r.draw_no if r.draw_no is not None else "—" for r in view_records],
            "Data": [r.date_str for r in view_records],
            "Wynik": [" ".join(f"{x:02d}" for x in r.nums) for r in view_records],
        })
        st.dataframe(df_results, use_container_width=True, hide_index=True)

        results_name = sanitize_txt_filename(st.text_input("Nazwa pliku wyników .txt", value="wyniki.txt"))
        st.download_button(
            "⬇️ Pobierz wyniki jako TXT",
            data=make_txt_for_results(view_records),
            file_name=results_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state["hot6_ticket"] is not None:
        ticket = st.session_state["hot6_ticket"]
        st.markdown("### 🔥 HOT 6")
        st.markdown(f"**Kupon:** {' '.join(f'{x:02d}' for x in ticket)}")
        hot_name = sanitize_txt_filename(st.text_input("Nazwa pliku HOT 6 .txt", value="hot6.txt"))
        st.download_button(
            "⬇️ Pobierz HOT 6 jako TXT",
            data=make_txt_for_simple_ticket("HOT 6", ticket),
            file_name=hot_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state["momentum_ticket"] is not None:
        info = st.session_state["momentum_ticket"]
        ticket = info["ticket"]
        st.markdown("### 🌟 Momentum Master")
        st.markdown(f"**Kupon:** {' '.join(f'{x:02d}' for x in ticket)}")
        st.markdown(f"**Średnia siła bazowa:** {info['avg_strength']:.6f}")
        with st.expander("Pokaż TOP 15 liczb Momentum"):
            st.dataframe(info["details"], use_container_width=True, hide_index=True)

        momentum_name = sanitize_txt_filename(st.text_input("Nazwa pliku Momentum .txt", value="momentum_master.txt"))
        st.download_button(
            "⬇️ Pobierz Momentum Master jako TXT",
            data=make_txt_for_simple_ticket(
                "Momentum Master",
                ticket,
                extra_lines=[f"Średnia siła bazowa: {info['avg_strength']:.6f}"]
            ),
            file_name=momentum_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state["daily_ticket"] is not None:
        info = st.session_state["daily_ticket"]
        st.markdown("### 🌿 Kupon dnia")
        st.markdown(f"**Kupon:** {' '.join(f'{x:02d}' for x in info['ticket'])}")
        st.markdown(f"Preferencja parzystości: **{info['parity_pref']}**")
        st.markdown(f"Preferencja poziomu: **{info['level_pref']}**")

        daily_name = sanitize_txt_filename(st.text_input("Nazwa pliku kupon dnia .txt", value="kupon_dnia.txt"))
        st.download_button(
            "⬇️ Pobierz kupon dnia jako TXT",
            data=make_txt_for_simple_ticket(
                "Kupon dnia",
                info["ticket"],
                extra_lines=[
                    f"Preferencja parzystości: {info['parity_pref']}",
                    f"Preferencja poziomu: {info['level_pref']}",
                ]
            ),
            file_name=daily_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state["cycle_ticket"] is not None:
        cycle_ticket = st.session_state["cycle_ticket"]
        cycle_df = st.session_state["cycle_df"]
        st.markdown("### 🔄 Cykle")
        st.markdown(f"**Kupon cykli:** {' '.join(f'{x:02d}' for x in cycle_ticket)}")
        with st.expander("Pokaż tabelę cykli"):
            st.dataframe(cycle_df.head(20), use_container_width=True, hide_index=True)

        cycle_name = sanitize_txt_filename(st.text_input("Nazwa pliku cykle .txt", value="cykle.txt"))
        st.download_button(
            "⬇️ Pobierz cykle jako TXT",
            data=make_txt_for_simple_ticket("Cykle", cycle_ticket),
            file_name=cycle_name,
            mime="text/plain",
            use_container_width=True
        )

    metrics = st.session_state.get("generated_metrics")
    if metrics:
        st.markdown("### 🎯 Najlepsze kupony silnika PRO")
        preview_n = min(len(metrics), 20)
        st.caption(f"Podgląd pierwszych **{preview_n}** kuponów.")
        for idx, metric in enumerate(metrics[:preview_n], start=1):
            render_ticket_card(idx, metric)

        with st.expander("Pokaż pełną tabelę kuponów"):
            df_metrics = pd.DataFrame([
                {
                    "Kupon": " ".join(f"{x:02d}" for x in m.ticket),
                    "Final Score": m.final_score,
                    "Freq": m.freq_score,
                    "Momentum": m.momentum_score,
                    "Overdue": m.overdue_score,
                    "Pair": m.pair_score,
                    "Triple": m.triple_score,
                    "Shape": m.shape_score,
                    "Kara różnorodność": m.diversity_penalty,
                    "Kara ostatnie": m.recent_overlap_penalty,
                    "P/N": m.odd_even,
                    "N/W": m.low_high,
                    "Rozstrzał": m.spread,
                    "Pary kolejne": m.consecutive_pairs,
                    "Suma": m.sum_total,
                    "Źródło": m.source,
                }
                for m in metrics
            ])
            st.dataframe(df_metrics, use_container_width=True, hide_index=True)

        metrics_name = sanitize_txt_filename(st.text_input("Nazwa pliku kupony PRO .txt", value="kupony_pro.txt"))
        st.download_button(
            "⬇️ Pobierz kupony PRO jako TXT",
            data=make_txt_for_ticket_metrics(metrics),
            file_name=metrics_name,
            mime="text/plain",
            use_container_width=True
        )

    if feature_export_btn:
        st.markdown("### 📊 TOP / LOW diagnostyka")
        st.markdown("**TOP 15 liczb wg BaseStrength**")
        st.dataframe(feature_df.head(15), use_container_width=True, hide_index=True)
        st.markdown("**LOW 15 liczb wg BaseStrength**")
        st.dataframe(feature_df.tail(15).sort_values("BaseStrength", ascending=True), use_container_width=True, hide_index=True)

    with st.expander("✅ Kontrola odczytu pierwszych 10 rekordów z PDF"):
        for i, r in enumerate(all_records[:10], start=1):
            draw_str = str(r.draw_no) if r.draw_no is not None else "—"
            st.write(f"{i}. Losowanie: {draw_str} | Wynik: {' '.join(f'{x:02d}' for x in r.nums)}")

    with st.expander("📘 Co robi ten silnik?"):
        st.markdown("""
Nowy silnik:
1. Czyta PDF i buduje historyczne losowania 6/49.
2. Liczy siłę każdej liczby na wielu oknach naraz: 20 / 50 / 100 / 250 / całość.
3. Liczy Momentum, umiarkowane Overdue i karę za zbyt świeże liczby.
4. Liczy synergię par i trójek historycznych.
5. Buduje profil typowego losowania: P/N, N/W, suma, rozstrzał, pary kolejne.
6. Losuje tysiące kandydatów ważonych jakością liczb.
7. Dodatkowo mutuje i dopieszcza część kuponów przez local search.
8. Ocenia wszystkie kandydaty wspólną funkcją score.
9. Zwraca najlepsze kupony według końcowego rankingu.
        """)


if __name__ == "__main__":
    main()
