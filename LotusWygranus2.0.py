
import os
import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Iterable, Set
from collections import Counter
from itertools import combinations

import fitz  # PyMuPDF
import numpy as np
import pandas as pd
import streamlit as st
import scipy.stats as stats


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
APP_TITLE = "🏆 Victory Lotto Pro — 6/49 (Weibull & Markov Edition)"
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
    weibull_hazard_score: float
    markov_score: float
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
    return ev, len(nums) - ev


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


def safe_mean(values: Iterable[float], default: float = 0.0) -> float:
    vals = list(values)
    return float(sum(vals) / len(vals)) if vals else default


def normalize_scores(score_map: Dict[int, float]) -> Dict[int, float]:
    if not score_map:
        return {}
    vals = list(score_map.values())
    mn, mx = min(vals), max(vals)
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
        raise ValueError(f"Plik nie wygląda jak PDF. Początek:\n{head}")


def _read_pdf_pages_text(pdf_bytes: bytes) -> List[str]:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return [page.get_text("text") or "" for page in doc]


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", (line or "").strip())


def _is_noise_line(line: str) -> bool:
    low = line.lower()
    noise_fragments = ["lotto 6/49", "www.", "©", "multipasko", "drukuj", "reklama"]
    return any(fragment in low for fragment in noise_fragments)


def _split_numbers_from_lines(page_text: str) -> Tuple[List[int], List[int]]:
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

        if has_large and not has_small_lotto:
            drawno_mode = True

        if not drawno_mode:
            result_tokens.extend(x for x in ints if NUM_MIN <= x <= NUM_MAX)
        else:
            draw_numbers.extend(x for x in ints if DRAWNO_MIN <= x < 100000)

    return result_tokens, draw_numbers


def _chunk_tokens_to_draws(tokens: List[int]) -> List[List[int]]:
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
            if len(set(draw)) == PICK_COUNT and all(NUM_MIN <= n <= NUM_MAX for n in draw):
                score += 3
            if (draw[-1] - draw[0]) >= 8:
                score += 1

        if score > best_score:
            best_score = score
            best_draws = draws

    return [d for d in best_draws if len(d) == PICK_COUNT and len(set(d)) == PICK_COUNT and all(NUM_MIN <= x <= NUM_MAX for x in d)]


def _pair_draws_with_drawnos(draws: List[List[int]], drawnos: List[int]) -> List[DrawRecord]:
    n = min(len(draws), len(drawnos))
    records = [DrawRecord(draw_no=drawnos[i], nums=draws[i]) for i in range(n)]
    records.extend(DrawRecord(draw_no=None, nums=draws[j]) for j in range(n, len(draws)))

    with_numbers = [r for r in records if r.draw_no is not None]
    if len(with_numbers) > 10:
        records.sort(key=lambda r: (r.draw_no is None, r.draw_no or -1), reverse=True)

    return records


@st.cache_data(show_spinner=False)
def load_records_cached(pdf_bytes: bytes) -> List[DrawRecord]:
    _validate_pdf_bytes(pdf_bytes)
    pages = _read_pdf_pages_text(pdf_bytes)

    all_tokens, all_drawnos = [], []
    for page_text in pages:
        tokens, drawnos = _split_numbers_from_lines(page_text)
        all_tokens.extend(tokens)
        all_drawnos.extend(drawnos)

    draws = _chunk_tokens_to_draws(all_tokens)
    if not draws:
        raise RuntimeError("Nie udało się wyciągnąć poprawnych losowań z PDF.")

    records = _pair_draws_with_drawnos(draws, all_drawnos)
    if len(records) < 20:
        raise RuntimeError(f"Zbyt mało rekordów ({len(records)}). Sprawdź strukturę PDF.")

    return records


# =========================================================
# ADVANCED ANALYTICS (WEIBULL & MARKOV)
# =========================================================
@st.cache_data(show_spinner=False)
def compute_markov_transition_matrix(draws: List[List[int]]) -> np.ndarray:
    """
    Buduje macierz prawdopodobieństwa przejść 49x49.
    P(X_{t+1} = j | X_t = i)
    """
    matrix = np.zeros((NUM_MAX + 1, NUM_MAX + 1), dtype=float)
    # Losowania w `draws` są zazwyczaj od najnowszego do najstarszego.
    # Musimy iterować chronologicznie: od końca do początku.
    chronological = list(reversed(draws))
    
    for t in range(len(chronological) - 1):
        current_draw = chronological[t]
        next_draw = chronological[t + 1]
        for c_num in current_draw:
            for n_num in next_draw:
                matrix[c_num][n_num] += 1.0

    # Normalizacja wierszy
    for i in range(1, NUM_MAX + 1):
        row_sum = matrix[i].sum()
        if row_sum > 0:
            matrix[i] = matrix[i] / row_sum

    return matrix


