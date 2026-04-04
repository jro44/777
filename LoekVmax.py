import random
import re
import statistics
from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Tuple

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st


# =========================================================
# KONFIGURACJA
# =========================================================
APP_TITLE = "🎯 Lotto PRO Generator"
APP_SUBTITLE = (
    "Losowy • Losowy statyczny • Hot • Cold • 50/50 • HOT MAX • "
    "Złoty Strzał • Ranking • Szlaczek"
)

LOTTO_MIN = 1
LOTTO_MAX = 49
LOTTO_PICK = 6

DEFAULT_HISTORY_WINDOW = 999
DEFAULT_CANDIDATES = 3000
DEFAULT_RANDOM_SEED = 42

LINE_DRAWNO = re.compile(r"^\d{4}$")
NUM_TOKEN_RE = re.compile(r"^\d{1,2}$")


# =========================================================
# STYLE
# =========================================================
st.set_page_config(page_title=APP_TITLE, layout="wide")

APP_CSS = """
<style>
:root{
  --bg0:#eef8ef;
  --bg1:#ffffff;
  --card:#ffffff;
  --card2:#f8fff8;
  --txt:#111111;
  --mut:#4b5563;
  --green:#0d7a34;
  --green2:#2ea85d;
  --gold:#d3aa2b;
  --border: rgba(13,122,52,0.18);
  --shadow: 0 10px 28px rgba(0,0,0,.08);
}

.stApp{
  background-color: var(--bg0) !important;
  background-image:
    radial-gradient(1200px 800px at 12% 10%, rgba(46,168,93,0.08), transparent 58%),
    radial-gradient(950px 650px at 92% 18%, rgba(211,170,43,0.07), transparent 55%),
    linear-gradient(180deg, var(--bg0), var(--bg1)) !important;
}

.block-container{
  padding-top: 1.2rem !important;
}

.ticket-card{
  background: linear-gradient(180deg, #ffffff, #f6fff8);
  border: 1px solid rgba(13,122,52,0.18);
  border-radius: 18px;
  padding: 16px;
  margin: 10px 0;
  box-shadow: 0 8px 18px rgba(0,0,0,.05);
}

.ticket-card-gold{
  background: linear-gradient(135deg, #fff7dd 0%, #fff0b8 100%);
  border: 2px solid #f3c63a;
  border-radius: 18px;
  padding: 18px;
  margin: 10px 0;
  box-shadow: 0 12px 24px rgba(243,198,58,0.22);
}

.ticket-title{
  font-size: 1.02rem;
  font-weight: 900;
  margin-bottom: 8px;
}

.ticket-main{
  font-size: 1.20rem;
  font-weight: 900;
  letter-spacing: .5px;
  margin-bottom: 8px;
}

.ticket-meta{
  font-size: .94rem;
  line-height: 1.55;
  color: #1f2937;
}

div.stButton > button{
  width: 100%;
  border-radius: 14px;
  min-height: 3.1rem;
  border: 0 !important;
  background: linear-gradient(90deg, var(--green) 0%, var(--green2) 100%) !important;
  color: white !important;
  font-weight: 800 !important;
}

div.stDownloadButton > button{
  width: 100%;
  border-radius: 14px;
  min-height: 3rem;
  font-weight: 800 !important;
}
</style>
"""
st.markdown(APP_CSS, unsafe_allow_html=True)


# =========================================================
# MODELE
# =========================================================
@dataclass
class Draw:
    draw_id: int
    nums: List[int]


@dataclass
class TicketResult:
    mode: str
    nums: List[int]
    score: float
    note: str


# =========================================================
# POMOCNICZE
# =========================================================
def fmt_nums(nums: List[int]) -> str:
    return " ".join(f"{n:02d}" for n in sorted(nums))


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def count_even(nums: List[int]) -> int:
    return sum(1 for n in nums if n % 2 == 0)


def count_adjacent_pairs(nums: List[int]) -> int:
    s = sorted(nums)
    return sum(1 for a, b in zip(s, s[1:]) if b == a + 1)


def max_run(nums: List[int]) -> int:
    s = sorted(nums)
    if not s:
        return 0
    best = 1
    cur = 1
    for a, b in zip(s, s[1:]):
        if b == a + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def safe_mean(values: List[float], default: float = 0.0) -> float:
    return sum(values) / len(values) if values else default


def sanitize_txt_filename(name: str) -> str:
    name = (name or "").strip()
    if not name:
        name = "lotto_kupony.txt"
    name = name.replace("\\", "_").replace("/", "_").replace("..", "_")
    if not name.lower().endswith(".txt"):
        name += ".txt"
    return name


def normalize_score_dict(raw: Dict[int, float]) -> Dict[int, float]:
    if not raw:
        return {}
    vals = list(raw.values())
    mn = min(vals)
    mx = max(vals)
    if mx == mn:
        return {k: 1.0 for k in raw}
    return {k: 0.1 + ((v - mn) / (mx - mn)) for k, v in raw.items()}


def weighted_sample_without_replacement(
    population: List[int],
    weights: List[float],
    k: int,
    rng: random.Random,
) -> List[int]:
    if k > len(population):
        raise ValueError("k nie może być większe niż populacja.")
    pop = population[:]
    wts = weights[:]
    result = []

    for _ in range(k):
        total = sum(wts)
        if total <= 0:
            pick_idx = rng.randrange(len(pop))
        else:
            r = rng.uniform(0, total)
            acc = 0.0
            pick_idx = 0
            for i, w in enumerate(wts):
                acc += w
                if acc >= r:
                    pick_idx = i
                    break

        result.append(pop.pop(pick_idx))
        wts.pop(pick_idx)

    return sorted(result)


def ticket_overlap(a: List[int], b: List[int]) -> int:
    return len(set(a) & set(b))


