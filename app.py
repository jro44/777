import io
import os
import re
import zipfile
import random
from collections import Counter
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import pandas as pd
import streamlit as st
from pypdf import PdfReader
from pypdf.errors import PdfReadError


# =========================================================
# APP CONFIG
# =========================================================
APP_TITLE = "🏆 Generator-Victory — Lotto 6/49"
PDF_FILENAME = "wyniki.pdf"
NUM_MIN = 1
NUM_MAX = 49
PICK_COUNT = 6


# =========================================================
# UI STYLE (LIGHT BACKGROUND + GREEN ACCENTS + DARK TEXT)
# Stable after reruns (no css-* selectors)
# =========================================================
LIGHT_GREEN_CSS = """
<style>
:root{
  --bg0:#f3fbf7;
  --bg1:#ffffff;
  --card:#ffffff;
  --card2:#f7fffb;
  --txt:#0b1b2b;
  --mut:#334155;
  --green:#00a86b;
  --green2:#00c27a;
  --border: rgba(0,168,107,0.22);
  --shadow: 0 10px 28px rgba(0,0,0,.08);
}

/* App background (non-transparent) */
.stApp{
  background-color: var(--bg0) !important;
  background-image:
    radial-gradient(1100px 700px at 12% 10%, rgba(0, 194, 122, 0.12), transparent 58%),
    radial-gradient(900px 600px at 92% 18%, rgba(0, 168, 107, 0.10), transparent 55%),
    linear-gradient(180deg, var(--bg0), var(--bg1)) !important;
  color: var(--txt) !important;
}

/* Dark readable text ONLY inside Streamlit container */
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] *{
  color: var(--txt);
}

/* Headings */
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

/* Layout */
.block-container{
  padding-top: 2.0rem;
  padding-bottom: 2.5rem;
  max-width: 1100px;
}

/* Cards */
.v-card{
  background: linear-gradient(180deg, var(--card), var(--card2));
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  border-radius: 18px;
  padding: 16px 16px 12px 16px;
}

/* Pills */
.v-pill{
  display:inline-block;
  padding: 6px 10px;
  margin: 3px 4px 0 0;
  border-radius: 999px;
  border: 1px solid rgba(0, 168, 107, 0.28);
  background: rgba(0, 168, 107, 0.10);
  font-weight: 900;
  color: #064e3b !important;
}

/* Muted text */
.v-muted{
  opacity: .82;
  font-size: .92rem;
  color: var(--mut) !important;
}

/* Sidebar */
section[data-testid="stSidebar"]{
  background: linear-gradient(180deg, rgba(0, 194, 122, 0.10) 0%, rgba(255,255,255,0.75) 100%) !important;
  border-right: 1px solid rgba(0, 168, 107, 0.16);
}
section[data-testid="stSidebar"] *{
  color: var(--txt) !important;
}

/* Inputs */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div{
  border-radius: 14px !important;
}

/* Primary button */
div.stButton > button[kind="primary"]{
  background: linear-gradient(90deg, var(--green) 0%, var(--green2) 100%) !important;
  color: #052e16 !important;
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

/* Result row */
.v-row{
  background: rgba(0, 168, 107, 0.06);
  border: 1px solid rgba(0, 168, 107, 0.18);
  border-radius: 14px;
  padding: 10px 12px;
  margin: 8px 0;
  color: var(--txt) !important;
}

/* Dataframe */
[data-testid="stDataFrame"]{
  border-radius: 16px !important;
  overflow: hidden !important;
  border: 1px solid rgba(0, 168, 107, 0.22) !important;
}

/* Caption */
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] *{
  color: rgba(51,65,85,0.95) !important;
}

/* Mobile */
@media (max-width: 640px){
  .block-container{ padding-left: 1rem; padding-right: 1rem; }
  div.stButton > button[kind="primary"]{ width: 100% !important; }
}
</style>
"""


