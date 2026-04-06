import random
import re
from dataclasses import dataclass
from itertools import combinations
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st


# =========================================================
# KONFIGURACJA
# =========================================================
APP_TITLE = "🎯 Lotto ULTRA PRO MAX 6/49"
APP_SUBTITLE = "PDF Analyzer + Comeback Cycle + Bystrzacha 2.0 + Tournament Scoring + Diversity Selector"

MIN_N = 1
MAX_N = 49
DRAW_LEN = 6
DEFAULT_PDF_NAME = "https___www.multipasko.pl_mapy.PDF"

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🎯",
    layout="wide",
)


# =========================================================
# MODELE DANYCH
# =========================================================
@dataclass
class DrawRecord:
    draw_no: Optional[int]
    numbers: List[int]


# =========================================================
# PODSTAWY
# =========================================================
def normalize_draw(nums: List[int]) -> List[int]:
    return sorted(nums)


def valid_draw(nums: List[int]) -> bool:
    return (
        len(nums) == DRAW_LEN
        and len(set(nums)) == DRAW_LEN
        and all(MIN_N <= n <= MAX_N for n in nums)
    )


def odd_even_balance(ticket: List[int]) -> Tuple[int, int]:
    odd = sum(1 for x in ticket if x % 2 == 1)
    even = len(ticket) - odd
    return odd, even


def range_split(ticket: List[int]) -> Tuple[int, int, int]:
    low = sum(1 for x in ticket if 1 <= x <= 16)
    mid = sum(1 for x in ticket if 17 <= x <= 33)
    high = sum(1 for x in ticket if 34 <= x <= 49)
    return low, mid, high


def consecutive_run_length(ticket: List[int]) -> int:
    nums = sorted(ticket)
    longest = 1
    current = 1
    for i in range(1, len(nums)):
        if nums[i] == nums[i - 1] + 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def ticket_span(ticket: List[int]) -> int:
    nums = sorted(ticket)
    return nums[-1] - nums[0]


def ticket_sum(ticket: List[int]) -> int:
    return sum(ticket)


def overlap_size(a: List[int], b: List[int]) -> int:
    return len(set(a) & set(b))


def ticket_distance(a: List[int], b: List[int]) -> int:
    return len(set(a) ^ set(b))


# =========================================================
# PARSER PDF - WERSJA ODPORNA NA STREAMLIT CLOUD
# =========================================================
def extract_rows_from_pdf_words(pdf_bytes: bytes) -> List[List[str]]:
    """
    Odporny parser:
    - pobiera słowa z pozycjami,
    - grupuje po współrzędnej Y,
    - sortuje po X.
    Dzięki temu działa stabilniej niż zwykłe get_text("text").
    """
    rows: List[List[str]] = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            words = page.get_text("words")
            # Format:
            # (x0, y0, x1, y1, "text", block_no, line_no, word_no)

            if not words:
                continue

            grouped: Dict[float, List[Tuple[float, str]]] = {}

            for word in words:
                x0, y0, x1, y1, text, *_ = word
                text = str(text).strip()

                if not text:
                    continue

                # Grupowanie po przybliżonym Y
                y_key = round(float(y0), 1)
                grouped.setdefault(y_key, []).append((float(x0), text))

            for y_key in sorted(grouped.keys()):
                row = grouped[y_key]
                row.sort(key=lambda item: item[0])
                tokens = [token for _, token in row]
                rows.append(tokens)

    return rows


def parse_lotto_pdf_bytes(pdf_bytes: bytes) -> List[DrawRecord]:
    """
    Parser ULTRA-ROBUST:
    - wykrywa wiersze z 6 liczbami Lotto,
    - wykrywa osobne numery losowań 4-5 cyfrowe,
    - obsługuje też wiersze mieszane.
    """
    rows = extract_rows_from_pdf_words(pdf_bytes)

    draw_rows: List[List[int]] = []
    draw_numbers: List[int] = []

    for tokens in rows:
        cleaned = []
        for t in tokens:
            t = t.replace("\xa0", " ").strip()
            if t:
                cleaned.append(t)

        if not cleaned:
            continue

        joined = " ".join(cleaned).lower()

        # Pomijamy nagłówki
        if "lotto" in joined:
            continue

        # Wyciągnij tokeny numeryczne
        numeric_tokens: List[int] = []
        for t in cleaned:
            if re.fullmatch(r"\d{1,5}", t):
                numeric_tokens.append(int(t))

        if not numeric_tokens:
            continue

        # Przypadek 1: dokładnie 6 liczb Lotto
        if len(numeric_tokens) == 6 and all(MIN_N <= x <= MAX_N for x in numeric_tokens):
            nums = normalize_draw(numeric_tokens)
            if valid_draw(nums):
                draw_rows.append(nums)
            continue

        # Przypadek 2: pojedynczy numer losowania
        if len(numeric_tokens) == 1 and 1000 <= numeric_tokens[0] <= 99999:
            draw_numbers.append(numeric_tokens[0])
            continue

        # Przypadek 3: mieszany wiersz
        small = [x for x in numeric_tokens if MIN_N <= x <= MAX_N]
        big = [x for x in numeric_tokens if x > MAX_N]

        if len(small) == 6:
            nums = normalize_draw(small)
            if valid_draw(nums):
                draw_rows.append(nums)

        if len(big) == 1 and 1000 <= big[0] <= 99999:
            draw_numbers.append(big[0])

    # Łączenie liczb z numerami losowań
    records: List[DrawRecord] = []
    common = min(len(draw_rows), len(draw_numbers))

    for i in range(common):
        records.append(DrawRecord(draw_no=draw_numbers[i], numbers=draw_rows[i]))

    for i in range(common, len(draw_rows)):
        records.append(DrawRecord(draw_no=None, numbers=draw_rows[i]))

    # Deduplikacja po samych liczbach
    unique_records: List[DrawRecord] = []
    seen = set()

    for rec in records:
        key = tuple(rec.numbers)
        if key not in seen:
            unique_records.append(rec)
            seen.add(key)

    return unique_records


