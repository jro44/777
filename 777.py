import io
import re
import zipfile
import random
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st
from pypdf import PdfReader


# =========================
# 🎨 GOTYCKI $ STYL (czytelniejszy + mocny czarny przycisk)
# =========================
GOTHIC_CSS = """
<style>
:root{
  --bg0:#07070b;
  --bg1:#0b0b12;
  --card:#111118;
  --card2:#151524;
  --txt:#f4f4f6;
  --mut:#c2c2d3;
  --gold:#d7c36a;
  --green:#00ff99;
  --border:rgba(215,195,106,.30);
  --shadow: 0 12px 40px rgba(0,0,0,.60);
}

html, body, [class*="css"]  {
  background: radial-gradient(1200px 600px at 15% 10%, rgba(0,255,153,0.10), transparent 60%),
              radial-gradient(900px 500px at 90% 20%, rgba(215,195,106,0.10), transparent 55%),
              linear-gradient(180deg, var(--bg0), var(--bg1));
  color: var(--txt) !important;
}

/* Szerokość i mobile */
.main .block-container{
  padding-top: 1.2rem;
  padding-bottom: 2rem;
  max-width: 1100px;
}

/* Nagłówki */
h1, h2, h3 { letter-spacing: .5px; }
h1{
  font-family: ui-serif, Georgia, "Times New Roman", serif;
  text-transform: uppercase;
  margin-bottom: .35rem;
}
.badge{
  display:inline-block;
  padding:.25rem .60rem;
  border:1px solid var(--border);
  border-radius: 999px;
  background: rgba(215,195,106,0.10);
  color: var(--gold);
  font-weight: 700;
  margin-left: .5rem;
  font-size: .85rem;
}

/* Karty */
.card{
  background: linear-gradient(180deg, rgba(17,17,24,0.96), rgba(11,11,18,0.96));
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  border-radius: 18px;
  padding: 14px 14px;
}
.card + .card{ margin-top: 12px; }

/* “$” ornament */
.orn{
  font-family: ui-serif, Georgia, "Times New Roman", serif;
  color: rgba(215,195,106,.90);
  font-size: 1.05rem;
  margin: .25rem 0 .75rem 0;
}
.orn span{ color: rgba(0,255,153,.80); }

/* ✅ SUPER CZYTELNY PRZYCISK "GENERUJ" */
div.stButton > button{
  background-color: #000000 !important;
  color: var(--green) !important;
  font-size: 20px !important;
  font-weight: 900 !important;
  padding: 14px 18px !important;
  border-radius: 14px !important;
  border: 2px solid var(--green) !important;
  width: 100% !important;
}
div.stButton > button:hover{
  background-color: var(--green) !important;
  color: #000000 !important;
  border: 2px solid var(--green) !important;
}

/* Tabele */
.dataframe{
  border-radius: 16px !important;
  overflow: hidden !important;
  border: 1px solid var(--border) !important;
}

/* Teksty pomocnicze */
small, .muted{ color: var(--mut); }
hr{ border-color: rgba(215,195,106,.18); }
</style>
"""


# =========================
# 🧠 LOGIKA: PARSE PDF (z pliku wyniki.pdf w repo)
# =========================
LINE_6NUM = re.compile(
    r"(?<!\d)([0-4]?\d)\s+([0-4]?\d)\s+([0-4]?\d)\s+([0-4]?\d)\s+([0-4]?\d)\s+([0-4]?\d)(?!\d)"
)

def extract_draws_from_pdf_path(pdf_path: Path) -> list[list[int]]:
    """
    Wyciąga wszystkie losowania (linie z 6 liczbami 1–49) z PDF.
    Zwraca listę losowań: [[n1..n6], ...]
    """
    reader = PdfReader(str(pdf_path))
    draws: list[list[int]] = []

    for page in reader.pages:
        text = page.extract_text() or ""
        for m in LINE_6NUM.finditer(text):
            nums = [int(m.group(i)) for i in range(1, 7)]
            # filtr: tylko 1..49 i brak zer
            if all(1 <= n <= 49 for n in nums):
                # w losowaniu nie powinno być duplikatów
                if len(set(nums)) == 6:
                    draws.append(sorted(nums))

    return draws


def compute_stats(draws: list[list[int]]) -> pd.DataFrame:
    """
    Zwraca tabelę 1..49 z częstotliwością (posortowane malejąco).
    """
    flat = [n for draw in draws for n in draw]
    c = Counter(flat)

    rows = []
    for n in range(1, 50):
        rows.append({"Liczba": n, "Wystąpienia": c.get(n, 0)})

    df = pd.DataFrame(rows).sort_values(["Wystąpienia", "Liczba"], ascending=[False, True]).reset_index(drop=True)
    return df