# =========================================================
# PDF PARSING (robust) + CACHE
# =========================================================
LINE_6NUM = re.compile(
    r"(?<!\d)([0-4]?\d)\s+([0-4]?\d)\s+([0-4]?\d)\s+([0-4]?\d)\s+([0-4]?\d)\s+([0-4]?\d)(?!\d)"
)

@st.cache_data(show_spinner=False)
def extract_draws_from_pdf_bytes(pdf_bytes: bytes) -> List[List[int]]:
    """
    Heavy operation -> cached by content.
    Extracts lines that look like: 6 numbers 1..49
    """
    if not pdf_bytes.startswith(b"%PDF"):
        head = pdf_bytes[:240].decode("utf-8", errors="replace")
        raise ValueError(
            "Plik 'wyniki.pdf' NIE wygląda jak prawdziwy PDF (brak nagłówka %PDF).\n"
            "Najczęściej oznacza to wskaźnik Git LFS lub uszkodzony upload.\n\n"
            f"Pierwsze znaki pliku:\n{head}"
        )

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
    except PdfReadError as e:
        raise PdfReadError(f"PdfReadError: {e}\nPDF może być uszkodzony lub niekompletny.")

    draws: List[List[int]] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""

        for m in LINE_6NUM.finditer(text):
            nums = [int(m.group(i)) for i in range(1, 7)]
            if all(NUM_MIN <= n <= NUM_MAX for n in nums) and len(set(nums)) == 6:
                draws.append(sorted(nums))

    return draws

@st.cache_data(show_spinner=False)
def compute_stats_cached(draws: List[List[int]]) -> pd.DataFrame:
    flat = [n for d in draws for n in d]
    c = Counter(flat)
    rows = [{"Liczba": n, "Wystąpienia": c.get(n, 0)} for n in range(NUM_MIN, NUM_MAX + 1)]
    return (
        pd.DataFrame(rows)
        .sort_values(["Wystąpienia", "Liczba"], ascending=[False, True])
        .reset_index(drop=True)
    )


# =========================================================
# GROUPS + GENERATION
# =========================================================
def build_groups(freq_df: pd.DataFrame, hot_size: int, cold_size: int) -> Tuple[List[int], List[int], List[int]]:
    hot = freq_df.head(hot_size)["Liczba"].tolist()
    cold = freq_df.tail(cold_size)["Liczba"].tolist()
    neutral = [n for n in range(NUM_MIN, NUM_MAX + 1) if n not in hot and n not in cold]
    return hot, cold, neutral

def pick_unique(pool: List[int], k: int) -> List[int]:
    pool = list(dict.fromkeys(pool))
    if len(pool) < k:
        raise ValueError("Za mało liczb w puli, aby wylosować unikalny zestaw.")
    return sorted(random.sample(pool, k))

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


# =========================================================
# SMART MODE FILTERS
# =========================================================
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

def even_odd_split(nums: List[int]) -> Tuple[int, int]:
    ev = sum(1 for n in nums if n % 2 == 0)
    od = len(nums) - ev
    return ev, od

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
# "TWOJE SZCZĘŚLIWE CYFRY DNIA" (like Eurojackpot style)
# =========================================================
def flatten_last_n(draws: List[List[int]], n: int) -> List[int]:
    return [x for d in draws[:n] for x in d]