def get_draws(records: List[DrawRecord]) -> List[List[int]]:
    return [r.numbers for r in records if valid_draw(r.numbers)]


# =========================================================
# ANALIZA CZĘSTOTLIWOŚCI
# =========================================================
def frequency(draws: List[List[int]]) -> Counter:
    c = Counter()
    for d in draws:
        c.update(d)
    return c


def rolling_frequency(draws: List[List[int]], window: int) -> Counter:
    return frequency(draws[:window])


def last_seen_index(draws: List[List[int]]) -> Dict[int, int]:
    result = {n: 10**9 for n in range(MIN_N, MAX_N + 1)}
    for idx, draw in enumerate(draws):
        for n in draw:
            if result[n] == 10**9:
                result[n] = idx
    return result


def hot_and_cold_lists(draws: List[List[int]], top_n: int = 10) -> Tuple[List[int], List[int]]:
    freq_all = frequency(draws)
    seen = last_seen_index(draws)

    hot = sorted(
        range(MIN_N, MAX_N + 1),
        key=lambda x: (freq_all[x], -x),
        reverse=True
    )[:top_n]

    cold = sorted(
        range(MIN_N, MAX_N + 1),
        key=lambda x: (seen[x], -freq_all[x]),
        reverse=True
    )[:top_n]

    return hot, cold


# =========================================================
# COME BACK CYCLE ENGINE
# =========================================================
def build_occurrence_positions(draws: List[List[int]]) -> Dict[int, List[int]]:
    positions = defaultdict(list)
    for idx, draw in enumerate(draws):
        for n in draw:
            positions[n].append(idx)
    return positions


def build_gap_history(draws: List[List[int]]) -> Dict[int, List[int]]:
    positions = build_occurrence_positions(draws)
    gaps = defaultdict(list)

    for n in range(MIN_N, MAX_N + 1):
        pos = positions.get(n, [])
        if len(pos) < 2:
            continue

        for i in range(len(pos) - 1):
            gap = pos[i + 1] - pos[i]
            gaps[n].append(gap)

    return gaps


def comeback_cycle_score(number: int, draws: List[List[int]]) -> float:
    gaps = build_gap_history(draws)
    last_seen = last_seen_index(draws)

    current_gap = last_seen[number]
    gap_list = gaps.get(number, [])

    if not gap_list:
        if 8 <= current_gap <= 28:
            return 0.75
        if 5 <= current_gap <= 35:
            return 0.55
        return 0.30

    avg_gap = sum(gap_list) / len(gap_list)
    gap_min = min(gap_list)
    gap_max = max(gap_list)

    distance = abs(current_gap - avg_gap)
    normalized_distance = distance / max(1.0, avg_gap)

    if normalized_distance <= 0.15:
        base = 1.00
    elif normalized_distance <= 0.30:
        base = 0.82
    elif normalized_distance <= 0.50:
        base = 0.62
    else:
        base = 0.35

    if gap_min <= current_gap <= gap_max:
        base += 0.08

    return min(base, 1.0)


def all_comeback_scores(draws: List[List[int]]) -> Dict[int, float]:
    return {n: comeback_cycle_score(n, draws) for n in range(MIN_N, MAX_N + 1)}


# =========================================================
# BYSTRZACHA 2.0
# =========================================================
def positional_frequency(draws: List[List[int]]) -> Dict[int, Counter]:
    pos = {i: Counter() for i in range(DRAW_LEN)}
    for d in draws:
        s = sorted(d)
        for i, n in enumerate(s):
            pos[i][n] += 1
    return pos


def positional_deltas(draws: List[List[int]]) -> Dict[int, Counter]:
    delta_map = {i: Counter() for i in range(DRAW_LEN)}
    sorted_draws = [sorted(d) for d in draws]

    for i in range(len(sorted_draws) - 1):
        now = sorted_draws[i]
        nxt = sorted_draws[i + 1]
        for p in range(DRAW_LEN):
            delta = now[p] - nxt[p]
            delta_map[p][delta] += 1

    return delta_map


def positional_deltas_window(draws: List[List[int]], window: int) -> Dict[int, Counter]:
    subset = draws[:window]
    if len(subset) < 2:
        return {i: Counter() for i in range(DRAW_LEN)}
    return positional_deltas(subset)


