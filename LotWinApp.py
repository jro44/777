import io
import os
import re
import math
import random
import itertools
from dataclasses import dataclass
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st


# ============================================================
# KONFIGURACJA APLIKACJI
# ============================================================

APP_TITLE = "🎯 Generator Lotto PRO"
APP_SUBTITLE = "Analiza PDF + rytmika liczb + układy historyczne + gorące/zimne liczby + tryb Bystrzacha"

DEFAULT_PDF = "wyniki.pdf"
PDF_CANDIDATES = ["wyniki.pdf", "wynik.pdf"]

LOTTO_MIN = 1
LOTTO_MAX = 49
NUMBERS_IN_DRAW = 6
DRAWNO_MIN = 1000

MAX_DRAWS_DEFAULT = 999
DEFAULT_TICKETS_COUNT = 6
DEFAULT_RANDOM_SEED = 42

DEFAULT_WEIGHT_FREQ = 0.30
DEFAULT_WEIGHT_RECENCY = 0.15
DEFAULT_WEIGHT_RHYTHM = 0.25
DEFAULT_WEIGHT_PAIR = 0.15
DEFAULT_WEIGHT_TRIPLE = 0.10
DEFAULT_WEIGHT_OVERDUE = 0.05

DEFAULT_HOT_POOL = 24
DEFAULT_GENERATION_ATTEMPTS = 7000

DEFAULT_ENABLE_BYSTRZACHA = True
DEFAULT_BYSTRZACHA_TOP_DELTAS = 10

INT_RE = re.compile(r"\d+")


# ============================================================
# MODELE DANYCH
# ============================================================

@dataclass
class Draw:
    draw_id: Optional[int]
    numbers: List[int]


@dataclass
class AnalyzerConfig:
    weight_freq: float
    weight_recency: float
    weight_rhythm: float
    weight_pair: float
    weight_triple: float
    weight_overdue: float
    hot_pool: int
    generation_attempts: int
    seed: int
    rule_force_even_odd: bool
    rule_force_spread: bool
    rule_force_sum_range: bool
    rule_avoid_last_draw_clone: bool
    enable_bystrzacha: bool
    bystrzacha_top_deltas: int


# ============================================================
# FUNKCJE POMOCNICZE
# ============================================================

def safe_percent(part: int, whole: int) -> float:
    if whole == 0:
        return 0.0
    return (part / whole) * 100.0


def format_num(n: int) -> str:
    return f"{n:02d}"


def format_number_list(nums: List[int]) -> str:
    return " ".join(format_num(n) for n in sorted(nums))


def count_even(nums: List[int]) -> int:
    return sum(1 for n in nums if n % 2 == 0)


def max_consecutive_run(nums: List[int]) -> int:
    if not nums:
        return 0

    nums = sorted(nums)
    best = 1
    current = 1

    for i in range(1, len(nums)):
        if nums[i] == nums[i - 1] + 1:
            current += 1
            best = max(best, current)
        else:
            current = 1

    return best


def calculate_zscores(values_dict: Dict[int, float]) -> Dict[int, float]:
    if not values_dict:
        return {}

    values = list(values_dict.values())
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)

    if std == 0:
        return {k: 0.0 for k in values_dict}

    return {k: (v - mean) / std for k, v in values_dict.items()}


def make_bytesio_from_upload(uploaded_file) -> io.BytesIO:
    if uploaded_file is None:
        raise ValueError("Nie przesłano pliku PDF.")
    return io.BytesIO(uploaded_file.read())


def resolve_pdf_path() -> Path:
    cwd = Path(os.getcwd())
    for name in PDF_CANDIDATES:
        p = cwd / name
        if p.exists():
            return p
    return cwd / PDF_CANDIDATES[0]


def resolve_pdf_source(uploaded_file, default_path: str):
    if uploaded_file is not None:
        return make_bytesio_from_upload(uploaded_file)

    if os.path.exists(default_path):
        return default_path

    auto_path = resolve_pdf_path()
    if auto_path.exists():
        return str(auto_path)

    return None


def read_pdf_bytes(pdf_source) -> bytes:
    if isinstance(pdf_source, str):
        if not os.path.exists(pdf_source):
            raise FileNotFoundError(f"Nie znaleziono pliku: {pdf_source}")
        with open(pdf_source, "rb") as f:
            return f.read()

    if isinstance(pdf_source, bytes):
        return pdf_source

    if isinstance(pdf_source, io.BytesIO):
        return pdf_source.getvalue()

    raise TypeError("Nieobsługiwany typ źródła PDF.")


# ============================================================
# PARSER PDF — ODCZYT JAK W SPRAWDZONYM KODZIE
# ============================================================

@st.cache_data(show_spinner=False)
def load_records_cached(pdf_bytes: bytes) -> List[Draw]:
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Brak nagłówka %PDF.")

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        pages = [page.get_text("text") or "" for page in doc]

    all_tokens: List[int] = []
    all_drawnos: List[int] = []

    for page_text in pages:
        lines = [re.sub(r"\s+", " ", ln.strip()) for ln in page_text.splitlines() if ln.strip()]
        drawno_mode = False

        for ln in lines:
            ln_lower = ln.lower()

            if any(skip in ln_lower for skip in ["lotto 6/49", "www.", "©", "multipasko"]):
                continue

            ints = [int(x) for x in INT_RE.findall(ln)]
            if not ints:
                continue

            if any(x >= DRAWNO_MIN for x in ints) and not any(LOTTO_MIN <= x <= LOTTO_MAX for x in ints):
                drawno_mode = True

            if not drawno_mode:
                all_tokens.extend(x for x in ints if LOTTO_MIN <= x <= LOTTO_MAX)
            else:
                all_drawnos.extend(x for x in ints if DRAWNO_MIN <= x < 100000)

    draws_numbers: List[List[int]] = []
    for i in range(0, len(all_tokens) - NUMBERS_IN_DRAW + 1, NUMBERS_IN_DRAW):
        d = sorted(all_tokens[i:i + NUMBERS_IN_DRAW])
        if len(set(d)) == NUMBERS_IN_DRAW and all(LOTTO_MIN <= x <= LOTTO_MAX for x in d):
            draws_numbers.append(d)

    n = min(len(draws_numbers), len(all_drawnos))
    records: List[Draw] = [Draw(draw_id=all_drawnos[i], numbers=draws_numbers[i]) for i in range(n)]
    records.extend(Draw(draw_id=None, numbers=draws_numbers[j]) for j in range(n, len(draws_numbers)))

    records.sort(key=lambda r: (r.draw_id is None, r.draw_id or -1), reverse=True)
    return records