def build_groups(freq_df: pd.DataFrame, hot_size: int, cold_size: int):
    """
    Gorące: top hot_size
    Zimne: bottom cold_size
    Neutralne: reszta
    """
    hot = freq_df.head(hot_size)["Liczba"].tolist()
    cold = freq_df.tail(cold_size)["Liczba"].tolist()
    neutral = [n for n in range(1, 50) if n not in hot and n not in cold]
    return hot, cold, neutral


# =========================
# 🎲 GENERATOR KUPONÓW (oryginał)
# =========================
def pick_unique(pool: list[int], k: int) -> list[int]:
    if len(pool) < k:
        raise ValueError("Za mało liczb w puli, aby wylosować unikalny zestaw.")
    return sorted(random.sample(pool, k))


def gen_ticket(mode: str, hot: list[int], cold: list[int], mix_hot_count: int) -> list[int]:
    """
    mode:
      - "hot"  -> 6 z hot
      - "cold" -> 6 z cold
      - "mix"  -> mix_hot_count z hot + reszta z cold
    """
    if mode == "hot":
        return pick_unique(hot, 6)
    if mode == "cold":
        return pick_unique(cold, 6)
    if mode == "mix":
        h = pick_unique(hot, mix_hot_count)
        c = pick_unique([x for x in cold if x not in h], 6 - mix_hot_count)
        return sorted(h + c)

    raise ValueError("Nieznany tryb losowania.")


def gen_tickets_hybrid(
    n_tickets: int,
    hot: list[int],
    cold: list[int],
    mix_hot_count: int,
    w_hot: float = 0.70,
    w_cold: float = 0.20,
    w_mix: float = 0.10,
) -> list[dict]:
    """
    70% kuponów hot, 20% cold, 10% mix.
    Zwraca listę rekordów: {"Typ": "...", "Kupon": [..]}
    """
    labels = ["hot", "cold", "mix"]
    probs = [w_hot, w_cold, w_mix]

    out = []
    for _ in range(n_tickets):
        chosen = random.choices(labels, weights=probs, k=1)[0]
        ticket = gen_ticket(chosen, hot, cold, mix_hot_count)
        out.append({"Typ": chosen, "Kupon": ticket})
    return out


# =========================
# 🧠 TRYB INTELIGENTNY: FILTRY
# =========================
def count_adjacent_runs(nums: list[int]) -> int:
    """
    Liczy ile jest par sąsiadujących (różnica 1) w posortowanym kuponie.
    """
    nums = sorted(nums)
    runs = 0
    for i in range(len(nums) - 1):
        if nums[i + 1] - nums[i] == 1:
            runs += 1
    return runs


def count_pairs_by_decade(nums: list[int]) -> int:
    """
    Liczy liczbę par w tych samych 'dziesiątkach':
    1-9, 10-19, 20-29, 30-39, 40-49.
    Zwraca sumę par (kombinacje 2-elementowe) we wszystkich koszykach.
    """
    buckets = {}
    for n in nums:
        key = n // 10  # 0..4
        buckets[key] = buckets.get(key, 0) + 1

    pairs = 0
    for cnt in buckets.values():
        if cnt >= 2:
            pairs += (cnt * (cnt - 1)) // 2  # C(cnt,2)
    return pairs


def parity_ratio(nums: list[int]) -> tuple[int, int]:
    ev = sum(1 for n in nums if n % 2 == 0)
    od = 6 - ev
    return ev, od


def smart_ok(
    ticket: list[int],
    block_adjacent: bool,
    block_adjacent_level: str,   # "1-2" albo "1-3"
    limit_pairs_enabled: bool,
    max_pairs_in_decade: int,
    parity_rule: str,            # "brak", "3/3", "3/2"
) -> bool:
    """
    Zwraca True jeśli kupon przechodzi wszystkie włączone reguły.
    """
    nums = sorted(ticket)

    # 1) Blokada układów kolejnych liczb
    # - "1-2" => odrzuca kupony z >=2 parami sąsiadującymi
    # - "1-3" => odrzuca kupony z >=3 parami sąsiadującymi
    if block_adjacent:
        runs = count_adjacent_runs(nums)
        if block_adjacent_level == "1-2":
            if runs >= 2:
                return False
        elif block_adjacent_level == "1-3":
            if runs >= 3:
                return False

    # 2) Limit par w dziesiątkach
    if limit_pairs_enabled:
        pairs = count_pairs_by_decade(nums)
        if pairs > max_pairs_in_decade:
            return False

    # 3) Parzyste/nieparzyste — wybór tylko jednego wariantu
    if parity_rule != "brak":
        ev, od = parity_ratio(nums)
        if parity_rule == "3/3":
            if not (ev == 3 and od == 3):
                return False
        elif parity_rule == "3/2":
            # 3/2 interpretujemy jako: 4/2 lub 2/4
            if not ((ev == 4 and od == 2) or (ev == 2 and od == 4)):
                return False

    return True


