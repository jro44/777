import io
import os
import re
import zipfile
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import pandas as pd
import streamlit as st
from pypdf import PdfReader
from pypdf.errors import PdfReadError


# =========================================================
# APP CONFIG
# =========================================================
APP_TITLE = "💀 Gothic $ Lotto Generator"
PDF_FILENAME = "wyniki.pdf"
NUM_MIN = 1
NUM_MAX = 49
PICK_COUNT = 6


# =========================================================
# UI STYLE (dark + green accents) — like Multi-Multi layout
# =========================================================
DARK_GREEN_CSS = """
<style>
:root{
  --bg0:#050507;
  --bg1:#0b0b10;
  --card: rgba(16,16,24,0.92);
  --card2: rgba(12,12,18,0.92);
  --txt:#f4f4f6;
  --mut:#b9b9c8;
  --green:#00ff99;
  --green2:#23ffb0;
  --border: rgba(0,255,153,0.22);
  --shadow: 0 14px 44px rgba(0,0,0,.65);
}

/* App background */
.stApp{
  background:
    radial-gradient(900px 600px at 10% 10%, rgba(0,255,153,0.12), transparent 55%),
    radial-gradient(900px 600px at 90% 15%, rgba(0,255,153,0.06), transparent 50%),
    linear-gradient(180deg, var(--bg0), var(--bg1));
  color: var(--txt) !important;
}

.block-container{ padding-top: 2.0rem; padding-bottom: 2.5rem; max-width: 1100px; }

/* Headers */
h1,h2,h3,h4{ letter-spacing: .4px; }
h1{
  font-family: ui-serif, Georgia, "Times New Roman", serif;
  text-transform: uppercase;
}

/* Cards (same idea as Multi-Multi) */
.gg-card{
  background: linear-gradient(180deg, var(--card), var(--card2));
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  border-radius: 18px;
  padding: 16px 16px 12px 16px;
}

/* Pills */
.gg-pill{
  display:inline-block;
  padding: 6px 10px;
  margin: 3px 4px 0 0;
  border-radius: 999px;
  border: 1px solid rgba(0,255,153,0.28);
  background: rgba(0,255,153,0.08);
  font-weight: 800;
  color: #dfffee;
}

/* Muted */
.gg-muted{ opacity: .80; font-size: .92rem; }

/* Sidebar */
section[data-testid="stSidebar"]{
  background: linear-gradient(180deg, rgba(0,255,153,0.10) 0%, rgba(0,0,0,0.20) 100%);
  border-right: 1px solid rgba(0,255,153,0.12);
}

/* Inputs */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div{
  border-radius: 14px !important;
}

/* Primary button */
div.stButton > button[kind="primary"]{
  background: linear-gradient(90deg, #00ff99 0%, #23ffb0 100%) !important;
  color: #000000 !important;
  border: 0 !important;
  border-radius: 14px !important;
  padding: 0.80rem 1.10rem !important;
  font-weight: 900 !important;
  letter-spacing: .5px !important;
  box-shadow: 0 12px 26px rgba(0,255,153,0.18) !important;
}
div.stButton > button[kind="primary"]:hover{
  filter: brightness(1.04);
  transform: translateY(-1px);
}

/* Secondary buttons keep readable */
div.stButton > button{
  border-radius: 14px !important;
}

/* Row result card */
.gg-row{
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(0,255,153,0.18);
  border-radius: 14px;
  padding: 10px 12px;
  margin: 8px 0;
}

/* Dataframe */
[data-testid="stDataFrame"]{
  border-radius: 16px !important;
  overflow: hidden !important;
  border: 1px solid rgba(0,255,153,0.22) !important;
}

/* Mobile */
@media (max-width: 640px){
  .block-container{ padding-left: 1rem; padding-right: 1rem; }
  div.stButton > button[kind="primary"]{ width: 100% !important; }
}
</style>
"""


# =========================================================
# PDF PARSING (robust + diagnostics like you fixed earlier)
# =========================================================
LINE_6NUM = re.compile(
    r"(?<!\d)([0-4]?\d)\s+([0-4]?\d)\s+([0-4]?\d)\s+([0-4]?\d)\s+([0-4]?\d)\s+([0-4]?\d)(?!\d)"
)