def parse_lotto_pdf(pdf_source, max_draws: int = 999) -> Tuple[List[Draw], Dict]:
    pdf_bytes = read_pdf_bytes(pdf_source)

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        pages_total = len(doc)

    parsed_records = load_records_cached(pdf_bytes)

    if not parsed_records:
        raise ValueError(
            "Parser nie odczytał żadnych poprawnych losowań z PDF. "
            "Upewnij się, że w repo jest właściwy plik wyniki.pdf."
        )

    draws_total_before_dedup = len(parsed_records)

    dedup_with_id: Dict[int, Draw] = {}
    without_id: List[Draw] = []

    for draw in parsed_records:
        if draw.draw_id is None:
            without_id.append(draw)
        else:
            if draw.draw_id not in dedup_with_id:
                dedup_with_id[draw.draw_id] = draw

    draws = sorted(dedup_with_id.values(), key=lambda d: d.draw_id if d.draw_id is not None else -1, reverse=True)

    if without_id:
        existing_sets = {tuple(d.numbers) for d in draws}
        for d in without_id:
            if tuple(d.numbers) not in existing_sets:
                draws.append(d)
                existing_sets.add(tuple(d.numbers))

    if max_draws is not None:
        draws = draws[:max_draws]

    if not draws:
        raise ValueError("Po deduplikacji nie pozostały żadne losowania do analizy.")

    diagnostics = {
        "pages_total": pages_total,
        "draws_total_before_dedup": draws_total_before_dedup,
        "draws_total_after_dedup": len(draws),
        "newest_draw_id": next((d.draw_id for d in draws if d.draw_id is not None), None),
        "oldest_draw_id": next((d.draw_id for d in reversed(draws) if d.draw_id is not None), None),
        "pages": [
            {
                "page": "cały dokument",
                "method": "text-token-parser",
                "paired_rows_selected": len(draws),
                "sample_first_numbers_row": format_number_list(draws[0].numbers) if draws else None,
                "sample_first_draw_id": draws[0].draw_id if draws and draws[0].draw_id is not None else None,
            }
        ],
    }

    return draws, diagnostics


# ============================================================
# ANALIZATOR LOTTO
# ============================================================