def predict_positional_ticket_v2(draws: List[List[int]]) -> List[int]:
    if not draws:
        return []

    last_draw = sorted(draws[0])
    d25 = positional_deltas_window(draws, min(25, len(draws)))
    d50 = positional_deltas_window(draws, min(50, len(draws)))
    d100 = positional_deltas_window(draws, min(100, len(draws)))

    predicted = []

    for pos in range(DRAW_LEN):
        candidate_scores = defaultdict(float)

        for delta, count in d25[pos].most_common(5):
            candidate_scores[delta] += count * 0.45

        for delta, count in d50[pos].most_common(5):
            candidate_scores[delta] += count * 0.35

        for delta, count in d100[pos].most_common(5):
            candidate_scores[delta] += count * 0.20

        if not candidate_scores:
            best_delta = 0
        else:
            best_delta = max(candidate_scores.items(), key=lambda x: x[1])[0]

        value = last_draw[pos] + best_delta
        value = max(MIN_N, min(MAX_N, value))
        predicted.append(value)

    predicted = sorted(predicted)

    fixed = []
    used = set()
    for x in predicted:
        while x in used and x <= MAX_N:
            x += 1
        if x > MAX_N:
            x = MIN_N
            while x in used:
                x += 1
        fixed.append(x)
        used.add(x)

    return sorted(fixed)


def positional_trend_score(ticket: List[int], draws: List[List[int]]) -> float:
    pos_freq = positional_frequency(draws)
    ticket_sorted = sorted(ticket)
    vals = []

    for i, n in enumerate(ticket_sorted):
        count = pos_freq[i][n]
        denom = max(1, sum(pos_freq[i].values()))
        vals.append(count / denom)

    return sum(vals) / len(vals)


# =========================================================
# PARY I TRÓJKI
# =========================================================
def strongest_pairs(draws: List[List[int]]) -> Counter:
    c = Counter()
    for d in draws:
        for pair in combinations(sorted(d), 2):
            c[pair] += 1
    return c


def strongest_triplets(draws: List[List[int]]) -> Counter:
    c = Counter()
    for d in draws:
        for tri in combinations(sorted(d), 3):
            c[tri] += 1
    return c


def strongest_pairs_window(draws: List[List[int]], window: int) -> Counter:
    return strongest_pairs(draws[:window])


def strongest_triplets_window(draws: List[List[int]], window: int) -> Counter:
    return strongest_triplets(draws[:window])


def pair_strength_score(ticket: List[int], draws: List[List[int]]) -> float:
    all_pairs = strongest_pairs(draws)
    recent_pairs = strongest_pairs_window(draws, min(50, len(draws)))

    vals = []
    for p in combinations(sorted(ticket), 2):
        vals.append((all_pairs[p] * 0.55) + (recent_pairs[p] * 0.45))

    if not vals:
        return 0.0

    max_reference = max(all_pairs.values()) if all_pairs else 1
    return (sum(vals) / len(vals)) / max(1, max_reference)


def triplet_strength_score(ticket: List[int], draws: List[List[int]]) -> float:
    all_tr = strongest_triplets(draws)
    recent_tr = strongest_triplets_window(draws, min(100, len(draws)))

    vals = []
    for t in combinations(sorted(ticket), 3):
        vals.append((all_tr[t] * 0.60) + (recent_tr[t] * 0.40))

    if not vals:
        return 0.0

    max_reference = max(all_tr.values()) if all_tr else 1
    return (sum(vals) / len(vals)) / max(1, max_reference)


# =========================================================
# NUMBER SCORE
# =========================================================
def number_scores(draws: List[List[int]]) -> Dict[int, float]:
    total = len(draws)

    freq_12 = rolling_frequency(draws, min(12, total))
    freq_25 = rolling_frequency(draws, min(25, total))
    freq_50 = rolling_frequency(draws, min(50, total))
    freq_100 = rolling_frequency(draws, min(100, total))
    freq_250 = rolling_frequency(draws, min(250, total))
    freq_all = frequency(draws)

    comeback_scores = all_comeback_scores(draws)

    result = {}
    for n in range(MIN_N, MAX_N + 1):
        s12 = freq_12[n] / max(1, min(12, total))
        s25 = freq_25[n] / max(1, min(25, total))
        s50 = freq_50[n] / max(1, min(50, total))
        s100 = freq_100[n] / max(1, min(100, total))
        s250 = freq_250[n] / max(1, min(250, total))
        sall = freq_all[n] / max(1, total)
        comeback = comeback_scores[n]

        result[n] = (
            0.10 * s12 +
            0.14 * s25 +
            0.18 * s50 +
            0.16 * s100 +
            0.12 * s250 +
            0.15 * sall +
            0.15 * comeback
        )

    return result


# =========================================================
# FILTRY STRUKTURALNE
# =========================================================
def odd_even_score(ticket: List[int]) -> float:
    odd, even = odd_even_balance(ticket)
    if (odd, even) == (3, 3):
        return 1.0
    if (odd, even) in {(2, 4), (4, 2)}:
        return 0.82
    return 0.35


def range_score(ticket: List[int]) -> float:
    low, mid, high = range_split(ticket)
    non_zero = sum(1 for x in [low, mid, high] if x > 0)

    if non_zero == 3:
        if 1 <= low <= 3 and 1 <= mid <= 3 and 1 <= high <= 3:
            return 1.0
        return 0.85

    if non_zero == 2:
        return 0.45

    return 0.12


def span_score(ticket: List[int]) -> float:
    span = ticket_span(ticket)
    if 22 <= span <= 42:
        return 1.0
    if 18 <= span <= 45:
        return 0.75
    return 0.22