@st.cache_data(show_spinner=False)
def compute_weibull_hazard_and_gaps(draws: List[List[int]]) -> pd.DataFrame:
    """
    Wylicza luki (gaps) oraz dopasowuje Rozkład Weibulla do wyznaczenia
    aktualnego poziomu "Hazardu" (prawdopodobieństwa pojawienia się liczby).
    """
    chronological = list(reversed(draws))
    total = len(chronological)
    rows = []

    for num in range(NUM_MIN, NUM_MAX + 1):
        positions = [idx for idx, draw in enumerate(chronological) if num in draw]
        occurrences = len(positions)
        
        current_gap = float(total - 1 - positions[-1]) if positions else float(total)
        
        hazard_rate = 0.0
        avg_gap = 0.0
        
        if occurrences >= 3:
            gaps = [b - a for a, b in zip(positions[:-1], positions[1:])]
            avg_gap = safe_mean(gaps, 0.0)
            
            # Dopasowanie rozkładu Weibulla do historycznych przerw
            try:
                # floc=0 blokuje przesunięcie, wymuszając start od 0
                shape, loc, scale = stats.weibull_min.fit(gaps, floc=0)
                if scale > 0 and current_gap > 0:
                    # Funkcja Hazardu h(t) = (shape / scale) * (t / scale)^(shape - 1)
                    hazard_rate = (shape / scale) * ((current_gap / scale) ** (shape - 1))
            except Exception:
                hazard_rate = 0.0
        
        # Ograniczamy matematyczne anomalie
        hazard_rate = min(hazard_rate, 1.0)

        rows.append({
            "Liczba": num,
            "Wystąpienia": occurrences,
            "Średni_gap": round(avg_gap, 3),
            "Aktualny_gap": round(current_gap, 3),
            "Weibull_Hazard": hazard_rate
        })

    df = pd.DataFrame(rows)
    # Zabezpieczenie na wypadek NaN
    df["Weibull_Hazard"] = df["Weibull_Hazard"].fillna(0.0)
    return df.sort_values(["Weibull_Hazard", "Liczba"], ascending=[False, True]).reset_index(drop=True)


# =========================================================
# ANALYSIS CORE
# =========================================================
@st.cache_data(show_spinner=False)
def compute_pair_triple_counters_cached(draws: List[List[int]]) -> Tuple[Counter, Counter]:
    pair_counter, triple_counter = Counter(), Counter()
    for draw in draws:
        s = sorted(draw)
        for pair in combinations(s, 2):
            pair_counter[pair] += 1
        for triple in combinations(s, 3):
            triple_counter[triple] += 1
    return pair_counter, triple_counter


@st.cache_data(show_spinner=False)
def compute_last_seen_map_cached(draws: List[List[int]]) -> Dict[int, int]:
    result = {n: 999999 for n in range(NUM_MIN, NUM_MAX + 1)}
    for idx, draw in enumerate(draws):
        for n in draw:
            if result[n] == 999999:
                result[n] = idx
    return result