class LottoAnalyzer:
    def __init__(self, draws: List[Draw], config: AnalyzerConfig):
        self.draws = self._sort_draws(draws)
        self.total_draws = len(self.draws)
        self.config = config
        self.random = random.Random(config.seed)

        self.number_counter = Counter()
        self.pair_counter = Counter()
        self.triple_counter = Counter()
        self.quad_counter = Counter()
        self.position_counter = [Counter() for _ in range(NUMBERS_IN_DRAW)]

        self.intervals = {}
        self.positional_delta_counters: List[Counter] = [Counter() for _ in range(NUMBERS_IN_DRAW)]
        self.positional_direction_counters: List[Counter] = [Counter() for _ in range(NUMBERS_IN_DRAW)]

        self._analyze()
        self.intervals = self._analyze_intervals()
        self._analyze_positional_deltas()

    def _sort_draws(self, draws: List[Draw]) -> List[Draw]:
        with_id = [d for d in draws if d.draw_id is not None]
        without_id = [d for d in draws if d.draw_id is None]

        with_id = sorted(with_id, key=lambda d: d.draw_id, reverse=True)
        return with_id + without_id

    def _analyze(self):
        for draw in self.draws:
            nums = sorted(draw.numbers)

            self.number_counter.update(nums)

            for i, n in enumerate(nums):
                self.position_counter[i][n] += 1

            for pair in itertools.combinations(nums, 2):
                self.pair_counter[pair] += 1

            for triple in itertools.combinations(nums, 3):
                self.triple_counter[triple] += 1

            for quad in itertools.combinations(nums, 4):
                self.quad_counter[quad] += 1

    def _analyze_intervals(self) -> Dict[int, Dict]:
        chronological = list(reversed(self.draws))
        intervals_data = {
            n: {
                "gaps": [],
                "avg_gap": 0.0,
                "most_common_gap": 0,
                "current_gap": 0,
                "overdue_factor": 0.0,
            }
            for n in range(LOTTO_MIN, LOTTO_MAX + 1)
        }

        last_seen = {n: -1 for n in range(LOTTO_MIN, LOTTO_MAX + 1)}

        for idx, draw in enumerate(chronological):
            for n in draw.numbers:
                if last_seen[n] != -1:
                    gap = idx - last_seen[n]
                    intervals_data[n]["gaps"].append(gap)
                last_seen[n] = idx

        total_draws = len(chronological)

        for n in range(LOTTO_MIN, LOTTO_MAX + 1):
            if last_seen[n] != -1:
                intervals_data[n]["current_gap"] = total_draws - 1 - last_seen[n]
            else:
                intervals_data[n]["current_gap"] = total_draws

            gaps = intervals_data[n]["gaps"]

            if gaps:
                intervals_data[n]["avg_gap"] = sum(gaps) / len(gaps)
                intervals_data[n]["most_common_gap"] = Counter(gaps).most_common(1)[0][0]

                avg_gap = intervals_data[n]["avg_gap"]
                current_gap = intervals_data[n]["current_gap"]

                if avg_gap > 0:
                    intervals_data[n]["overdue_factor"] = current_gap / avg_gap
                else:
                    intervals_data[n]["overdue_factor"] = 0.0

        return intervals_data

    def _analyze_positional_deltas(self):
        chronological = list(reversed(self.draws))
        if len(chronological) < 2:
            return

        for i in range(len(chronological) - 1):
            current_draw = sorted(chronological[i].numbers)
            next_draw = sorted(chronological[i + 1].numbers)

            for pos in range(NUMBERS_IN_DRAW):
                delta = next_draw[pos] - current_draw[pos]
                self.positional_delta_counters[pos][delta] += 1

                if delta > 0:
                    self.positional_direction_counters[pos]["góra"] += 1
                elif delta < 0:
                    self.positional_direction_counters[pos]["dół"] += 1
                else:
                    self.positional_direction_counters[pos]["bez zmiany"] += 1

    def get_last_draw(self) -> Optional[Draw]:
        return self.draws[0] if self.draws else None

    def get_recent_draws_table(self, limit: int = 15) -> List[Dict]:
        rows = []
        for d in self.draws[:limit]:
            rows.append({
                "ID losowania": d.draw_id if d.draw_id is not None else "-",
                "Liczby": format_number_list(d.numbers)
            })
        return rows

    def compute_number_scores(self) -> Dict[int, float]:
        freq_dict = {n: self.number_counter[n] for n in range(LOTTO_MIN, LOTTO_MAX + 1)}

        recency_points = {n: 0.0 for n in range(LOTTO_MIN, LOTTO_MAX + 1)}
        recent_window = min(80, self.total_draws)

        for idx, draw in enumerate(self.draws[:recent_window]):
            weight = recent_window - idx
            for n in draw.numbers:
                recency_points[n] += weight

        pair_by_number = defaultdict(int)
        for pair, cnt in self.pair_counter.items():
            a, b = pair
            pair_by_number[a] += cnt
            pair_by_number[b] += cnt

        triple_by_number = defaultdict(int)
        for triple, cnt in self.triple_counter.items():
            for n in triple:
                triple_by_number[n] += cnt

        overdue_raw = {
            n: self.intervals[n]["overdue_factor"]
            for n in range(LOTTO_MIN, LOTTO_MAX + 1)
        }

        freq_z = calculate_zscores(freq_dict)
        recency_z = calculate_zscores(recency_points)
        pair_z = calculate_zscores(pair_by_number)
        triple_z = calculate_zscores(triple_by_number)
        overdue_z = calculate_zscores(overdue_raw)

        scores = {}
        for n in range(LOTTO_MIN, LOTTO_MAX + 1):
            current_gap = self.intervals[n]["current_gap"]
            most_common_gap = self.intervals[n]["most_common_gap"]
            avg_gap = self.intervals[n]["avg_gap"]

            rhythm_bonus = 0.0

            if most_common_gap > 0:
                if current_gap == most_common_gap:
                    rhythm_bonus += 2.5
                elif abs(current_gap - most_common_gap) == 1:
                    rhythm_bonus += 1.25

            if avg_gap > 0:
                diff = abs(current_gap - avg_gap)
                if diff <= 1.0:
                    rhythm_bonus += 0.8
                elif diff <= 2.0:
                    rhythm_bonus += 0.4

            scores[n] = (
                self.config.weight_freq * freq_z.get(n, 0.0)
                + self.config.weight_recency * recency_z.get(n, 0.0)
                + self.config.weight_pair * pair_z.get(n, 0.0)
                + self.config.weight_triple * triple_z.get(n, 0.0)
                + self.config.weight_rhythm * rhythm_bonus
                + self.config.weight_overdue * overdue_z.get(n, 0.0)
            )

        return scores

    def validate_ticket(self, nums: List[int]) -> bool:
        nums = sorted(nums)

        if len(nums) != NUMBERS_IN_DRAW:
            return False
        if len(set(nums)) != NUMBERS_IN_DRAW:
            return False
        if any(n < LOTTO_MIN or n > LOTTO_MAX for n in nums):
            return False

        if self.config.rule_force_even_odd:
            evens = count_even(nums)
            if evens not in (2, 3, 4):
                return False

        if max_consecutive_run(nums) > 2:
            return False

        if self.config.rule_force_spread:
            spread = nums[-1] - nums[0]
            if spread < 20:
                return False

        if self.config.rule_force_sum_range:
            s = sum(nums)
            if s < 90 or s > 210:
                return False

        if self.config.rule_avoid_last_draw_clone:
            last_draw = self.get_last_draw()
            if last_draw and set(nums) == set(last_draw.numbers):
                return False

        return True

    def ticket_quality_score(self, nums: List[int], ranked_scores: Dict[int, float]) -> float:
        nums = sorted(nums)
        score = sum(ranked_scores.get(n, 0.0) for n in nums)

        pair_bonus = 0.0
        for pair in itertools.combinations(nums, 2):
            pair_bonus += self.pair_counter.get(pair, 0) * 0.08

        triple_bonus = 0.0
        for triple in itertools.combinations(nums, 3):
            triple_bonus += self.triple_counter.get(triple, 0) * 0.12

        rhythm_bonus = 0.0
        for n in nums:
            current_gap = self.intervals[n]["current_gap"]
            most_common_gap = self.intervals[n]["most_common_gap"]
            if most_common_gap > 0:
                if current_gap == most_common_gap:
                    rhythm_bonus += 0.7
                elif abs(current_gap - most_common_gap) == 1:
                    rhythm_bonus += 0.3

        diversity_penalty = 0.0
        if max_consecutive_run(nums) >= 3:
            diversity_penalty -= 2.0

        return score + pair_bonus + triple_bonus + rhythm_bonus + diversity_penalty

    def _split_hot_cold_numbers(self, ranked_numbers: List[int]) -> Tuple[List[int], List[int]]:
        hp = self.config.hot_pool

        if hp >= 49:
            hot_numbers = ranked_numbers[:]
            cold_numbers = []
        elif hp <= 0:
            hot_numbers = []
            cold_numbers = list(reversed(ranked_numbers))
        else:
            hot_numbers = ranked_numbers[:hp]
            cold_numbers = ranked_numbers[hp:]

        return hot_numbers, cold_numbers

    def _build_candidate_pool(self, ranked_numbers: List[int]) -> List[int]:
        hot_numbers, cold_numbers = self._split_hot_cold_numbers(ranked_numbers)

        if self.config.hot_pool >= 49:
            return hot_numbers[:]

        if self.config.hot_pool <= 0:
            return cold_numbers[:]

        return hot_numbers[:]

    def _build_bystrzacha_position_options(self) -> List[List[Tuple[int, float, int]]]:
        last_draw = self.get_last_draw()
        if not last_draw:
            return []

        latest = sorted(last_draw.numbers)
        options_per_position: List[List[Tuple[int, float, int]]] = []

        for pos in range(NUMBERS_IN_DRAW):
            counter = self.positional_delta_counters[pos]
            base_value = latest[pos]
            position_options: List[Tuple[int, float, int]] = []

            top_deltas = counter.most_common(max(1, self.config.bystrzacha_top_deltas))

            for rank_index, (delta, freq) in enumerate(top_deltas):
                predicted = base_value + delta
                if LOTTO_MIN <= predicted <= LOTTO_MAX:
                    score = float(freq) - (rank_index * 0.05)
                    position_options.append((predicted, score, delta))

            position_options.append((base_value, 0.01, 0))

            best_map: Dict[int, Tuple[int, float, int]] = {}
            for predicted, score, delta in position_options:
                if predicted not in best_map or score > best_map[predicted][1]:
                    best_map[predicted] = (predicted, score, delta)

            final_position_options = sorted(best_map.values(), key=lambda x: (-x[1], x[0]))
            options_per_position.append(final_position_options)

        return options_per_position

    def _search_best_bystrzacha_sequence(
        self,
        options_per_position: List[List[Tuple[int, float, int]]]
    ) -> Tuple[List[int], List[int], float]:
        best_numbers: Optional[List[int]] = None
        best_deltas: Optional[List[int]] = None
        best_score = float("-inf")

        def backtrack(pos: int, chosen_nums: List[int], chosen_deltas: List[int], total_score: float):
            nonlocal best_numbers, best_deltas, best_score

            if pos == NUMBERS_IN_DRAW:
                candidate = sorted(chosen_nums)
                if len(set(candidate)) != NUMBERS_IN_DRAW:
                    return
                if not self.validate_ticket(candidate):
                    return
                if total_score > best_score:
                    best_score = total_score
                    best_numbers = candidate[:]
                    best_deltas = chosen_deltas[:]
                return

            current_options = options_per_position[pos][:12]

            for predicted, score, delta in current_options:
                if predicted in chosen_nums:
                    continue
                if chosen_nums and predicted <= chosen_nums[-1]:
                    continue

                chosen_nums.append(predicted)
                chosen_deltas.append(delta)
                backtrack(pos + 1, chosen_nums, chosen_deltas, total_score + score)
                chosen_nums.pop()
                chosen_deltas.pop()

        backtrack(0, [], [], 0.0)

        if best_numbers is not None and best_deltas is not None:
            return best_numbers, best_deltas, best_score

        greedy_nums = []
        greedy_deltas = []
        for pos in range(NUMBERS_IN_DRAW):
            picked = None
            for predicted, score, delta in options_per_position[pos]:
                if predicted in greedy_nums:
                    continue
                if greedy_nums and predicted <= greedy_nums[-1]:
                    continue
                picked = (predicted, score, delta)
                break

            if picked is None:
                base = LOTTO_MIN if not greedy_nums else greedy_nums[-1] + 1
                if base > LOTTO_MAX:
                    base = LOTTO_MAX
                picked = (base, 0.0, 0)

            greedy_nums.append(picked[0])
            greedy_deltas.append(picked[2])

        greedy_nums = sorted(list(dict.fromkeys(greedy_nums)))
        while len(greedy_nums) < NUMBERS_IN_DRAW:
            for n in range(LOTTO_MIN, LOTTO_MAX + 1):
                if n not in greedy_nums:
                    greedy_nums.append(n)
                    if len(greedy_nums) == NUMBERS_IN_DRAW:
                        break

        greedy_nums = sorted(greedy_nums[:NUMBERS_IN_DRAW])
        return greedy_nums, greedy_deltas[:NUMBERS_IN_DRAW], 0.0

    def generate_bystrzacha_ticket(self) -> Dict[str, Any]:
        last_draw = self.get_last_draw()
        if not last_draw:
            return {
                "Liczby Lotto 6/49": "-",
                "Geneza": "Brak danych do analizy Bystrzachy.",
                "Delta 1": "-",
                "Delta 2": "-",
                "Delta 3": "-",
                "Delta 4": "-",
                "Delta 5": "-",
                "Delta 6": "-",
                "Suma": "-",
                "Parzyste": "-",
                "Seria kolejnych": "-",
                "Bystrzacha score": "-",
            }

        options_per_position = self._build_bystrzacha_position_options()
        ticket, deltas, score = self._search_best_bystrzacha_sequence(options_per_position)

        return {
            "Liczby Lotto 6/49": format_number_list(ticket),
            "Geneza": "Bystrzacha: najczęstsze zmiany pozycyjne między kolejnymi losowaniami",
            "Delta 1": f"{deltas[0]:+d}" if len(deltas) > 0 else "-",
            "Delta 2": f"{deltas[1]:+d}" if len(deltas) > 1 else "-",
            "Delta 3": f"{deltas[2]:+d}" if len(deltas) > 2 else "-",
            "Delta 4": f"{deltas[3]:+d}" if len(deltas) > 3 else "-",
            "Delta 5": f"{deltas[4]:+d}" if len(deltas) > 4 else "-",
            "Delta 6": f"{deltas[5]:+d}" if len(deltas) > 5 else "-",
            "Suma": sum(ticket),
            "Parzyste": count_even(ticket),
            "Seria kolejnych": max_consecutive_run(ticket),
            "Bystrzacha score": round(score, 4),
        }

    def get_bystrzacha_analysis_table(self) -> List[Dict]:
        rows = []
        for pos in range(NUMBERS_IN_DRAW):
            counter = self.positional_delta_counters[pos]
            directions = self.positional_direction_counters[pos]

            top_changes = counter.most_common(8)
            if not top_changes:
                rows.append({
                    "Pozycja": pos + 1,
                    "Najczęstsze zmiany": "Brak danych",
                    "Góra": 0,
                    "Dół": 0,
                    "Bez zmiany": 0,
                    "Najmocniejsza delta": "-",
                    "Wystąpienia": 0,
                })
                continue

            top_changes_text = ", ".join([f"{delta:+d} ({cnt}x)" for delta, cnt in top_changes])
            best_delta, best_count = top_changes[0]

            rows.append({
                "Pozycja": pos + 1,
                "Najczęstsze zmiany": top_changes_text,
                "Góra": directions.get("góra", 0),
                "Dół": directions.get("dół", 0),
                "Bez zmiany": directions.get("bez zmiany", 0),
                "Najmocniejsza delta": f"{best_delta:+d}",
                "Wystąpienia": best_count,
            })

        return rows

    def generate_smart_tickets(self, count: int = 6) -> List[Dict]:
        number_scores = self.compute_number_scores()
        ranked_numbers = [n for n, _ in sorted(number_scores.items(), key=lambda x: x[1], reverse=True)]

        hot_numbers, cold_numbers = self._split_hot_cold_numbers(ranked_numbers)
        candidate_pool = self._build_candidate_pool(ranked_numbers)

        top_quads = [q for q, c in self.quad_counter.most_common(12) if c > 1]
        top_triples = [t for t, c in self.triple_counter.most_common(30) if c > 1]
        top_pairs = [p for p, c in self.pair_counter.most_common(40) if c > 1]

        historical_bases: List[Tuple[List[int], str]] = []
        for quad in top_quads:
            historical_bases.append((list(quad), f"Rdzeń historyczny: częsta czwórka (padła {self.quad_counter[quad]}x)"))
        for triple in top_triples:
            historical_bases.append((list(triple), f"Rdzeń historyczny: częsta trójka (padła {self.triple_counter[triple]}x)"))
        for pair in top_pairs:
            historical_bases.append((list(pair), f"Rdzeń historyczny: częsta para (padła {self.pair_counter[pair]}x)"))

        results = []
        seen_tickets = set()

        if self.config.enable_bystrzacha:
            bystrzacha_ticket = self.generate_bystrzacha_ticket()
            if bystrzacha_ticket["Liczby Lotto 6/49"] != "-":
                bt_numbers = [int(x) for x in bystrzacha_ticket["Liczby Lotto 6/49"].split()]
                if len(bt_numbers) == NUMBERS_IN_DRAW:
                    seen_tickets.add(tuple(bt_numbers))
                    results.append({
                        "Kupon": "B",
                        "Liczby Lotto 6/49": bystrzacha_ticket["Liczby Lotto 6/49"],
                        "Suma": bystrzacha_ticket["Suma"],
                        "Parzyste": bystrzacha_ticket["Parzyste"],
                        "Seria kolejnych": bystrzacha_ticket["Seria kolejnych"],
                        "Geneza": f"🧠 {bystrzacha_ticket['Geneza']}",
                    })

        normal_count = count
        if self.config.enable_bystrzacha and len(results) > 0:
            normal_count = max(0, count - 1)

        for ticket_index in range(normal_count):
            best_ticket = None
            best_score = float("-inf")
            best_reason = "Ranking częstotliwość + rytm + układy"

            for attempt in range(self.config.generation_attempts):
                if ticket_index < len(historical_bases) and attempt < self.config.generation_attempts // 3:
                    base_nums, reason = historical_bases[ticket_index]
                else:
                    base_choice = self.random.choice([2, 3, 4, 0, 0, 0])

                    if base_choice == 4 and top_quads:
                        quad = self.random.choice(top_quads[:min(8, len(top_quads))])
                        base_nums = list(quad)
                        reason = f"Mocny rdzeń: częsta czwórka (padła {self.quad_counter[quad]}x)"
                    elif base_choice == 3 and top_triples:
                        triple = self.random.choice(top_triples[:min(15, len(top_triples))])
                        base_nums = list(triple)
                        reason = f"Mocny rdzeń: częsta trójka (padła {self.triple_counter[triple]}x)"
                    elif base_choice == 2 and top_pairs:
                        pair = self.random.choice(top_pairs[:min(20, len(top_pairs))])
                        base_nums = list(pair)
                        reason = f"Mocny rdzeń: częsta para (padła {self.pair_counter[pair]}x)"
                    else:
                        base_nums = []
                        reason = "Ranking częstotliwość + rytm + układy"

                current = set(base_nums)

                if self.config.hot_pool >= 49:
                    working_pool = candidate_pool[:]
                    self.random.shuffle(working_pool)

                    for n in working_pool:
                        if len(current) >= NUMBERS_IN_DRAW:
                            break
                        current.add(n)

                    nums = sorted(current)

                elif self.config.hot_pool <= 0:
                    working_pool = candidate_pool[:]
                    self.random.shuffle(working_pool)

                    for n in working_pool:
                        if len(current) >= NUMBERS_IN_DRAW:
                            break
                        current.add(n)

                    nums = sorted(current)

                else:
                    hot_candidates = hot_numbers[:]
                    self.random.shuffle(hot_candidates)

                    for n in hot_candidates:
                        if len(current) >= NUMBERS_IN_DRAW:
                            break
                        current.add(n)

                    if len(current) < NUMBERS_IN_DRAW:
                        remaining = [n for n in ranked_numbers if n not in current]
                        self.random.shuffle(remaining)
                        for n in remaining:
                            if len(current) >= NUMBERS_IN_DRAW:
                                break
                            current.add(n)

                    nums = sorted(current)

                repair_attempts = 0
                while not self.validate_ticket(nums) and repair_attempts < 30:
                    repair_attempts += 1
                    current = set(base_nums)

                    if self.config.hot_pool >= 49:
                        repair_pool = candidate_pool[:]
                    elif self.config.hot_pool <= 0:
                        repair_pool = candidate_pool[:]
                    else:
                        repair_pool = hot_numbers[:]

                    self.random.shuffle(repair_pool)

                    for n in repair_pool:
                        if len(current) >= NUMBERS_IN_DRAW:
                            break
                        current.add(n)

                    if len(current) < NUMBERS_IN_DRAW and self.config.hot_pool not in (0, 49):
                        remaining = [n for n in ranked_numbers if n not in current]
                        self.random.shuffle(remaining)
                        for n in remaining:
                            if len(current) >= NUMBERS_IN_DRAW:
                                break
                            current.add(n)

                    nums = sorted(current)

                    if len(nums) != NUMBERS_IN_DRAW:
                        continue

                if not self.validate_ticket(nums):
                    continue

                ticket_tuple = tuple(nums)
                if ticket_tuple in seen_tickets:
                    continue

                quality = self.ticket_quality_score(nums, number_scores)

                for existing in seen_tickets:
                    overlap = len(set(existing) & set(nums))
                    if overlap >= 5:
                        quality -= 1.2
                    elif overlap == 4:
                        quality -= 0.5

                if quality > best_score:
                    best_score = quality
                    best_ticket = nums
                    best_reason = reason

            if best_ticket is None:
                fallback_pool = candidate_pool[:] if candidate_pool else ranked_numbers[:]
                fallback = []

                for n in fallback_pool:
                    if len(fallback) < NUMBERS_IN_DRAW:
                        fallback.append(n)

                if len(fallback) < NUMBERS_IN_DRAW:
                    for n in ranked_numbers:
                        if n not in fallback and len(fallback) < NUMBERS_IN_DRAW:
                            fallback.append(n)

                best_ticket = sorted(fallback[:NUMBERS_IN_DRAW])

                if self.config.hot_pool >= 49:
                    best_reason = "Awaryjny kupon wyłącznie z puli gorących liczb"
                elif self.config.hot_pool <= 0:
                    best_reason = "Awaryjny kupon wyłącznie z puli zimnych liczb"
                else:
                    best_reason = "Awaryjny kupon z najwyżej punktowanych liczb"

            seen_tickets.add(tuple(best_ticket))

            if self.config.hot_pool >= 49:
                geneza_prefix = "Tryb: tylko gorące liczby"
            elif self.config.hot_pool <= 0:
                geneza_prefix = "Tryb: tylko zimne liczby"
            else:
                geneza_prefix = f"Tryb: top {self.config.hot_pool} gorących"

            results.append({
                "Kupon": str(len(results)),
                "Liczby Lotto 6/49": format_number_list(best_ticket),
                "Suma": sum(best_ticket),
                "Parzyste": count_even(best_ticket),
                "Seria kolejnych": max_consecutive_run(best_ticket),
                "Geneza": f"{geneza_prefix} | {best_reason}",
            })

        for row in results:
            row["Kupon"] = str(row["Kupon"])

        return results[:count]

    def get_number_analysis_table(self) -> List[Dict]:
        scores = self.compute_number_scores()
        ranked_numbers = [n for n, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]

        hot_set = set()
        cold_set = set()

        if self.config.hot_pool >= 49:
            hot_set = set(ranked_numbers)
        elif self.config.hot_pool <= 0:
            cold_set = set(ranked_numbers)
        else:
            hot_set = set(ranked_numbers[:self.config.hot_pool])
            cold_set = set(ranked_numbers[self.config.hot_pool:])

        rows = []

        for n in range(LOTTO_MIN, LOTTO_MAX + 1):
            if n in hot_set:
                temp_class = "🔥 GORĄCA"
            elif n in cold_set:
                temp_class = "🧊 ZIMNA"
            else:
                temp_class = "-"

            rows.append({
                "Liczba": format_num(n),
                "Trafienia": self.number_counter[n],
                "Częstotliwość %": round(safe_percent(self.number_counter[n], self.total_draws), 2),
                "Średni odstęp": round(self.intervals[n]["avg_gap"], 2),
                "Najczęstszy odstęp": self.intervals[n]["most_common_gap"],
                "Aktualny odstęp": self.intervals[n]["current_gap"],
                "Wsp. spóźnienia": round(self.intervals[n]["overdue_factor"], 2),
                "Wynik AI": round(scores[n], 4),
                "W rytmie": "✅ TAK" if self.intervals[n]["most_common_gap"] > 0 and self.intervals[n]["current_gap"] == self.intervals[n]["most_common_gap"] else "❌ NIE",
                "Klasa": temp_class,
            })

        rows.sort(key=lambda x: x["Wynik AI"], reverse=True)
        return rows

    def get_top_patterns_table(self) -> Dict[str, List[Dict]]:
        pairs = []
        for pair, cnt in self.pair_counter.most_common(20):
            pairs.append({
                "Para": format_number_list(list(pair)),
                "Wystąpienia": cnt
            })

        triples = []
        for triple, cnt in self.triple_counter.most_common(20):
            triples.append({
                "Trójka": format_number_list(list(triple)),
                "Wystąpienia": cnt
            })

        quads = []
        for quad, cnt in self.quad_counter.most_common(15):
            quads.append({
                "Czwórka": format_number_list(list(quad)),
                "Wystąpienia": cnt
            })

        return {
            "pairs": pairs,
            "triples": triples,
            "quads": quads
        }