def sum_score(ticket: List[int]) -> float:
    s = ticket_sum(ticket)
    if 90 <= s <= 180:
        return 1.0
    if 75 <= s <= 200:
        return 0.72
    return 0.25


def consecutive_penalty(ticket: List[int]) -> float:
    longest = consecutive_run_length(ticket)
    if longest >= 4:
        return -1.0
    if longest == 3:
        return -0.35
    return 0.0


def repeat_penalty(ticket: List[int], last_draw: List[int]) -> float:
    overlap = overlap_size(ticket, last_draw)
    if overlap >= 4:
        return -0.90
    if overlap == 3:
        return -0.35
    return 0.0


def ticket_balance_score(ticket: List[int], last_draw: Optional[List[int]] = None) -> float:
    score = (
        0.28 * odd_even_score(ticket) +
        0.25 * range_score(ticket) +
        0.20 * span_score(ticket) +
        0.22 * sum_score(ticket) +
        0.05 * (1.0 + consecutive_penalty(ticket))
    )

    if last_draw is not None:
        score += 0.05 * (1.0 + repeat_penalty(ticket, last_draw))

    return score


def ticket_passes_hard_filters(ticket: List[int], last_draw: List[int]) -> bool:
    if not valid_draw(ticket):
        return False

    odd, even = odd_even_balance(ticket)
    if (odd, even) not in {(3, 3), (2, 4), (4, 2)}:
        return False

    low, mid, high = range_split(ticket)
    if sum(1 for x in [low, mid, high] if x > 0) < 3:
        return False

    if consecutive_run_length(ticket) >= 4:
        return False

    if ticket_span(ticket) < 18:
        return False

    if not (75 <= ticket_sum(ticket) <= 200):
        return False

    if overlap_size(ticket, last_draw) >= 4:
        return False

    return True


# =========================================================
# GENEROWANIE KANDYDATÓW
# =========================================================
def weighted_pick_unique(pool: List[int], weights: Dict[int, float], k: int) -> List[int]:
    left = pool[:]
    out = []

    for _ in range(k):
        w = [max(weights[x], 1e-9) for x in left]
        pick = random.choices(left, weights=w, k=1)[0]
        out.append(pick)
        left.remove(pick)

    return sorted(out)


def build_candidate_ticket(draws: List[List[int]], mode: str = "hybrid") -> List[int]:
    scores = number_scores(draws)
    seen = last_seen_index(draws)
    byst = predict_positional_ticket_v2(draws)

    ranked = sorted(range(MIN_N, MAX_N + 1), key=lambda x: scores[x], reverse=True)

    hot = ranked[:15]
    mid = ranked[15:34]
    cold = sorted(range(MIN_N, MAX_N + 1), key=lambda x: seen[x], reverse=True)[:15]

    if mode == "hybrid":
        ticket = []
        ticket += random.sample(hot, 2)
        ticket += random.sample([x for x in mid if x not in ticket], 2)
        ticket += random.sample([x for x in cold if x not in ticket], 2)
        return sorted(ticket)

    if mode == "momentum":
        recent = ranked[:22]
        return sorted(random.sample(recent, 6))

    if mode == "comeback":
        comeback_sorted = sorted(
            range(MIN_N, MAX_N + 1),
            key=lambda x: (comeback_cycle_score(x, draws), scores[x]),
            reverse=True
        )[:20]
        return sorted(random.sample(comeback_sorted, 6))

    if mode == "bystrzacha":
        base = byst[:]
        while len(base) < 6:
            x = random.randint(MIN_N, MAX_N)
            if x not in base:
                base.append(x)
        return sorted(base[:6])

    if mode == "hot":
        return sorted(random.sample(hot, 6))

    if mode == "cold":
        return sorted(random.sample(cold, 6))

    if mode == "weighted":
        return weighted_pick_unique(list(range(MIN_N, MAX_N + 1)), scores, 6)

    if mode == "random":
        return sorted(random.sample(range(MIN_N, MAX_N + 1), 6))

    return weighted_pick_unique(list(range(MIN_N, MAX_N + 1)), scores, 6)


def mutate_ticket(ticket: List[int], intensity: int = 1) -> List[int]:
    t = ticket[:]
    for _ in range(intensity):
        idx = random.randint(0, DRAW_LEN - 1)
        new_val = random.randint(MIN_N, MAX_N)
        t[idx] = new_val
        t = sorted(set(t))
        while len(t) < DRAW_LEN:
            x = random.randint(MIN_N, MAX_N)
            if x not in t:
                t.append(x)
        t = sorted(t[:DRAW_LEN])
    return t


def crossover_tickets(a: List[int], b: List[int]) -> List[int]:
    merged = sorted(set(a[:3] + b[3:] + a[::2] + b[1::2]))
    out = []
    for x in merged:
        if x not in out:
            out.append(x)
        if len(out) == DRAW_LEN:
            break

    while len(out) < DRAW_LEN:
        x = random.randint(MIN_N, MAX_N)
        if x not in out:
            out.append(x)

    return sorted(out)