def build_shape_profile(draws: List[List[int]]) -> Dict:
    if not draws:
        return {
            "target_even_odd": (3, 3), "target_low_high": (3, 3),
            "target_sum": 150.0, "target_spread": 30.0, "target_adj_pairs": 0.8,
        }

    eo_counter, lh_counter = Counter(), Counter()
    sums, spreads, adj_pairs = [], [], []

    for draw in draws:
        s = sorted(draw)
        ev, od = even_odd_split(s)
        low = sum(1 for x in s if x <= LOW_HIGH_THRESHOLD)
        eo_counter[(ev, od)] += 1
        lh_counter[(low, PICK_COUNT - low)] += 1
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
    def pct_map(sub_draws: List[List[int]]) -> Dict[int, float]:
        total = len(sub_draws)
        c = Counter(n for d in sub_draws for n in d)
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
    weibull_df = compute_weibull_hazard_and_gaps(draws)
    weibull_map = dict(zip(weibull_df["Liczba"], weibull_df["Weibull_Hazard"]))
    last_seen_map = compute_last_seen_map_cached(draws)

    rows = []
    for n in range(NUM_MIN, NUM_MAX + 1):
        f20, f50 = freq_windows["w20"].get(n, 0.0), freq_windows["w50"].get(n, 0.0)
        f100, f250 = freq_windows["w100"].get(n, 0.0), freq_windows["w250"].get(n, 0.0)
        fall = freq_windows["wall"].get(n, 0.0)

        momentum = (f20 * 0.42 + f50 * 0.28 + f100 * 0.16 + f250 * 0.08 + fall * 0.06)
        hazard = weibull_map.get(n, 0.0)

        last_seen = last_seen_map.get(n, 999999)
        recency_penalty = 1.0 if last_seen == 0 else (0.65 if last_seen == 1 else (0.35 if last_seen == 2 else 0.0))

        # BaseStrength wykorzystuje teraz Hazard Weibullowy
        base_strength = (momentum * 0.60 + hazard * 0.40) - (recency_penalty * 0.10)

        rows.append({
            "Liczba": n, "Freq20": f20, "Freq50": f50, "Freq100": f100,
            "Freq250": f250, "FreqAll": fall, "Momentum": momentum,
            "WeibullHazard": hazard, "LastSeenIdx": last_seen,
            "RecencyPenalty": recency_penalty, "BaseStrength": base_strength,
        })

    df = pd.DataFrame(rows)
    for col in ["Freq20", "Freq50", "Freq100", "Freq250", "FreqAll", "Momentum", "WeibullHazard", "BaseStrength"]:
        df[col + "_Norm"] = list(normalize_scores(dict(zip(df["Liczba"], df[col]))).values())

    return df.sort_values(["BaseStrength", "Momentum", "Liczba"], ascending=[False, False, True]).reset_index(drop=True)


# =========================================================
# FAST SCORING ENGINE (OPTIMIZED)
# =========================================================
def fast_ticket_shape(ticket: List[int]) -> Tuple[int, int, int, int, int, int, int]:
    ev = sum(1 for x in ticket if x % 2 == 0)
    low = sum(1 for x in ticket if x <= LOW_HIGH_THRESHOLD)
    spread = ticket[-1] - ticket[0]
    adj_pairs = sum(1 for a, b in zip(ticket, ticket[1:]) if b == a + 1)
    return ev, PICK_COUNT - ev, low, PICK_COUNT - low, spread, adj_pairs, sum(ticket)


