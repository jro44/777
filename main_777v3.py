import os
import re
import random
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import fitz
import numpy as np
import pandas as pd
import streamlit as st

# =========================================================
# APP CONFIG
# =========================================================
APP_TITLE = "🏆 Generator-Victory — Lotto 6/49"
PDF_CANDIDATES = ["wyniki.pdf", "wynik.pdf"]
NUM_MIN = 1
NUM_MAX = 49
PICK_COUNT = 6
DRAWNO_MIN = 1000

HYBRID_HOT_P = 0.70
HYBRID_COLD_P = 0.20
HYBRID_MIX_P = 0.10

# =========================================================
# UI STYLE
# =========================================================
LIGHT_GREEN_CSS = """
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

[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3,
[data-testid="stAppViewContainer"] h4{
  color: var(--txt) !important;
  letter-spacing: .35px;
}

[data-testid="stAppViewContainer"] h1{
  font-family: ui-serif, Georgia, "Times New Roman", serif;
  text-transform: uppercase;
}

.v-card{
  background: linear-gradient(180deg, var(--card), var(--card2));
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  border-radius: 18px;
  padding: 16px 16px 12px 16px;
}

.v-pill{
  display:inline-block;
  padding: 6px 10px;
  margin: 3px 4px 0 0;
  border-radius: 999px;
  border: 1px solid rgba(0, 168, 107, 0.28);
  background: rgba(0, 168, 107, 0.10);
  font-weight: 900;
  color: #000000 !important;
}

.v-pill-premium{
  display:inline-block;
  padding: 6px 10px;
  margin: 3px 4px 0 0;
  border-radius: 999px;
  border: 1px solid rgba(212, 175, 55, 0.45);
  background: rgba(212, 175, 55, 0.16);
  font-weight: 900;
  color: #000000 !important;
}

.v-pill-blue{
  display:inline-block;
  padding: 6px 10px;
  margin: 3px 4px 0 0;
  border-radius: 999px;
  border: 1px solid rgba(45, 119, 209, 0.40);
  background: rgba(45, 119, 209, 0.12);
  font-weight: 900;
  color: #000000 !important;
}

.v-pill-danger{
  display:inline-block;
  padding: 6px 10px;
  margin: 3px 4px 0 0;
  border-radius: 999px;
  border: 1px solid rgba(207, 59, 59, 0.40);
  background: rgba(207, 59, 59, 0.12);
  font-weight: 900;
  color: #000000 !important;
}

.v-muted{
  opacity: .86;
  font-size: .92rem;
  color: var(--mut) !important;
}

.v-row{
  background: rgba(0, 168, 107, 0.06);
  border: 1px solid rgba(0, 168, 107, 0.18);
  border-radius: 14px;
  padding: 10px 12px;
  margin: 8px 0;
  color: #000000 !important;
}

.v-row-premium{
  background: rgba(212, 175, 55, 0.10);
  border: 1px solid rgba(212, 175, 55, 0.34);
  border-radius: 14px;
  padding: 10px 12px;
  margin: 8px 0;
  color: #000000 !important;
}

.v-row-blue{
  background: rgba(45, 119, 209, 0.08);
  border: 1px solid rgba(45, 119, 209, 0.24);
  border-radius: 14px;
  padding: 10px 12px;
  margin: 8px 0;
  color: #000000 !important;
}

.v-row-danger{
  background: rgba(207, 59, 59, 0.08);
  border: 1px solid rgba(207, 59, 59, 0.24);
  border-radius: 14px;
  padding: 10px 12px;
  margin: 8px 0;
  color: #000000 !important;
}

.rank-card{
  background: linear-gradient(180deg, #ffffff, #f8fffb);
  border: 1px solid rgba(0,168,107,0.18);
  border-radius: 16px;
  padding: 14px 14px 12px 14px;
  margin: 10px 0;
  box-shadow: 0 8px 18px rgba(0,0,0,.05);
}

.rank-card-premium{
  background: linear-gradient(180deg, #fffdf6, #fff9ea);
  border: 1px solid rgba(212,175,55,0.28);
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

[data-testid="stDataFrame"]{
  border-radius: 16px !important;
  overflow: hidden !important;
  border: 1px solid rgba(0, 168, 107, 0.22) !important;
}

div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div{
  border-radius: 14px !important;
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

div.stButton > button[kind="primary"]:hover{
  filter: brightness(1.03);
  transform: translateY(-1px);
}

button[kind="header"]{
  opacity: 1 !important;
  visibility: visible !important;
}

@media (max-width: 640px){
  div.stButton > button[kind="primary"]{ width: 100% !important; }
  .rank-main{ font-size: 1.05rem; }
}
</style>
"""

# =========================================================
# HELPERS
# =========================================================
INT_RE = re.compile(r"\d+")


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
    run = 1
    for a, b in zip(nums_sorted, nums_sorted[1:]):
        if b == a + 1:
            run += 1
            if run >= run_len:
                return True
        else:
            run = 1
    return False


def pick_unique(pool: List[int], k: int) -> List[int]:
    pool = list(dict.fromkeys(pool))
    if len(pool) < k:
        raise ValueError("Za mało liczb w puli, aby wylosować unikalny zestaw.")
    return sorted(random.sample(pool, k))


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


# =========================================================
# VISUAL HELPERS
# =========================================================
def render_ticket_cards(records: List[Dict], preview_n: int) -> None:
    for i in range(preview_n):
        typ = records[i]["Typ"]
        kupon = records[i]["Kupon"]
        nums_str = " ".join(f"{x:02d}" for x in kupon)
        ev, od = even_odd_split(kupon)
        pairs = count_adjacent_pairs(sorted(kupon))
        css_class = "rank-card-premium" if typ == "premium" else "rank-card"

        st.markdown(
            f"""
<div class="{css_class}">
  <div class="rank-title">Kupon #{i+1:03d} <span class="v-muted">[{typ}]</span></div>
  <div class="rank-main">{nums_str}</div>
  <div class="rank-meta">
    Parzyste/Nieparzyste: <b>{ev}/{od}</b><br>
    Pary kolejne: <b>{pairs}</b>
  </div>
</div>
            """,
            unsafe_allow_html=True
        )


def render_turbo_cards(rows: List[Dict]) -> None:
    for row in rows:
        st.markdown(
            f"""
<div class="rank-card">
  <div class="rank-title">Ranking #{row["Ranking"]}</div>
  <div class="rank-main">{row["Kupon"]}</div>
  <div class="rank-meta">
    Score: <b>{row["Score"]}</b><br>
    Score liczb: <b>{row["Score liczb"]}</b> | Score par: <b>{row["Score par"]}</b> | Score trójek: <b>{row["Score trójek"]}</b><br>
    Parzyste/Nieparzyste: <b>{row["Parzyste/Nieparzyste"]}</b><br>
    Niskie/Wysokie: <b>{row["Niskie/Wysokie"]}</b><br>
    Rozstrzał: <b>{row["Rozstrzał"]}</b> | Pary kolejne: <b>{row["Pary kolejne"]}</b><br>
    Podobieństwo do ostatnich: <b>{row["Podobieństwo do ostatnich"]}</b>
  </div>
</div>
            """,
            unsafe_allow_html=True
        )


def render_premium_cards(rows: List[Dict]) -> None:
    for row in rows:
        st.markdown(
            f"""
<div class="rank-card-premium">
  <div class="rank-title">Premium #{row["Ranking"]}</div>
  <div class="rank-main">{row["Kupon"]}</div>
  <div class="rank-meta">
    Premium Score: <b>{row["Premium Score"]}</b><br>
    Bazowy Score: <b>{row["Bazowy Score"]}</b> | Bonus Premium: <b>{row["Bonus Premium"]}</b><br>
    HOT MAX trafień: <b>{row["HOT MAX trafień"]}</b> | Różnice trafień: <b>{row["Różnice trafień"]}</b> | Hot trafień: <b>{row["Hot trafień"]}</b><br>
    Parzyste/Nieparzyste: <b>{row["Parzyste/Nieparzyste"]}</b><br>
    Niskie/Wysokie: <b>{row["Niskie/Wysokie"]}</b><br>
    Rozstrzał: <b>{row["Rozstrzał"]}</b> | Pary kolejne: <b>{row["Pary kolejne"]}</b><br>
    Podobieństwo do ostatnich: <b>{row["Podobieństwo do ostatnich"]}</b>
  </div>
</div>
            """,
            unsafe_allow_html=True
        )


def render_wielka_szansa_cards(details: List[Dict]) -> None:
    for d in details:
        st.markdown(
            f"""
<div class="rank-card">
  <div class="rank-title">Pozycja #{d["Pozycja"]}</div>
  <div class="rank-main">Prognoza po korekcie: {int(d["Prognoza_po_korekcie"]):02d}</div>
  <div class="rank-meta">
    Ostatnia wartość: <b>{d["Ostatnia wartość"]}</b><br>
    Prognoza surowa: <b>{d["Prognoza"]}</b><br>
    Pewność: <b>{d["Pewność %"]}%</b><br>
    Metoda: <b>{d["Metoda"]}</b>
  </div>
</div>
            """,
            unsafe_allow_html=True
        )


# =========================================================
# PDF PARSING
# =========================================================
def _validate_pdf_bytes(pdf_bytes: bytes) -> None:
    if not pdf_bytes.startswith(b"%PDF"):
        head = pdf_bytes[:240].decode("utf-8", errors="replace")
        raise ValueError(
            "Plik PDF nie wygląda jak prawdziwy PDF (brak nagłówka %PDF).\n"
            f"Początek pliku:\n{head}"
        )