# =========================================================
# SCORING GŁÓWNY
# =========================================================
def score_ticket(ticket: List[int], draws: List[List[int]]) -> Dict[str, float]:
    total = len(draws)

    freq_all = frequency(draws)
    freq_50 = rolling_frequency(draws, min(50, total))
    freq_100 = rolling_frequency(draws, min(100, total))
    freq_250 = rolling_frequency(draws, min(250, total))

    last_draw = draws[0]

    long_term_score = sum(freq_all[n] for n in ticket) / max(1, total)
    medium_term_score = (
        (sum(freq_250[n] for n in ticket) / max(1, min(250, total))) * 0.55 +
        (sum(freq_100[n] for n in ticket) / max(1, min(100, total))) * 0.45
    )
    short_term_score = sum(freq_50[n] for n in ticket) / max(1, min(50, total))
    comeback_score = sum(comeback_cycle_score(n, draws) for n in ticket) / DRAW_LEN
    positional_score = positional_trend_score(ticket, draws)
    pair_score = pair_strength_score(ticket, draws)
    triplet_score = triplet_strength_score(ticket, draws)
    structural_score = ticket_balance_score(ticket, last_draw)

    penalties = 0.0
    penalties += max(0.0, -consecutive_penalty(ticket)) * 0.08
    penalties += max(0.0, -repeat_penalty(ticket, last_draw)) * 0.05

    final_score = (
        0.18 * long_term_score +
        0.16 * medium_term_score +
        0.14 * short_term_score +
        0.16 * comeback_score +
        0.12 * positional_score +
        0.10 * pair_score +
        0.06 * triplet_score +
        0.08 * structural_score
    ) - penalties

    return {
        "long_term_score": round(long_term_score, 6),
        "medium_term_score": round(medium_term_score, 6),
        "short_term_score": round(short_term_score, 6),
        "comeback_score": round(comeback_score, 6),
        "positional_score": round(positional_score, 6),
        "pair_score": round(pair_score, 6),
        "triplet_score": round(triplet_score, 6),
        "structural_score": round(structural_score, 6),
        "penalties": round(penalties, 6),
        "final_score": round(final_score, 6),
    }


# =========================================================
# PROFILE KUPONÓW
# =========================================================
def classify_ticket(ticket: List[int], metrics: Dict[str, float]) -> str:
    fs = metrics["final_score"]
    comeback = metrics["comeback_score"]
    positional = metrics["positional_score"]
    structure = metrics["structural_score"]

    if fs >= 0.90 and structure >= 0.80:
        return "stabilny"

    if comeback >= 0.75 and fs >= 0.82:
        return "momentum"

    if positional >= 0.08 and fs >= 0.80:
        return "agresywny"

    return "mocny"