def score_ticket(
    ticket: List[int],
    feat_map: Dict[int, Dict[str, float]],
    pair_map: Dict[Tuple[int, int], float],
    triple_map: Dict[Tuple[int, int, int], float],
    markov_matrix: np.ndarray,
    last_draw: List[int],
    profile: Dict,
    recent_draws_sets: List[Set[int]],
    max_recent_overlap: int,
    source: str
) -> TicketMetrics:
    
    # Kształt zoptymalizowany (Tuple zamiast Dict)
    ev, od, low, high, spread, adj_pairs, total_sum = fast_ticket_shape(ticket)

    # 1. Siła bazowa + Weibull
    freq_score = sum(feat_map[n]["FreqAll_Norm"] for n in ticket) / PICK_COUNT
    momentum_score = sum(feat_map[n]["Momentum_Norm"] for n in ticket) / PICK_COUNT
    weibull_score = sum(feat_map[n]["WeibullHazard_Norm"] for n in ticket) / PICK_COUNT

    # 2. Łańcuchy Markowa (Synergia z poprzednim losowaniem)
    markov_score = 0.0
    if last_draw:
        m_sum = sum(markov_matrix[prev_n][curr_n] for prev_n in last_draw for curr_n in ticket)
        markov_score = m_sum / (PICK_COUNT * PICK_COUNT)

    # 3. Zoptymalizowane pary i trójki (bez wzywania set/combinations w pętli)
    p_score_sum = 0.0
    for i in range(PICK_COUNT):
        for j in range(i + 1, PICK_COUNT):
            p_score_sum += pair_map.get((ticket[i], ticket[j]), 0.0)
    pair_score = p_score_sum / 15.0 # 15 kombinacji dla 6 elementów

    t_score_sum = 0.0
    for i in range(PICK_COUNT):
        for j in range(i + 1, PICK_COUNT):
            for k in range(j + 1, PICK_COUNT):
                t_score_sum += triple_map.get((ticket[i], ticket[j], ticket[k]), 0.0)
    triple_score = t_score_sum / 20.0 # 20 trójek

    # 4. Kształt kuponu
    target_ev, target_od = profile["target_even_odd"]
    target_low, target_high = profile["target_low_high"]

    even_odd_pen = abs(ev - target_ev) + abs(od - target_od)
    low_high_pen = abs(low - target_low) + abs(high - target_high)
    spread_pen = abs(spread - profile["target_spread"]) / 25.0
    sum_pen = abs(total_sum - profile["target_sum"]) / 45.0
    adj_pen = abs(adj_pairs - profile["target_adj_pairs"]) / 2.0

    shape_score = max(0.0, 1.0 - (even_odd_pen * 0.10 + low_high_pen * 0.10 + spread_pen * 0.10 + sum_pen * 0.12 + adj_pen * 0.08))

    # 5. Podobieństwo do ostatnich (zoptymalizowane na pre-kalkulowanych setach)
    tset = set(ticket)
    recent_overlap = max((len(tset.intersection(d)) for d in recent_draws_sets), default=0)
    recent_overlap_penalty = ((recent_overlap - max_recent_overlap) * 0.30) if recent_overlap > max_recent_overlap else (recent_overlap * 0.05)

    # 6. Optymalizacja EV ("Anty-Ludzkie" kary)
    diversity_penalty = 0.0
    # Kara za liczby "z kalendarza" (1-31)
    cal_count = sum(1 for x in ticket if x <= 31)
    if cal_count >= 5:
        diversity_penalty += 0.30
    
    if has_run_length(ticket, 4): diversity_penalty += 0.65
    elif has_run_length(ticket, 3): diversity_penalty += 0.28
    if adj_pairs >= 3: diversity_penalty += 0.20
    if ev in (0, 6) or od in (0, 6): diversity_penalty += 0.40
    if low in (0, 6) or high in (0, 6): diversity_penalty += 0.35

    # 7. Ostateczny wynik hybrydowy
    final_score = (
        weibull_score * 1.80 +
        markov_score * 1.50 +
        momentum_score * 1.40 +
        pair_score * 0.90 +
        triple_score * 1.00 +
        shape_score * 1.20
        - diversity_penalty
        - recent_overlap_penalty
    )

    return TicketMetrics(
        ticket=ticket, final_score=round(final_score, 6), freq_score=round(freq_score, 6),
        momentum_score=round(momentum_score, 6), weibull_hazard_score=round(weibull_score, 6),
        markov_score=round(markov_score, 6), pair_score=round(pair_score, 6),
        triple_score=round(triple_score, 6), shape_score=round(shape_score, 6),
        diversity_penalty=round(diversity_penalty, 6), recent_overlap_penalty=round(recent_overlap_penalty, 6),
        odd_even=f"{ev}/{od}", low_high=f"{low}/{high}", spread=spread,
        consecutive_pairs=adj_pairs, sum_total=total_sum, source=source
    )


# =========================================================
# CANDIDATE GENERATION
# =========================================================
def build_generation_weights(feature_df: pd.DataFrame) -> Dict[int, float]:
    weights = {}
    for _, rec in feature_df.iterrows():
        w = (
            rec["BaseStrength_Norm"] * 0.45 +
            rec["WeibullHazard_Norm"] * 0.35 +
            rec["Momentum_Norm"] * 0.20
        )
        if rec["LastSeenIdx"] == 0: w *= 0.88
        elif rec["LastSeenIdx"] == 1: w *= 0.94
        weights[rec["Liczba"]] = max(w, 0.0001)
    return weights