def is_diverse_enough(candidate: List[int], existing: List[List[int]], max_overlap: int = 3) -> bool:
    for ex in existing:
        if ticket_overlap(candidate, ex) > max_overlap:
            return False
    return True


def basic_structure_score(nums: List[int]) -> float:
    nums = sorted(nums)
    score = 0.0

    evens = count_even(nums)
    if evens in (2, 3, 4):
        score += 1.2
    else:
        score -= 0.8

    spread = max(nums) - min(nums)
    if 18 <= spread <= 40:
        score += 1.4
    else:
        score -= 0.7

    adj = count_adjacent_pairs(nums)
    if adj <= 2:
        score += 0.8
    else:
        score -= 0.8

    run = max_run(nums)
    if run <= 3:
        score += 0.7
    else:
        score -= 1.0

    total = sum(nums)
    if 90 <= total <= 210:
        score += 1.1
    else:
        score -= 0.6

    return score


# =========================================================
# PDF PARSER
# =========================================================
def _validate_pdf_bytes(pdf_bytes: bytes) -> None:
    if not pdf_bytes.startswith(b"%PDF"):
        preview = pdf_bytes[:180].decode("utf-8", errors="replace")
        raise ValueError(
            "Plik nie wygląda jak prawdziwy PDF (brak nagłówka %PDF).\n"
            f"Początek pliku:\n{preview}"
        )


def _read_pdf_pages_words(pdf_bytes: bytes) -> List[List[Tuple]]:
    _validate_pdf_bytes(pdf_bytes)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_words = []
    for page in doc:
        pages_words.append(page.get_text("words") or [])
    doc.close()
    return pages_words


def _group_words_into_rows(words: List[Tuple], y_tolerance: float = 2.2) -> List[List[Tuple]]:
    if not words:
        return []

    words_sorted = sorted(words, key=lambda w: (round(float(w[1]), 1), float(w[0])))
    rows = []
    current = []
    current_y = None

    for w in words_sorted:
        y = float(w[1])

        if current_y is None:
            current = [w]
            current_y = y
            continue

        if abs(y - current_y) <= y_tolerance:
            current.append(w)
            current_y = (current_y + y) / 2.0
        else:
            rows.append(sorted(current, key=lambda x: x[0]))
            current = [w]
            current_y = y

    if current:
        rows.append(sorted(current, key=lambda x: x[0]))

    return rows


def _is_noise_row(texts: List[str]) -> bool:
    joined = " ".join(texts).lower()
    noise_markers = ["multipasko", "www.", "mapy", "liczbowe", "©"]
    return any(marker in joined and "lotto 6/49" not in joined for marker in noise_markers)


def _extract_records_from_grid_words(
    pages_words: List[List[Tuple]],
    num_min: int,
    num_max: int,
    pick_count: int,
    title_fragment: str,
) -> List[Dict]:
    records = []

    for page_words in pages_words:
        rows = _group_words_into_rows(page_words, y_tolerance=2.2)

        for row in rows:
            texts = [str(w[4]).strip() for w in row if str(w[4]).strip()]
            if not texts:
                continue

            joined = " ".join(texts).lower()
            if title_fragment.lower() in joined:
                continue
            if _is_noise_row(texts):
                continue

            row_sorted = sorted(row, key=lambda z: z[0])
            row_texts = [str(w[4]).strip() for w in row_sorted if str(w[4]).strip()]

            first = row_texts[0]
            if not LINE_DRAWNO.match(first):
                continue

            draw_no = int(first)
            nums = []

            for token in row_texts[1:]:
                if not NUM_TOKEN_RE.match(token):
                    continue
                val = int(token)
                if num_min <= val <= num_max:
                    nums.append(val)

            nums = sorted(nums)
            if len(nums) == pick_count and len(set(nums)) == pick_count:
                records.append({"draw_no": draw_no, "nums": nums})

    dedup = {}
    ordered = []
    for r in records:
        dno = r["draw_no"]
        if dno not in dedup:
            dedup[dno] = r["nums"]
            ordered.append(dno)

    final_records = [{"draw_no": dno, "nums": dedup[dno]} for dno in ordered]
    final_records.sort(key=lambda r: r["draw_no"], reverse=True)
    return final_records


@st.cache_data(show_spinner=False)
def load_draws_from_pdf_bytes(pdf_bytes: bytes) -> Tuple[List[Draw], Dict]:
    pages_words = _read_pdf_pages_words(pdf_bytes)

    records = _extract_records_from_grid_words(
        pages_words=pages_words,
        num_min=LOTTO_MIN,
        num_max=LOTTO_MAX,
        pick_count=LOTTO_PICK,
        title_fragment="Lotto 6/49",
    )

    if not records:
        raise RuntimeError("Nie udało się odczytać wyników Lotto 6/49 z PDF.")

    draws = [Draw(draw_id=r["draw_no"], nums=r["nums"]) for r in records]
    diagnostics = {
        "draws_found": len(draws),
        "latest_draw_id": draws[0].draw_id if draws else None,
        "oldest_draw_id": draws[-1].draw_id if draws else None,
    }
    return draws, diagnostics


# =========================================================
# DANE DEMO
# =========================================================
DEFAULT_DRAWS: List[Draw] = [
    Draw(1006, [5, 10, 14, 33, 34, 47]),
    Draw(1005, [3, 20, 26, 37, 45, 47]),
    Draw(1004, [6, 8, 14, 27, 29, 30]),
    Draw(1003, [10, 12, 16, 27, 36, 40]),
    Draw(1002, [9, 13, 16, 17, 38, 45]),
    Draw(1001, [21, 22, 25, 40, 47, 49]),
    Draw(1000, [1, 2, 19, 25, 36, 43]),
    Draw(999, [6, 7, 16, 18, 37, 41]),
    Draw(998, [22, 23, 30, 41, 46, 47]),
    Draw(997, [5, 6, 10, 15, 36, 42]),
]


