import io
import os
import re
import random
from collections import Counter
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import pandas as pd
import streamlit as st

# =========================================================
# PDF engines
# =========================================================
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except Exception:
    HAS_PYMUPDF = False

try:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    HAS_PYPDF = True
except Exception:
    HAS_PYPDF = False
    PdfReader = None
    PdfReadError = Exception


# =========================================================
# APP CONFIG
# =========================================================
APP_TITLE = "🏆 Generator-Victory — Lotto 6/49"
PDF_FILENAME = "wyniki.pdf"
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
}
</style>
"""


# =========================================================
# PDF PARSING
# =========================================================
INT_RE = re.compile(r"\d+")

def _validate_pdf_bytes(pdf_bytes: bytes) -> None:
    if not pdf_bytes.startswith(b"%PDF"):
        head = pdf_bytes[:240].decode("utf-8", errors="replace")
        raise ValueError(
            "Plik 'wyniki.pdf' nie wygląda jak prawdziwy PDF (brak nagłówka %PDF).\n"
            "Jeśli używasz Git LFS, do repo mógł trafić tylko pointer.\n\n"
            f"Początek pliku:\n{head}"
        )

def _read_pdf_pages_text_pymupdf(pdf_bytes: bytes) -> List[str]:
    if not HAS_PYMUPDF:
        raise RuntimeError("PyMuPDF not available")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page in doc:
        pages.append(page.get_text("text") or "")
    doc.close()
    return pages

def _read_pdf_pages_text_pypdf(pdf_bytes: bytes) -> List[str]:
    if not HAS_PYPDF:
        raise RuntimeError("pypdf not available")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
    except Exception as e:
        raise PdfReadError(str(e))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return pages

def _extract_tokens_and_drawnos_from_page(page_text: str) -> Tuple[List[int], List[int]]:
    tokens: List[int] = []
    drawnos: List[int] = []

    lines = [ln.strip() for ln in (page_text or "").splitlines() if ln.strip()]
    in_drawno_section = False

    for ln in lines:
        if "Lotto" in ln and "6/49" in ln:
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

    last_err = None
    pages: List[str] = []

    if HAS_PYMUPDF:
        try:
            pages = _read_pdf_pages_text_pymupdf(pdf_bytes)
        except Exception as e:
            last_err = e
            pages = []

    if not pages and HAS_PYPDF:
        try:
            pages = _read_pdf_pages_text_pypdf(pdf_bytes)
        except Exception as e:
            last_err = e
            pages = []

    if not pages:
        if last_err:
            raise RuntimeError(f"Nie udało się odczytać PDF. Ostatni błąd: {last_err}")
        raise RuntimeError("Nie udało się odczytać PDF.")

    all_tokens: List[int] = []
    all_drawnos: List[int] = []

    for ptxt in pages:
        tokens, drawnos = _extract_tokens_and_drawnos_from_page(ptxt)
        all_tokens.extend(tokens)
        all_drawnos.extend(drawnos)

    draws = _chunk_tokens_to_draws(all_tokens)
    if not draws:
        raise RuntimeError("Nie znaleziono żadnych wyników (tokenów 1–49) w PDF.")

    return _pair_draws_with_drawnos(draws, all_drawnos)


# =========================================================
# STATS & GROUPS
# =========================================================
@st.cache_data(show_spinner=False)
def compute_freq_df_cached(draws: List[List[int]]) -> pd.DataFrame:
    flat = [n for d in draws for n in d]
    c = Counter(flat)
    rows = [{"Liczba": n, "Wystąpienia": c.get(n, 0)} for n in range(NUM_MIN, NUM_MAX + 1)]
    df = pd.DataFrame(rows).sort_values(["Wystąpienia", "Liczba"], ascending=[False, True]).reset_index(drop=True)
    return df

def build_groups_from_freq(freq_df: pd.DataFrame, hot_size: int, cold_size: int) -> Tuple[List[int], List[int], List[int]]:
    hot = freq_df.head(hot_size)["Liczba"].tolist()
    cold = freq_df.tail(cold_size)["Liczba"].tolist()
    neutral = [n for n in range(NUM_MIN, NUM_MAX + 1) if n not in hot and n not in cold]
    return hot, cold, neutral

def build_hot_master_set(freq_df: pd.DataFrame) -> List[int]:
    """
    New feature:
    Returns one fixed set of 6 numbers built from the most frequent numbers
    in the true historical results currently selected by the user.
    """
    return sorted(freq_df.head(PICK_COUNT)["Liczba"].tolist())


# =========================================================
# GENERATION
# =========================================================
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
# EXPORT (TXT)
# =========================================================
def sanitize_txt_filename(name: str) -> str:
    name = (name or "").strip()
    if not name:
        name = "wyniki.txt"
    name = name.replace("\\", "_").replace("/", "_").replace("..", "_")
    if not name.lower().endswith(".txt"):
        name += ".txt"
    return name

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
        nums = " ".join(f"{x:02d}" for x in r["nums"])
        lines.append(f"Losowanie: {draw_str} | Wynik: {nums}")
    return ("\n".join(lines) + "\n").encode("utf-8")

def make_txt_for_hot_master_set(hot_master_set: List[int], history_window: int) -> bytes:
    nums = " ".join(f"{x:02d}" for x in hot_master_set)
    text = (
        f"Zestaw 6 najczęściej losowanych cyfr\n"
        f"Analizowana historia: ostatnie {history_window} losowań\n"
        f"Zestaw: {nums}\n"
    )
    return text.encode("utf-8")


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
        ],
        index=defaults.get("mode_index", 0)
    )

    history_window = st.selectbox(
        "Ile ostatnich losowań brać do analizy HOT/COLD?",
        [50, 100, 250, 500, 999],
        index=defaults.get("hist_index", 4)
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
        "n_tickets": int(n_tickets),
        "hot_size": int(hot_size),
        "cold_size": int(cold_size),
        "mix_hot_count": int(mix_hot_count),
        "preview_limit": int(preview_limit),
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
    st.write("Generator typowań Lotto na bazie historii losowań z pliku **wyniki.pdf** (1–49, typuje 6 liczb).")
    st.caption("Nowy element: możesz wyciągnąć jeden gotowy zestaw 6 najczęściej losowanych cyfr z prawdziwych wyników.")

    if "last_records" not in st.session_state:
        st.session_state["last_records"] = []
    if "last_daily" not in st.session_state:
        st.session_state["last_daily"] = None
    if "show_results" not in st.session_state:
        st.session_state["show_results"] = False
    if "hot_master_set" not in st.session_state:
        st.session_state["hot_master_set"] = None

    pdf_path = Path(os.getcwd()) / PDF_FILENAME

    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("📄 Dane wejściowe")
    st.write(f"Plik: `{pdf_path}`")
    st.write(f"Silnik PDF: **{'PyMuPDF (fitz)' if HAS_PYMUPDF else 'pypdf (fallback)'}**")
    st.markdown('<div class="v-muted">Jeśli sidebar jest niewidoczny na komputerze — to normalne. Ustawienia masz niżej w „Ustawienia (panel główny)”.</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if not pdf_path.exists():
        st.error(f"❌ Nie znaleziono `{PDF_FILENAME}` obok `app.py`. Dodaj plik do repo i zrób Reboot.")
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
        "hist_index": 4,
        "n_tickets": 50,
        "hot_size": 20,
        "cold_size": 20,
        "mix_hot_count": 3,
        "preview_limit": 60,
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

    result_records = result_records_all[:cfg["history_window"]]
    draws = [r["nums"] for r in result_records]

    freq_df = compute_freq_df_cached(draws)
    hot, cold, _neutral = build_groups_from_freq(freq_df, hot_size=cfg["hot_size"], cold_size=cfg["cold_size"])
    hot_master_set = build_hot_master_set(freq_df)

    left, right = st.columns([1.2, 0.8], gap="large")

    with left:
        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("📊 Częstotliwość 1–49 (z prawdziwych wyników)")
        st.success(f"✅ Analizowane losowania: **{len(result_records)}** (z {len(result_records_all)} w PDF)")
        st.dataframe(freq_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🔥 Gorące / ❄️ Zimne")
        st.markdown("**Gorące (Hot)**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(hot)]), unsafe_allow_html=True)
        st.markdown("**Zimne (Cold)**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(cold)]), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🎛️ Podsumowanie trybu")
        st.write(f"**Tryb:** {cfg['mode_ui']}")
        st.write(f"**Analiza HOT/COLD:** ostatnie **{cfg['history_window']}** losowań")
        st.write(f"**Tryb inteligentny:** {'TAK' if cfg['smart_enabled'] else 'NIE'}")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("🎟️ Generator")

    col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4, gap="large")
    with col_btn1:
        generate = st.button("🏆 GENERUJ KUPONY (6 liczb)", type="primary", use_container_width=True)
    with col_btn2:
        daily = st.button("🌿 TWOJE SZCZĘŚLIWE CYFRY DNIA", type="primary", use_container_width=True)
    with col_btn3:
        show_res = st.button("📋 POKAŻ WYNIKI", type="primary", use_container_width=True)
    with col_btn4:
        show_hot_set = st.button("🔥 ZESTAW 6 HOT", type="primary", use_container_width=True)

    if show_res:
        st.session_state["show_results"] = not st.session_state["show_results"]

    if show_hot_set:
        st.session_state["hot_master_set"] = hot_master_set

    mode_ui = cfg["mode_ui"]
    if mode_ui == "Hybryda 70/20/10 (hot/cold/mix)":
        base_mode_kind = "hybrid"
    elif mode_ui == "Tylko 🔥 gorące":
        base_mode_kind = "hot"
    elif mode_ui == "Tylko ❄️ zimne":
        base_mode_kind = "cold"
    else:
        base_mode_kind = "mix"

    def gen_one_record() -> Dict:
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
            if not cfg["smart_enabled"]:
                recs: List[Dict] = []
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

        if cfg["smart_enabled"] and len(recs) < int(cfg["n_tickets"]):
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

        st.markdown('<div class="v-muted">Zapis jest dostępny wyłącznie jako plik TXT (pobieranie → folder „Pobrane”).</div>', unsafe_allow_html=True)
        filename_input = st.text_input("Nazwa pliku .txt (np. wyniki.txt)", value="wyniki.txt")
        safe_name = sanitize_txt_filename(filename_input)
        st.download_button(
            "⬇️ Pobierz wyniki jako TXT",
            data=make_txt_for_results(slice_records),
            file_name=safe_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("hot_master_set") is not None:
        hot_set = st.session_state["hot_master_set"]
        hot_set_str = " ".join(f"{x:02d}" for x in hot_set)

        st.markdown("### 🔥 Zestaw 6 najczęściej losowanych cyfr")
        st.markdown(
            f'<div class="v-row"><b>Zestaw HOT 6</b> — {hot_set_str} '
            f'<span class="v-muted"> | wyliczone z ostatnich {cfg["history_window"]} prawdziwych losowań</span></div>',
            unsafe_allow_html=True
        )
        st.markdown("#### Jak to działa?")
        st.markdown(
            "Aplikacja bierze wszystkie prawdziwe wyniki z wybranego zakresu historii, "
            "liczy częstotliwość występowania każdej liczby 1–49 i wybiera dokładnie 6 liczb, "
            "które pojawiały się najczęściej."
        )

        hot_set_filename_input = st.text_input("Nazwa pliku zestawu HOT .txt (np. hot6.txt)", value="hot6.txt")
        safe_hot_name = sanitize_txt_filename(hot_set_filename_input)
        st.download_button(
            "⬇️ Pobierz zestaw HOT 6 jako TXT",
            data=make_txt_for_hot_master_set(hot_set, cfg["history_window"]),
            file_name=safe_hot_name,
            mime="text/plain",
            use_container_width=True
        )

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
        st.markdown(f"- Ostatnie 10 wyników: przewaga parzystych/nieparzystych → dziś: **{pref_to_text(info['prefer_parity'])}** (z puli hot).")
        st.markdown(f"- Ostatnie 2 wyniki: trend niskie/wysokie → dziś: **{level_to_text(info['prefer_level'])}** (z puli hot).")
        st.markdown(f"- Średni rozstrzał (10 wyników): **{info['target_spread']:.1f}** → dobieram zestaw o podobnym rozstrzale.")

    records = st.session_state.get("last_records", [])
    if records:
        st.markdown("### 🎯 Wygenerowane kupony")
        df_out = pd.DataFrame({
            "Typ": [r["Typ"] for r in records],
            "Kupon": [" ".join(f"{x:02d}" for x in r["Kupon"]) for r in records],
        })

        preview_n = min(int(cfg["preview_limit"]), len(records))
        st.caption(f"Podgląd pierwszych **{preview_n}** kuponów (pełna lista w tabeli).")

        for i in range(preview_n):
            nums_str = df_out.iloc[i]["Kupon"]
            typ = df_out.iloc[i]["Typ"]
            t = [int(x) for x in nums_str.split()]
            ev, od = even_odd_split(t)
            pairs = count_adjacent_pairs(sorted(t))
            st.markdown(
                f'<div class="v-row"><b>Kupon #{i+1:03d}</b> '
                f'<span class="v-muted">[{typ}]</span> — {nums_str} '
                f'<span class="v-muted"> | parzyste/nieparzyste: {ev}/{od} | pary: {pairs}</span></div>',
                unsafe_allow_html=True
            )

        st.markdown("#### Pełna tabela")
        st.dataframe(df_out, use_container_width=True, hide_index=True)

        st.markdown('<div class="v-muted">Zapis kuponów jest dostępny wyłącznie jako plik TXT (pobieranie → „Pobrane”).</div>', unsafe_allow_html=True)
        ticket_filename_input = st.text_input("Nazwa pliku kuponów .txt (np. kupony.txt)", value="kupony.txt")
        safe_ticket_name = sanitize_txt_filename(ticket_filename_input)
        st.download_button(
            "⬇️ Pobierz kupony jako TXT",
            data=make_txt_for_tickets(records),
            file_name=safe_ticket_name,
            mime="text/plain",
            use_container_width=True
        )

    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("✅ Kontrola (pierwsze 3 rekordy z PDF — powinny być najnowsze)"):
        for i, r in enumerate(result_records_all[:3], start=1):
            st.write(f"{i}. Losowanie: {r['draw_no']} | Wynik: {' '.join(f'{x:02d}' for x in r['nums'])}")

if __name__ == "__main__":
    main()