def extract_draws_from_pdf_path(pdf_path: Path) -> List[List[int]]:
    """
    Reads local wyniki.pdf (same folder/repo) and extracts all draws as 6 numbers 1..49.
    Includes:
    - header check (%PDF) to catch Git LFS pointer
    - strict=False and safe extraction
    """
    pdf_bytes = pdf_path.read_bytes()

    # Header check
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
        raise PdfReadError(
            f"PdfReadError: {e}\n"
            "PDF może być uszkodzony lub niekompletny."
        )

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


# =========================================================
# STATS: frequency + groups
# =========================================================
def compute_stats(draws: List[List[int]]) -> pd.DataFrame:
    flat = [n for d in draws for n in d]
    c = Counter(flat)
    rows = [{"Liczba": n, "Wystąpienia": c.get(n, 0)} for n in range(NUM_MIN, NUM_MAX + 1)]
    df = pd.DataFrame(rows).sort_values(["Wystąpienia", "Liczba"], ascending=[False, True]).reset_index(drop=True)
    return df


def build_groups(freq_df: pd.DataFrame, hot_size: int, cold_size: int) -> Tuple[List[int], List[int], List[int]]:
    hot = freq_df.head(hot_size)["Liczba"].tolist()
    cold = freq_df.tail(cold_size)["Liczba"].tolist()
    neutral = [n for n in range(NUM_MIN, NUM_MAX + 1) if n not in hot and n not in cold]
    return hot, cold, neutral


# =========================================================
# ORIGINAL GENERATOR (hot/cold/mix + hybrid 70/20/10)
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
        h = pick_unique(hot, mix_hot_count)
        c = pick_unique([x for x in cold if x not in h], PICK_COUNT - mix_hot_count)
        return sorted(h + c)
    raise ValueError("Nieznany tryb losowania.")


def gen_tickets_hybrid(
    n_tickets: int,
    hot: List[int],
    cold: List[int],
    mix_hot_count: int,
    w_hot: float = 0.70,
    w_cold: float = 0.20,
    w_mix: float = 0.10
) -> List[Dict]:
    labels = ["hot", "cold", "mix"]
    weights = [w_hot, w_cold, w_mix]
    out = []
    for _ in range(n_tickets):
        chosen = random.choices(labels, weights=weights, k=1)[0]
        out.append({"Typ": chosen, "Kupon": gen_ticket(chosen, hot, cold, mix_hot_count)})
    return out