# =========================================================
# ANALITYKA
# =========================================================
class LottoAnalyzer:
    def __init__(self, draws: List[Draw]):
        self.draws = sorted(draws, key=lambda d: d.draw_id, reverse=True)
        self.total_draws = len(self.draws)
        self.draw_only = [d.nums for d in self.draws]

        self.freq = self._freq_map(self.draw_only, LOTTO_MIN, LOTTO_MAX)
        self.presence_pct = self._presence_pct(self.draw_only, LOTTO_MIN, LOTTO_MAX)
        self.last_seen = self._last_seen_map(self.draw_only, LOTTO_MIN, LOTTO_MAX)
        self.avg_gaps, self.gap_consistency = self._gap_stats(self.draw_only, LOTTO_MIN, LOTTO_MAX)

        self.pair_counter = self._pair_counter(self.draw_only)
        self.triple_counter = self._triple_counter(self.draw_only)
        self.quad_counter = self._quad_counter(self.draw_only)

        self.target_profile = self._target_profile(self.draw_only, threshold=24)

    def _freq_map(self, draws: List[List[int]], low: int, high: int) -> Dict[int, int]:
        freq = {n: 0 for n in range(low, high + 1)}
        for d in draws:
            for n in d:
                freq[n] += 1
        return freq

    def _presence_pct(self, draws: List[List[int]], low: int, high: int) -> Dict[int, float]:
        total = len(draws)
        if total == 0:
            return {n: 0.0 for n in range(low, high + 1)}

        pct = {}
        for n in range(low, high + 1):
            hits = sum(1 for d in draws if n in d)
            pct[n] = 100.0 * hits / total
        return pct

    def _last_seen_map(self, draws: List[List[int]], low: int, high: int) -> Dict[int, int]:
        out = {}
        for n in range(low, high + 1):
            idx = next((i for i, d in enumerate(draws) if n in d), None)
            out[n] = idx if idx is not None else len(draws) + 10
        return out

    def _gap_stats(self, draws: List[List[int]], low: int, high: int) -> Tuple[Dict[int, float], Dict[int, float]]:
        positions = {n: [] for n in range(low, high + 1)}
        chronological = list(reversed(draws))

        for idx, d in enumerate(chronological):
            for n in d:
                positions[n].append(idx)

        avg_gaps = {}
        consistency = {}

        for n in range(low, high + 1):
            pos = positions[n]
            if len(pos) < 2:
                avg_gaps[n] = 999.0
                consistency[n] = 0.0
                continue

            gaps = [b - a for a, b in zip(pos, pos[1:])]
            avg_gaps[n] = safe_mean(gaps, 999.0)

            try:
                std = statistics.pstdev(gaps) if len(gaps) > 1 else 0.0
                consistency[n] = 1.0 / (1.0 + std)
            except Exception:
                consistency[n] = 0.0

        return avg_gaps, consistency

    def _pair_counter(self, draws: List[List[int]]) -> Dict[Tuple[int, int], int]:
        counter = {}
        for d in draws:
            for pair in combinations(sorted(d), 2):
                counter[pair] = counter.get(pair, 0) + 1
        return counter

    def _triple_counter(self, draws: List[List[int]]) -> Dict[Tuple[int, int, int], int]:
        counter = {}
        for d in draws:
            for tri in combinations(sorted(d), 3):
                counter[tri] = counter.get(tri, 0) + 1
        return counter

    def _quad_counter(self, draws: List[List[int]]) -> Dict[Tuple[int, int, int, int], int]:
        counter = {}
        for d in draws:
            for quad in combinations(sorted(d), 4):
                counter[quad] = counter.get(quad, 0) + 1
        return counter

    def _target_profile(self, draws: List[List[int]], threshold: int) -> Dict:
        if not draws:
            return {
                "target_even": 3,
                "target_spread": 25.0,
                "target_pairs": 0.5,
                "target_sum": 0.0,
            }

        even_counts = []
        spreads = []
        adj_pairs = []
        sums_ = []

        for d in draws:
            s = sorted(d)
            even_counts.append(count_even(s))
            spreads.append(max(s) - min(s))
            adj_pairs.append(count_adjacent_pairs(s))
            sums_.append(sum(s))

        target_even = max(set(even_counts), key=even_counts.count)
        return {
            "target_even": target_even,
            "target_spread": safe_mean(spreads),
            "target_pairs": safe_mean(adj_pairs),
            "target_sum": safe_mean(sums_),
            "threshold": threshold,
        }

    def percent_df(self) -> pd.DataFrame:
        rows = []
        for n in range(LOTTO_MIN, LOTTO_MAX + 1):
            rows.append(
                {
                    "Liczba": n,
                    "Wystąpienia": self.freq[n],
                    "Procent_losowań": round(self.presence_pct[n], 2),
                    "Opóźnienie": self.last_seen[n],
                    "Średnia_przerwa": round(self.avg_gaps[n], 2),
                }
            )

        return pd.DataFrame(rows).sort_values(
            ["Procent_losowań", "Wystąpienia", "Liczba"],
            ascending=[False, False, True],
        ).reset_index(drop=True)