def parity_bias_from_last_n(draws: List[List[int]], n: int) -> str:
    nums = flatten_last_n(draws, n)
    ev = sum(1 for x in nums if x % 2 == 0)
    od = len(nums) - ev
    # contrarian (if last had more evens -> prefer odds, etc.)
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
    # contrarian with margin
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
    prefer_parity: str,     # "EVEN" | "ODD" | "ANY"
    prefer_level: str,      # "LOW" | "HIGH" | "ANY"
    threshold: int,
    target_spread: Optional[float] = None,
    max_attempts: int = 600
) -> List[int]:
    hot_unique = sorted(set([x for x in hot if nmin <= x <= nmax]))
    if len(hot_unique) < pick_count:
        hot_unique = hot_unique + [x for x in range(nmin, nmax + 1) if x not in hot_unique]

    pool = hot_unique[:]

    # level preference (soft)
    if prefer_level != "ANY":
        filtered = [x for x in pool if (x <= threshold)] if prefer_level == "LOW" else [x for x in pool if (x > threshold)]
        if len(filtered) >= pick_count:
            pool = filtered

    # parity preference (soft)
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

        # early accept if both preferences have clear majority
        if prefer_parity != "ANY" and prefer_level != "ANY":
            ev, od = even_odd_split(cand)
            low = sum(1 for x in cand if x <= threshold)
            high = pick_count - low
            parity_ok = (ev > od) if prefer_parity == "EVEN" else (od > ev)
            level_ok = (high > low) if prefer_level == "HIGH" else (low > high)
            if parity_ok and level_ok:
                return cand

    return best if best is not None else sorted(random.sample(range(nmin, nmax + 1), pick_count))


# =========================================================
# EXPORT HELPERS
# =========================================================
def records_to_dataframe(records: List[Dict]) -> pd.DataFrame:
    return pd.DataFrame({
        "Typ": [r["Typ"] for r in records],
        "Kupon": [" ".join(f"{x:02d}" for x in r["Kupon"]) for r in records],
    })

def make_zip_package(records: List[Dict], draws_count: int, hot: List[int], cold: List[int], settings: Dict) -> bytes:
    df_out = records_to_dataframe(records)
    csv_bytes = df_out.to_csv(index=False).encode("utf-8")

    txt_lines = [
        f"{i+1:03d}. [{records[i]['Typ']}] " + " ".join(f"{x:02d}" for x in records[i]["Kupon"])
        for i in range(len(records))
    ]
    txt_bytes = ("\n".join(txt_lines)).encode("utf-8")

    report = {
        "pdf_file": PDF_FILENAME,
        "draws_found": draws_count,
        "hot": sorted(hot),
        "cold": sorted(cold),
        "settings": settings,
    }
    report_bytes = (pd.Series(report).to_json(indent=2, force_ascii=False)).encode("utf-8")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("kupony.csv", csv_bytes)
        z.writestr("kupony.txt", txt_bytes)
        z.writestr("raport.json", report_bytes)

    return zip_buffer.getvalue()