# =========================================================
# SMART MODE FILTERS (optional)
# =========================================================
def count_adjacent_pairs(nums_sorted: List[int]) -> int:
    pairs = 0
    for a, b in zip(nums_sorted, nums_sorted[1:]):
        if b == a + 1:
            pairs += 1
    return pairs


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
# STREAMLIT APP
# =========================================================
def main():
    st.set_page_config(
        page_title="Gothic $ Lotto Generator",
        page_icon="💀",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    st.markdown(DARK_GREEN_CSS, unsafe_allow_html=True)

    st.title(APP_TITLE)
    st.write("Generator typowań na bazie historii losowań z pliku **wyniki.pdf** (zakres **1–49**, typuje **6 liczb**).")
    st.caption("Źródło danych: lokalny plik `wyniki.pdf` w repo (obok pliku aplikacji).")

    # Resolve PDF path robustly for Streamlit Cloud
    pdf_path = Path(os.getcwd()) / PDF_FILENAME

    # Sidebar settings
    with st.sidebar:
        st.header("⚙️ Ustawienia")

        st.markdown("**Tryb typowania**")
        mode_ui = st.selectbox(
            "Wybierz tryb",
            [
                "Hybryda 70/20/10 (hot/cold/mix)",
                "Tylko 🔥 gorące",
                "Tylko ❄️ zimne",
                "Tylko ⚗️ mix (hot+zimne)",
            ],
            index=0
        )

        st.divider()

        st.markdown("**Ile kuponów wygenerować?**")
        n_tickets = st.slider("Liczba kuponów", 1, 500, 20, 1)

        st.divider()

        st.markdown("**Wielkość grup Hot/Cold**")
        hot_size = st.slider("Ile liczb w grupie Gorących", 6, 35, 20, 1)
        cold_size = st.slider("Ile liczb w grupie Zimnych", 6, 35, 20, 1)

        st.divider()

        st.markdown("**MIX: ile liczb z gorących?**")
        mix_hot_count = st.slider("W trybie MIX", 1, 5, 3, 1)

        st.divider()

        st.subheader("🧠 Tryb inteligentny (opcjonalny)")
        smart_enabled = st.checkbox("Włącz tryb inteligentny", value=False)

        if smart_enabled:
            st.caption("Możesz zaznaczyć kilka filtrów naraz. Rozkład parzyste/nieparzyste: jeden wybór (radio).")

            block_run_2 = st.checkbox("Blokuj układy 1–2 (kolejne liczby)", value=True)
            block_run_3 = st.checkbox("Blokuj układy 1–3 (ciąg 3 kolejnych)", value=True)

            limit_pairs_on = st.checkbox("Włącz limit par (kolejne liczby)", value=True)
            max_adj_pairs = None
            if limit_pairs_on:
                max_adj_pairs = st.slider("Maks. liczba par kolejnych", 0, 5, 2, 1)

            even_odd_choice = st.radio(
                "Parzyste / Nieparzyste",
                ["Dowolnie", "3/3", "4/2", "2/4", "5/1", "1/5"],
                index=1
            )

            max_attempts_per_ticket = st.slider("Limit prób na kupon", 10, 500, 120, 10)
        else:
            block_run_2 = False
            block_run_3 = False
            max_adj_pairs = None
            even_odd_choice = "Dowolnie"
            max_attempts_per_ticket = 120

    # Load & analyze
    left, right = st.columns([1.2, 0.8], gap="large")

    with left:
        st.markdown('<div class="gg-card">', unsafe_allow_html=True)
        st.subheader("📄 Dane wejściowe")
        st.write(f"Ścieżka PDF: `{pdf_path}`")

        if not pdf_path.exists():
            st.error(f"❌ Nie znaleziono pliku `{PDF_FILENAME}` w katalogu aplikacji. Wrzuć go do repo obok pliku aplikacji.")
            st.stop()

        try:
            draws = extract_draws_from_pdf_path(pdf_path)
        except ValueError as e:
            st.error("❌ Problem z plikiem `wyniki.pdf` (to nie jest prawdziwy PDF lub jest wskaźnikiem LFS).")
            st.code(str(e))
            st.stop()
        except Exception as e:
            st.error("❌ Błąd podczas czytania PDF (prawdopodobnie plik uszkodzony / niepełny).")
            st.code(str(e))
            st.stop()

        if len(draws) == 0:
            st.error("❌ Nie udało się znaleźć losowań (linii z 6 liczbami 1–49) w PDF.")
            st.stop()

        st.success(f"✅ Załadowano losowania: **{len(draws)}**")
        st.markdown('<div class="gg-muted">Aplikacja analizuje wszystkie losowania z pliku i buduje grupy Hot/Cold.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="gg-card">', unsafe_allow_html=True)
        st.subheader("📊 Częstotliwość 1–49")
        freq_df = compute_stats(draws)
        st.dataframe(freq_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    hot, cold, neutral = build_groups(freq_df, hot_size=hot_size, cold_size=cold_size)

    with right:
        st.markdown('<div class="gg-card">', unsafe_allow_html=True)
        st.subheader("🔥 Gorące / ❄️ Zimne")

        st.markdown("**Gorące (Hot)**")
        st.markdown(" ".join([f'<span class="gg-pill">{n:02d}</span>' for n in sorted(hot)]), unsafe_allow_html=True)

        st.markdown("**Zimne (Cold)**")
        st.markdown(" ".join([f'<span class="gg-pill">{n:02d}</span>' for n in sorted(cold)]), unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="gg-card">', unsafe_allow_html=True)
        st.subheader("🎛️ Wybrany tryb")
        st.write(f"**Tryb:** {mode_ui}")
        if mode_ui == "Tylko ⚗️ mix (hot+zimne)":
            st.write(f"**MIX:** {mix_hot_count} z gorących + {PICK_COUNT - mix_hot_count} z zimnych")
        st.write(f"**Tryb inteligentny:** {'TAK' if smart_enabled else 'NIE'}")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    # Generate
    st.markdown('<div class="gg-card">', unsafe_allow_html=True)
    st.subheader("🎟️ Generator kuponów")

    generate = st.button("🎯 GENERUJ KUPONY (6 liczb)", type="primary", use_container_width=True)

    if generate:
        # Map UI mode to internal
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
                chosen = random.choices(["hot", "cold", "mix"], weights=[0.70, 0.20, 0.10], k=1)[0]
                return {"Typ": chosen, "Kupon": gen_ticket(chosen, hot, cold, mix_hot_count)}
            if base_mode_kind == "hot":
                return {"Typ": "hot", "Kupon": gen_ticket("hot", hot, cold, mix_hot_count)}
            if base_mode_kind == "cold":
                return {"Typ": "cold", "Kupon": gen_ticket("cold", hot, cold, mix_hot_count)}
            return {"Typ": "mix", "Kupon": gen_ticket("mix", hot, cold, mix_hot_count)}

        if not smart_enabled:
            records = [gen_one_record() for _ in range(int(n_tickets))]
        else:
            smart_kwargs = {
                "block_run_2": block_run_2,
                "block_run_3": block_run_3,
                "max_adjacent_pairs": max_adj_pairs,
                "even_odd_choice": even_odd_choice
            }
            records = generate_with_smart_filters(
                gen_func=gen_one_record,
                n_tickets=int(n_tickets),
                max_attempts_per_ticket=int(max_attempts_per_ticket),
                smart_kwargs=smart_kwargs
            )

            if len(records) < int(n_tickets):
                st.warning(
                    f"⚠️ Filtry są dość ostre: udało się wygenerować **{len(records)}** / {int(n_tickets)} kuponów. "
                    "Poluzuj filtry albo zwiększ limit prób."
                )

        # Render results list (nice rows)
        st.markdown("### Wyniki")
        for i, r in enumerate(records, start=1):
            t = r["Kupon"]
            nums = " ".join([f"{n:02d}" for n in t])
            ev, od = even_odd_split(t)
            pairs = count_adjacent_pairs(sorted(t))
            st.markdown(
                f'<div class="gg-row"><b>Kupon #{i:03d}</b> '
                f'<span class="gg-muted">[{r["Typ"]}]</span> — {nums} '
                f'<span class="gg-muted"> | parzyste/nieparzyste: {ev}/{od} | pary: {pairs}</span></div>',
                unsafe_allow_html=True
            )

        # Downloads: CSV + TXT + report JSON in ZIP
        df_out = pd.DataFrame({
            "Typ": [r["Typ"] for r in records],
            "Kupon": [" ".join(f"{x:02d}" for x in r["Kupon"]) for r in records],
        })

        csv_bytes = df_out.to_csv(index=False).encode("utf-8")

        txt_lines = [
            f"{i+1:03d}. [{records[i]['Typ']}] " + " ".join(f"{x:02d}" for x in records[i]["Kupon"])
            for i in range(len(records))
        ]
        txt_bytes = ("\n".join(txt_lines)).encode("utf-8")

        report = {
            "pdf_file": PDF_FILENAME,
            "draws_found": len(draws),
            "hot_size": int(hot_size),
            "cold_size": int(cold_size),
            "hot": sorted(hot),
            "cold": sorted(cold),
            "mix_hot_count": int(mix_hot_count),
            "mode": mode_ui,
            "smart_enabled": bool(smart_enabled),
            "smart_filters": {
                "block_run_2": bool(block_run_2),
                "block_run_3": bool(block_run_3),
                "max_adjacent_pairs": max_adj_pairs,
                "even_odd_choice": even_odd_choice
            } if smart_enabled else {},
            "smart_max_attempts_per_ticket": int(max_attempts_per_ticket) if smart_enabled else None,
        }
        report_bytes = (pd.Series(report).to_json(indent=2, force_ascii=False)).encode("utf-8")

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("kupony.csv", csv_bytes)
            z.writestr("kupony.txt", txt_bytes)
            z.writestr("raport.json", report_bytes)

        st.download_button(
            "⬇️ Pobierz paczkę (ZIP: kupony + raport)",
            data=zip_buffer.getvalue(),
            file_name="gothic_lotto_kupony.zip",
            mime="application/zip",
            use_container_width=True,
        )

        st.caption("Uwaga: losowania są losowe — analiza historii nie zwiększa realnych szans wygranej. Generator ma charakter analityczny/rozrywkowy.")

    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("📊 Statystyki (diagnostyka)"):
        st.write("Top 15 najczęstszych liczb:")
        top15 = freq_df.head(15)
        st.dataframe(top15, use_container_width=True, hide_index=True)

        st.write("Top 15 najrzadszych liczb:")
        low15 = freq_df.tail(15).sort_values(["Wystąpienia", "Liczba"], ascending=[True, True])
        st.dataframe(low15, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