# =========================================================
# SCORING
# =========================================================
class LottoScoringEngine:
    def __init__(self, analyzer: LottoAnalyzer):
        self.a = analyzer
        self.number_component = self._build_number_scores(
            self.a.presence_pct,
            self.a.last_seen,
            self.a.avg_gaps,
            self.a.gap_consistency,
        )

    def _build_number_scores(
        self,
        pct_map: Dict[int, float],
        last_seen_map: Dict[int, int],
        avg_gap_map: Dict[int, float],
        consistency_map: Dict[int, float],
    ) -> Dict[int, float]:
        raw = {}

        for n, pct in pct_map.items():
            hotness = pct
            recency_bonus = max(0.0, 18.0 - abs(last_seen_map[n] - 7))
            rhythm_bonus = consistency_map[n] * 25.0
            avg_gap_bonus = 0.0 if avg_gap_map[n] >= 900 else max(0.0, 12.0 - abs(avg_gap_map[n] - 8))
            raw[n] = hotness + recency_bonus + rhythm_bonus + avg_gap_bonus

        return normalize_score_dict(raw)

    def score_ticket(self, nums: List[int]) -> float:
        nums = sorted(nums)
        base = sum(self.number_component.get(n, 0.1) for n in nums)

        pair_bonus = sum(self.a.pair_counter.get(tuple(sorted(pair)), 0) for pair in combinations(nums, 2)) * 0.02
        triple_bonus = sum(self.a.triple_counter.get(tuple(sorted(tri)), 0) for tri in combinations(nums, 3)) * 0.03
        quad_bonus = sum(self.a.quad_counter.get(tuple(sorted(quad)), 0) for quad in combinations(nums, 4)) * 0.04

        even_target = self.a.target_profile["target_even"]
        even_penalty = abs(count_even(nums) - even_target) * 0.24

        spread = max(nums) - min(nums)
        spread_penalty = abs(spread - self.a.target_profile["target_spread"]) / 85.0

        sum_penalty = abs(sum(nums) - self.a.target_profile["target_sum"]) / 220.0
        seq_penalty = max(0, max_run(nums) - 2) * 0.35

        recent_similarity_penalty = 0.0
        for d in self.a.draw_only[:8]:
            common = len(set(nums) & set(d))
            if common >= 5:
                recent_similarity_penalty += 0.7
            elif common == 6:
                recent_similarity_penalty += 2.0

        structure_bonus = basic_structure_score(nums)

        return (
            base
            + pair_bonus
            + triple_bonus
            + quad_bonus
            + structure_bonus
            - even_penalty
            - spread_penalty
            - sum_penalty
            - seq_penalty
            - recent_similarity_penalty
        )


# =========================================================
# SZLACZEK
# =========================================================
def build_position_paths(draws: List[Draw], count: int = LOTTO_PICK) -> List[List[int]]:
    paths = [[] for _ in range(count)]
    chronological = list(reversed(draws))
    for d in chronological:
        nums = sorted(d.nums)
        for i in range(count):
            paths[i].append(nums[i])
    return paths


def fix_duplicates(nums: List[int], low: int, high: int) -> List[int]:
    seen = set()
    result = []
    for n in nums:
        candidate = n
        while candidate in seen:
            candidate += 1
            if candidate > high:
                candidate = low
        seen.add(candidate)
        result.append(candidate)
    return result


def predict_single_path(
    path: List[int],
    low: int,
    high: int,
    window_short: int = 5,
    window_long: int = 10,
    use_position_range: bool = True,
) -> Tuple[int, Dict]:
    if len(path) < 3:
        pred = clamp(path[-1], low, high)
        return pred, {
            "last_value": path[-1],
            "avg_delta_short": 0.0,
            "avg_delta_long": 0.0,
            "common_delta": 0,
            "bounce": 0,
            "confidence": "LOW",
            "raw": float(pred),
            "final": pred,
        }

    deltas = [path[i] - path[i - 1] for i in range(1, len(path))]
    last_value = path[-1]

    short = deltas[-window_short:] if len(deltas) >= window_short else deltas[:]
    long_ = deltas[-window_long:] if len(deltas) >= window_long else deltas[:]

    avg_short = safe_mean(short)
    avg_long = safe_mean(long_)

    try:
        common_delta = max(set(deltas), key=deltas.count)
    except Exception:
        common_delta = 0

    trend = sum(short)
    bounce = 0
    if trend > 5:
        bounce = -1
    elif trend < -5:
        bounce = 1

    raw = (
        last_value
        + 0.40 * avg_short
        + 0.25 * avg_long
        + 0.20 * common_delta
        + 0.15 * bounce
    )

    predicted = int(round(raw))
    predicted = clamp(predicted, low, high)

    if use_position_range and len(path) >= 8:
        try:
            q = statistics.quantiles(path, n=10, method="inclusive")
            local_low = int(q[1])
            local_high = int(q[-2])
            if local_low <= local_high:
                predicted = clamp(predicted, max(low, local_low), min(high, local_high))
        except Exception:
            pass

    try:
        std = statistics.pstdev(deltas) if len(deltas) > 1 else 999.0
        if std < 2:
            confidence = "HIGH"
        elif std < 5:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
    except Exception:
        confidence = "LOW"

    return predicted, {
        "last_value": last_value,
        "avg_delta_short": round(avg_short, 3),
        "avg_delta_long": round(avg_long, 3),
        "common_delta": common_delta,
        "bounce": bounce,
        "confidence": confidence,
        "raw": round(raw, 3),
        "final": predicted,
    }


def predict_positions(
    paths: List[List[int]],
    low: int,
    high: int,
    window_short: int = 5,
    window_long: int = 10,
    use_position_range: bool = True,
) -> Tuple[List[int], List[Dict]]:
    results = []
    details = []

    for idx, path in enumerate(paths, start=1):
        pred, info = predict_single_path(
            path=path,
            low=low,
            high=high,
            window_short=window_short,
            window_long=window_long,
            use_position_range=use_position_range,
        )
        info["position"] = idx
        results.append(pred)
        details.append(info)

    return results, details


def adjust_distribution(nums: List[int]) -> List[int]:
    nums = sorted(nums)
    if not nums:
        return nums

    evens = count_even(nums)
    if evens == len(nums):
        nums[-1] = clamp(nums[-1] - 1, LOTTO_MIN, LOTTO_MAX)
    elif evens == 0:
        nums[-1] = clamp(nums[-1] + 1, LOTTO_MIN, LOTTO_MAX)

    if max_run(nums) >= 4:
        nums[-1] = clamp(nums[-1] + 2, LOTTO_MIN, LOTTO_MAX)

    nums = sorted(fix_duplicates(nums, LOTTO_MIN, LOTTO_MAX))
    return nums