# =========================================================
# DIVERSITY SELECTOR
# =========================================================
def diversity_select(
    ranked_candidates: List[Tuple[List[int], Dict[str, float], str, str]],
    desired_count: int
) -> List[Tuple[List[int], Dict[str, float], str, str]]:
    if not ranked_candidates:
        return []

    selected = []
    profiles_count = Counter()

    for candidate in ranked_candidates:
        ticket, metrics, mode, profile = candidate

        if not selected:
            selected.append(candidate)
            profiles_count[profile] += 1
            if len(selected) >= desired_count:
                break
            continue

        too_similar = False
        for chosen_ticket, _, _, _ in selected:
            if overlap_size(ticket, chosen_ticket) >= 4:
                too_similar = True
                break

        if too_similar:
            continue

        if profiles_count[profile] >= max(2, desired_count // 3):
            continue

        selected.append(candidate)
        profiles_count[profile] += 1

        if len(selected) >= desired_count:
            break

    if len(selected) < desired_count:
        selected_keys = {tuple(x[0]) for x in selected}
        for candidate in ranked_candidates:
            if tuple(candidate[0]) not in selected_keys:
                selected.append(candidate)
                selected_keys.add(tuple(candidate[0]))
            if len(selected) >= desired_count:
                break

    return selected[:desired_count]


# =========================================================
# TOURNAMENT SCORING
# =========================================================
def generate_tournament_candidates(
    draws: List[List[int]],
    n_candidates: int,
    modes: List[str],
    use_bystrzacha_blend: bool
) -> List[Tuple[List[int], Dict[str, float], str, str]]:
    last_draw = draws[0]
    byst = predict_positional_ticket_v2(draws)

    raw_candidates = []
    seen = set()

    if not modes:
        modes = ["hybrid", "weighted", "momentum", "comeback", "hot", "cold", "bystrzacha", "random"]

    per_mode = max(1, n_candidates // len(modes))

    mode_list = []
    for m in modes:
        mode_list.extend([m] * per_mode)

    while len(mode_list) < n_candidates:
        mode_list.append(random.choice(modes))

    random.shuffle(mode_list)

    for mode in mode_list:
        ticket = build_candidate_ticket(draws, mode)

        if use_bystrzacha_blend and random.random() < 0.22:
            blend = sorted(set(ticket[:3] + byst[:3]))
            while len(blend) < DRAW_LEN:
                x = random.randint(MIN_N, MAX_N)
                if x not in blend:
                    blend.append(x)
            ticket = sorted(blend[:DRAW_LEN])

        if random.random() < 0.12:
            ticket = mutate_ticket(ticket, intensity=random.randint(1, 2))

        if random.random() < 0.06:
            other = build_candidate_ticket(draws, random.choice(modes))
            ticket = crossover_tickets(ticket, other)

        ticket = sorted(set(ticket))
        while len(ticket) < DRAW_LEN:
            x = random.randint(MIN_N, MAX_N)
            if x not in ticket:
                ticket.append(x)
        ticket = sorted(ticket[:DRAW_LEN])

        if not ticket_passes_hard_filters(ticket, last_draw):
            continue

        key = tuple(ticket)
        if key in seen:
            continue
        seen.add(key)

        metrics = score_ticket(ticket, draws)
        profile = classify_ticket(ticket, metrics)

        raw_candidates.append((ticket, metrics, mode, profile))

    raw_candidates.sort(key=lambda x: x[1]["final_score"], reverse=True)
    return raw_candidates


def build_final_ticket_set(
    draws: List[List[int]],
    n_candidates: int = 30000,
    final_count: int = 6,
    modes: Optional[List[str]] = None,
    use_bystrzacha_blend: bool = True
) -> List[Tuple[List[int], Dict[str, float], str, str]]:
    if modes is None:
        modes = ["hybrid", "weighted", "momentum", "comeback", "hot", "cold", "bystrzacha", "random"]

    ranked = generate_tournament_candidates(
        draws=draws,
        n_candidates=n_candidates,
        modes=modes,
        use_bystrzacha_blend=use_bystrzacha_blend
    )

    top_pool = ranked[:100]
    diverse = diversity_select(top_pool, desired_count=final_count)

    if ranked:
        gold = max(
            ranked[:50],
            key=lambda x: (
                x[1]["comeback_score"] * 0.40 +
                x[1]["positional_score"] * 0.25 +
                x[1]["pair_score"] * 0.15 +
                x[1]["triplet_score"] * 0.10 +
                x[1]["structural_score"] * 0.10
            )
        )

        if tuple(gold[0]) not in {tuple(x[0]) for x in diverse} and len(diverse) < final_count + 1:
            diverse.append((gold[0], gold[1], gold[2], "złoty strzał"))

    return diverse


# =========================================================
# DATAFRAME
# =========================================================
def draws_dataframe(records: List[DrawRecord]) -> pd.DataFrame:
    rows = []
    for r in records:
        rows.append({
            "draw_no": r.draw_no,
            "n1": r.numbers[0],
            "n2": r.numbers[1],
            "n3": r.numbers[2],
            "n4": r.numbers[3],
            "n5": r.numbers[4],
            "n6": r.numbers[5],
            "sum": sum(r.numbers),
            "span": max(r.numbers) - min(r.numbers),
        })
    return pd.DataFrame(rows)


def frequency_dataframe(draws: List[List[int]]) -> pd.DataFrame:
    freq_all = frequency(draws)
    seen = last_seen_index(draws)
    comeback = all_comeback_scores(draws)
    total = len(draws)

    rows = []
    for n in range(MIN_N, MAX_N + 1):
        rows.append({
            "number": n,
            "count": freq_all[n],
            "percent": round((freq_all[n] / max(1, total)) * 100, 2),
            "last_seen_draws_ago": seen[n],
            "comeback_score": round(comeback[n], 6),
        })

    return pd.DataFrame(rows).sort_values(
        by=["count", "comeback_score", "last_seen_draws_ago", "number"],
        ascending=[False, False, False, True]
    )


def positional_dataframe(draws: List[List[int]]) -> pd.DataFrame:
    pos = positional_frequency(draws)
    rows = []
    for p in range(DRAW_LEN):
        for number, count in pos[p].most_common(12):
            rows.append({
                "position": p + 1,
                "number": number,
                "count": count,
            })
    return pd.DataFrame(rows)


def bystrzacha_dataframe(draws: List[List[int]]) -> pd.DataFrame:
    d25 = positional_deltas_window(draws, min(25, len(draws)))
    d50 = positional_deltas_window(draws, min(50, len(draws)))
    d100 = positional_deltas_window(draws, min(100, len(draws)))

    rows = []
    for p in range(DRAW_LEN):
        for delta, count in d25[p].most_common(5):
            rows.append({"window": 25, "position": p + 1, "delta": delta, "count": count})
        for delta, count in d50[p].most_common(5):
            rows.append({"window": 50, "position": p + 1, "delta": delta, "count": count})
        for delta, count in d100[p].most_common(5):
            rows.append({"window": 100, "position": p + 1, "delta": delta, "count": count})

    return pd.DataFrame(rows)


def pairs_dataframe(draws: List[List[int]], top_n: int = 25) -> pd.DataFrame:
    pairs = strongest_pairs(draws)
    rows = []
    for (a, b), count in pairs.most_common(top_n):
        rows.append({"a": a, "b": b, "count": count})
    return pd.DataFrame(rows)


def triplets_dataframe(draws: List[List[int]], top_n: int = 25) -> pd.DataFrame:
    tris = strongest_triplets(draws)
    rows = []
    for (a, b, c), count in tris.most_common(top_n):
        rows.append({"a": a, "b": b, "c": c, "count": count})
    return pd.DataFrame(rows)


# =========================================================
# STYL
# =========================================================
def inject_css():
    st.markdown(
        """
        <style>
        .main {
            background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
            color: white;
        }
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2rem;
        }
        h1, h2, h3, h4 {
            color: #f8fafc !important;
        }
        .stMetric {
            background: rgba(255,255,255,0.04);
            padding: 10px;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.08);
        }
        .ticket-card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
            padding: 14px;
            margin-bottom: 12px;
        }
        .ticket-title {
            font-weight: 800;
            font-size: 18px;
            color: #facc15;
            margin-bottom: 6px;
        }
        .ticket-numbers {
            font-size: 26px;
            font-weight: 900;
            color: #ffffff;
            margin-bottom: 6px;
            letter-spacing: 1px;
        }
        .ticket-meta {
            font-size: 13px;
            color: #cbd5e1;
            line-height: 1.5;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# CACHE
# =========================================================
@st.cache_data(show_spinner=False)
def load_default_pdf_if_exists() -> Optional[bytes]:
    try:
        with open(DEFAULT_PDF_NAME, "rb") as f:
            return f.read()
    except Exception:
        return None


@st.cache_data(show_spinner=True)
def parse_pdf_cached(pdf_bytes: bytes) -> List[DrawRecord]:
    return parse_lotto_pdf_bytes(pdf_bytes)


# =========================================================
# UI POMOCNICZE
# =========================================================
def ticket_to_text(ticket: List[int]) -> str:
    return " ".join(f"{x:02d}" for x in ticket)


def build_result_dataframe(results: List[Tuple[List[int], Dict[str, float], str, str]]) -> pd.DataFrame:
    rows = []
    for i, (ticket, metrics, mode, profile) in enumerate(results, start=1):
        rows.append({
            "rank": i,
            "numbers": ticket_to_text(ticket),
            "mode": mode,
            "profile": profile,
            **metrics,
        })
    return pd.DataFrame(rows)


# =========================================================
# MAIN
# =========================================================
def main():
    inject_css()

    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    st.markdown(
        """
        Wersja **ULTRA PRO MAX**:
        - parser PDF,
        - hot / cold / rolling windows,
        - **Comeback Cycle Engine**,
        - **Bystrzacha 2.0**,
        - analiza par i trójek,
        - **Tournament Scoring**,
        - **Diversity Selector**,
        - profile kuponów: stabilny / momentum / agresywny / złoty strzał.
        """
    )

    with st.sidebar:
        st.header("⚙️ Ustawienia")

        uploaded_file = st.file_uploader("Wgraj PDF Lotto", type=["pdf"])
        use_default_pdf = st.checkbox("Użyj domyślnego pliku PDF", value=(uploaded_file is None))

        analysis_window = st.slider(
            "Ile ostatnich losowań analizować",
            min_value=50,
            max_value=999,
            value=999,
            step=1,
        )

        candidate_pool = st.slider(
            "Pula kandydatów w turnieju",
            min_value=5000,
            max_value=50000,
            value=30000,
            step=1000,
        )

        final_count = st.slider(
            "Ile finalnych kuponów wybrać",
            min_value=3,
            max_value=12,
            value=6,
            step=1,
        )

        chosen_modes = st.multiselect(
            "Tryby źródłowe",
            options=["hybrid", "weighted", "momentum", "comeback", "hot", "cold", "bystrzacha", "random"],
            default=["hybrid", "weighted", "momentum", "comeback", "hot", "cold", "bystrzacha", "random"],
        )

        use_bystrzacha_blend = st.checkbox("Domieszka Bystrzachy 2.0", value=True)

        custom_seed = st.checkbox("Ustaw seed", value=False)
        seed_value = None
        if custom_seed:
            seed_value = st.number_input("Seed", min_value=0, max_value=999999999, value=12345, step=1)

        run_button = st.button("🚀 Uruchom ULTRA PRO MAX", use_container_width=True)

    if seed_value is not None:
        random.seed(int(seed_value))
    else:
        random.seed()

    pdf_bytes = None
    if uploaded_file is not None:
        pdf_bytes = uploaded_file.read()
    elif use_default_pdf:
        pdf_bytes = load_default_pdf_if_exists()

    if not pdf_bytes:
        st.warning("Wgraj plik PDF albo umieść domyślny plik obok aplikacji.")
        st.stop()

    with st.spinner("Czytam PDF i buduję model..."):
        records = parse_pdf_cached(pdf_bytes)

    draws_all = get_draws(records)

    # DEBUG
    st.write("DEBUG - liczba rekordów:", len(records))
    st.write("DEBUG - liczba poprawnych losowań:", len(draws_all))
    if records[:5]:
        st.write("DEBUG - pierwsze rekordy:", records[:5])

    if not draws_all:
        st.error("Nie udało się odczytać poprawnych losowań z PDF. Parser nie znalazł wierszy z 6 liczbami Lotto.")
        st.stop()

    draws = draws_all[:analysis_window]
    records_cut = records[:len(draws)]

    last_draw = draws[0]
    hot_list, cold_list = hot_and_cold_lists(draws, top_n=10)
    byst_ticket = predict_positional_ticket_v2(draws)
    freq_df = frequency_dataframe(draws)
    pos_df = positional_dataframe(draws)
    byst_df = bystrzacha_dataframe(draws)
    pair_df = pairs_dataframe(draws, top_n=25)
    tri_df = triplets_dataframe(draws, top_n=25)
    raw_df = draws_dataframe(records_cut)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Odczytane losowania", len(draws_all))
    c2.metric("Analizowane losowania", len(draws))
    c3.metric("Ostatnie losowanie", ticket_to_text(last_draw))
    c4.metric("Bystrzacha 2.0", ticket_to_text(byst_ticket))

    tabs = st.tabs([
        "🎟️ Generator",
        "📊 Częstotliwość",
        "🔥 Hot / Cold / Comeback",
        "🧠 Bystrzacha 2.0",
        "🔗 Pary i trójki",
        "📄 Dane",
    ])

    with tabs[0]:
        st.subheader("Generator ULTRA PRO MAX")

        if run_button:
            with st.spinner("Trwa turniej kandydatów i wybór najlepszych kuponów..."):
                results = build_final_ticket_set(
                    draws=draws,
                    n_candidates=candidate_pool,
                    final_count=final_count,
                    modes=chosen_modes if chosen_modes else None,
                    use_bystrzacha_blend=use_bystrzacha_blend
                )

            if not results:
                st.warning("Nie udało się wygenerować finalnych kuponów.")
            else:
                st.success(f"Wybrano {len(results)} finalnych kuponów z puli {candidate_pool} kandydatów.")

                for i, (ticket, metrics, mode, profile) in enumerate(results, start=1):
                    st.markdown(
                        f"""
                        <div class="ticket-card">
                            <div class="ticket-title">Kupon #{i} — {profile.upper()}</div>
                            <div class="ticket-numbers">{ticket_to_text(ticket)}</div>
                            <div class="ticket-meta">
                                mode={mode} | final_score={metrics['final_score']}<br>
                                long={metrics['long_term_score']} |
                                medium={metrics['medium_term_score']} |
                                short={metrics['short_term_score']} |
                                comeback={metrics['comeback_score']} |
                                positional={metrics['positional_score']} |
                                pair={metrics['pair_score']} |
                                triplet={metrics['triplet_score']} |
                                structural={metrics['structural_score']} |
                                penalties={metrics['penalties']}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                result_df = build_result_dataframe(results)
                st.dataframe(result_df, use_container_width=True)

                txt_output = "\n".join(
                    f"{i+1:02d}. {ticket_to_text(ticket)} | {profile} | mode={mode} | score={metrics['final_score']}"
                    for i, (ticket, metrics, mode, profile) in enumerate(results)
                )

                st.download_button(
                    "⬇️ Pobierz kupony TXT",
                    data=txt_output.encode("utf-8"),
                    file_name="lotto_ultra_pro_max_tickets.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

                csv_output = result_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Pobierz ranking CSV",
                    data=csv_output,
                    file_name="lotto_ultra_pro_max_ranking.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        else:
            st.info("Ustaw parametry po lewej i kliknij „Uruchom ULTRA PRO MAX”.")

        st.markdown("### Szybki podgląd")
        a, b, c = st.columns(3)
        with a:
            st.write("**Hot 10**")
            st.write(", ".join(f"{x:02d}" for x in hot_list))
        with b:
            st.write("**Cold 10**")
            st.write(", ".join(f"{x:02d}" for x in cold_list))
        with c:
            st.write("**Bystrzacha 2.0**")
            st.write(", ".join(f"{x:02d}" for x in byst_ticket))

    with tabs[1]:
        st.subheader("Częstotliwość liczb")
        st.dataframe(freq_df, use_container_width=True)

        chart_df = freq_df.sort_values("number").set_index("number")
        st.bar_chart(chart_df["count"])

    with tabs[2]:
        st.subheader("Hot / Cold / Comeback")

        left, right = st.columns(2)
        with left:
            st.markdown("### 🔥 Hot 10")
            for i, n in enumerate(hot_list, start=1):
                st.write(f"{i}. {n:02d}")

        with right:
            st.markdown("### ❄️ Cold 10")
            for i, n in enumerate(cold_list, start=1):
                st.write(f"{i}. {n:02d}")

        st.markdown("### Number Score + Comeback Score")
        ns = number_scores(draws)
        comeback = all_comeback_scores(draws)

        ns_df = pd.DataFrame(
            [
                {
                    "number": n,
                    "number_score": round(ns[n], 6),
                    "comeback_score": round(comeback[n], 6),
                }
                for n in range(MIN_N, MAX_N + 1)
            ]
        ).sort_values(by=["number_score", "comeback_score"], ascending=False)

        st.dataframe(ns_df, use_container_width=True)

    with tabs[3]:
        st.subheader("Bystrzacha 2.0")

        st.markdown("### Prognoza pozycyjna")
        st.code(ticket_to_text(byst_ticket))

        st.markdown("### Najczęstsze liczby na pozycjach")
        st.dataframe(pos_df, use_container_width=True)

        st.markdown("### Najczęstsze delty w oknach 25 / 50 / 100")
        st.dataframe(byst_df, use_container_width=True)

    with tabs[4]:
        st.subheader("Pary i trójki")

        left, right = st.columns(2)
        with left:
            st.markdown("### Top pary")
            st.dataframe(pair_df, use_container_width=True)

        with right:
            st.markdown("### Top trójki")
            st.dataframe(tri_df, use_container_width=True)

    with tabs[5]:
        st.subheader("Surowe dane losowań")
        st.dataframe(raw_df, use_container_width=True)

        csv_data = raw_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Pobierz dane losowań CSV",
            data=csv_data,
            file_name="lotto_draws.csv",
            mime="text/csv",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