def generate_with_smart_filters(
    gen_func,
    n_tickets: int,
    max_attempts_per_ticket: int,
    smart_kwargs: dict,
) -> list[dict]:
    """
    gen_func() -> {"Typ": "...", "Kupon": [...]}
    W trybie inteligentnym: generujemy jak oryginał, ale odrzucamy kupony nieprzechodzące filtrów.
    """
    out: list[dict] = []
    attempts = 0

    while len(out) < n_tickets:
        attempts += 1
        if attempts > n_tickets * max_attempts_per_ticket:
            break

        rec = gen_func()
        if smart_ok(rec["Kupon"], **smart_kwargs):
            out.append(rec)

    return out


# =========================
# 🖥️ STREAMLIT UI
# =========================
st.set_page_config(
    page_title="Gothic $ Lotto Generator",
    page_icon="💀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(GOTHIC_CSS, unsafe_allow_html=True)

st.markdown(
    "# 💀 Gothic $ Lotto Generator"
    ' <span class="badge">Baza: wyniki.pdf</span>',
    unsafe_allow_html=True
)
st.markdown(
    '<div class="orn">$ <span>†</span> $ <span>†</span> $ — czytelnie, gotycko i z kontrolą typowań.</div>',
    unsafe_allow_html=True
)

# =========================
# 📄 Wczytanie lokalnego PDF (wyniki.pdf)
# =========================
BASE_PDF = Path(__file__).parent / "wyniki.pdf"

with st.container():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.write("**Źródło danych:** aplikacja korzysta z lokalnego pliku `wyniki.pdf` w tym samym folderze co `app.py`.")
    st.write(f"**Ścieżka:** `{BASE_PDF}`")
    st.markdown('</div>', unsafe_allow_html=True)

if not BASE_PDF.exists():
    st.error("❌ Nie znaleziono pliku **wyniki.pdf** w repozytorium. Wrzuć go obok pliku aplikacji i zdeployuj ponownie.")
    st.stop()

try:
    draws = extract_draws_from_pdf_path(BASE_PDF)
except Exception as e:
    st.error(f"❌ Błąd podczas czytania PDF: {e}")
    st.stop()

if len(draws) == 0:
    st.error("❌ Nie udało się znaleźć losowań (linii z 6 liczbami 1–49) w `wyniki.pdf`. Sprawdź format pliku.")
    st.stop()

st.success(f"✅ Załadowano losowania: **{len(draws)}** z `wyniki.pdf`.")

freq_df = compute_stats(draws)

colA, colB = st.columns([1.1, 0.9], gap="large")

with colA:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("📊 Częstotliwość 1–49")
    st.caption("Sortowanie: najczęstsze na górze.")
    st.dataframe(freq_df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

with colB:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("⚙️ Ustawienia grup")

    hot_size = st.slider("Ile liczb w grupie 🔥 gorących?", 6, 35, 20, 1)
    cold_size = st.slider("Ile liczb w grupie ❄️ zimnych?", 6, 35, 20, 1)

    if hot_size + cold_size > 49:
        st.error("Suma rozmiarów grup przekracza 49. Zmniejsz jedną z grup.")
        st.stop()

    hot, cold, neutral = build_groups(freq_df, hot_size, cold_size)

    st.markdown("**🔥 Gorące:** " + ", ".join(f"{x:02d}" for x in hot))
    st.markdown("**❄️ Zimne:** " + ", ".join(f"{x:02d}" for x in cold))
    st.markdown(f'<span class="muted">Neutralne (poza grupami): {len(neutral)}</span>', unsafe_allow_html=True)

    st.divider()
    st.subheader("🎛️ Tryb typowania (oryginał)")
    mode = st.selectbox(
        "Wybierz tryb",
        [
            "Hybryda 70/20/10 (hot/cold/mix)",
            "Tylko 🔥 gorące",
            "Tylko ❄️ zimne",
            "Tylko ⚗️ mix (hot + zimne)",
        ],
    )

    mix_hot_count = st.slider("W trybie MIX: ile liczb ma być z gorących?", 1, 5, 3, 1)

    st.divider()
    st.subheader("🧠 Tryb inteligentny (opcjonalny)")
    smart_enabled = st.checkbox(
        "✅ Włącz tryb inteligentny",
        value=False,
        help="Jeśli wyłączone — generator działa dokładnie jak oryginał (bez filtrów)."
    )

    # domyślne (gdy smart off — nie wpływają)
    block_adjacent = False
    block_adjacent_level = "1-2"
    limit_pairs_enabled = False
    max_pairs_in_decade = 2
    parity_rule = "brak"
    max_attempts_per_ticket = 120

    if smart_enabled:
        st.caption("Zaznacz filtry. Możesz włączyć wszystkie albo tylko kilka.")
        block_adjacent = st.checkbox("Blokada układów kolejnych liczb (1-2 / 1-3)", value=True)

        if block_adjacent:
            block_adjacent_level = st.radio(
                "Poziom blokady kolejnych liczb",
                ["1-2", "1-3"],
                horizontal=True,
                help="1-2 = odrzuca kupony z ≥2 parami sąsiadującymi. 1-3 = odrzuca kupony z ≥3 parami sąsiadującymi."
            )

        limit_pairs_enabled = st.checkbox("Limit par w dziesiątkach (1-9, 10-19, ...)", value=True)
        if limit_pairs_enabled:
            max_pairs_in_decade = st.slider(
                "Maksymalna liczba par (sumarycznie po dziesiątkach)",
                min_value=0, max_value=6, value=2, step=1,
                help="Im mniejsza wartość, tym bardziej 'rozstrzelone' kupony."
            )

        parity_rule = st.radio(
            "Rozkład parzyste/nieparzyste (jeden wybór)",
            ["brak", "3/3", "3/2"],
            horizontal=True,
            help="3/3 = 3 parzyste i 3 nieparzyste. 3/2 = 4/2 lub 2/4."
        )

        max_attempts_per_ticket = st.slider(
            "Limit prób na kupon (gdy filtry odrzucają)",
            10, 500, 120, 10
        )

    st.divider()
    st.subheader("🎲 Generowanie kuponów")
    n_tickets = st.number_input("Ile kuponów wygenerować?", min_value=1, max_value=500, value=20, step=1)

    st.markdown('</div>', unsafe_allow_html=True)


# =========================
# 🎬 GENERUJ
# =========================
if st.button("🚀 GENERUJ KUPONY"):
    smart_kwargs = {
        "block_adjacent": block_adjacent,
        "block_adjacent_level": block_adjacent_level,
        "limit_pairs_enabled": limit_pairs_enabled,
        "max_pairs_in_decade": int(max_pairs_in_decade),
        "parity_rule": parity_rule,
    }

    def gen_one_record() -> dict:
        """
        Jedna próbka kuponu dokładnie wg oryginału (w zależności od wybranego mode).
        """
        if mode == "Hybryda 70/20/10 (hot/cold/mix)":
            chosen = random.choices(["hot", "cold", "mix"], weights=[0.70, 0.20, 0.10], k=1)[0]
            return {"Typ": chosen, "Kupon": gen_ticket(chosen, hot, cold, int(mix_hot_count))}
        elif mode == "Tylko 🔥 gorące":
            return {"Typ": "hot", "Kupon": gen_ticket("hot", hot, cold, int(mix_hot_count))}
        elif mode == "Tylko ❄️ zimne":
            return {"Typ": "cold", "Kupon": gen_ticket("cold", hot, cold, int(mix_hot_count))}
        else:
            return {"Typ": "mix", "Kupon": gen_ticket("mix", hot, cold, int(mix_hot_count))}

    # jeśli smart off -> oryginał 1:1
    if not smart_enabled:
        records = [gen_one_record() for _ in range(int(n_tickets))]
    else:
        records = generate_with_smart_filters(
            gen_func=gen_one_record,
            n_tickets=int(n_tickets),
            max_attempts_per_ticket=int(max_attempts_per_ticket),
            smart_kwargs=smart_kwargs,
        )
        if len(records) < int(n_tickets):
            st.warning(
                f"⚠️ Filtry są dość ostre: udało się wygenerować **{len(records)}** / {int(n_tickets)} kuponów. "
                "Zwiększ limit prób albo poluzuj filtry."
            )

    # Tabela kuponów
    df_out = pd.DataFrame({
        "Typ": [r["Typ"] for r in records],
        "Kupon": [" ".join(f"{x:02d}" for x in r["Kupon"]) for r in records],
    })

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("✅ Wygenerowane kupony")
    st.dataframe(df_out, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Paczka do pobrania (CSV + TXT + raport)
    csv_bytes = df_out.to_csv(index=False).encode("utf-8")

    txt_lines = [
        f"{i+1:03d}. [{records[i]['Typ']}] " + " ".join(f"{x:02d}" for x in records[i]["Kupon"])
        for i in range(len(records))
    ]
    txt_bytes = ("\n".join(txt_lines)).encode("utf-8")

    report = {
        "pdf_file": "wyniki.pdf",
        "draws_found": len(draws),
        "hot_size": int(hot_size),
        "cold_size": int(cold_size),
        "hot": hot,
        "cold": cold,
        "mix_hot_count": int(mix_hot_count),
        "mode": mode,
        "smart_enabled": bool(smart_enabled),
        "smart_filters": smart_kwargs if smart_enabled else {},
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

st.caption("Uwaga: losowania są losowe — analiza historii nie zwiększa realnych szans wygranej. To narzędzie do analizy i wygodnego typowania.")