def predict_from_szlaczek(draws: List[Draw], pro: bool = False) -> Tuple[List[int], List[Dict]]:
    paths = build_position_paths(draws, LOTTO_PICK)
    pred, details = predict_positions(
        paths,
        LOTTO_MIN,
        LOTTO_MAX,
        window_short=5,
        window_long=10,
        use_position_range=pro,
    )
    fixed = sorted(fix_duplicates(pred, LOTTO_MIN, LOTTO_MAX))
    if pro:
        fixed = adjust_distribution(fixed)
    return fixed, details


def build_position_variants(detail: Dict, low: int, high: int) -> List[int]:
    center = int(detail["final"])
    common = int(detail["common_delta"])
    bounce = int(detail["bounce"])

    raw_variants = [
        center,
        center - 1,
        center + 1,
        center + common,
        center + bounce,
    ]

    cleaned = []
    for v in raw_variants:
        v = clamp(v, low, high)
        if v not in cleaned:
            cleaned.append(v)

    return cleaned


def generate_szlaczek_variants(
    draws: List[Draw],
    scorer: "LottoScoringEngine",
    count: int = 5,
    pro: bool = True,
) -> Tuple[List[TicketResult], List[Dict]]:
    _, details = predict_from_szlaczek(draws, pro=pro)

    per_position_variants = []
    for d in details:
        per_position_variants.append(build_position_variants(d, LOTTO_MIN, LOTTO_MAX))

    rng = random.Random()
    candidates: List[TicketResult] = []
    seen = set()

    for _ in range(1200):
        nums = []
        for variants in per_position_variants:
            nums.append(rng.choice(variants))

        nums = sorted(fix_duplicates(nums, LOTTO_MIN, LOTTO_MAX))
        if pro:
            nums = adjust_distribution(nums)

        key = tuple(nums)
        if key in seen:
            continue
        seen.add(key)

        score = scorer.score_ticket(nums)
        candidates.append(
            TicketResult(
                "Szlaczek wariantowy PRO" if pro else "Szlaczek wariantowy",
                nums,
                score,
                "Wariant wygenerowany z kilku prognoz pozycyjnych dla każdej ścieżki szlaczka.",
            )
        )

    candidates.sort(key=lambda x: x.score, reverse=True)

    final = []
    chosen = []
    for c in candidates:
        if is_diverse_enough(c.nums, chosen, max_overlap=3):
            final.append(c)
            chosen.append(c.nums)
        if len(final) >= count:
            break

    return final, details


