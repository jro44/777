import os
import re
import logging
import time
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

LOW_HIGH_THRESHOLD = 24

WINDOWS_SHORT = 20
WINDOWS_MEDIUM = 50
WINDOWS_LONG = 100
WINDOWS_ULTRA = 250

INT_RE = re.compile(r"\d+")


# =========================================================
# CSS (UI STYLING)
# =========================================================
APP_CSS = """
<style>
:root{
  --bg0:#f3fbf7; --bg1:#ffffff; --card:#ffffff; --card2:#f7fffb;
  --txt:#000000; --mut:#111827; --green:#00a86b; --green2:#00c27a;
  --gold:#d4af37; --border: rgba(0,168,107,0.22); --shadow: 0 10px 28px rgba(0,0,0,.08);
}
.stApp{
  background-color: var(--bg0) !important;
  background-image:
    radial-gradient(1100px 700px at 12% 10%, rgba(0, 194, 122, 0.10), transparent 58%),
    radial-gradient(900px 600px at 92% 18%, rgba(0, 168, 107, 0.08), transparent 55%),
    linear-gradient(180deg, var(--bg0), var(--bg1)) !important;
  color: var(--txt) !important;
}
.v-card{
  background: linear-gradient(180deg, var(--card), var(--card2));
  border: 1px solid var(--border); box-shadow: var(--shadow);
  border-radius: 18px; padding: 16px; margin-bottom: 16px;
}
.v-muted{ opacity:.86; font-size:.92rem; color:var(--mut) !important; }
.rank-card{
  background: linear-gradient(180deg, #ffffff, #f8fffb);
  border: 1px solid rgba(0,168,107,0.18); border-radius: 16px;
  padding: 14px; margin: 10px 0; box-shadow: 0 8px 18px rgba(0,0,0,.05);
}
div.stButton > button[kind="primary"]{
  background: linear-gradient(90deg, var(--green) 0%, var(--green2) 100%) !important;
  color: #000000 !important; border: 0 !important; border-radius: 14px !important;
  font-weight: 1000 !important; box-shadow: 0 10px 22px rgba(0, 168, 107, 0.18) !important;
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

@dataclass
class TicketMetrics:
    ticket: List[int]
    final_score: float
    freq_score: float
    momentum_score: float
    weibull_hazard_score: float
    markov_score: float
    shape_score: float
    diversity_penalty: float
    recent_overlap_penalty: float
    odd_even: str
    low_high: str
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
# HELPERS & OPTIMIZATIONS
# =========================================================
def resolve_pdf_path() -> Path:
    cwd = Path(os.getcwd())
    for name in PDF_CANDIDATES:
        p = cwd / name
        if p.exists(): return p
    return cwd / PDF_CANDIDATES[0]

def even_odd_split(nums: List[int]) -> Tuple[int, int]:
    ev = sum(1 for n in nums if n % 2 == 0)
    return ev, len(nums) - ev

def count_adjacent_pairs(nums_sorted: List[int]) -> int:
    return sum(1 for a, b in zip(nums_sorted, nums_sorted[1:]) if b == a + 1)

def has_run_length(nums_sorted: List[int], run_len: int) -> bool:
    if run_len <= 1: return True
    current = 1
    for a, b in zip(nums_sorted, nums_sorted[1:]):
        if b == a + 1:
            current += 1
            if current >= run_len: return True
        else:
            current = 1
    return False

def safe_mean(values: Iterable[float], default: float = 0.0) -> float:
    vals = list(values)
    return float(sum(vals) / len(vals)) if vals else default

def normalize_scores(score_map: Dict[int, float]) -> Dict[int, float]:
    if not score_map: return {}
    vals = list(score_map.values())
    mn, mx = min(vals), max(vals)
    if mx == mn: return {k: 0.0 for k in score_map}
    return {k: (v - mn) / (mx - mn) for k, v in score_map.items()}

def weighted_unique_sample(rng: np.random.Generator, population: List[int], weights: List[float], k: int) -> List[int]:
    arr_pop, arr_w = np.array(population, dtype=int), np.array(weights, dtype=float)
    if len(arr_pop) < k: raise ValueError("Populacja mniejsza niż k.")
    if arr_w.sum() <= 0: arr_w = np.ones_like(arr_w, dtype=float)
    probs = arr_w / arr_w.sum()
    return sorted(rng.choice(arr_pop, size=k, replace=False, p=probs).tolist())


# =========================================================
# PDF PARSER
# =========================================================
@st.cache_data(show_spinner=False)
def load_records_cached(pdf_bytes: bytes) -> List[DrawRecord]:
    if not pdf_bytes.startswith(b"%PDF"): raise ValueError("Brak nagłówka %PDF.")
    
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        pages = [page.get_text("text") or "" for page in doc]

    all_tokens, all_drawnos = [], []
    for page_text in pages:
        lines = [re.sub(r"\s+", " ", ln.strip()) for ln in page_text.splitlines() if ln]
        drawno_mode = False
        for ln in lines:
            if any(f in ln.lower() for f in ["lotto 6/49", "www.", "©", "multipasko"]): continue
            ints = [int(x) for x in INT_RE.findall(ln)]
            if not ints: continue
            if any(x >= DRAWNO_MIN for x in ints) and not any(NUM_MIN <= x <= NUM_MAX for x in ints):
                drawno_mode = True
            if not drawno_mode:
                all_tokens.extend(x for x in ints if NUM_MIN <= x <= NUM_MAX)
            else:
                all_drawnos.extend(x for x in ints if DRAWNO_MIN <= x < 100000)

    draws = []
    for i in range(0, len(all_tokens) - PICK_COUNT + 1, PICK_COUNT):
        d = sorted(all_tokens[i:i + PICK_COUNT])
        if len(set(d)) == PICK_COUNT and all(NUM_MIN <= x <= NUM_MAX for x in d): draws.append(d)

    n = min(len(draws), len(all_drawnos))
    records = [DrawRecord(draw_no=all_drawnos[i], nums=draws[i]) for i in range(n)]
    records.extend(DrawRecord(draw_no=None, nums=draws[j]) for j in range(n, len(draws)))
    records.sort(key=lambda r: (r.draw_no is None, r.draw_no or -1), reverse=True)
    return records


# =========================================================
# ADVANCED ANALYTICS
# =========================================================
@st.cache_data(show_spinner=False)
def compute_markov_transition_matrix(draws: List[List[int]]) -> np.ndarray:
    matrix = np.zeros((NUM_MAX + 1, NUM_MAX + 1), dtype=float)
    chronological = list(reversed(draws))
    for t in range(len(chronological) - 1):
        for c_num in chronological[t]:
            for n_num in chronological[t + 1]:
                matrix[c_num][n_num] += 1.0
    for i in range(1, NUM_MAX + 1):
        row_sum = matrix[i].sum()
        if row_sum > 0: matrix[i] = matrix[i] / row_sum
    return matrix

@st.cache_data(show_spinner=False)
def compute_weibull_hazard_and_gaps(draws: List[List[int]]) -> pd.DataFrame:
    chronological = list(reversed(draws))
    total = len(chronological)
    rows = []
    for num in range(NUM_MIN, NUM_MAX + 1):
        positions = [idx for idx, draw in enumerate(chronological) if num in draw]
        current_gap = float(total - 1 - positions[-1]) if positions else float(total)
        hazard_rate = 0.0
        
        if len(positions) >= 3:
            gaps = [b - a for a, b in zip(positions[:-1], positions[1:])]
            try:
                shape, loc, scale = stats.weibull_min.fit(gaps, floc=0)
                if scale > 0 and current_gap > 0:
                    hazard_rate = (shape / scale) * ((current_gap / scale) ** (shape - 1))
            except Exception: pass
        rows.append({"Liczba": num, "Weibull_Hazard": min(hazard_rate, 1.0)})
    return pd.DataFrame(rows).fillna(0.0)

def build_shape_profile(draws: List[List[int]]) -> Dict:
    eo_counter, lh_counter = Counter(), Counter()
    sums, spreads, adj_pairs = [], [], []
    for draw in draws:
        s = sorted(draw)
        ev = sum(1 for x in s if x % 2 == 0)
        low = sum(1 for x in s if x <= LOW_HIGH_THRESHOLD)
        eo_counter[(ev, PICK_COUNT - ev)] += 1
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

def build_number_feature_table(draws: List[List[int]]) -> pd.DataFrame:
    def pct_map(sub: List[List[int]]) -> Dict[int, float]:
        c = Counter(n for d in sub for n in d)
        return {n: (c.get(n, 0) / len(sub) if len(sub) else 0.0) for n in range(NUM_MIN, NUM_MAX + 1)}

    w20, w50 = pct_map(draws[:20]), pct_map(draws[:50])
    w100, fall = pct_map(draws[:100]), pct_map(draws)
    weibull_map = dict(zip((w_df := compute_weibull_hazard_and_gaps(draws))["Liczba"], w_df["Weibull_Hazard"]))
    
    last_seen = {n: 999 for n in range(NUM_MIN, NUM_MAX + 1)}
    for idx, d in enumerate(draws):
        for n in d:
            if last_seen[n] == 999: last_seen[n] = idx

    rows = []
    for n in range(NUM_MIN, NUM_MAX + 1):
        momentum = (w20[n] * 0.45 + w50[n] * 0.30 + w100[n] * 0.15 + fall[n] * 0.10)
        hazard = weibull_map.get(n, 0.0)
        rp = 1.0 if last_seen[n] == 0 else (0.65 if last_seen[n] == 1 else 0.0)
        rows.append({
            "Liczba": n, "FreqAll": fall[n], "Momentum": momentum,
            "WeibullHazard": hazard, "LastSeenIdx": last_seen[n],
            "BaseStrength": (momentum * 0.50 + hazard * 0.50) - (rp * 0.15)
        })

    df = pd.DataFrame(rows)
    for col in ["FreqAll", "Momentum", "WeibullHazard", "BaseStrength"]:
        df[col + "_Norm"] = list(normalize_scores(dict(zip(df["Liczba"], df[col]))).values())
    return df.sort_values(["BaseStrength"], ascending=False).reset_index(drop=True)


# =========================================================
# FAST SCORING ENGINE
# =========================================================
def score_ticket(
    ticket: List[int], feat_map: Dict[int, Dict[str, float]],
    markov_matrix: np.ndarray, last_draw: List[int], profile: Dict,
    recent_draws_sets: List[Set[int]], max_recent_overlap: int, source: str
) -> TicketMetrics:
    
    ev = sum(1 for x in ticket if x % 2 == 0)
    od = PICK_COUNT - ev
    low = sum(1 for x in ticket if x <= LOW_HIGH_THRESHOLD)
    high = PICK_COUNT - low
    spread = ticket[-1] - ticket[0]
    adj_pairs = sum(1 for a, b in zip(ticket, ticket[1:]) if b == a + 1)
    t_sum = sum(ticket)

    freq_score = sum(feat_map[n]["FreqAll_Norm"] for n in ticket) / PICK_COUNT
    mom_score = sum(feat_map[n]["Momentum_Norm"] for n in ticket) / PICK_COUNT
    weib_score = sum(feat_map[n]["WeibullHazard_Norm"] for n in ticket) / PICK_COUNT

    markov_score = 0.0
    if last_draw:
        markov_score = sum(markov_matrix[p][c] for p in last_draw for c in ticket) / 36.0

    even_odd_pen = abs(ev - profile["target_even_odd"][0]) + abs(od - profile["target_even_odd"][1])
    low_high_pen = abs(low - profile["target_low_high"][0]) + abs(high - profile["target_low_high"][1])
    shape_score = max(0.0, 1.0 - (even_odd_pen * 0.15 + low_high_pen * 0.15 + abs(spread - profile["target_spread"])/30.0 * 0.1))

    recent_overlap = max((len(set(ticket).intersection(d)) for d in recent_draws_sets), default=0)
    overlap_pen = ((recent_overlap - max_recent_overlap) * 0.40) if recent_overlap > max_recent_overlap else 0.0

    div_pen = 0.0
    if sum(1 for x in ticket if x <= 31) >= 5: div_pen += 0.30  # Anty-Data Urodzin
    if has_run_length(ticket, 4): div_pen += 0.65
    if ev in (0, 6) or low in (0, 6): div_pen += 0.35

    final_score = (weib_score * 1.8 + markov_score * 1.6 + mom_score * 1.2 + shape_score * 1.0) - div_pen - overlap_pen

    return TicketMetrics(
        ticket=ticket, final_score=round(final_score, 6), freq_score=round(freq_score, 6),
        momentum_score=round(mom_score, 6), weibull_hazard_score=round(weib_score, 6),
        markov_score=round(markov_score, 6), shape_score=round(shape_score, 6),
        diversity_penalty=round(div_pen, 6), recent_overlap_penalty=round(overlap_pen, 6),
        odd_even=f"{ev}/{od}", low_high=f"{low}/{high}", source=source
    )


# =========================================================
# CANDIDATE GENERATION WITH PROGRESS
# =========================================================
def build_candidates(
    draws: List[List[int]], feature_df: pd.DataFrame, markov_matrix: np.ndarray,
    profile: Dict, cfg: EngineConfig, progress_bar, status_text
) -> List[TicketMetrics]:
    rng = np.random.default_rng(cfg.seed)
    recent_sets = [set(d) for d in draws[:10]]
    last_draw = draws[0] if draws else []
    feat_map = feature_df.set_index("Liczba").to_dict("index")
    
    weights = {n: max((r["BaseStrength_Norm"] * 0.5 + r["WeibullHazard_Norm"] * 0.3 + r["Momentum_Norm"] * 0.2), 0.001) for n, r in feature_df.iterrows()}
    
    elite_pool = feature_df.head(cfg.elite_pool_size)["Liczba"].tolist()
    soft_pool = feature_df.head(cfg.soft_pool_size)["Liczba"].tolist()
    full_pool = list(range(1, 50))

    def eval_fn(t: List[int], s: str = "gen") -> TicketMetrics:
        return score_ticket(t, feat_map, markov_matrix, last_draw, profile, recent_sets, cfg.max_recent_overlap, s)

    results, uniq = [], set()
    target = cfg.candidate_count
    
    start_time = time.time()

    for i in range(target):
        # Update progress bar every 10%
        if i % (target // 10 + 1) == 0:
            progress = int((i / target) * 100)
            progress_bar.progress(progress)
            status_text.write(f"⏳ Generowanie i optymalizacja kuponów: {progress}% (przeliczono {i} wektorów)...")

        mode = rng.choice(["elite", "diverse"], p=[0.75, 0.25])
        if mode == "elite":
            elite_take = min(int(rng.choice([2, 3, 4], p=[0.3, 0.5, 0.2])), PICK_COUNT)
            e_part = weighted_unique_sample(rng, elite_pool, [weights[n] for n in elite_pool], elite_take)
            rem = [n for n in soft_pool if n not in e_part] or full_pool
            r_part = weighted_unique_sample(rng, rem, [weights[n] for n in rem], PICK_COUNT - elite_take)
            ticket = sorted(e_part + r_part)
            src = "elite_hybrid"
        else:
            ticket = weighted_unique_sample(rng, full_pool, [weights[n] for n in full_pool], PICK_COUNT)
            src = "diverse"

        if tuple(ticket) in uniq: continue

        if cfg.enable_local_search:
            best, b_score = ticket, eval_fn(ticket).final_score
            for _ in range(cfg.local_search_steps):
                to_rm = set(rng.choice(best, size=int(rng.choice([1, 2])), replace=False).tolist())
                kept = [n for n in best if n not in to_rm]
                cands = [n for n in soft_pool if n not in kept] or full_pool
                cand = sorted(kept + weighted_unique_sample(rng, cands, [weights[n] for n in cands], PICK_COUNT - len(kept)))
                c_score = eval_fn(cand).final_score
                if c_score > b_score: best, b_score = cand, c_score
            ticket, src = best, "local_search"

        if tuple(ticket) in uniq: continue
        uniq.add(tuple(ticket))
        results.append(eval_fn(ticket, src))

    results.sort(key=lambda x: x.final_score, reverse=True)
    
    elapsed = time.time() - start_time
    progress_bar.progress(100)
    status_text.success(f"✅ Przeliczono {len(results)} unikalnych kuponów w {elapsed:.2f} sekund!")
    return results


# =========================================================
# UI & SETTINGS
# =========================================================
def set_genius_preset():
    """Funkcja ustawiająca naszą 'Ideologię Pro' w Session State."""
    st.session_state['window'] = 250
    st.session_state['cands'] = 15000
    st.session_state['overlap'] = 2
    st.session_state['soft'] = 24
    st.session_state['evolve'] = True
    st.session_state['steps'] = 12
    st.toast("✅ Załadowano Strategię Geniusza! Parametry zoptymalizowane pod EV.", icon="🧠")

def settings_panel(max_rec: int) -> EngineConfig:
    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("⚙️ Panel Sterowania Silnikiem")
    
    st.info("💡 **Wskazówka:** Jeśli nie wiesz co ustawić, kliknij przycisk poniżej. Ustawi on maszynę według naszej matematycznej ideologii (redukcja wariancji, szukanie krawędzi).")
    if st.button("🧠 Załaduj 'Strategię Geniusza' (Zalecane)", use_container_width=True):
        set_genius_preset()

    # Inicjalizacja stanu domyślnego
    st.session_state.setdefault('window', 250)
    st.session_state.setdefault('cands', 10000)
    st.session_state.setdefault('overlap', 3)
    st.session_state.setdefault('soft', 28)
    st.session_state.setdefault('evolve', True)
    st.session_state.setdefault('steps', 10)

    c1, c2, c3 = st.columns(3)
    with c1:
        window = st.number_input(
            "Ile losowań analizować?", min_value=50, max_value=max_rec, value=st.session_state['window'], key="cfg_w",
            help="Balans pomiędzy historią a obecnym trendem. Zbyt duża wartość (np. 1000) 'spłaszczy' wyniki. Zalecane: 250."
        )
        cands = st.number_input(
            "Liczba generowanych kuponów", min_value=1000, max_value=50000, value=st.session_state['cands'], key="cfg_c", step=1000,
            help="Im więcej kuponów silnik wygeneruje w tle, tym większa szansa, że znajdzie 'perełkę'. Zalecane minimum: 10 000."
        )
    with c2:
        overlap = st.slider(
            "Maks. podobieństwo do ostatnich", 1, 6, st.session_state['overlap'], key="cfg_o",
            help="Jeśli kupon ma więcej wspólnych liczb z poprzednimi losowaniami niż ta wartość, zostanie odrzucony. Historycznie rzadko powtarzają się 3 liczby."
        )
        tickets = st.slider("Ile najlepszych pokazać?", 1, 50, 10, help="Ile finałowych kuponów chcesz zobaczyć na ekranie.")
    with c3:
        seed = st.number_input("Ziarno losowości (Seed)", value=123456, help="Zmiana tej liczby przetasuje pulę generowanych wyników.")
        soft = st.slider(
            "Wielkość puli SOFT", 15, 49, st.session_state['soft'], key="cfg_s",
            help="Z ilu 'najgorętszych' liczb maszyna ma budować kupony. Ustawienie 24 oznacza, że odrzucamy połowę 'najzimniejszych' kul."
        )

    st.markdown("---")
    evolve = st.checkbox(
        "🧬 Włącz algorytm ewolucyjny (Szukanie lokalne i optymalizacja EV)", value=st.session_state['evolve'], key="cfg_e",
        help="Silnik spróbuje ulepszyć wygenerowane kupony, podmieniając pojedyncze liczby, aby zmaksymalizować wynik matematyczny i ominąć ludzkie wzorce (np. liczby 1-31)."
    )
    steps = st.slider(
        "Kroki algorytmu ewolucyjnego", 0, 30, st.session_state['steps'], key="cfg_steps",
        help="Ile prób ulepszenia podejmie silnik dla każdego kuponu. 12 to bardzo solidna wartość."
    ) if evolve else 0

    st.markdown("</div>", unsafe_allow_html=True)

    return EngineConfig(
        int(window), int(cands), tickets, seed, overlap,
        20, 12, soft, evolve, steps
    )

def render_ticket_card(idx: int, metric: TicketMetrics) -> None:
    st.markdown(
        f"""