# ============================================================
# UI / STYL
# ============================================================

def inject_custom_css():
    st.markdown(
        """
        <style>
        .main {
            background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
            color: #e5e7eb;
        }

        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2rem;
            max-width: 1400px;
        }

        h1, h2, h3 {
            color: #f8fafc !important;
        }

        .app-card {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 16px 18px;
            margin-bottom: 14px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.18);
        }

        .small-note {
            color: #cbd5e1;
            font-size: 0.95rem;
            line-height: 1.5;
        }

        div[data-testid="stMetric"] {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.07);
            padding: 12px;
            border-radius: 16px;
        }

        .stButton > button {
            border-radius: 14px;
            padding: 0.7rem 1rem;
            border: 1px solid rgba(255,255,255,0.08);
            font-weight: 700;
        }

        .stDownloadButton > button {
            border-radius: 14px;
            padding: 0.7rem 1rem;
            font-weight: 700;
        }

        div[data-baseweb="tab-list"] {
            gap: 10px;
        }

        button[data-baseweb="tab"] {
            border-radius: 12px !important;
            padding: 10px 14px !important;
            background: rgba(255,255,255,0.04) !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )


def render_header():
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    st.markdown(
        """
        <div class="app-card">
            <div class="small-note">
                Ta aplikacja analizuje historię losowań Lotto 6/49 z pliku PDF, wyciąga częste układy,
                sprawdza rytm występowania liczb, analizuje gorące i zimne liczby oraz potrafi
                zbudować zestaw metodą <b>Bystrzachy</b> na podstawie zmian pozycyjnych między kolejnymi losowaniami.
                <br><br>
                <b>Ważne:</b> to nie jest gwarancja wygranej. To rozbudowany generator statystyczno-historyczny,
                który tworzy sensowne, uporządkowane kupony zamiast całkowicie przypadkowych zestawów.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_sidebar() -> Tuple[int, int, AnalyzerConfig]:
    st.sidebar.header("⚙️ Ustawienia")

    max_draws = st.sidebar.number_input(
        "Maksymalna liczba losowań do analizy",
        min_value=50,
        max_value=5000,
        value=MAX_DRAWS_DEFAULT,
        step=1,
        help="Im więcej losowań, tym szersza historia."
    )

    tickets_count = st.sidebar.number_input(
        "Ile kuponów wygenerować?",
        min_value=1,
        max_value=20,
        value=DEFAULT_TICKETS_COUNT,
        step=1
    )

    st.sidebar.subheader("Zasady kuponu")
    rule_even_odd = st.sidebar.checkbox(
        "Wymuś balans parzyste/nieparzyste",
        value=True
    )

    rule_spread = st.sidebar.checkbox(
        "Wymuś rozsądny rozstrzał liczb",
        value=True
    )

    rule_sum_range = st.sidebar.checkbox(
        "Wymuś rozsądny zakres sumy",
        value=True
    )

    rule_avoid_last_draw_clone = st.sidebar.checkbox(
        "Nie powtarzaj dokładnie ostatniego losowania",
        value=True
    )

    st.sidebar.subheader("Silnik generatora")
    hot_pool = st.sidebar.slider(
        "Rozmiar puli najmocniejszych liczb",
        min_value=0,
        max_value=49,
        value=DEFAULT_HOT_POOL,
        step=1,
        help="0 = tylko zimne liczby, 49 = tylko gorące liczby, wartości pośrednie = top N gorących."
    )

    generation_attempts = st.sidebar.slider(
        "Liczba prób budowy każdego kuponu",
        min_value=500,
        max_value=12000,
        value=DEFAULT_GENERATION_ATTEMPTS,
        step=500
    )

    seed = st.sidebar.number_input(
        "Seed losowania pomocniczego",
        min_value=0,
        max_value=999999,
        value=DEFAULT_RANDOM_SEED,
        step=1
    )

    st.sidebar.subheader("🧠 Bystrzacha")
    enable_bystrzacha = st.sidebar.checkbox(
        "Włącz kupon Bystrzachy",
        value=DEFAULT_ENABLE_BYSTRZACHA,
        help="Analiza zmian pozycyjnych między kolejnymi losowaniami."
    )

    bystrzacha_top_deltas = st.sidebar.slider(
        "Ile najmocniejszych zmian pozycyjnych brać pod uwagę?",
        min_value=3,
        max_value=20,
        value=DEFAULT_BYSTRZACHA_TOP_DELTAS,
        step=1,
        help="Dla każdej z 6 pozycji Bystrzacha bierze pod uwagę top N najczęstszych zmian w górę lub w dół."
    )

    if hot_pool == 49:
        st.sidebar.success("Tryb aktywny: losowanie tylko z gorących liczb.")
    elif hot_pool == 0:
        st.sidebar.warning("Tryb aktywny: losowanie tylko z zimnych liczb.")
    else:
        st.sidebar.info(f"Tryb aktywny: top {hot_pool} gorących liczb.")

    if enable_bystrzacha:
        st.sidebar.success("Bystrzacha aktywna: będzie liczony kupon pozycyjny.")
    else:
        st.sidebar.info("Bystrzacha wyłączona.")

    config = AnalyzerConfig(
        weight_freq=DEFAULT_WEIGHT_FREQ,
        weight_recency=DEFAULT_WEIGHT_RECENCY,
        weight_rhythm=DEFAULT_WEIGHT_RHYTHM,
        weight_pair=DEFAULT_WEIGHT_PAIR,
        weight_triple=DEFAULT_WEIGHT_TRIPLE,
        weight_overdue=DEFAULT_WEIGHT_OVERDUE,
        hot_pool=hot_pool,
        generation_attempts=generation_attempts,
        seed=seed,
        rule_force_even_odd=rule_even_odd,
        rule_force_spread=rule_spread,
        rule_force_sum_range=rule_sum_range,
        rule_avoid_last_draw_clone=rule_avoid_last_draw_clone,
        enable_bystrzacha=enable_bystrzacha,
        bystrzacha_top_deltas=bystrzacha_top_deltas,
    )

    return int(max_draws), int(tickets_count), config


def render_file_input():
    st.subheader("📄 Plik wejściowy PDF")

    uploaded = st.file_uploader(
        "Wgraj plik wyniki.pdf z historią Lotto",
        type=["pdf"]
    )

    use_local_file = st.checkbox(
        "Użyj lokalnego pliku wyniki.pdf, jeśli nic nie wgrano",
        value=True
    )

    col1, col2 = st.columns(2)
    with col1:
        st.info("Format docelowy: Lotto 6/49, 6 liczb w wierszu, osobne 4-cyfrowe ID losowań.")
    with col2:
        st.info("Parser ignoruje stopki typu „www.multipasko.pl © 2004 - 2026”.")

    return uploaded, use_local_file


def render_overview(analyzer: LottoAnalyzer, diagnostics: Dict):
    st.subheader("📊 Podsumowanie analizy")

    newest_with_id = next((d.draw_id for d in analyzer.draws if d.draw_id is not None), "-")
    oldest_with_id = next((d.draw_id for d in reversed(analyzer.draws) if d.draw_id is not None), "-")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Przeanalizowane losowania", analyzer.total_draws)
    c2.metric("Najnowsze ID", newest_with_id)
    c3.metric("Najstarsze ID", oldest_with_id)
    c4.metric("Strony PDF", diagnostics.get("pages_total", "-"))

    st.markdown("### Ostatnie losowania")
    recent_df = pd.DataFrame(analyzer.get_recent_draws_table(15))
    st.dataframe(recent_df, width="stretch", height=420)

    st.markdown("### Informacja o parserze")
    st.success(
        "Parser korzysta z metody tekstowej opartej o page.get_text('text'), tak jak w sprawdzonym kodzie."
    )


def render_generated_tickets(analyzer: LottoAnalyzer, tickets_count: int):
    st.subheader("🎟️ Inteligentne kupony Lotto 6/49")

    st.markdown(
        """
        <div class="app-card">
            <div class="small-note">
                Generator:
                <br>• szuka częstych par, trójek i czwórek,
                <br>• sprawdza rytmikę liczb,
                <br>• buduje rdzeń kuponu na podstawie historii,
                <br>• dopełnia go najsilniejszymi liczbami,
                <br>• odrzuca układy skrajne,
                <br>• może działać w trybie wyłącznie gorących albo wyłącznie zimnych liczb,
                <br>• może też dodać kupon <b>Bystrzachy</b>, liczony po zmianach pozycyjnych.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    tickets = analyzer.generate_smart_tickets(tickets_count)
    tickets_df = pd.DataFrame(tickets)

    if "Kupon" in tickets_df.columns:
        tickets_df["Kupon"] = tickets_df["Kupon"].astype(str)

    st.dataframe(tickets_df, width="stretch", height=420)

    txt_content = "=== TWOJE KUPONY LOTTO PRO ===\n\n"
    for row in tickets:
        txt_content += f"Kupon {row['Kupon']}:\n"
        txt_content += f"Liczby Lotto 6/49: {row['Liczby Lotto 6/49']}\n"
        txt_content += f"Suma: {row['Suma']}\n"
        txt_content += f"Parzyste: {row['Parzyste']}\n"
        txt_content += f"Najdłuższa seria kolejnych: {row['Seria kolejnych']}\n"
        txt_content += f"Geneza: {row['Geneza']}\n\n"

    st.download_button(
        label="📥 Pobierz kupony do pliku TXT",
        data=txt_content,
        file_name="kupony_lotto_pro.txt",
        mime="text/plain",
        type="primary"
    )


def render_numbers_analysis(analyzer: LottoAnalyzer):
    st.subheader("🔢 Analiza liczb 1–49")

    table = analyzer.get_number_analysis_table()
    table_df = pd.DataFrame(table)
    st.dataframe(table_df, width="stretch", height=650)


def render_patterns(analyzer: LottoAnalyzer):
    st.subheader("🧩 Najczęstsze układy historyczne")

    patterns = analyzer.get_top_patterns_table()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### Najczęstsze pary")
        st.dataframe(pd.DataFrame(patterns["pairs"]), width="stretch", height=420)

    with col2:
        st.markdown("### Najczęstsze trójki")
        st.dataframe(pd.DataFrame(patterns["triples"]), width="stretch", height=420)

    with col3:
        st.markdown("### Najczęstsze czwórki")
        st.dataframe(pd.DataFrame(patterns["quads"]), width="stretch", height=420)


def render_bystrzacha(analyzer: LottoAnalyzer):
    st.subheader("🧠 Bystrzacha — analiza zmian pozycyjnych")

    st.markdown(
        """
        <div class="app-card">
            <div class="small-note">
                Bystrzacha analizuje każdą pozycję osobno:
                <br>• pozycja 1 → jak najczęściej zmieniała się 1. liczba między kolejnymi losowaniami,
                <br>• pozycja 2 → jak zmieniała się 2. liczba,
                <br>• ...
                <br>• pozycja 6 → jak zmieniała się 6. liczba.
                <br><br>
                Przykład:
                jeśli w jednym losowaniu na danej pozycji było 04, a w następnym 12,
                to delta wynosi <b>+8</b>.
                Jeśli takie przejście powtarzało się często, Bystrzacha bierze je pod uwagę przy typowaniu.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    bystrzacha_ticket = analyzer.generate_bystrzacha_ticket()

    st.markdown("### Kupon Bystrzachy")
    bystrzacha_df = pd.DataFrame([bystrzacha_ticket])
    st.dataframe(bystrzacha_df, width="stretch", height=140)

    st.markdown("### Analiza pozycji 1–6")
    table = analyzer.get_bystrzacha_analysis_table()
    st.dataframe(pd.DataFrame(table), width="stretch", height=420)


def render_diagnostics(diagnostics: Dict):
    st.subheader("🛠️ Diagnostyka parsowania PDF")

    col1, col2, col3 = st.columns(3)
    col1.metric("Losowania przed deduplikacją", diagnostics.get("draws_total_before_dedup", 0))
    col2.metric("Losowania po deduplikacji", diagnostics.get("draws_total_after_dedup", 0))
    col3.metric("Liczba stron", diagnostics.get("pages_total", 0))

    st.markdown("### Szczegóły parsera")
    st.dataframe(pd.DataFrame(diagnostics.get("pages", [])), width="stretch", height=520)

    with st.expander("Podgląd pełnej diagnostyki parsera"):
        st.json(diagnostics)


# ============================================================
# GŁÓWNA FUNKCJA
# ============================================================

def main():
    st.set_page_config(
        page_title=APP_TITLE,
        layout="wide",
        initial_sidebar_state="expanded"
    )

    inject_custom_css()
    render_header()

    max_draws, tickets_count, analyzer_config = render_sidebar()
    uploaded_file, use_local_file = render_file_input()

    pdf_source = resolve_pdf_source(uploaded_file, DEFAULT_PDF) if (uploaded_file is not None or use_local_file) else None

    if pdf_source is None:
        st.warning("Wgraj plik PDF albo umieść lokalnie plik 'wyniki.pdf' obok aplikacji.")
        st.stop()

    if not st.button("🚀 Analizuj plik i wygeneruj kupony", type="primary"):
        st.stop()

    try:
        with st.spinner("Trwa analiza historii Lotto i budowa modeli statystycznych..."):
            draws, diagnostics = parse_lotto_pdf(pdf_source, max_draws=max_draws)
            analyzer = LottoAnalyzer(draws, analyzer_config)

        tabs = st.tabs([
            "📊 Podsumowanie",
            "🎟️ Kupony",
            "🧠 Bystrzacha",
            "🔢 Liczby 1–49",
            "🧩 Układy historyczne",
            "🛠️ Diagnostyka"
        ])

        with tabs[0]:
            render_overview(analyzer, diagnostics)

        with tabs[1]:
            render_generated_tickets(analyzer, tickets_count)

        with tabs[2]:
            render_bystrzacha(analyzer)

        with tabs[3]:
            render_numbers_analysis(analyzer)

        with tabs[4]:
            render_patterns(analyzer)

        with tabs[5]:
            render_diagnostics(diagnostics)

    except Exception as e:
        st.error(f"Wystąpił błąd podczas analizy: {e}")
        st.stop()


if __name__ == "__main__":
    main()