# =========================================================
# GENERATOR
# =========================================================
class LottoTicketGenerator:
    def __init__(self, analyzer: LottoAnalyzer, scorer: LottoScoringEngine, seed: int = DEFAULT_RANDOM_SEED):
        self.a = analyzer
        self.s = scorer
        self.rng = random.Random(seed)

    def generate_random_ticket(self) -> TicketResult:
        best = None
        best_score = -999999.0

        for _ in range(250):
            nums = sorted(self.rng.sample(list(range(LOTTO_MIN, LOTTO_MAX + 1)), LOTTO_PICK))
            score = self.s.score_ticket(nums)
            if score > best_score:
                best_score = score
                best = nums

        return TicketResult(
            "Losowy",
            best,
            best_score,
            "Losowy zestaw wybrany z wielu kandydatów tak, aby był bardziej różnorodny i miał lepszy układ.",
        )

    def generate_static_random_ticket(self, pool_size: int = 15) -> TicketResult:
        hot_pool = self._top_numbers(self.a.presence_pct, pool_size)

        best = None
        best_score = -999999.0

        for _ in range(250):
            nums = sorted(self.rng.sample(hot_pool, LOTTO_PICK))
            score = self.s.score_ticket(nums)
            if score > best_score:
                best_score = score
                best = nums

        return TicketResult(
            "Losowy statyczny",
            best,
            best_score,
            f"Najlepszy losowy zestaw wybrany z wielu prób, ale tylko z puli TOP {pool_size} liczb o najwyższym procencie wystąpień.",
        )

    def generate_hot_ticket(self, top_n: int = 18) -> TicketResult:
        pool = self._top_numbers(self.a.presence_pct, top_n)

        best = None
        best_score = -999999.0
        for _ in range(180):
            nums = sorted(self.rng.sample(pool, LOTTO_PICK))
            score = self.s.score_ticket(nums)
            if score > best_score:
                best_score = score
                best = nums

        return TicketResult("Hot %", best, best_score, "Zestaw z puli liczb najczęściej występujących procentowo.")

    def generate_cold_ticket(self, bottom_n: int = 18) -> TicketResult:
        pool = self._bottom_numbers(self.a.presence_pct, bottom_n)

        best = None
        best_score = -999999.0
        for _ in range(180):
            nums = sorted(self.rng.sample(pool, LOTTO_PICK))
            score = self.s.score_ticket(nums)
            if score > best_score:
                best_score = score
                best = nums

        return TicketResult("Cold %", best, best_score, "Zestaw z puli liczb najrzadziej występujących procentowo.")

    def generate_hybrid_ticket(self, hot_n: int = 2, cold_n: int = 2) -> TicketResult:
        hot_pool = self._top_numbers(self.a.presence_pct, 18)
        cold_pool = self._bottom_numbers(self.a.presence_pct, 18)
        neutral = [n for n in range(LOTTO_MIN, LOTTO_MAX + 1) if n not in hot_pool and n not in cold_pool]

        best = None
        best_score = -999999.0

        for _ in range(220):
            nums = []
            nums.extend(self.rng.sample(hot_pool, hot_n))
            nums.extend(self.rng.sample([n for n in cold_pool if n not in nums], cold_n))
            nums.extend(self.rng.sample([n for n in neutral if n not in nums], LOTTO_PICK - len(nums)))
            nums = sorted(nums)

            score = self.s.score_ticket(nums)
            if score > best_score:
                best_score = score
                best = nums

        return TicketResult("50/50", best, best_score, "Mieszanka hot, cold i neutral dla zbalansowanego kuponu.")

    def generate_hot_max_ticket(self) -> TicketResult:
        nums = sorted(self._top_numbers(self.a.presence_pct, LOTTO_PICK))
        score = self.s.score_ticket(nums)
        return TicketResult("HOT MAX", nums, score, "Sztywny zestaw z 6 najmocniejszych liczb procentowo.")

    def generate_golden_ticket(self) -> TicketResult:
        population = list(range(LOTTO_MIN, LOTTO_MAX + 1))
        weights = [self.s.number_component[n] for n in population]

        best_ticket = None
        best_score = -999999.0
        for _ in range(500):
            nums = weighted_sample_without_replacement(population, weights, LOTTO_PICK, self.rng)
            score = self.s.score_ticket(nums)
            if score > best_score:
                best_score = score
                best_ticket = nums

        return TicketResult(
            "Złoty Strzał",
            best_ticket,
            best_score,
            "Najmocniejszy kupon znaleziony z wykorzystaniem score częstotliwości, rytmu, opóźnienia i zgodności układu.",
        )

    def generate_probability_ranking(self, candidates: int = DEFAULT_CANDIDATES, top_n: int = 10) -> List[TicketResult]:
        results: List[TicketResult] = []
        seen = set()

        population = list(range(LOTTO_MIN, LOTTO_MAX + 1))
        weights = [self.s.number_component[n] for n in population]

        for _ in range(candidates):
            nums = tuple(weighted_sample_without_replacement(population, weights, LOTTO_PICK, self.rng))
            if nums in seen:
                continue
            seen.add(nums)

            score = self.s.score_ticket(list(nums))
            results.append(
                TicketResult(
                    "Ranking prawdopodobieństwa",
                    list(nums),
                    score,
                    "Kupon rankingowy z dużej puli kandydatów ocenionych przez silnik scoringu.",
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)

        final = []
        chosen = []
        for r in results:
            if is_diverse_enough(r.nums, chosen, max_overlap=3):
                final.append(r)
                chosen.append(r.nums)
            if len(final) >= top_n:
                break

        return final

    def generate_szlaczek_ticket(self, pro: bool = False) -> Tuple[TicketResult, List[Dict]]:
        nums, details = predict_from_szlaczek(self.a.draws, pro=pro)
        score = self.s.score_ticket(nums)
        mode = "Szlaczek PRO" if pro else "Szlaczek"
        note = (
            "Prognoza pozycyjna na bazie trajektorii każdej pozycji osobno + korekta rozkładu."
            if pro
            else "Prognoza pozycyjna na bazie trajektorii każdej pozycji osobno."
        )
        return TicketResult(mode, nums, score, note), details

    def generate_szlaczek_multi(self, count: int = 5, pro: bool = True) -> Tuple[List[TicketResult], List[Dict]]:
        return generate_szlaczek_variants(self.a.draws, self.s, count=count, pro=pro)

    def _top_numbers(self, pct_map: Dict[int, float], k: int) -> List[int]:
        return [n for n, _ in sorted(pct_map.items(), key=lambda x: (-x[1], x[0]))[:k]]

    def _bottom_numbers(self, pct_map: Dict[int, float], k: int) -> List[int]:
        return [n for n, _ in sorted(pct_map.items(), key=lambda x: (x[1], x[0]))[:k]]


# =========================================================
# RENDER
# =========================================================
def render_ticket(ticket: TicketResult, highlight: bool = False) -> None:
    css = "ticket-card-gold" if highlight else "ticket-card"
    st.markdown(
        f"""
        <div class="{css}">
          <div class="ticket-title">{ticket.mode}</div>
          <div class="ticket-main">{fmt_nums(ticket.nums)}</div>
          <div class="ticket-meta">
            <b>Score:</b> {ticket.score:.4f}<br>
            <b>Opis:</b> {ticket.note}<br>
            <b>Parzyste:</b> {count_even(ticket.nums)}/{len(ticket.nums)-count_even(ticket.nums)} |
            <b>Pary kolejne:</b> {count_adjacent_pairs(ticket.nums)} |
            <b>Maks. ciąg:</b> {max_run(ticket.nums)} |
            <b>Suma:</b> {sum(ticket.nums)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pattern_details(details: List[Dict]) -> None:
    rows = []
    for d in details:
        rows.append(
            {
                "Pozycja": d["position"],
                "Ostatnia wartość": d["last_value"],
                "Śr. delta 5": d["avg_delta_short"],
                "Śr. delta 10": d["avg_delta_long"],
                "Najczęstsza delta": d["common_delta"],
                "Bounce": d["bounce"],
                "Pewność": d["confidence"],
                "Prognoza surowa": d["raw"],
                "Prognoza końcowa": d["final"],
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def ticket_list_to_txt(tickets: List[TicketResult]) -> str:
    lines = []
    for i, t in enumerate(tickets, start=1):
        lines.append(f"#{i:03d} | {t.mode}")
        lines.append(f"Liczby: {fmt_nums(t.nums)}")
        lines.append(f"Score: {t.score:.4f}")
        lines.append(f"Opis: {t.note}")
        lines.append("")
    return "\n".join(lines)


def render_help_tab() -> None:
    st.header("📚 Opis funkcji i przykłady użycia")

    help_items = [
        (
            "🎲 Losowy",
            "Generuje wiele losowych kandydatów i wybiera taki, który ma lepszy układ. Dzięki temu kupon jest nadal losowy, ale sensowniejszy.",
            "Przykład najlepszego użycia: gdy chcesz czysty los, ale nie chcesz dziwnych układów."
        ),
        (
            "🎯 Losowy statyczny",
            "Buduje stałą pulę TOP liczb z największym procentem wystąpień i z niej losuje wiele kandydatów, wybierając lepszy.",
            "Przykład najlepszego użycia: gdy chcesz różne kupony, ale tylko z najsilniejszych historycznie liczb."
        ),
        (
            "🔥 Hot %",
            "Buduje zestaw z puli gorących liczb i wybiera lepszy wariant.",
            "Przykład najlepszego użycia: gdy chcesz grać liczbami gorącymi, ale nie zawsze tym samym układem."
        ),
        (
            "❄️ Cold %",
            "Buduje zestaw z puli zimnych liczb i wybiera lepszy wariant.",
            "Przykład najlepszego użycia: gdy chcesz szukać mniej oczywistych kombinacji."
        ),
        (
            "⚖️ 50/50",
            "Miesza pule hot, cold i neutral, a potem wybiera lepszy kandydat.",
            "Przykład najlepszego użycia: gdy chcesz balansu i różnorodności."
        ),
        (
            "📌 HOT MAX",
            "Sztywny zestaw z 6 najmocniejszych liczb procentowo.",
            "Przykład najlepszego użycia: gdy chcesz najprostszy wariant oparty o top liczby."
        ),
        (
            "🏆 Złoty Strzał",
            "Najmocniejszy kupon znaleziony z dużej puli kandydatów.",
            "Przykład najlepszego użycia: gdy chcesz jeden najlepszy kupon."
        ),
        (
            "📈 Ranking TOP 10",
            "Pokazuje 10 najlepszych i jednocześnie dość różnych kuponów.",
            "Przykład najlepszego użycia: gdy chcesz kilka propozycji do wyboru."
        ),
        (
            "🧠 Szlaczek",
            "Jedna prognoza pozycyjna oparta o ruch każdej pozycji osobno.",
            "Przykład najlepszego użycia: gdy chcesz jeden klasyczny kupon szlaczkowy."
        ),
        (
            "🚀 Szlaczek PRO",
            "Szlaczek z korektą rozkładu i zakresów pozycji.",
            "Przykład najlepszego użycia: gdy chcesz bardziej naturalny układ końcowy."
        ),
        (
            "🧠 Szlaczek TOP 5",
            "Tworzy kilka wariantów dla każdej pozycji i składa z nich różne kupony.",
            "Przykład najlepszego użycia: gdy chcesz kilka różnych kuponów opartych o szlaczek."
        ),
        (
            "🚀 Szlaczek PRO TOP 5",
            "Jak wyżej, ale z korektą układu i większym naciskiem na sensowną strukturę.",
            "Przykład najlepszego użycia: gdy chcesz różne kupony szlaczkowe, ale bardziej dopracowane."
        ),
    ]

    for title, desc, ex in help_items:
        with st.expander(title):
            st.write(desc)
            st.markdown(f"**Przykład najlepszego użycia:** {ex}")


# =========================================================
# GŁÓWNA APLIKACJA
# =========================================================
def main():
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    if "generated_tickets" not in st.session_state:
        st.session_state.generated_tickets = []

    with st.sidebar:
        st.markdown("## ⚙️ Ustawienia")

        data_mode = st.radio("Źródło danych", ["Tryb bez PDF", "Tryb z PDF"], index=0)

        uploaded_pdf = None
        if data_mode == "Tryb z PDF":
            uploaded_pdf = st.file_uploader("Wgraj PDF Lotto 6/49", type=["pdf"])

        history_window = st.selectbox("Zakres historii do analizy", [50, 100, 250, 500, 999], index=4)

        ranking_candidates = st.slider(
            "Ile kandydatów dla rankingu i złotego strzału",
            min_value=300,
            max_value=10000,
            value=3000,
            step=100,
        )

        static_pool_size = st.selectbox("Pula dla trybu Losowy statyczny", [10, 12, 15, 18, 20], index=2)

        seed = st.number_input("Seed losowania", min_value=1, max_value=999999, value=DEFAULT_RANDOM_SEED)
        txt_filename = st.text_input("Nazwa pliku TXT do eksportu", value="lotto_kupony.txt")

    draws: List[Draw] = []
    diagnostics = {}

    try:
        if data_mode == "Tryb z PDF":
            if uploaded_pdf is None:
                st.info("Wgraj plik PDF Lotto 6/49, aby uruchomić pełną analizę.")
                draws = DEFAULT_DRAWS[:]
                diagnostics = {
                    "draws_found": len(draws),
                    "latest_draw_id": draws[0].draw_id,
                    "oldest_draw_id": draws[-1].draw_id,
                    "mode": "fallback_demo",
                }
            else:
                pdf_bytes = uploaded_pdf.read()
                draws, diagnostics = load_draws_from_pdf_bytes(pdf_bytes)
        else:
            draws = DEFAULT_DRAWS[:]
            diagnostics = {
                "draws_found": len(draws),
                "latest_draw_id": draws[0].draw_id,
                "oldest_draw_id": draws[-1].draw_id,
                "mode": "demo",
            }
    except Exception as e:
        st.error(f"Błąd wczytywania danych: {e}")
        draws = DEFAULT_DRAWS[:]
        diagnostics = {
            "draws_found": len(draws),
            "latest_draw_id": draws[0].draw_id,
            "oldest_draw_id": draws[-1].draw_id,
            "mode": "fallback_error",
        }

    draws = draws[: min(history_window, len(draws))]

    analyzer = LottoAnalyzer(draws)
    scorer = LottoScoringEngine(analyzer)
    generator = LottoTicketGenerator(analyzer, scorer, seed=int(seed))

    tab1, tab2, tab3, tab4 = st.tabs(["🚀 Generator", "📊 Analiza", "🧠 Szlaczek", "📚 Opisy funkcji"])

    with tab1:
        c1, c2, c3 = st.columns(3)

        with c1:
            if st.button("🎲 Generuj: Losowy"):
                t = generator.generate_random_ticket()
                st.session_state.generated_tickets = [t]

            if st.button("🎯 Generuj: Losowy statyczny"):
                t = generator.generate_static_random_ticket(pool_size=int(static_pool_size))
                st.session_state.generated_tickets = [t]

            if st.button("🔥 Generuj: Hot %"):
                t = generator.generate_hot_ticket()
                st.session_state.generated_tickets = [t]

            if st.button("❄️ Generuj: Cold %"):
                t = generator.generate_cold_ticket()
                st.session_state.generated_tickets = [t]

        with c2:
            if st.button("⚖️ Generuj: 50/50"):
                t = generator.generate_hybrid_ticket()
                st.session_state.generated_tickets = [t]

            if st.button("📌 Generuj: HOT MAX"):
                t = generator.generate_hot_max_ticket()
                st.session_state.generated_tickets = [t]

            if st.button("🏆 Generuj: Złoty Strzał"):
                results = generator.generate_probability_ranking(candidates=ranking_candidates, top_n=1)
                best = results[0]
                best.mode = "Złoty Strzał"
                best.note = "Najmocniejszy kupon wybrany spośród dużej puli kandydatów ocenionych scoringiem."
                st.session_state.generated_tickets = [best]

            if st.button("📈 Generuj: Ranking TOP 10"):
                results = generator.generate_probability_ranking(candidates=ranking_candidates, top_n=10)
                st.session_state.generated_tickets = results

        with c3:
            if st.button("🧠 Generuj: Szlaczek"):
                t, _ = generator.generate_szlaczek_ticket(pro=False)
                st.session_state.generated_tickets = [t]

            if st.button("🚀 Generuj: Szlaczek PRO"):
                t, _ = generator.generate_szlaczek_ticket(pro=True)
                st.session_state.generated_tickets = [t]

            if st.button("🧠 Generuj: Szlaczek TOP 5"):
                tickets, _ = generator.generate_szlaczek_multi(count=5, pro=False)
                st.session_state.generated_tickets = tickets

            if st.button("🚀 Generuj: Szlaczek PRO TOP 5"):
                tickets, _ = generator.generate_szlaczek_multi(count=5, pro=True)
                st.session_state.generated_tickets = tickets

            if st.button("🧹 Wyczyść wyniki"):
                st.session_state.generated_tickets = []

        st.markdown("---")
        st.markdown("### Wyniki")

        if st.session_state.generated_tickets:
            for idx, ticket in enumerate(st.session_state.generated_tickets):
                render_ticket(ticket, highlight=(idx == 0 and "Złoty Strzał" in ticket.mode))

            txt_content = ticket_list_to_txt(st.session_state.generated_tickets)
            st.download_button(
                "💾 Pobierz wyniki jako TXT",
                data=txt_content.encode("utf-8"),
                file_name=sanitize_txt_filename(txt_filename),
                mime="text/plain",
            )
        else:
            st.info("Wybierz jedną z funkcji generatora, aby zobaczyć kupony.")

        st.markdown("---")
        st.markdown("### Informacje o danych")
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Liczba losowań", diagnostics.get("draws_found", len(draws)))
        col_b.metric("Najnowsze ID", diagnostics.get("latest_draw_id", "—"))
        col_c.metric("Najstarsze ID", diagnostics.get("oldest_draw_id", "—"))
        col_d.metric("Tryb", data_mode)

    with tab2:
        st.markdown("### Top liczby Lotto 6/49")
        st.dataframe(analyzer.percent_df().head(20), use_container_width=True, hide_index=True)

        st.markdown("### Wykres obecności %")
        chart_df = analyzer.percent_df().sort_values("Liczba")
        st.line_chart(chart_df.set_index("Liczba")["Procent_losowań"])

        st.markdown("### Ostatnie losowania")
        rows = []
        for d in draws[:15]:
            rows.append(
                {
                    "ID": d.draw_id,
                    "Liczby": fmt_nums(d.nums),
                    "Suma": sum(d.nums),
                    "Parzyste": count_even(d.nums),
                    "Pary kolejne": count_adjacent_pairs(d.nums),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with tab3:
        st.markdown("### Moduł szlaczka")
        st.caption("Każda pozycja jest analizowana osobno: 1→1, 2→2, 3→3, 4→4, 5→5, 6→6.")

        szl_simple, _ = generator.generate_szlaczek_ticket(pro=False)
        szl_pro, details_pro = generator.generate_szlaczek_ticket(pro=True)

        st.markdown("#### Wynik Szlaczek")
        render_ticket(szl_simple)

        st.markdown("#### Wynik Szlaczek PRO")
        render_ticket(szl_pro, highlight=True)

        st.markdown("### Szczegóły prognozy pozycyjnej")
        render_pattern_details(details_pro)

        st.markdown("### Wizualizacja ścieżek pozycji")
        paths = build_position_paths(draws, LOTTO_PICK)
        df_paths = pd.DataFrame({f"Poz {i+1}": path for i, path in enumerate(paths)})
        st.line_chart(df_paths)

        with st.expander("Jak najlepiej używać funkcji Szlaczek?"):
            st.write(
                "Najlepiej używać jej wtedy, gdy chcesz typować zestaw na podstawie trajektorii pozycji. "
                "Wersje TOP 5 są lepsze, jeśli chcesz kilka różnych propozycji zamiast jednego sztywnego wyniku."
            )

    with tab4:
        render_help_tab()


if __name__ == "__main__":
    main()