# =========================================================
# STREAMLIT APP
# =========================================================
def main():
    st.set_page_config(
        page_title="Generator-Victory Lotto",
        page_icon="🏆",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    st.markdown(LIGHT_GREEN_CSS, unsafe_allow_html=True)

    st.title(APP_TITLE)
    st.write("Generator typowań Lotto na bazie historii losowań z pliku **wyniki.pdf** (zakres **1–49**, typuje **6 liczb**).")
    st.caption("Źródło danych: lokalny plik `wyniki.pdf` w repo (obok `app.py`). PDF + statystyki są cachowane (płynnie na telefonie).")

    pdf_path = Path(os.getcwd()) / PDF_FILENAME

    # Session cache for outputs (avoid regen on widget changes)
    if "last_records" not in st.session_state:
        st.session_state["last_records"] = []
    if "last_settings" not in st.session_state:
        st.session_state["last_settings"] = {}
    if "last_daily" not in st.session_state:
        st.session_state["last_daily"] = None

    # Sidebar settings
    with st.sidebar:
        st.header("⚙️ Ustawienia")

        mode_ui = st.selectbox(
            "Tryb typowania",
            [
                "Hybryda 70/20/10 (hot/cold/mix)",
                "Tylko 🔥 gorące",
                "Tylko ❄️ zimne",
                "Tylko ⚗️ mix (hot+zimne)",
            ],
            index=0
        )

        st.divider()
        n_tickets = st.slider("Liczba kuponów", 1, 500, 50, 1)

        st.divider()
        hot_size = st.slider("Ile liczb w grupie Gorących", 6, 35, 20, 1)
        cold_size = st.slider("Ile liczb w grupie Zimnych", 6, 35, 20, 1)

        st.divider()
        mix_hot_count = st.slider("MIX: ile liczb z gorących?", 1, 5, 3, 1)

        st.divider()
        st.subheader("🧠 Tryb inteligentny (opcjonalny)")
        smart_enabled = st.checkbox("Włącz tryb inteligentny", value=False)

        if smart_enabled:
            block_run_2 = st.checkbox("Blokuj układy 1–2 (kolejne liczby)", value=True)
            block_run_3 = st.checkbox("Blokuj układy 1–3 (ciąg 3 kolejnych)", value=True)

            limit_pairs_on = st.checkbox("Włącz limit par (kolejne liczby)", value=True)
            max_adj_pairs = None
            if limit_pairs_on:
                max_adj_pairs = st.slider("Maks. liczba par kolejnych", 0, 5, 2, 1)

            even_odd_choice = st.radio(
                "Parzyste / Nieparzyste (6 liczb)",
                ["Dowolnie", "3/3", "4/2", "2/4", "5/1", "1/5", "6/0", "0/6"],
                index=0
            )

            max_attempts_per_ticket = st.slider("Limit prób na kupon", 10, 500, 120, 10)
        else:
            block_run_2 = False
            block_run_3 = False
            max_adj_pairs = None
            even_odd_choice = "Dowolnie"
            max_attempts_per_ticket = 120

        st.divider()
        st.subheader("⚡ Wydajność")
        preview_limit = st.slider("Ile kuponów pokazać w podglądzie (ładnie)", 10, 200, 60, 10)

    # Load & analyze (cached)
    left, right = st.columns([1.2, 0.8], gap="large")

    with left:
        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("📄 Dane wejściowe")
        st.write(f"Ścieżka PDF: `{pdf_path}`")

        if not pdf_path.exists():
            st.error(f"❌ Nie znaleziono pliku `{PDF_FILENAME}`. Dodaj go do repo obok pliku aplikacji.")
            st.stop()

        try:
            pdf_bytes = pdf_path.read_bytes()
            draws = extract_draws_from_pdf_bytes(pdf_bytes)
        except ValueError as e:
            st.error("❌ Problem z plikiem `wyniki.pdf` (to nie jest prawdziwy PDF / Git LFS pointer).")
            st.code(str(e))
            st.stop()
        except Exception as e:
            st.error("❌ Błąd podczas czytania PDF (może być uszkodzony / niepełny).")
            st.code(str(e))
            st.stop()

        if len(draws) == 0:
            st.error("❌ Nie udało się znaleźć losowań (linii z 6 liczbami 1–49) w PDF.")
            st.stop()

        st.success(f"✅ Załadowano losowania: **{len(draws)}**")
        st.markdown('<div class="v-muted">PDF i analiza są cachowane — zmiana suwaków nie powinna powodować lagów.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("📊 Częstotliwość 1–49")
        freq_df = compute_stats_cached(draws)
        st.dataframe(freq_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    hot, cold, _neutral = build_groups(freq_df, hot_size=hot_size, cold_size=cold_size)

    with right:
        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🔥 Gorące / ❄️ Zimne")

        st.markdown("**Gorące (Hot)**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(hot)]), unsafe_allow_html=True)

        st.markdown("**Zimne (Cold)**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(cold)]), unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🎛️ Wybrany tryb")
        st.write(f"**Tryb:** {mode_ui}")
        if mode_ui == "Tylko ⚗️ mix (hot+zimne)":
            st.write(f"**MIX:** {mix_hot_count} z gorących + {PICK_COUNT - mix_hot_count} z zimnych")
        st.write(f"**Tryb inteligentny:** {'TAK' if smart_enabled else 'NIE'}")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("🎟️ Generator")

    col_btn1, 