<div class="rank-card">
  <div class="rank-title">Kupon #{idx:03d}</div>
  <div class="rank-main">{" ".join(f"{x:02d}" for x in metric.ticket)}</div>
  <div class="rank-meta">
    <b>Score: {metric.final_score:.4f}</b><br>
    <span class="v-muted">
    Ciśnienie powrotu (Weibull): {metric.weibull_hazard_score:.4f} | Zgodność Markowa: {metric.markov_score:.4f}<br>
    Kary (za ludzkie wzorce): -{metric.diversity_penalty + metric.recent_overlap_penalty:.4f} | Źródło: {metric.source}
    </span>
  </div>
</div>
        """, unsafe_allow_html=True
    )


# =========================================================
# MAIN APP
# =========================================================
def main() -> None:
    st.set_page_config(page_title="Victory Lotto Pro", page_icon="🏆", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(APP_CSS, unsafe_allow_html=True)
    st.title(APP_TITLE)

    if "metrics" not in st.session_state: st.session_state["metrics"] = None

    pdf_path = resolve_pdf_path()
    if not pdf_path.exists():
        st.error("❌ Nie znaleziono pliku PDF (wyniki.pdf).")
        st.stop()

    try:
        all_records = load_records_cached(pdf_path.read_bytes())
    except Exception as e:
        st.error(f"❌ Błąd PDF: {e}")
        st.stop()

    cfg = settings_panel(len(all_records))
    draws = [r.nums for r in all_records[:min(cfg.analysis_window, len(all_records))]]

    feature_df = build_number_feature_table(draws)
    markov_matrix = compute_markov_transition_matrix(draws)
    shape_profile = build_shape_profile(draws)

    left, right = st.columns([1.2, 0.8], gap="large")
    with left:
        st.markdown('<div class="v-card"><h4>📈 Tabela Siły (Weibull Hazard)</h4>', unsafe_allow_html=True)
        st.caption("Poniższa tabela pokazuje matematyczne ciśnienie powrotu liczby. Im 'WeibullHazard' bliższe 1.0, tym powrót jest bardziej prawdopodobny.")
        display_df = feature_df[["Liczba", "WeibullHazard", "Momentum", "BaseStrength"]].copy()
        st.dataframe(display_df.round(5), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="v-card"><h4>🎯 Matryca Maszyny</h4>', unsafe_allow_html=True)
        st.caption("Informacje o ostatnim losowaniu i rekomendowany 'Kształt' (ilość liczb parzystych do nieparzystych itd.).")
        st.write(f"Ostatnio wylosowano: **{draws[0] if draws else 'Brak'}**")
        st.write(f"Zalecane Parzyste/Nieparzyste: **{shape_profile['target_even_odd'][0]}/{shape_profile['target_even_odd'][1]}**")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    if st.button("🚀 URUCHOM SILNIK PREDYKCYJNY", type="primary", use_container_width=True):
        st.markdown("### ⚙️ Trwa przetwarzanie...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        metrics = build_candidates(draws, feature_df, markov_matrix, shape_profile, cfg, progress_bar, status_text)
        st.session_state["metrics"] = metrics[:cfg.n_tickets]

    if st.session_state["metrics"]:
        st.markdown("### 🏆 Najlepsze zoptymalizowane kupony (TOP EV)")
        st.info("💡 **Jak czytać wyniki?** Najwyższy Score oznacza, że kupon spełnia najwięcej naszych reguł: ma silne liczby (Weibull), unika wzorów ludzkich (np. brak samych dat 1-31) i dobrze łączy się historycznie (Markow).")
        for idx, m in enumerate(st.session_state["metrics"], 1):
            render_ticket_card(idx, m)

if __name__ == "__main__":
    main()