def _read_pdf_pages_text_pymupdf(pdf_bytes: bytes) -> List[str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page in doc:
        pages.append(page.get_text("text") or "")
    doc.close()
    return pages


def _extract_tokens_and_drawnos_from_page(page_text: str) -> Tuple[List[int], List[int]]:
    tokens: List[int] = []
    drawnos: List[int] = []

    lines = [ln.strip() for ln in (page_text or "").splitlines() if ln.strip()]
    in_drawno_section = False

    for ln in lines:
        if "Lotto" in ln and "6/49" in ln:
            continue
        if "multipasko" in ln.lower():
            continue
        if "www." in ln.lower():
            continue
        if "©" in ln:
            continue

        ints = [int(x) for x in INT_RE.findall(ln)]
        if not ints:
            continue

        if any(x >= DRAWNO_MIN for x in ints):
            in_drawno_section = True

        if in_drawno_section:
            for x in ints:
                if DRAWNO_MIN <= x < 100000:
                    drawnos.append(x)
        else:
            for x in ints:
                if NUM_MIN <= x <= NUM_MAX:
                    tokens.append(x)

    return tokens, drawnos


def _chunk_tokens_to_draws(tokens: List[int]) -> List[List[int]]:
    if len(tokens) < PICK_COUNT:
        return []

    if len(tokens) % PICK_COUNT == 0:
        draws = []
        for i in range(0, len(tokens), PICK_COUNT):
            d = tokens[i:i + PICK_COUNT]
            draws.append(sorted(d))
        return draws

    best = []
    best_valid = -1
    for offset in range(PICK_COUNT):
        t = tokens[offset:]
        if len(t) < PICK_COUNT:
            continue
        cut = (len(t) // PICK_COUNT) * PICK_COUNT
        t = t[:cut]
        draws = []
        valid = 0
        for i in range(0, len(t), PICK_COUNT):
            d = t[i:i + PICK_COUNT]
            if len(set(d)) == PICK_COUNT and all(NUM_MIN <= n <= NUM_MAX for n in d):
                valid += 1
            draws.append(sorted(d))
        if valid > best_valid:
            best_valid = valid
            best = draws
    return best


def _pair_draws_with_drawnos(draws: List[List[int]], drawnos: List[int]) -> List[Dict]:
    n = min(len(draws), len(drawnos))
    records: List[Dict] = []

    for i in range(n):
        records.append({
            "draw_no": drawnos[i],
            "date_str": "—",
            "date_iso": "",
            "nums": draws[i],
        })

    for j in range(n, len(draws)):
        records.append({
            "draw_no": None,
            "date_str": "—",
            "date_iso": "",
            "nums": draws[j],
        })

    with_no = [r for r in records if r["draw_no"] is not None]
    if len(with_no) > 10:
        records.sort(key=lambda r: (r["draw_no"] is None, r["draw_no"] or -1), reverse=True)

    return records


@st.cache_data(show_spinner=False)
def load_records_cached(pdf_bytes: bytes) -> List[Dict]:
    _validate_pdf_bytes(pdf_bytes)
    pages = _read_pdf_pages_text_pymupdf(pdf_bytes)

    all_tokens: List[int] = []
    all_drawnos: List[int] = []

    for ptxt in pages:
        tokens, drawnos = _extract_tokens_and_drawnos_from_page(ptxt)
        all_tokens.extend(tokens)
        all_drawnos.extend(drawnos)

    draws = _chunk_tokens_to_draws(all_tokens)
    if not draws:
        raise RuntimeError("Nie znaleziono żadnych wyników (tokenów 1–49) w PDF.")

    records = _pair_draws_with_drawnos(draws, all_drawnos)
    return records


# =========================================================
# STATS
# =========================================================
@st.cache_data(show_spinner=False)
def compute_presence_percent_df_cached(draws: List[List[int]]) -> pd.DataFrame:
    total_draws = len(draws)
    presence_counter = Counter()

    for draw in draws:
        unique_nums = set(draw)
        for n in unique_nums:
            presence_counter[n] += 1

    rows = []
    for n in range(NUM_MIN, NUM_MAX + 1):
        hits = presence_counter.get(n, 0)
        pct = (hits / total_draws * 100.0) if total_draws > 0 else 0.0
        rows.append({
            "Liczba": n,
            "Liczba_losowan_z_wystapieniem": hits,
            "Procent_losowan": pct
        })

    df = pd.DataFrame(rows).sort_values(
        ["Procent_losowan", "Liczba_losowan_z_wystapieniem", "Liczba"],
        ascending=[False, False, True]
    ).reset_index(drop=True)
    return df


def build_groups_from_percent(percent_df: pd.DataFrame, hot_size: int, cold_size: int) -> Tuple[List[int], List[int], List[int]]:
    hot = percent_df.head(hot_size)["Liczba"].tolist()
    cold = percent_df.tail(cold_size)["Liczba"].tolist()
    neutral = [n for n in range(NUM_MIN, NUM_MAX + 1) if n not in hot and n not in cold]
    return hot, cold, neutral


def build_hot_master_set(percent_df: pd.DataFrame) -> List[int]:
    return sorted(percent_df.head(PICK_COUNT)["Liczba"].tolist())


@st.cache_data(show_spinner=False)
def compute_pair_triple_stats_cached(draws: List[List[int]]) -> Tuple[Counter, Counter]:
    pair_counter = Counter()
    triple_counter = Counter()

    for draw in draws:
        sdraw = sorted(draw)
        for pair in combinations(sdraw, 2):
            pair_counter[pair] += 1
        for triple in combinations(sdraw, 3):
            triple_counter[triple] += 1

    return pair_counter, triple_counter


def build_target_profile(draws: List[List[int]]) -> Dict:
    spreads = [(max(d) - min(d)) for d in draws if d]
    pair_counts = [count_adjacent_pairs(sorted(d)) for d in draws if d]

    even_odd_counter = Counter()
    low_high_counter = Counter()

    for d in draws:
        s = sorted(d)
        ev, od = even_odd_split(s)
        even_odd_counter[(ev, od)] += 1

        low = sum(1 for x in s if x <= 24)
        high = len(s) - low
        low_high_counter[(low, high)] += 1

    target_even_odd = even_odd_counter.most_common(1)[0][0] if even_odd_counter else (3, 3)
    target_low_high = low_high_counter.most_common(1)[0][0] if low_high_counter else (3, 3)
    target_spread = sum(spreads) / len(spreads) if spreads else 0.0
    target_pairs = sum(pair_counts) / len(pair_counts) if pair_counts else 0.0

    return {
        "target_even_odd": target_even_odd,
        "target_low_high": target_low_high,
        "target_spread": target_spread,
        "target_pairs": target_pairs,
    }


# =========================================================
# HEATMAP
# =========================================================
def build_heatmap_df(percent_df: pd.DataFrame, columns_per_row: int = 7) -> pd.DataFrame:
    values = dict(zip(percent_df["Liczba"], percent_df["Procent_losowan"]))
    rows = []
    current = []
    for n in range(NUM_MIN, NUM_MAX + 1):
        current.append(f"{n:02d}\n{values.get(n, 0.0):.2f}%")
        if len(current) == columns_per_row:
            rows.append(current)
            current = []
    if current:
        while len(current) < columns_per_row:
            current.append("")
        rows.append(current)

    col_names = [f"C{i+1}" for i in range(columns_per_row)]
    return pd.DataFrame(rows, columns=col_names)


# =========================================================
# GENERATION
# =========================================================
def gen_ticket(mode: str, hot: List[int], cold: List[int], mix_hot_count: int) -> List[int]:
    if mode == "hot":
        return pick_unique(hot, PICK_COUNT)
    if mode == "cold":
        return pick_unique(cold, PICK_COUNT)
    if mode == "mix":
        if mix_hot_count >= PICK_COUNT:
            return pick_unique(hot, PICK_COUNT)
        if mix_hot_count <= 0:
            return pick_unique(cold, PICK_COUNT)
        h = pick_unique(hot, mix_hot_count)
        c = pick_unique([x for x in cold if x not in h], PICK_COUNT - mix_hot_count)
        return sorted(h + c)
    raise ValueError("Nieznany tryb losowania.")


def gen_ticket_hot_max_percent(draws_for_window: List[List[int]]) -> Tuple[List[int], pd.DataFrame]:
    pct_df = compute_presence_percent_df_cached(draws_for_window)
    top6 = pct_df.head(PICK_COUNT).copy()
    result_set = sorted(top6["Liczba"].tolist())
    return result_set, top6


# =========================================================
# SMART MODE
# =========================================================
def smart_ok(
    ticket: List[int],
    block_run_2: bool,
    block_run_3: bool,
    max_adjacent_pairs: Optional[int],
    even_odd_choice: str
) -> bool:
    nums = sorted(ticket)

    if block_run_3 and has_run_length(nums, 3):
        return False
    if block_run_2 and has_run_length(nums, 2):
        return False

    pairs = count_adjacent_pairs(nums)
    if max_adjacent_pairs is not None and pairs > max_adjacent_pairs:
        return False

    ev, od = even_odd_split(nums)
    if even_odd_choice != "Dowolnie":
        try:
            ev_t, od_t = even_odd_choice.split("/")
            if not (ev == int(ev_t) and od == int(od_t)):
                return False
        except Exception:
            pass

    return True


def generate_with_smart_filters(
    gen_func,
    n_tickets: int,
    max_attempts_per_ticket: int,
    smart_kwargs: Dict
) -> List[Dict]:
    out: List[Dict] = []
    attempts = 0
    while len(out) < n_tickets:
        attempts += 1
        if attempts > n_tickets * max_attempts_per_ticket:
            break
        rec = gen_func()
        if smart_ok(rec["Kupon"], **smart_kwargs):
            out.append(rec)
    return out


# =========================================================
# DAILY NUMBERS
# =========================================================
def flatten_last_n(draws: List[List[int]], n: int) -> List[int]:
    return [x for d in draws[:n] for x in d]


def parity_bias_from_last_n(draws: List[List[int]], n: int) -> str:
    nums = flatten_last_n(draws, n)
    ev = sum(1 for x in nums if x % 2 == 0)
    od = len(nums) - ev
    if ev > od:
        return "ODD"
    if od > ev:
        return "EVEN"
    return "ANY"


def high_low_bias_from_last_two(draws: List[List[int]], threshold: int) -> str:
    if len(draws) < 2:
        return "ANY"
    last2 = draws[:2]
    all_nums = [x for d in last2 for x in d]
    low = sum(1 for x in all_nums if x <= threshold)
    high = len(all_nums) - low
    if low >= high + 2:
        return "HIGH"
    if high >= low + 2:
        return "LOW"
    return "ANY"


def avg_spread_last_n(draws: List[List[int]], n: int) -> float:
    spreads = [(max(d) - min(d)) for d in draws[:n] if d]
    return sum(spreads) / len(spreads) if spreads else 0.0


def pick_daily_set_from_hot(
    hot: List[int],
    pick_count: int,
    nmin: int,
    nmax: int,
    prefer_parity: str,
    prefer_level: str,
    threshold: int,
    target_spread: Optional[float] = None,
    max_attempts: int = 650
) -> List[int]:
    hot_unique = sorted(set([x for x in hot if nmin <= x <= nmax]))
    if len(hot_unique) < pick_count:
        hot_unique = hot_unique + [x for x in range(nmin, nmax + 1) if x not in hot_unique]

    pool = hot_unique[:]

    if prefer_level != "ANY":
        filtered = [x for x in pool if (x <= threshold)] if prefer_level == "LOW" else [x for x in pool if (x > threshold)]
        if len(filtered) >= pick_count:
            pool = filtered

    if prefer_parity != "ANY":
        filtered = [x for x in pool if (x % 2 == 0)] if prefer_parity == "EVEN" else [x for x in pool if (x % 2 == 1)]
        if len(filtered) >= pick_count:
            pool = filtered

    best = None
    best_score = -10**9

    for _ in range(max_attempts):
        cand = sorted(random.sample(pool, pick_count))
        spread = cand[-1] - cand[0]
        score = 0.0

        if target_spread is not None:
            score -= abs(spread - target_spread) * 0.25

        if prefer_parity != "ANY":
            ev, od = even_odd_split(cand)
            score += (ev * 0.35) if prefer_parity == "EVEN" else (od * 0.35)

        if prefer_level != "ANY":
            low = sum(1 for x in cand if x <= threshold)
            high = pick_count - low
            score += (high * 0.25) if prefer_level == "HIGH" else (low * 0.25)

        if score > best_score:
            best_score = score
            best = cand

    return best if best is not None else sorted(random.sample(range(nmin, nmax + 1), pick_count))


# =========================================================
# POSITIONAL DIFFERENCE ANALYSIS
# =========================================================
def _choose_candidate_from_diffs(base_value: int, diff_counter: Counter, used: set, nmin: int, nmax: int) -> Optional[int]:
    for diff, _count in diff_counter.most_common():
        candidate = base_value + diff
        if nmin <= candidate <= nmax and candidate not in used:
            return candidate
    return None


def build_positional_difference_set(draws: List[List[int]], window: int) -> Dict:
    if not draws:
        return {
            "set": [],
            "details": [],
            "window_used": 0
        }

    latest = sorted(draws[0])
    subset = draws[:max(2, min(window, len(draws)))]
    previous_draws = [sorted(d) for d in subset[1:]]

    used = set()
    result: List[int] = []
    details: List[Dict] = []

    for pos in range(PICK_COUNT):
        latest_val = latest[pos]
        diffs = []

        for prev in previous_draws:
            if len(prev) != PICK_COUNT:
                continue
            diff = prev[pos] - latest_val
            diffs.append(diff)

        diff_counter = Counter(diffs)
        chosen = _choose_candidate_from_diffs(latest_val, diff_counter, used, NUM_MIN, NUM_MAX)

        if chosen is None:
            fallback = latest_val
            if fallback in used:
                for candidate in range(NUM_MIN, NUM_MAX + 1):
                    if candidate not in used:
                        fallback = candidate
                        break
            chosen = fallback

        used.add(chosen)
        result.append(chosen)

        most_common_diff = None
        most_common_count = 0
        if diff_counter:
            most_common_diff, most_common_count = diff_counter.most_common(1)[0]

        details.append({
            "Pozycja": pos + 1,
            "Najnowsza liczba": latest_val,
            "Najczęstsza różnica": most_common_diff if most_common_diff is not None else 0,
            "Ile razy": most_common_count,
            "Wybrana liczba": chosen
        })

    result = sorted(result)

    if len(set(result)) < PICK_COUNT:
        fixed = []
        used2 = set()
        for n in result:
            if n not in used2:
                fixed.append(n)
                used2.add(n)
            else:
                for c in range(NUM_MIN, NUM_MAX + 1):
                    if c not in used2:
                        fixed.append(c)
                        used2.add(c)
                        break
        result = sorted(fixed[:PICK_COUNT])

    return {
        "set": result,
        "details": details,
        "window_used": len(subset)
    }


# =========================================================
# TURBO SCORE
# =========================================================
def similarity_to_recent(ticket: List[int], recent_draws: List[List[int]]) -> int:
    tset = set(ticket)
    if not recent_draws:
        return 0
    return max(len(tset.intersection(set(d))) for d in recent_draws)


def score_ticket(
    ticket: List[int],
    percent_map: Dict[int, float],
    pair_counter: Counter,
    triple_counter: Counter,
    target_profile: Dict,
    recent_draws: List[List[int]]
) -> Dict:
    sticket = sorted(ticket)

    number_score = sum(percent_map.get(n, 0.0) for n in sticket)
    pair_score_raw = sum(pair_counter.get(tuple(pair), 0) for pair in combinations(sticket, 2))
    triple_score_raw = sum(triple_counter.get(tuple(triple), 0) for triple in combinations(sticket, 3))

    ev, od = even_odd_split(sticket)
    target_ev, target_od = target_profile["target_even_odd"]
    even_odd_penalty = abs(ev - target_ev) + abs(od - target_od)

    low = sum(1 for x in sticket if x <= 24)
    high = len(sticket) - low
    target_low, target_high = target_profile["target_low_high"]
    low_high_penalty = abs(low - target_low) + abs(high - target_high)

    spread = sticket[-1] - sticket[0]
    spread_penalty = abs(spread - target_profile["target_spread"])

    adj_pairs = count_adjacent_pairs(sticket)
    pair_shape_penalty = abs(adj_pairs - target_profile["target_pairs"])

    recent_similarity = similarity_to_recent(sticket, recent_draws)

    final_score = (
        number_score * 3.0
        + pair_score_raw * 0.55
        + triple_score_raw * 1.10
        - even_odd_penalty * 2.0
        - low_high_penalty * 2.0
        - spread_penalty * 0.10
        - pair_shape_penalty * 1.3
        - recent_similarity * 4.0
    )

    return {
        "ticket": sticket,
        "number_score": number_score,
        "pair_score_raw": pair_score_raw,
        "triple_score_raw": triple_score_raw,
        "evens": ev,
        "odds": od,
        "low": low,
        "high": high,
        "spread": spread,
        "adj_pairs": adj_pairs,
        "recent_similarity": recent_similarity,
        "final_score": final_score,
    }


def generate_candidate_tickets(
    count_candidates: int,
    base_mode_kind: str,
    hot: List[int],
    cold: List[int],
    mix_hot_count: int
) -> List[List[int]]:
    candidates = []

    for _ in range(count_candidates):
        if base_mode_kind == "hybrid":
            chosen = random.choices(["hot", "cold", "mix"], weights=[HYBRID_HOT_P, HYBRID_COLD_P, HYBRID_MIX_P], k=1)[0]
            candidates.append(gen_ticket(chosen, hot, cold, mix_hot_count))
        elif base_mode_kind == "hot":
            candidates.append(gen_ticket("hot", hot, cold, mix_hot_count))
        elif base_mode_kind == "cold":
            candidates.append(gen_ticket("cold", hot, cold, mix_hot_count))
        else:
            candidates.append(gen_ticket("mix", hot, cold, mix_hot_count))

    uniq = []
    seen = set()
    for t in candidates:
        key = tuple(sorted(t))
        if key not in seen:
            seen.add(key)
            uniq.append(sorted(t))

    return uniq


def build_turbo_score_ranking(
    draws_for_window: List[List[int]],
    hot: List[int],
    cold: List[int],
    base_mode_kind: str,
    mix_hot_count: int,
    candidate_count: int,
    top_n: int
) -> Dict:
    percent_df = compute_presence_percent_df_cached(draws_for_window)
    percent_map = dict(zip(percent_df["Liczba"], percent_df["Procent_losowan"]))

    pair_counter, triple_counter = compute_pair_triple_stats_cached(draws_for_window)
    target_profile = build_target_profile(draws_for_window)
    recent_draws = draws_for_window[:10]

    candidates = generate_candidate_tickets(
        count_candidates=candidate_count,
        base_mode_kind=base_mode_kind,
        hot=hot,
        cold=cold,
        mix_hot_count=mix_hot_count
    )

    scored = []
    for ticket in candidates:
        scored.append(
            score_ticket(
                ticket=ticket,
                percent_map=percent_map,
                pair_counter=pair_counter,
                triple_counter=triple_counter,
                target_profile=target_profile,
                recent_draws=recent_draws
            )
        )

    scored.sort(key=lambda x: x["final_score"], reverse=True)
    best = scored[:top_n]

    rows = []
    for i, item in enumerate(best, start=1):
        rows.append({
            "Ranking": i,
            "Kupon": " ".join(f"{x:02d}" for x in item["ticket"]),
            "Score": round(item["final_score"], 2),
            "Score liczb": round(item["number_score"], 2),
            "Score par": item["pair_score_raw"],
            "Score trójek": item["triple_score_raw"],
            "Parzyste/Nieparzyste": f"{item['evens']}/{item['odds']}",
            "Niskie/Wysokie": f"{item['low']}/{item['high']}",
            "Rozstrzał": item["spread"],
            "Pary kolejne": item["adj_pairs"],
            "Podobieństwo do ostatnich": item["recent_similarity"],
        })

    return {
        "rows": rows,
        "target_profile": target_profile,
        "candidate_count_used": len(candidates)
    }


# =========================================================
# PREMIUM MODE
# =========================================================
def mutate_ticket(ticket: List[int], source_pool: List[int], replace_count: int) -> List[int]:
    base = set(ticket)
    replace_count = min(replace_count, len(base))
    to_remove = set(random.sample(list(base), replace_count))
    kept = [x for x in base if x not in to_remove]
    available = [x for x in source_pool if x not in kept]
    need = PICK_COUNT - len(kept)

    if len(available) < need:
        available = [x for x in range(NUM_MIN, NUM_MAX + 1) if x not in kept]

    added = random.sample(available, need)
    return sorted(kept + added)


def build_premium_ranking(
    draws_for_window: List[List[int]],
    hot: List[int],
    cold: List[int],
    mix_hot_count: int,
    candidate_count: int,
    top_n: int
) -> Dict:
    percent_df = compute_presence_percent_df_cached(draws_for_window)
    percent_map = dict(zip(percent_df["Liczba"], percent_df["Procent_losowan"]))
    pair_counter, triple_counter = compute_pair_triple_stats_cached(draws_for_window)
    target_profile = build_target_profile(draws_for_window)
    recent_draws = draws_for_window[:10]

    hot_max_set, hot_max_table = gen_ticket_hot_max_percent(draws_for_window)
    diff_data = build_positional_difference_set(draws_for_window, min(999, len(draws_for_window)))
    diff_set = diff_data["set"]

    turbo_seed = build_turbo_score_ranking(
        draws_for_window=draws_for_window,
        hot=hot,
        cold=cold,
        base_mode_kind="hybrid",
        mix_hot_count=mix_hot_count,
        candidate_count=max(100, candidate_count // 2),
        top_n=min(10, top_n * 2)
    )

    seed_candidates = []
    seed_candidates.append(sorted(hot_max_set))
    seed_candidates.append(sorted(diff_set))

    for row in turbo_seed["rows"]:
        seed_candidates.append(sorted([int(x) for x in row["Kupon"].split()]))

    ordinary_candidates = generate_candidate_tickets(
        count_candidates=max(candidate_count, 200),
        base_mode_kind="hybrid",
        hot=hot,
        cold=cold,
        mix_hot_count=mix_hot_count
    )
    seed_candidates.extend(ordinary_candidates)

    source_pool = list(dict.fromkeys(hot + hot_max_set + diff_set + list(range(NUM_MIN, NUM_MAX + 1))))
    mutated = []
    for cand in seed_candidates[:min(len(seed_candidates), candidate_count)]:
        mutated.append(sorted(cand))
        mutated.append(mutate_ticket(cand, source_pool, 1))
        mutated.append(mutate_ticket(cand, source_pool, 2))

    all_candidates = seed_candidates + mutated

    uniq = []
    seen = set()
    for t in all_candidates:
        key = tuple(sorted(t))
        if len(key) == PICK_COUNT and key not in seen:
            seen.add(key)
            uniq.append(sorted(t))

    hot_max_set_ref = set(hot_max_set)
    diff_set_ref = set(diff_set)
    hot_ref = set(hot)

    premium_scored = []

    for ticket in uniq:
        base = score_ticket(
            ticket=ticket,
            percent_map=percent_map,
            pair_counter=pair_counter,
            triple_counter=triple_counter,
            target_profile=target_profile,
            recent_draws=recent_draws
        )

        overlap_hot_max = len(set(ticket).intersection(hot_max_set_ref))
        overlap_diff = len(set(ticket).intersection(diff_set_ref))
        overlap_hot = len(set(ticket).intersection(hot_ref))

        premium_bonus = (
            overlap_hot_max * 5.0
            + overlap_diff * 3.0
            + overlap_hot * 1.2
        )

        final_premium_score = base["final_score"] + premium_bonus

        premium_scored.append({
            **base,
            "premium_bonus": premium_bonus,
            "overlap_hot_max": overlap_hot_max,
            "overlap_diff": overlap_diff,
            "overlap_hot": overlap_hot,
            "premium_final_score": final_premium_score,
        })

    premium_scored.sort(key=lambda x: x["premium_final_score"], reverse=True)
    best = premium_scored[:top_n]

    rows = []
    for i, item in enumerate(best, start=1):
        rows.append({
            "Ranking": i,
            "Kupon": " ".join(f"{x:02d}" for x in item["ticket"]),
            "Premium Score": round(item["premium_final_score"], 2),
            "Bazowy Score": round(item["final_score"], 2),
            "Bonus Premium": round(item["premium_bonus"], 2),
            "HOT MAX trafień": item["overlap_hot_max"],
            "Różnice trafień": item["overlap_diff"],
            "Hot trafień": item["overlap_hot"],
            "Parzyste/Nieparzyste": f"{item['evens']}/{item['odds']}",
            "Niskie/Wysokie": f"{item['low']}/{item['high']}",
            "Rozstrzał": item["spread"],
            "Pary kolejne": item["adj_pairs"],
            "Podobieństwo do ostatnich": item["recent_similarity"],
        })

    return {
        "rows": rows,
        "candidate_count_used": len(uniq),
        "hot_max_set": hot_max_set,
        "hot_max_table": hot_max_table,
        "diff_set": diff_set,
        "diff_details": diff_data["details"],
        "target_profile": target_profile,
    }


# =========================================================
# AI SIMULATION
# =========================================================
def weighted_sample_without_replacement(population: np.ndarray, weights: np.ndarray, k: int, rng: np.random.Generator) -> List[int]:
    probs = weights / weights.sum()
    chosen = rng.choice(population, size=k, replace=False, p=probs)
    return sorted(chosen.tolist())


@st.cache_data(show_spinner=False)
def run_ai_simulation_cached(percent_df: pd.DataFrame, n_sims: int) -> Dict:
    rng = np.random.default_rng(12345)

    population = np.array(percent_df["Liczba"].tolist(), dtype=int)
    weights = np.array(percent_df["Procent_losowan"].tolist(), dtype=float) + 0.01

    number_occ = Counter()
    pair_occ = Counter()

    for _ in range(n_sims):
        draw = weighted_sample_without_replacement(population, weights, PICK_COUNT, rng)

        for n in draw:
            number_occ[n] += 1

        for pair in combinations(draw, 2):
            pair_occ[pair] += 1

    sim_df = pd.DataFrame(
        [{"Liczba": n, "Symulacje_wystapien": number_occ.get(n, 0)} for n in range(NUM_MIN, NUM_MAX + 1)]
    ).sort_values(["Symulacje_wystapien", "Liczba"], ascending=[False, True]).reset_index(drop=True)

    sim_set = sorted(sim_df.head(PICK_COUNT)["Liczba"].tolist())

    top_pairs = pd.DataFrame(
        [{"Para": f"{a:02d}-{b:02d}", "Wystąpienia": c} for (a, b), c in pair_occ.most_common(15)]
    )

    return {
        "sim_df": sim_df,
        "sim_set": sim_set,
        "top_pairs": top_pairs,
        "n_sims": n_sims
    }


# =========================================================
# CYCLE DETECTION
# =========================================================
@st.cache_data(show_spinner=False)
def detect_cycles_cached(draws: List[List[int]]) -> pd.DataFrame:
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
            avg_gap = float(sum(gaps) / len(gaps))
            last_gap = float((total - 1) - positions[-1])
            cycle_ratio = (last_gap / avg_gap) if avg_gap > 0 else 0.0
        elif occurrences == 1:
            avg_gap = 0.0
            last_gap = float((total - 1) - positions[-1])
            cycle_ratio = 0.0
        else:
            avg_gap = 0.0
            last_gap = float(total)
            cycle_ratio = 0.0

        rows.append({
            "Liczba": num,
            "Wystąpienia": occurrences,
            "Średni_cykl": round(avg_gap, 2),
            "Aktualna_przerwa": round(last_gap, 2),
            "Cycle_Ratio": round(cycle_ratio, 3)
        })

    df = pd.DataFrame(rows).sort_values(
        ["Cycle_Ratio", "Wystąpienia", "Liczba"],
        ascending=[False, False, True]
    ).reset_index(drop=True)

    return df


# =========================================================
# WIELKA SZANSA
# =========================================================
def _series_for_position(draws_newest_first: List[List[int]], pos_idx: int, window: int) -> List[int]:
    subset = draws_newest_first[:min(window, len(draws_newest_first))]
    chronological = list(reversed(subset))
    return [row[pos_idx] for row in chronological if len(row) == PICK_COUNT]


def _linear_projection(series: List[int], recent_points: int = 8) -> float:
    if len(series) < 2:
        return float(series[-1]) if series else 1.0

    use = series[-min(recent_points, len(series)):]
    x = np.arange(len(use), dtype=float)
    y = np.array(use, dtype=float)

    if len(use) == 1:
        return float(use[-1])

    a, b = np.polyfit(x, y, 1)
    return float(a * len(use) + b)


def _recent_delta_projection(series: List[int], max_deltas: int = 6) -> float:
    if len(series) < 2:
        return float(series[-1]) if series else 1.0

    deltas = np.diff(series)
    if len(deltas) == 0:
        return float(series[-1])

    recent = deltas[-min(max_deltas, len(deltas)):]
    weights = np.linspace(1.0, 2.2, len(recent))
    step = float(np.average(recent, weights=weights))
    return float(series[-1] + step)


def _curvature_projection(series: List[int], max_points: int = 8) -> float:
    if len(series) < 3:
        return _recent_delta_projection(series)

    use = series[-min(max_points, len(series)):]
    x = np.arange(len(use), dtype=float)
    y = np.array(use, dtype=float)

    if len(use) < 3:
        return _recent_delta_projection(series)

    coeff = np.polyfit(x, y, 2)
    poly = np.poly1d(coeff)
    return float(poly(len(use)))


def _normalized_step_pattern(series: List[int], step_len: int = 4) -> Optional[Tuple[int, ...]]:
    if len(series) < step_len + 1:
        return None
    deltas = np.diff(series[-(step_len + 1):])
    clipped = [int(np.clip(round(d), -6, 6)) for d in deltas]
    return tuple(clipped)


def _pattern_match_projection(series: List[int], nmin: int, nmax: int, step_len: int = 4) -> Optional[float]:
    if len(series) < step_len + 6:
        return None

    target = _normalized_step_pattern(series, step_len=step_len)
    if target is None:
        return None

    candidates = []
    for end_idx in range(step_len, len(series) - 1):
        past = series[:end_idx + 1]
        patt = _normalized_step_pattern(past, step_len=step_len)
        if patt is None:
            continue

        distance = sum(abs(a - b) for a, b in zip(target, patt))
        if distance <= 4:
            candidates.append((distance, series[end_idx + 1]))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    best_vals = [v for _, v in candidates[:12]]
    return float(sum(best_vals) / len(best_vals))


def _smooth_prediction(preds: List[float], fallback: float) -> float:
    clean = [p for p in preds if p is not None and not np.isnan(p)]
    if not clean:
        return fallback
    return float(sum(clean) / len(clean))


def _enforce_sorted_forecast(raw_values: List[int]) -> List[int]:
    vals = raw_values[:]
    vals[0] = clamp(vals[0], NUM_MIN, NUM_MAX - (PICK_COUNT - 1))

    for i in range(1, PICK_COUNT):
        low = vals[i - 1] + 1
        high = NUM_MAX - (PICK_COUNT - 1 - i)
        vals[i] = clamp(vals[i], low, high)

    vals = sorted(vals)

    fixed = []
    for i, v in enumerate(vals):
        low = NUM_MIN if i == 0 else fixed[-1] + 1
        high = NUM_MAX - (PICK_COUNT - 1 - i)
        fixed.append(clamp(v, low, high))

    return fixed


def _score_forecast_confidence(series: List[int], predicted: int) -> float:
    if len(series) < 6:
        return 0.0

    last = series[-1]
    deltas = np.diff(series[-8:]) if len(series) >= 8 else np.diff(series)
    delta_std = float(np.std(deltas)) if len(deltas) > 0 else 0.0
    step = abs(predicted - last)

    base = 100.0
    base -= delta_std * 8.0
    base -= step * 2.2

    unique_recent = len(set(series[-10:])) if len(series) >= 10 else len(set(series))
    base += min(unique_recent, 10) * 0.8

    return round(clamp(int(round(base)), 1, 99), 2)


def build_wielka_szansa_set(draws_newest_first: List[List[int]], window: int) -> Dict:
    use_window = min(window, len(draws_newest_first))
    subset_newest = draws_newest_first[:use_window]

    forecast = []
    details = []

    for pos in range(PICK_COUNT):
        series = _series_for_position(subset_newest, pos, use_window)
        if not series:
            fallback = pos + 1
            forecast.append(fallback)
            details.append({
                "Pozycja": pos + 1,
                "Ostatnia wartość": fallback,
                "Prognoza": fallback,
                "Pewność %": 0.0,
                "Metoda": "fallback"
            })
            continue

        last_val = float(series[-1])
        p1 = _linear_projection(series, recent_points=8)
        p2 = _recent_delta_projection(series, max_deltas=6)
        p3 = _curvature_projection(series, max_points=8)
        p4 = _pattern_match_projection(series, NUM_MIN, NUM_MAX, step_len=4)

        blended = _smooth_prediction([p1, p2, p3, p4], fallback=last_val)

        pred = int(round(blended))
        pred = clamp(pred, NUM_MIN, NUM_MAX)

        confidence = _score_forecast_confidence(series, pred)

        used_methods = ["linia", "delta", "krzywizna"]
        if p4 is not None:
            used_methods.append("wzorzec")

        forecast.append(pred)
        details.append({
            "Pozycja": pos + 1,
            "Ostatnia wartość": int(series[-1]),
            "Prognoza": pred,
            "Pewność %": confidence,
            "Metoda": ", ".join(used_methods)
        })

    forecast = _enforce_sorted_forecast(forecast)

    for i in range(PICK_COUNT):
        details[i]["Prognoza_po_korekcie"] = forecast[i]

    return {
        "set": forecast,
        "details": details,
        "window_used": use_window,
        "opis": "Prognoza dalszego przebiegu każdej pozycji 1–6 na podstawie trendu, delty, krzywizny i podobnych wzorców historycznych."
    }


# =========================================================
# TXT EXPORTS
# =========================================================
def make_txt_for_tickets(records: List[Dict]) -> bytes:
    lines = []
    for i, r in enumerate(records, start=1):
        nums = " ".join(f"{x:02d}" for x in r["Kupon"])
        lines.append(f"{i:03d}. [{r['Typ']}] {nums}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_txt_for_results(result_records: List[Dict]) -> bytes:
    lines = []
    for r in result_records:
        draw_no = r.get("draw_no")
        draw_str = str(draw_no) if draw_no is not None else "—"
        date_str = r.get("date_str") or "—"
        nums = " ".join(f"{x:02d}" for x in r["nums"])
        lines.append(f"Losowanie: {draw_str} | Data: {date_str} | Wynik: {nums}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_txt_for_hot_master_set(hot_master_set: List[int], history_window: int) -> bytes:
    nums = " ".join(f"{x:02d}" for x in hot_master_set)
    text = (
        f"Zestaw 6 najczęściej padających liczb wg procentu losowań\n"
        f"Analizowana historia: ostatnie {history_window} losowań\n"
        f"Zestaw: {nums}\n"
    )
    return text.encode("utf-8")


def make_txt_for_difference_set(diff_data: Dict, selected_window: int) -> bytes:
    nums = " ".join(f"{x:02d}" for x in diff_data["set"])
    lines = [
        "Zestaw różnic pozycyjnych",
        f"Wybrany zakres użytkownika: {selected_window}",
        f"Faktycznie użyty zakres: {diff_data['window_used']}",
        f"Zestaw: {nums}",
        "",
        "Szczegóły pozycji:"
    ]
    for d in diff_data["details"]:
        lines.append(
            f"Pozycja {d['Pozycja']}: "
            f"najnowsza={d['Najnowsza liczba']}, "
            f"najczęstsza różnica={d['Najczęstsza różnica']}, "
            f"ile razy={d['Ile razy']}, "
            f"wybrana={d['Wybrana liczba']}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_txt_for_hot_max_set(hot_max_set: List[int], hot_max_table: pd.DataFrame, selected_window: int) -> bytes:
    nums = " ".join(f"{x:02d}" for x in hot_max_set)
    lines = [
        "HOT MAX 6 — zestaw 6 najczęściej padających liczb wg procentu losowań",
        f"Zakres analizy: ostatnie {selected_window} losowań",
        f"Zestaw: {nums}",
        "",
        "TOP 6:"
    ]
    for _, row in hot_max_table.iterrows():
        lines.append(
            f"Liczba {int(row['Liczba']):02d} | "
            f"Losowania z wystąpieniem: {int(row['Liczba_losowan_z_wystapieniem'])} | "
            f"Procent: {float(row['Procent_losowan']):.2f}%"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_txt_for_turbo_score(rows: List[Dict], candidate_count_used: int) -> bytes:
    lines = [
        "Turbo Score — ranking kuponów",
        f"Liczba ocenionych kandydatów: {candidate_count_used}",
        ""
    ]
    for row in rows:
        lines.append(
            f"#{row['Ranking']} | {row['Kupon']} | "
            f"Score={row['Score']} | "
            f"Liczby={row['Score liczb']} | "
            f"Pary={row['Score par']} | "
            f"Trójki={row['Score trójek']} | "
            f"Parzyste/Nieparzyste={row['Parzyste/Nieparzyste']} | "
            f"Niskie/Wysokie={row['Niskie/Wysokie']} | "
            f"Rozstrzał={row['Rozstrzał']} | "
            f"Pary kolejne={row['Pary kolejne']} | "
            f"Podobieństwo do ostatnich={row['Podobieństwo do ostatnich']}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_txt_for_premium(rows: List[Dict], candidate_count_used: int) -> bytes:
    lines = [
        "Premium Mode — ranking kuponów",
        f"Liczba ocenionych kandydatów: {candidate_count_used}",
        ""
    ]
    for row in rows:
        lines.append(
            f"#{row['Ranking']} | {row['Kupon']} | "
            f"Premium Score={row['Premium Score']} | "
            f"Base Score={row['Bazowy Score']} | "
            f"Bonus={row['Bonus Premium']} | "
            f"HOT MAX trafień={row['HOT MAX trafień']} | "
            f"Różnice trafień={row['Różnice trafień']} | "
            f"Hot trafień={row['Hot trafień']} | "
            f"Parzyste/Nieparzyste={row['Parzyste/Nieparzyste']} | "
            f"Niskie/Wysokie={row['Niskie/Wysokie']} | "
            f"Rozstrzał={row['Rozstrzał']} | "
            f"Pary kolejne={row['Pary kolejne']} | "
            f"Podobieństwo do ostatnich={row['Podobieństwo do ostatnich']}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_txt_for_simulation(sim: Dict) -> bytes:
    nums = " ".join(f"{x:02d}" for x in sim["sim_set"])
    lines = [
        f"AI symulacja Lotto — liczba symulacji: {sim['n_sims']}",
        f"Sugerowany zestaw: {nums}",
        "",
        "TOP pary:"
    ]
    if not sim["top_pairs"].empty:
        for _, row in sim["top_pairs"].iterrows():
            lines.append(f"{row['Para']} -> {row['Wystąpienia']}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_txt_for_cycles(cycle_df: pd.DataFrame, cycle_set: List[int]) -> bytes:
    nums = " ".join(f"{x:02d}" for x in cycle_set)
    lines = [
        "Lotto — analiza cykli liczb",
        f"Sugerowany zestaw cykli: {nums}",
        "",
        "TOP liczby cykliczne:"
    ]
    for _, row in cycle_df.head(15).iterrows():
        lines.append(
            f"Liczba {int(row['Liczba']):02d} | Wystąpienia={int(row['Wystąpienia'])} | "
            f"Średni cykl={row['Średni_cykl']} | Aktualna przerwa={row['Aktualna_przerwa']} | "
            f"Cycle ratio={row['Cycle_Ratio']}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_txt_for_wielka_szansa(ws: Dict, selected_window: int) -> bytes:
    nums = " ".join(f"{x:02d}" for x in ws["set"])
    lines = [
        "Wielka Szansa — prognoza wykresowa pozycji 1–6",
        f"Zakres analizy: {selected_window}",
        f"Faktycznie użyty zakres: {ws['window_used']}",
        f"Zestaw: {nums}",
        "",
        ws["opis"],
        "",
        "Szczegóły pozycji:"
    ]
    for d in ws["details"]:
        lines.append(
            f"Pozycja {d['Pozycja']} | ostatnia={d['Ostatnia wartość']} | "
            f"prognoza surowa={d['Prognoza']} | prognoza po korekcie={d['Prognoza_po_korekcie']} | "
            f"pewność={d['Pewność %']} | metoda={d['Metoda']}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


# =========================================================
# FEATURE DESCRIPTIONS
# =========================================================
def render_feature_descriptions():
    with st.expander("📘 Opisy funkcji aplikacji", expanded=False):
        st.markdown("""
**🏆 Generuj kupony**  
Tworzy kupony zgodnie z wybranym trybem: hybryda, tylko gorące, tylko zimne, mix albo premium.

**🌿 Szczęśliwe cyfry dnia**  
Buduje zestaw dnia na podstawie ostatnich losowań, balansu parzyste/nieparzyste, niskie/wysokie i rozstrzału.

**📋 Pokaż wyniki**  
Pokazuje ostatnie wyniki wczytane z `wyniki.pdf` albo `wynik.pdf`.

**🔥 Zestaw 6 HOT**  
Pokazuje 6 liczb o najwyższym procencie wystąpień w losowaniach z wybranego zakresu.

**📐 Zestaw różnic**  
Analizuje różnice pozycji 1–6 między najnowszym losowaniem a wcześniejszymi losowaniami i buduje nowy zestaw.

**🔥 HOT MAX 6**  
Gdy aktywne i ustawione na 6 przy trybie „Tylko gorące”, tworzy pełny zestaw 6 liczb o najwyższym procencie wystąpień.

**⭐ Turbo Score / Ranking kuponów**  
Generuje wielu kandydatów, punktuje ich i wybiera najlepsze kupony na podstawie:
- procentu wystąpień liczb,
- częstotliwości par,
- częstotliwości trójek,
- balansu parzyste/nieparzyste,
- balansu niskie/wysokie,
- rozstrzału,
- podobieństwa do ostatnich losowań.

**👑 Premium**  
Łączy:
- HOT/COLD,
- HOT MAX,
- zestaw różnic pozycyjnych,
- Turbo Score,
- mutacje kandydatów.

**🟦 Heatmapa**  
Pokazuje mapę 1–49 z procentem wystąpień każdej liczby.

**🤖 AI symulacja**  
Uruchamia ważone symulacje losowań na podstawie historycznych procentów i pokazuje sugerowany zestaw.

**🔄 Cykle liczb**  
Wyszukuje liczby, które historycznie miały pewien rytm pojawiania się i sprawdza, czy są blisko swojego cyklu.

**🎯 Wielka Szansa**  
Dla każdej pozycji 1–6 buduje dalszy ciąg „wykresu” tej pozycji:
- bierze serię z tej samej pozycji,
- analizuje trend liniowy,
- analizuje ostatnie przyrosty,
- analizuje krzywiznę przebiegu,
- szuka podobnych wzorców historycznych,
- łączy te prognozy w jedną liczbę końcową,
- pilnuje, aby końcowy zestaw był rosnący i poprawny jak w Lotto.

**🧠 Tryb inteligentny**  
Dodatkowe filtry ograniczające mało pożądane układy, np. za dużo kolejnych liczb.
        """)


# =========================================================
# SETTINGS PANEL
# =========================================================
def settings_panel(defaults: Dict) -> Dict:
    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("⚙️ Ustawienia (panel główny — działa na komputerze i telefonie)")

    mode_ui = st.selectbox(
        "Tryb typowania",
        [
            "Hybryda 70/20/10 (hot/cold/mix)",
            "Tylko 🔥 gorące",
            "Tylko ❄️ zimne",
            "Tylko ⚗️ mix (hot+zimne)",
            "Premium 👑",
        ],
        index=defaults.get("mode_index", 0),
        help="Premium łączy HOT/COLD, HOT MAX, różnice pozycyjne i ranking scoringowy."
    )

    history_window = st.selectbox(
        "Ile ostatnich losowań brać do analizy HOT/COLD?",
        [50, 100, 250, 500, 750, 1000],
        index=defaults.get("hist_index", 5)
    )

    difference_window = st.selectbox(
        "Analiza różnic pozycyjnych — zakres losowań",
        [50, 100, 250, 500, 750, 999],
        index=defaults.get("diff_hist_index", 5)
    )

    wielka_szansa_window = st.selectbox(
        "Wielka Szansa — zakres wykresu pozycji",
        [100, 999],
        index=defaults.get("wielka_idx", 1),
        help="100 = krótszy, świeższy trend. 999 = pełna historia."
    )

    c1, c2 = st.columns(2)
    with c1:
        n_tickets = st.slider("Liczba kuponów", 1, 500, defaults.get("n_tickets", 50), 1)
        hot_size = st.slider("Ile liczb w grupie Gorących", 6, 35, defaults.get("hot_size", 20), 1)
    with c2:
        preview_limit = st.slider("Ile kuponów pokazać w podglądzie", 10, 200, defaults.get("preview_limit", 60), 10)
        cold_size = st.slider("Ile liczb w grupie Zimnych", 6, 35, defaults.get("cold_size", 20), 1)

    mix_hot_count = st.slider("MIX: ile liczb z gorących?", 1, 5, defaults.get("mix_hot_count", 3), 1)

    st.markdown("---")
    st.subheader("🔥 Opcja HOT MAX")
    hot_max_enabled = st.checkbox(
        "Włącz HOT MAX 6 (działa tylko przy trybie: Tylko gorące)",
        value=defaults.get("hot_max_enabled", False)
    )
    hot_max_count = st.selectbox(
        "Ile cyfr z HOT MAX?",
        [1, 2, 3, 4, 5, 6],
        index=defaults.get("hot_max_count_idx", 5)
    )

    st.markdown("---")
    st.subheader("⭐ Turbo Score / Ranking kuponów")
    turbo_candidate_count = st.selectbox(
        "Ile kandydatów ma ocenić Turbo Score?",
        [100, 200, 300, 500, 750, 1000],
        index=defaults.get("turbo_candidate_idx", 3)
    )
    turbo_top_n = st.selectbox(
        "Ile najlepszych kuponów pokazać?",
        [3, 5, 10, 15, 20],
        index=defaults.get("turbo_top_idx", 4)
    )

    st.markdown("---")
    st.subheader("👑 Premium")
    premium_candidate_count = st.selectbox(
        "Premium: ile kandydatów ma zbudować silnik premium?",
        [200, 300, 500, 750, 1000, 1500],
        index=defaults.get("premium_candidate_idx", 2)
    )
    premium_top_n = st.selectbox(
        "Premium: ile finalnych kuponów pokazać?",
        [3, 5, 10, 15, 20],
        index=defaults.get("premium_top_idx", 4)
    )

    st.markdown("---")
    st.subheader("🤖 AI symulacja")
    ai_sim_count = st.selectbox(
        "Ile losowań ma zasymulować AI?",
        [5000, 10000, 25000, 50000, 100000],
        index=defaults.get("ai_sim_idx", 4)
    )

    st.markdown("---")
    st.subheader("🧠 Tryb inteligentny (opcjonalny)")
    smart_enabled = st.checkbox("Włącz tryb inteligentny", value=defaults.get("smart_enabled", False))

    if smart_enabled:
        block_run_2 = st.checkbox("Blokuj układy 1–2 (kolejne liczby)", value=defaults.get("block_run_2", True))
        block_run_3 = st.checkbox("Blokuj układy 1–3 (ciąg 3 kolejnych)", value=defaults.get("block_run_3", True))

        limit_pairs_on = st.checkbox("Włącz limit par (kolejne liczby)", value=defaults.get("limit_pairs_on", True))
        max_adj_pairs = None
        if limit_pairs_on:
            max_adj_pairs = st.slider("Maks. liczba par kolejnych", 0, 5, defaults.get("max_adj_pairs", 2), 1)

        even_odd_choice = st.radio(
            "Parzyste / Nieparzyste (6 liczb)",
            ["Dowolnie", "3/3", "4/2", "2/4", "5/1", "1/5", "6/0", "0/6"],
            index=defaults.get("even_odd_idx", 0)
        )

        max_attempts_per_ticket = st.slider("Limit prób na kupon", 10, 500, defaults.get("max_attempts", 120), 10)
    else:
        block_run_2 = False
        block_run_3 = False
        max_adj_pairs = None
        even_odd_choice = "Dowolnie"
        max_attempts_per_ticket = 120

    st.markdown("</div>", unsafe_allow_html=True)

    return {
        "mode_ui": mode_ui,
        "history_window": int(history_window),
        "difference_window": int(difference_window),
        "wielka_szansa_window": int(wielka_szansa_window),
        "n_tickets": int(n_tickets),
        "hot_size": int(hot_size),
        "cold_size": int(cold_size),
        "mix_hot_count": int(mix_hot_count),
        "preview_limit": int(preview_limit),
        "hot_max_enabled": bool(hot_max_enabled),
        "hot_max_count": int(hot_max_count),
        "turbo_candidate_count": int(turbo_candidate_count),
        "turbo_top_n": int(turbo_top_n),
        "premium_candidate_count": int(premium_candidate_count),
        "premium_top_n": int(premium_top_n),
        "ai_sim_count": int(ai_sim_count),
        "smart_enabled": bool(smart_enabled),
        "block_run_2": bool(block_run_2),
        "block_run_3": bool(block_run_3),
        "max_adj_pairs": max_adj_pairs,
        "even_odd_choice": even_odd_choice,
        "max_attempts_per_ticket": int(max_attempts_per_ticket),
    }


# =========================================================
# MAIN APP
# =========================================================
def main():
    st.set_page_config(
        page_title="Generator-Victory Lotto",
        page_icon="🏆",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    st.markdown(LIGHT_GREEN_CSS, unsafe_allow_html=True)

    st.title(APP_TITLE)
    st.write("Generator typowań Lotto na bazie historii losowań z pliku **wyniki.pdf** / **wynik.pdf** (1–49, typuje 6 liczb).")
    st.caption("Poprawiona wersja: rankingi Turbo Score, Premium i Wielka Szansa są wyświetlane jako czytelne karty, bez psucia układu na telefonach.")

    session_defaults = {
        "last_records": [],
        "last_daily": None,
        "show_results": False,
        "hot_master_set": None,
        "difference_set": None,
        "hot_max_set": None,
        "turbo_score_result": None,
        "premium_result": None,
        "ai_sim_result": None,
        "cycle_result": None,
        "heatmap_df": None,
        "wielka_szansa_result": None,
    }
    for key, value in session_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    pdf_path = resolve_pdf_path()

    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("📄 Dane wejściowe")
    st.write(f"Plik: `{pdf_path}`")
    st.write("Silnik PDF: **PyMuPDF (fitz)**")
    st.markdown(
        '<div class="v-muted">Gorące = najwyższy procent losowań z wystąpieniem liczby. '
        'Zimne = najniższy procent losowań z wystąpieniem liczby.</div>',
        unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)

    render_feature_descriptions()

    if not pdf_path.exists():
        st.error("❌ Nie znaleziono pliku `wyniki.pdf` ani `wynik.pdf` obok `app.py`.")
        st.stop()

    try:
        pdf_bytes = pdf_path.read_bytes()
        result_records_all = load_records_cached(pdf_bytes)
    except Exception as e:
        st.error("❌ Aplikacja nie mogła wczytać PDF albo wyciągnąć wyników.")
        st.code(str(e))
        st.stop()

    defaults = {
        "mode_index": 0,
        "hist_index": 5,
        "diff_hist_index": 5,
        "wielka_idx": 1,
        "n_tickets": 50,
        "hot_size": 20,
        "cold_size": 20,
        "mix_hot_count": 3,
        "preview_limit": 60,
        "hot_max_enabled": False,
        "hot_max_count_idx": 5,
        "turbo_candidate_idx": 3,
        "turbo_top_idx": 4,
        "premium_candidate_idx": 2,
        "premium_top_idx": 4,
        "ai_sim_idx": 4,
        "smart_enabled": False,
        "block_run_2": True,
        "block_run_3": True,
        "limit_pairs_on": True,
        "max_adj_pairs": 2,
        "even_odd_idx": 0,
        "max_attempts": 120
    }

    with st.expander("⚙️ Ustawienia (kliknij, aby rozwinąć)", expanded=True):
        cfg = settings_panel(defaults)

    history_window_used = min(cfg["history_window"], len(result_records_all))
    result_records = result_records_all[:history_window_used]
    draws = [r["nums"] for r in result_records]

    percent_df = compute_presence_percent_df_cached(draws)
    hot, cold, _neutral = build_groups_from_percent(percent_df, hot_size=cfg["hot_size"], cold_size=cfg["cold_size"])
    hot_master_set = build_hot_master_set(percent_df)

    left, right = st.columns([1.2, 0.8], gap="large")

    with left:
        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("📊 Statystyka procentowa 1–49 (z prawdziwych wyników)")
        st.success(f"✅ Analizowane losowania: **{len(result_records)}** (z {len(result_records_all)} w PDF)")
        percent_df_display = percent_df.copy()
        percent_df_display["Procent_losowan"] = percent_df_display["Procent_losowan"].map(lambda x: f"{x:.2f}%")
        st.dataframe(percent_df_display, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🔥 Gorące / ❄️ Zimne")
        st.markdown("**Gorące (Hot) — najwyższy % wystąpień**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(hot)]), unsafe_allow_html=True)
        st.markdown("**Zimne (Cold) — najniższy % wystąpień**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(cold)]), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🎛️ Wybrany tryb")
        st.write(f"**Tryb:** {cfg['mode_ui']}")
        st.write(f"**Analiza HOT/COLD:** ostatnie **{history_window_used}** losowań")
        st.write(f"**Wielka Szansa:** zakres **{cfg['wielka_szansa_window']}**")
        st.write(f"**Turbo Score — kandydaci:** {cfg['turbo_candidate_count']}")
        st.write(f"**Turbo Score — TOP:** {cfg['turbo_top_n']}")
        st.write(f"**Premium — kandydaci:** {cfg['premium_candidate_count']}")
        st.write(f"**Premium — TOP:** {cfg['premium_top_n']}")
        st.write(f"**AI symulacja:** {cfg['ai_sim_count']} losowań")
        st.write(f"**Tryb inteligentny:** {'TAK' if cfg['smart_enabled'] else 'NIE'}")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("🎟️ Narzędzia")

    c1, c2, c3, c4 = st.columns(4, gap="large")
    with c1:
        generate = st.button("🏆 GENERUJ KUPONY", type="primary", use_container_width=True)
        daily = st.button("🌿 SZCZĘŚLIWE CYFRY DNIA", type="primary", use_container_width=True)
    with c2:
        show_res = st.button("📋 POKAŻ WYNIKI", type="primary", use_container_width=True)
        show_hot_set = st.button("🔥 ZESTAW 6 HOT", type="primary", use_container_width=True)
    with c3:
        build_diff_set = st.button("📐 ZESTAW RÓŻNIC", type="primary", use_container_width=True)
        build_turbo = st.button("⭐ TURBO SCORE", type="primary", use_container_width=True)
    with c4:
        build_premium = st.button("👑 PREMIUM", type="primary", use_container_width=True)
        build_ai_sim = st.button("🤖 AI SYMULACJA", type="primary", use_container_width=True)

    c5, c6, c7 = st.columns(3, gap="large")
    with c5:
        build_heatmap = st.button("🟦 HEATMAPA", type="primary", use_container_width=True)
    with c6:
        build_cycles = st.button("🔄 CYKLE LICZB", type="primary", use_container_width=True)
    with c7:
        build_wielka_szansa = st.button("🎯 WIELKA SZANSA", type="primary", use_container_width=True)

    if show_res:
        st.session_state["show_results"] = not st.session_state["show_results"]

    if show_hot_set:
        st.session_state["hot_master_set"] = hot_master_set

    if build_diff_set:
        diff_data = build_positional_difference_set([r["nums"] for r in result_records_all], cfg["difference_window"])
        st.session_state["difference_set"] = diff_data

    if build_wielka_szansa:
        ws_data = build_wielka_szansa_set([r["nums"] for r in result_records_all], cfg["wielka_szansa_window"])
        st.session_state["wielka_szansa_result"] = ws_data

    mode_ui = cfg["mode_ui"]
    if mode_ui == "Hybryda 70/20/10 (hot/cold/mix)":
        base_mode_kind = "hybrid"
    elif mode_ui == "Tylko 🔥 gorące":
        base_mode_kind = "hot"
    elif mode_ui == "Tylko ❄️ zimne":
        base_mode_kind = "cold"
    elif mode_ui == "Premium 👑":
        base_mode_kind = "premium"
    else:
        base_mode_kind = "mix"

    hot_max_mode_active = (
        base_mode_kind == "hot"
        and cfg["hot_max_enabled"]
        and cfg["hot_max_count"] == 6
    )

    if build_turbo:
        turbo_result = build_turbo_score_ranking(
            draws_for_window=draws,
            hot=hot,
            cold=cold,
            base_mode_kind="hybrid" if base_mode_kind == "premium" else base_mode_kind,
            mix_hot_count=cfg["mix_hot_count"],
            candidate_count=cfg["turbo_candidate_count"],
            top_n=cfg["turbo_top_n"]
        )
        st.session_state["turbo_score_result"] = turbo_result

    if build_premium or base_mode_kind == "premium":
        premium_result = build_premium_ranking(
            draws_for_window=draws,
            hot=hot,
            cold=cold,
            mix_hot_count=cfg["mix_hot_count"],
            candidate_count=cfg["premium_candidate_count"],
            top_n=cfg["premium_top_n"]
        )
        st.session_state["premium_result"] = premium_result

    if build_ai_sim:
        st.session_state["ai_sim_result"] = run_ai_simulation_cached(
            percent_df=percent_df,
            n_sims=cfg["ai_sim_count"]
        )

    if build_cycles:
        cycle_df = detect_cycles_cached(draws)
        st.session_state["cycle_result"] = {
            "df": cycle_df,
            "set": sorted(cycle_df.head(PICK_COUNT)["Liczba"].tolist())
        }

    if build_heatmap:
        st.session_state["heatmap_df"] = build_heatmap_df(percent_df, columns_per_row=7)

    def gen_one_record() -> Dict:
        if base_mode_kind == "premium":
            premium_result_local = build_premium_ranking(
                draws_for_window=draws,
                hot=hot,
                cold=cold,
                mix_hot_count=cfg["mix_hot_count"],
                candidate_count=cfg["premium_candidate_count"],
                top_n=max(3, min(cfg["premium_top_n"], 20))
            )
            best_row = premium_result_local["rows"][0]
            return {
                "Typ": "premium",
                "Kupon": [int(x) for x in best_row["Kupon"].split()]
            }

        if hot_max_mode_active:
            hot_max_set, hot_max_table = gen_ticket_hot_max_percent(draws)
            return {
                "Typ": "hot_max_6",
                "Kupon": hot_max_set,
                "HotMaxTable": hot_max_table
            }

        if base_mode_kind == "hybrid":
            chosen = random.choices(["hot", "cold", "mix"], weights=[HYBRID_HOT_P, HYBRID_COLD_P, HYBRID_MIX_P], k=1)[0]
            return {"Typ": chosen, "Kupon": gen_ticket(chosen, hot, cold, cfg["mix_hot_count"])}
        if base_mode_kind == "hot":
            return {"Typ": "hot", "Kupon": gen_ticket("hot", hot, cold, cfg["mix_hot_count"])}
        if base_mode_kind == "cold":
            return {"Typ": "cold", "Kupon": gen_ticket("cold", hot, cold, cfg["mix_hot_count"])}
        return {"Typ": "mix", "Kupon": gen_ticket("mix", hot, cold, cfg["mix_hot_count"])}

    if generate:
        progress = st.progress(0)
        status = st.empty()

        with st.spinner("Generuję kupony..."):
            if base_mode_kind == "premium":
                premium_result_local = build_premium_ranking(
                    draws_for_window=draws,
                    hot=hot,
                    cold=cold,
                    mix_hot_count=cfg["mix_hot_count"],
                    candidate_count=cfg["premium_candidate_count"],
                    top_n=cfg["premium_top_n"]
                )
                st.session_state["premium_result"] = premium_result_local
                premium_rows = premium_result_local["rows"]

                recs = []
                total = min(int(cfg["n_tickets"]), len(premium_rows))
                for i in range(total):
                    recs.append({
                        "Typ": "premium",
                        "Kupon": [int(x) for x in premium_rows[i]["Kupon"].split()]
                    })
                    progress.progress(int((i + 1) / total * 100))
                    status.write(f"Postęp: {i+1}/{total}")

            elif hot_max_mode_active:
                hot_max_set, hot_max_table = gen_ticket_hot_max_percent(draws)
                recs = []
                total = int(cfg["n_tickets"])
                for i in range(total):
                    recs.append({
                        "Typ": "hot_max_6",
                        "Kupon": hot_max_set,
                        "HotMaxTable": hot_max_table
                    })
                    if (i + 1) % 10 == 0 or (i + 1) == total:
                        progress.progress(int((i + 1) / total * 100))
                        status.write(f"Postęp: {i+1}/{total}")
                st.session_state["hot_max_set"] = {
                    "set": hot_max_set,
                    "table": hot_max_table,
                    "window": history_window_used
                }
            else:
                if not cfg["smart_enabled"]:
                    recs = []
                    total = int(cfg["n_tickets"])
                    for i in range(total):
                        recs.append(gen_one_record())
                        if (i + 1) % 10 == 0 or (i + 1) == total:
                            progress.progress(int((i + 1) / total * 100))
                            status.write(f"Postęp: {i+1}/{total}")
                else:
                    smart_kwargs = {
                        "block_run_2": cfg["block_run_2"],
                        "block_run_3": cfg["block_run_3"],
                        "max_adjacent_pairs": cfg["max_adj_pairs"],
                        "even_odd_choice": cfg["even_odd_choice"]
                    }
                    recs = generate_with_smart_filters(
                        gen_func=gen_one_record,
                        n_tickets=int(cfg["n_tickets"]),
                        max_attempts_per_ticket=int(cfg["max_attempts_per_ticket"]),
                        smart_kwargs=smart_kwargs
                    )
                    progress.progress(100)
                    status.write(f"Postęp: {len(recs)}/{int(cfg['n_tickets'])}")

        progress.empty()
        status.empty()

        if cfg["smart_enabled"] and (not hot_max_mode_active) and base_mode_kind != "premium" and len(recs) < int(cfg["n_tickets"]):
            st.warning(
                f"⚠️ Filtry są ostre: wygenerowano **{len(recs)}** / {int(cfg['n_tickets'])} kuponów. "
                "Poluzuj filtry albo zwiększ limit prób."
            )

        st.session_state["last_records"] = recs

    if daily:
        prefer_parity = parity_bias_from_last_n(draws, 10)
        prefer_level = high_low_bias_from_last_two(draws, threshold=24)
        target_spread = avg_spread_last_n(draws, 10)

        daily_set = pick_daily_set_from_hot(
            hot=hot,
            pick_count=PICK_COUNT,
            nmin=NUM_MIN,
            nmax=NUM_MAX,
            prefer_parity=prefer_parity,
            prefer_level=prefer_level,
            threshold=24,
            target_spread=target_spread,
            max_attempts=650
        )

        st.session_state["last_daily"] = {
            "set": daily_set,
            "prefer_parity": prefer_parity,
            "prefer_level": prefer_level,
            "target_spread": target_spread
        }

    # =========================================================
    # OUTPUT SECTIONS
    # =========================================================
    if st.session_state["show_results"]:
        st.markdown("### 📋 Ostatnie wyniki (z PDF)")
        count_choice = st.selectbox("Ile ostatnich wyników pokazać?", [10, 50, 100], index=0)

        slice_records = result_records_all[:int(count_choice)]
        df_results = pd.DataFrame({
            "Numer losowania": [r["draw_no"] if r["draw_no"] is not None else "—" for r in slice_records],
            "Data": [r["date_str"] for r in slice_records],
            "Wynik": [" ".join(f"{x:02d}" for x in r["nums"]) for r in slice_records],
        })
        st.dataframe(df_results, use_container_width=True, hide_index=True)

        results_name = sanitize_txt_filename(st.text_input("Nazwa pliku wyników .txt", value="wyniki.txt"))
        st.download_button(
            "⬇️ Pobierz wyniki jako TXT",
            data=make_txt_for_results(slice_records),
            file_name=results_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("hot_master_set") is not None:
        hot_set = st.session_state["hot_master_set"]
        hot_set_str = " ".join(f"{x:02d}" for x in hot_set)

        st.markdown("### 🔥 Zestaw 6 najczęściej padających liczb")
        st.markdown(
            f'<div class="v-row"><b>Zestaw HOT 6</b> — {hot_set_str} '
            f'<span class="v-muted"> | wyliczone z ostatnich {history_window_used} losowań według najwyższego % wystąpień</span></div>',
            unsafe_allow_html=True
        )

        hot_set_name = sanitize_txt_filename(st.text_input("Nazwa pliku zestawu HOT .txt", value="hot6.txt"))
        st.download_button(
            "⬇️ Pobierz zestaw HOT 6 jako TXT",
            data=make_txt_for_hot_master_set(hot_set, history_window_used),
            file_name=hot_set_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("difference_set") is not None:
        diff_data = st.session_state["difference_set"]
        diff_set_str = " ".join(f"{x:02d}" for x in diff_data["set"])

        st.markdown("### 📐 Zestaw różnic pozycyjnych")
        st.markdown(
            f'<div class="v-row"><b>Zestaw różnic</b> — {diff_set_str} '
            f'<span class="v-muted"> | zakres użytkownika: {cfg["difference_window"]} | faktycznie użyto: {diff_data["window_used"]}</span></div>',
            unsafe_allow_html=True
        )

        st.markdown("#### Szczegóły pozycji")
        df_diff = pd.DataFrame(diff_data["details"])
        st.dataframe(df_diff, use_container_width=True, hide_index=True)

        diff_name = sanitize_txt_filename(st.text_input("Nazwa pliku zestawu różnic .txt", value="roznice_pozycyjne.txt"))
        st.download_button(
            "⬇️ Pobierz zestaw różnic jako TXT",
            data=make_txt_for_difference_set(diff_data, cfg["difference_window"]),
            file_name=diff_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("wielka_szansa_result") is not None:
        ws = st.session_state["wielka_szansa_result"]
        ws_str = " ".join(f"{x:02d}" for x in ws["set"])

        st.markdown("### 🎯 Wielka Szansa")
        st.markdown(
            f'<div class="v-row-danger"><b>Prognoza wykresowa</b> — {ws_str} '
            f'<span class="v-muted"> | zakres: {cfg["wielka_szansa_window"]} | użyto: {ws["window_used"]}</span></div>',
            unsafe_allow_html=True
        )
        st.markdown(f'<div class="v-muted">{ws["opis"]}</div>', unsafe_allow_html=True)
        st.markdown("#### Szczegóły pozycji")
        render_wielka_szansa_cards(ws["details"])

        with st.expander("Pokaż tabelę szczegółową Wielkiej Szansy"):
            st.dataframe(pd.DataFrame(ws["details"]), use_container_width=True, hide_index=True)

        ws_name = sanitize_txt_filename(st.text_input("Nazwa pliku Wielka Szansa .txt", value="wielka_szansa.txt"))
        st.download_button(
            "⬇️ Pobierz Wielką Szansę jako TXT",
            data=make_txt_for_wielka_szansa(ws, cfg["wielka_szansa_window"]),
            file_name=ws_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("hot_max_set") is not None:
        hms = st.session_state["hot_max_set"]
        hot_max_set = hms["set"]
        hot_max_table = hms["table"]
        hot_max_str = " ".join(f"{x:02d}" for x in hot_max_set)

        st.markdown("### 🔥 HOT MAX 6 — zestaw procentowy")
        st.markdown(
            f'<div class="v-row"><b>HOT MAX 6</b> — {hot_max_str} '
            f'<span class="v-muted"> | zakres: ostatnie {hms["window"]} losowań | tryb: tylko gorące + HOT MAX 6</span></div>',
            unsafe_allow_html=True
        )

        st.markdown("#### TOP 6 według procentu losowań")
        hot_max_table_display = hot_max_table.copy()
        hot_max_table_display["Procent_losowan"] = hot_max_table_display["Procent_losowan"].map(lambda x: f"{x:.2f}%")
        st.dataframe(hot_max_table_display, use_container_width=True, hide_index=True)

        hot_max_name = sanitize_txt_filename(st.text_input("Nazwa pliku HOT MAX .txt", value="hot_max_6.txt"))
        st.download_button(
            "⬇️ Pobierz HOT MAX 6 jako TXT",
            data=make_txt_for_hot_max_set(hot_max_set, hot_max_table, hms["window"]),
            file_name=hot_max_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("turbo_score_result") is not None:
        turbo = st.session_state["turbo_score_result"]

        st.markdown("### ⭐ Turbo Score — ranking kuponów")
        st.markdown(
            f'<div class="v-row"><b>Turbo Score</b> — oceniono {turbo["candidate_count_used"]} kandydatów '
            f'i wybrano TOP {len(turbo["rows"])}</div>',
            unsafe_allow_html=True
        )

        st.markdown("#### Najlepsze kupony według punktacji")
        render_turbo_cards(turbo["rows"])

        with st.expander("Pokaż tabelę Turbo Score"):
            st.dataframe(pd.DataFrame(turbo["rows"]), use_container_width=True, hide_index=True)

        profile = turbo["target_profile"]
        st.markdown("#### Profil docelowy wyliczony z bazy")
        st.markdown(
            f"""
<div class="v-row">
<b>Balans parzyste/nieparzyste:</b> {profile["target_even_odd"][0]}/{profile["target_even_odd"][1]} |
<b>Balans niskie/wysokie:</b> {profile["target_low_high"][0]}/{profile["target_low_high"][1]} |
<b>Średni rozstrzał:</b> {profile["target_spread"]:.2f} |
<b>Średnia liczba par kolejnych:</b> {profile["target_pairs"]:.2f}
</div>
            """,
            unsafe_allow_html=True
        )

        turbo_name = sanitize_txt_filename(st.text_input("Nazwa pliku Turbo Score .txt", value="turbo_score.txt"))
        st.download_button(
            "⬇️ Pobierz ranking Turbo Score jako TXT",
            data=make_txt_for_turbo_score(turbo["rows"], turbo["candidate_count_used"]),
            file_name=turbo_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("premium_result") is not None:
        premium = st.session_state["premium_result"]

        st.markdown("### 👑 Premium — ranking końcowy")
        st.markdown(
            f'<div class="v-row-premium"><b>Premium Mode</b> — oceniono {premium["candidate_count_used"]} kandydatów '
            f'i wybrano TOP {len(premium["rows"])}</div>',
            unsafe_allow_html=True
        )

        st.markdown("#### Najlepsze kupony premium")
        render_premium_cards(premium["rows"])

        with st.expander("Pokaż tabelę Premium"):
            st.dataframe(pd.DataFrame(premium["rows"]), use_container_width=True, hide_index=True)

        hot_max_str = " ".join(f"{x:02d}" for x in premium["hot_max_set"])
        diff_str = " ".join(f"{x:02d}" for x in premium["diff_set"])
        st.markdown(
            f"""
<div class="v-row-premium">
<b>Źródła premium:</b><br>
HOT MAX 6: {hot_max_str}<br>
Zestaw różnic: {diff_str}
</div>
            """,
            unsafe_allow_html=True
        )

        profile = premium["target_profile"]
        st.markdown(
            f"""
<div class="v-row-premium">
<b>Profil docelowy premium:</b><br>
Parzyste/Nieparzyste: {profile["target_even_odd"][0]}/{profile["target_even_odd"][1]}<br>
Niskie/Wysokie: {profile["target_low_high"][0]}/{profile["target_low_high"][1]}<br>
Średni rozstrzał: {profile["target_spread"]:.2f}<br>
Średnia liczba par kolejnych: {profile["target_pairs"]:.2f}
</div>
            """,
            unsafe_allow_html=True
        )

        premium_name = sanitize_txt_filename(st.text_input("Nazwa pliku Premium .txt", value="premium_mode.txt"))
        st.download_button(
            "⬇️ Pobierz ranking Premium jako TXT",
            data=make_txt_for_premium(premium["rows"], premium["candidate_count_used"]),
            file_name=premium_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("ai_sim_result") is not None:
        sim = st.session_state["ai_sim_result"]
        sim_str = " ".join(f"{x:02d}" for x in sim["sim_set"])

        st.markdown("### 🤖 AI symulacja")
        st.markdown(
            f'<div class="v-row-blue"><b>Symulacje:</b> {sim["n_sims"]} | <b>Sugerowany zestaw:</b> {sim_str}</div>',
            unsafe_allow_html=True
        )

        st.markdown("#### Wyniki symulacji")
        st.dataframe(sim["sim_df"].head(20), use_container_width=True, hide_index=True)

        if not sim["top_pairs"].empty:
            st.markdown("#### Najczęstsze pary w symulacji")
            st.dataframe(sim["top_pairs"], use_container_width=True, hide_index=True)

        sim_name = sanitize_txt_filename(st.text_input("Nazwa pliku AI symulacji .txt", value="ai_symulacja.txt"))
        st.download_button(
            "⬇️ Pobierz wynik AI symulacji jako TXT",
            data=make_txt_for_simulation(sim),
            file_name=sim_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("cycle_result") is not None:
        cyc = st.session_state["cycle_result"]
        cycle_set_str = " ".join(f"{x:02d}" for x in cyc["set"])

        st.markdown("### 🔄 Cykle liczb")
        st.markdown(
            f'<div class="v-row-blue"><b>Sugerowany zestaw cykli:</b> {cycle_set_str}</div>',
            unsafe_allow_html=True
        )

        st.markdown("#### TOP liczby cykliczne")
        st.dataframe(cyc["df"].head(20), use_container_width=True, hide_index=True)

        cycle_name = sanitize_txt_filename(st.text_input("Nazwa pliku cykli .txt", value="cykle_liczb.txt"))
        st.download_button(
            "⬇️ Pobierz analizę cykli jako TXT",
            data=make_txt_for_cycles(cyc["df"], cyc["set"]),
            file_name=cycle_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("heatmap_df") is not None:
        st.markdown("### 🟦 Heatmapa 1–49")
        st.dataframe(st.session_state["heatmap_df"], use_container_width=True, hide_index=True)

    if st.session_state.get("last_daily") is not None:
        info = st.session_state["last_daily"]
        daily_set = info["set"]
        nums = " ".join(f"{n:02d}" for n in daily_set)
        ev, od = even_odd_split(daily_set)
        pairs = count_adjacent_pairs(sorted(daily_set))

        def pref_to_text(p: str) -> str:
            if p == "EVEN":
                return "parzyste"
            if p == "ODD":
                return "nieparzyste"
            return "dowolnie"

        def level_to_text(p: str) -> str:
            if p == "LOW":
                return "niższe"
            if p == "HIGH":
                return "wyższe"
            return "dowolnie"

        st.markdown("### 🌿 Twoje szczęśliwe cyfry dnia")
        st.markdown(
            f'<div class="v-row"><b>Zestaw dnia</b> — {nums} '
            f'<span class="v-muted"> | parzyste/nieparzyste: {ev}/{od} | pary: {pairs}</span></div>',
            unsafe_allow_html=True
        )
        st.markdown("#### Jak to wyliczam?")
        st.markdown(f"- Ostatnie 10 wyników: przewaga parzystych/nieparzystych → dziś: **{pref_to_text(info['prefer_parity'])}**.")
        st.markdown(f"- Ostatnie 2 wyniki: trend niskie/wysokie → dziś: **{level_to_text(info['prefer_level'])}**.")
        st.markdown(f"- Średni rozstrzał (10 wyników): **{info['target_spread']:.1f}**.")

    records = st.session_state.get("last_records", [])
    if records:
        st.markdown("### 🎯 Wygenerowane kupony")
        preview_n = min(int(cfg["preview_limit"]), len(records))
        st.caption(f"Podgląd pierwszych **{preview_n}** kuponów.")
        render_ticket_cards(records, preview_n)

        with st.expander("Pokaż pełną tabelę kuponów"):
            df_out = pd.DataFrame({
                "Typ": [r["Typ"] for r in records],
                "Kupon": [" ".join(f"{x:02d}" for x in r["Kupon"]) for r in records],
            })
            st.dataframe(df_out, use_container_width=True, hide_index=True)

        tickets_name = sanitize_txt_filename(st.text_input("Nazwa pliku kuponów .txt", value="kupony.txt"))
        st.download_button(
            "⬇️ Pobierz kupony jako TXT",
            data=make_txt_for_tickets(records),
            file_name=tickets_name,
            mime="text/plain",
            use_container_width=True
        )

    with st.expander("✅ Kontrola (pierwsze 5 rekordów z PDF — powinny być najnowsze)"):
        for i, r in enumerate(result_records_all[:5], start=1):
            st.write(f"{i}. Losowanie: {r['draw_no']} | Wynik: {' '.join(f'{x:02d}' for x in r['nums'])}")

    with st.expander("📌 Diagnostyka procentowa (TOP/LOW)"):
        st.write("TOP 15 liczb o najwyższym procencie wystąpień:")
        top_display = percent_df.head(15).copy()
        top_display["Procent_losowan"] = top_display["Procent_losowan"].map(lambda x: f"{x:.2f}%")
        st.dataframe(top_display, use_container_width=True, hide_index=True)

        st.write("LOW 15 liczb o najniższym procencie wystąpień:")
        low_display = percent_df.tail(15).sort_values(
            ["Procent_losowan", "Liczba_losowan_z_wystapieniem", "Liczba"],
            ascending=[True, True, True]
        ).copy()
        low_display["Procent_losowan"] = low_display["Procent_losowan"].map(lambda x: f"{x:.2f}%")
        st.dataframe(low_display, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