def build_candidates(
    draws: List[List[int]], feature_df: pd.DataFrame,
    pair_counter: Counter, triple_counter: Counter,
    markov_matrix: np.ndarray, profile: Dict, cfg: EngineConfig
) -> List[TicketMetrics]:
    rng = np.random.default_rng(cfg.seed)

    # Optymalizacja wstępna dla Setów i słowników
    recent_draws_sets = [set(d) for d in draws[:10]]
    last_draw = draws[0] if draws else []
    
    max_pair = max(pair_counter.values()) if pair_counter else 1
    pair_map = {k: v / max_pair for k, v in pair_counter.items()}
    max_triple = max(triple_counter.values()) if triple_counter else 1
    triple_map = {k: v / max_triple for k, v in triple_counter.items()}
    
    feat_map = feature_df.set_index("Liczba").to_dict("index")
    generation_weights = build_generation_weights(feature_df)

    elite_pool = feature_df.head(cfg.elite_pool_size)["Liczba"].tolist()
    soft_pool = feature_df.head(cfg.soft_pool_size)["Liczba"].tolist()
    full_pool = list(range(NUM_MIN, NUM_MAX + 1))

    def eval_fn(ticket: List[int], source: str = "gen") -> TicketMetrics:
        return score_ticket(
            ticket, feat_map, pair_map, triple_map, markov_matrix,
            last_draw, profile, recent_draws_sets, cfg.max_recent_overlap, source
        )

    uniq = set()
    results: List[TicketMetrics] = []
    target = cfg.candidate_count

    while len(results) < target:
        mode = rng.choice(["weighted", "diverse", "mutated"], p=[0.60, 0.20, 0.20])

        if mode == "weighted":
            elite_take = min(int(rng.choice([2, 3, 4], p=[0.30, 0.45, 0.25])), PICK_COUNT)
            elite_part = weighted_unique_sample(rng, elite_pool, [generation_weights[n] for n in elite_pool], elite_take)
            rem_pop = [n for n in soft_pool if n not in elite_part] or [n for n in full_pool if n not in elite_part]
            rest = weighted_unique_sample(rng, rem_pop, [generation_weights[n] for n in rem_pop], PICK_COUNT - elite_take)
            ticket = sorted(elite_part + rest)
            source = "weighted"
        elif mode == "diverse":
            ticket = weighted_unique_sample(rng, full_pool, [generation_weights[n] for n in full_pool], PICK_COUNT)
            source = "diverse"
        else:
            seed_ticket = weighted_unique_sample(rng, elite_pool, [generation_weights[n] for n in elite_pool], 2)
            rem_pop = [n for n in full_pool if n not in seed_ticket]
            rest = weighted_unique_sample(rng, rem_pop, [generation_weights[n] for n in rem_pop], PICK_COUNT - 2)
            ticket = sorted(seed_ticket + rest)
            source = "mutated"

        if tuple(ticket) in uniq: continue

        if cfg.enable_local_search:
            best = ticket
            best_score = eval_fn(best).final_score
            for _ in range(cfg.local_search_steps):
                replace_count = int(rng.choice([1, 2], p=[0.8, 0.2]))
                to_remove = set(rng.choice(best, size=replace_count, replace=False).tolist())
                kept = [n for n in best if n not in to_remove]
                cands = [n for n in soft_pool if n not in kept] or [n for n in full_pool if n not in kept]
                added = weighted_unique_sample(rng, cands, [generation_weights[n] for n in cands], PICK_COUNT - len(kept))
                candidate = sorted(kept + added)
                
                c_score = eval_fn(candidate).final_score
                if c_score > best_score:
                    best, best_score = candidate, c_score
            ticket = best
            source = "local_search"

        if tuple(ticket) in uniq: continue
        uniq.add(tuple(ticket))
        results.append(eval_fn(ticket, source))

    results.sort(key=lambda x: x.final_score, reverse=True)
    return results


# =========================================================
# UI HELPERS & EXPORTS
# =========================================================
def render_ticket_card(idx: int, metric: TicketMetrics) -> None:
    st.markdown(
        f"""
<div class="rank-card">
  <div class="rank-title">Kupon #{idx:03d}</div>
  <div class="rank-main">{" ".join(f"{x:02d}" for x in metric.ticket)}</div>
  <div class="rank-meta">
    Score: <b>{metric.final_score:.4f}</b> | Weibull: <b>{metric.weibull_hazard_score:.4f}</b> | Markov: <b>{metric.markov_score:.4f}</b><br>
    Freq: <b>{metric.freq_score:.4f}</b> | Momentum: <b>{metric.momentum_score:.4f}</b><br>
    Shape: <b>{metric.shape_score:.4f}</b> | P/N: <b>{metric.odd_even}</b> | N/W: <b>{metric.low_high}</b><br>
    Kary (Anty-Ludzkie/Podobne): <b>-{metric.diversity_penalty + metric.recent_overlap_penalty:.4f}</b> | Źródło: <b>{metric.source}</b>
  </div>
</div>
        """, unsafe_allow_html=True
    )


def settings_panel(max_records: int) -> Dict:
    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("⚙️ Ustawienia silnika (Weibull & Markov)")
    c1, c2, c3 = st.columns(3)
    with c1:
        analysis_window = st.selectbox("Analizowane losowania", [50, 100, 250, 500, 1000, max_records], index=3)
        candidate_count = st.slider("Kandydaci do oceny", 1000, 50000, 10000, 1000)
    with c2:
        n_tickets = st.slider("Ile finalnych kuponów", 1, 100, DEFAULT_TICKETS, 1)
        max_recent_overlap = st.slider("Maks. podobieństwo", 1, 6, 3, 1)
    with c3:
        seed = st.number_input("Seed losowania", value=DEFAULT_SEED, step=1)
        soft_pool_size = st.slider("Pula SOFT", 15, 49, 28, 1)
    
    enable_local_search = st.checkbox("Włącz optymalizację EV i szukanie lokalne", value=True)
    local_search_steps = st.slider("Kroki algorytmu ewolucyjnego", 0, 30, 10, 1) if enable_local_search else 0
    st.markdown("</div>", unsafe_allow_html=True)

    return {
        "analysis_window": int(analysis_window), "candidate_count": int(candidate_count),
        "n_tickets": int(n_tickets), "seed": int(seed), "max_recent_overlap": int(max_recent_overlap),
        "hot_pool_size": 20, "elite_pool_size": 12, "soft_pool_size": int(soft_pool_size),
        "enable_local_search": bool(enable_local_search), "local_search_steps": int(local_search_steps),
    }


# =========================================================
# MAIN APP
# =========================================================
def main() -> None:
    st.set_page_config(page_title="Victory Lotto Pro", page_icon="🏆", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(APP_CSS, unsafe_allow_html=True)
    st.title(APP_TITLE)

    if "generated_metrics" not in st.session_state:
        st.session_state["generated_metrics"] = None

    pdf_path = resolve_pdf_path()
    if not pdf_path.exists():
        st.error("❌ Nie znaleziono pliku PDF.")
        st.stop()

    try:
        all_records = load_records_cached(pdf_path.read_bytes())
    except Exception as e:
        st.error(f"❌ Błąd PDF: {e}")
        st.stop()

    cfg = EngineConfig(**settings_panel(len(all_records)))
    draws = [r.nums for r in all_records[:min(cfg.analysis_window, len(all_records))]]

    feature_df = build_number_feature_table(draws)
    pair_counter, triple_counter = compute_pair_triple_counters_cached(draws)
    markov_matrix = compute_markov_transition_matrix(draws)
    shape_profile = build_shape_profile(draws)

    left, right = st.columns([1.2, 0.8], gap="large")
    with left:
        st.markdown('<div class="v-card"><h4>📈 Tabela Analityczna (Weibull Hazard Rate)</h4>', unsafe_allow_html=True)
        display_df = feature_df[["Liczba", "WeibullHazard", "Momentum", "BaseStrength", "FreqAll"]].copy()
        for col in display_df.columns[1:]: display_df[col] = display_df[col].round(5)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="v-card"><h4>🎯 Matryca Oczekiwań</h4>', unsafe_allow_html=True)
        st.write(f"Najbliższe losowanie wg Markowa (odniesienie do ostatniego: **{draws[0]}**)")
        st.write(f"Zalecany Profil: Parzyste/Nieparzyste: **{shape_profile['target_even_odd'][0]}/{shape_profile['target_even_odd'][1]}**")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    if st.button("🚀 URUCHOM SILNIK PREDYKCYJNY (MARKOV & WEIBULL)", type="primary", use_container_width=True):
        with st.spinner(f"Przetwarzanie {cfg.candidate_count} wektorów z optymalizacją K-Means / Ewolucyjną..."):
            metrics = build_candidates(draws, feature_df, pair_counter, triple_counter, markov_matrix, shape_profile, cfg)
            st.session_state["generated_metrics"] = metrics[:cfg.n_tickets]
        st.success("✅ Predykcja zakończona pomyślnie.")

    if st.session_state["generated_metrics"]:
        st.markdown("### 🏆 Wyniki Predykcji (TOP Kupony)")
        for idx, m in enumerate(st.session_state["generated_metrics"], 1):
            render_ticket_card(idx, m)

if __name__ == "__main__":
    main()
