import io
import os
import re
import math
import random
import itertools
from dataclasses import dataclass
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Optional

import fitz  # PyMuPDF
import streamlit as st


# ============================================================
# KONFIGURACJA APLIKACJI
# ============================================================

APP_TITLE = "🎯 Generator Lotto PRO"
APP_SUBTITLE = "Analiza PDF + rytmika liczb + powtarzalne układy historyczne + inteligentne kupony Lotto 6/49"

DEFAULT_PDF = "wyniki.pdf"

LOTTO_MIN = 1
LOTTO_MAX = 49
NUMBERS_IN_DRAW = 6

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


# ============================================================
# MODELE DANYCH
# ============================================================

@dataclass
class Draw:
    """
    Reprezentuje jedno losowanie Lotto.
    """
    draw_id: int
    numbers: List[int]


@dataclass
class AnalyzerConfig:
    """
    Zbiór ustawień sterujących analizą i generowaniem kuponów.
    """
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


# ============================================================
# FUNKCJE POMOCNICZE
# ============================================================

def safe_percent(part: int, whole: int) -> float:
    """
    Zwraca procent z zabezpieczeniem przed dzieleniem przez zero.
    """
    if whole == 0:
        return 0.0
    return (part / whole) * 100.0


def format_num(n: int) -> str:
    """
    Zamienia liczbę na zapis dwucyfrowy, np. 3 -> 03.
    """
    return f"{n:02d}"


def format_number_list(nums: List[int]) -> str:
    """
    Formatuje listę liczb do czytelnego zapisu.
    """
    return " ".join(format_num(n) for n in sorted(nums))


def count_even(nums: List[int]) -> int:
    """
    Zlicza ile liczb parzystych znajduje się w zestawie.
    """
    return sum(1 for n in nums if n % 2 == 0)


def max_consecutive_run(nums: List[int]) -> int:
    """
    Zwraca długość najdłuższej serii kolejnych liczb.
    Np. dla [3,4,5,11,20,21] wynik to 3.
    """
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
    """
    Zamienia słownik wartości na z-score.
    Dzięki temu różne metryki można łatwiej porównywać i łączyć.
    """
    if not values_dict:
        return {}

    values = list(values_dict.values())
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)

    if std == 0:
        return {k: 0.0 for k in values_dict}

    return {k: (v - mean) / std for k, v in values_dict.items()}


def min_max_normalize(values_dict: Dict[int, float]) -> Dict[int, float]:
    """
    Normalizuje wartości do zakresu 0..1.
    """
    if not values_dict:
        return {}

    vals = list(values_dict.values())
    vmin = min(vals)
    vmax = max(vals)

    if vmax == vmin:
        return {k: 0.0 for k in values_dict}

    return {k: (v - vmin) / (vmax - vmin) for k, v in values_dict.items()}


def make_bytesio_from_upload(uploaded_file) -> io.BytesIO:
    """
    Zamienia plik wgrany przez użytkownika do pamięci BytesIO.
    """
    if uploaded_file is None:
        raise ValueError("Nie przesłano pliku PDF.")
    return io.BytesIO(uploaded_file.read())


def open_pdf_document(pdf_source):
    """
    Otwiera dokument PDF z:
    - ścieżki pliku,
    - bytes,
    - BytesIO.
    """
    if isinstance(pdf_source, str):
        if not os.path.exists(pdf_source):
            raise FileNotFoundError(f"Nie znaleziono pliku: {pdf_source}")
        return fitz.open(pdf_source)

    if isinstance(pdf_source, bytes):
        return fitz.open(stream=pdf_source, filetype="pdf")

    if isinstance(pdf_source, io.BytesIO):
        return fitz.open(stream=pdf_source.getvalue(), filetype="pdf")

    raise TypeError("Nieobsługiwany typ źródła PDF.")


# ============================================================
# PARSER PDF DLA PLIKU LOTTO Z MULTIPASKO
# ============================================================

def is_footer_line(line: str) -> bool:
    """
    Sprawdza, czy linia wygląda na stopkę strony / zbędny tekst.
    """
    low = line.lower().strip()
    if not low:
        return True

    footer_patterns = [
        "www.multipasko.pl",
        "multipasko.pl",
        "copyright",
        "©",
        "lotto 6/49",
    ]

    return any(p in low for p in footer_patterns)


def extract_numeric_tokens(line: str) -> List[str]:
    """
    Wyciąga wszystkie samodzielne liczby z linii tekstu.
    """
    return re.findall(r"\b\d+\b", line)


def parse_lotto_pdf(pdf_source, max_draws: int = 999) -> Tuple[List[Draw], Dict]:
    """
    Parser dostosowany do pliku wyniki.pdf w układzie Multipasko.

    Założenia tego konkretnego formatu:
    1. Na każdej stronie najpierw występują wiersze z 6 liczbami losowań.
    2. Poniżej znajdują się numery losowań (4-cyfrowe), po jednym w linii.
    3. Ostatnia strona może zawierać stopkę typu:
       www.multipasko.pl © 2004 - 2026
    4. Najnowsze losowania są u góry.
    """
    doc = open_pdf_document(pdf_source)

    parsed_draws: List[Draw] = []
    diagnostics_pages = []

    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            raw_text = page.get_text("text")
            raw_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

            numbers_rows: List[List[int]] = []
            draw_ids: List[int] = []

            for line in raw_lines:
                if is_footer_line(line):
                    continue

                tokens = extract_numeric_tokens(line)
                if not tokens:
                    continue

                # Wiersz z 6 liczbami Lotto
                if len(tokens) == 6:
                    nums = [int(t) for t in tokens]
                    if all(LOTTO_MIN <= n <= LOTTO_MAX for n in nums):
                        if len(set(nums)) == NUMBERS_IN_DRAW:
                            numbers_rows.append(sorted(nums))
                            continue

                # Linia z numerem losowania
                if len(tokens) == 1 and len(tokens[0]) == 4:
                    val = int(tokens[0])
                    if 1000 <= val <= 9999:
                        draw_ids.append(val)
                        continue

            pair_count = min(len(numbers_rows), len(draw_ids))

            page_draws = []
            for i in range(pair_count):
                page_draws.append(Draw(draw_id=draw_ids[i], numbers=numbers_rows[i]))

            parsed_draws.extend(page_draws)

            diagnostics_pages.append({
                "page": page_index + 1,
                "numbers_rows_found": len(numbers_rows),
                "draw_ids_found": len(draw_ids),
                "paired_rows": pair_count,
                "unpaired_number_rows": max(0, len(numbers_rows) - pair_count),
                "unpaired_draw_ids": max(0, len(draw_ids) - pair_count),
            })

        # Usuwanie ewentualnych duplikatów numerów losowań
        dedup: Dict[int, Draw] = {}
        for d in parsed_draws:
            if d.draw_id not in dedup:
                dedup[d.draw_id] = d

        draws = sorted(dedup.values(), key=lambda x: x.draw_id, reverse=True)[:max_draws]

        if not draws:
            raise ValueError("Parser nie odczytał żadnych poprawnych losowań z PDF.")

        diagnostics = {
            "pages_total": len(doc),
            "draws_total_before_dedup": len(parsed_draws),
            "draws_total_after_dedup": len(draws),
            "newest_draw_id": draws[0].draw_id if draws else None,
            "oldest_draw_id": draws[-1].draw_id if draws else None,
            "pages": diagnostics_pages,
        }

        return draws, diagnostics

    finally:
        doc.close()


# ============================================================
# ANALIZATOR LOTTO
# ============================================================

class LottoAnalyzer:
    """
    Główna klasa odpowiedzialna za:
    - analizę częstotliwości,
    - analizę odstępów / rytmów,
    - analizę par i trójek,
    - tworzenie inteligentnych kuponów.
    """

    def __init__(self, draws: List[Draw], config: AnalyzerConfig):
        self.draws = sorted(draws, key=lambda d: d.draw_id, reverse=True)
        self.total_draws = len(self.draws)
        self.config = config
        self.random = random.Random(config.seed)

        self.number_counter = Counter()
        self.pair_counter = Counter()
        self.triple_counter = Counter()
        self.quad_counter = Counter()
        self.position_counter = [Counter() for _ in range(NUMBERS_IN_DRAW)]

        self.last_seen_index: Dict[int, int] = {}
        self.intervals = {}

        self._analyze()
        self.intervals = self._analyze_intervals()

    def _analyze(self):
        """
        Buduje wszystkie główne statystyki na podstawie historii losowań.
        """
        for draw_idx, draw in enumerate(self.draws):
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
        """
        Analizuje odstępy pomiędzy wystąpieniami każdej liczby.
        Dzięki temu można sprawdzić:
        - jaki odstęp pojawia się najczęściej,
        - jak dawno liczba nie padła,
        - czy liczba jest 'w rytmie'.
        """
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

    def get_last_draw(self) -> Optional[Draw]:
        """
        Zwraca najnowsze losowanie.
        """
        return self.draws[0] if self.draws else None

    def get_recent_draws_table(self, limit: int = 15) -> List[Dict]:
        """
        Zwraca tabelę ostatnich losowań do wyświetlenia w UI.
        """
        rows = []
        for d in self.draws[:limit]:
            rows.append({
                "ID losowania": d.draw_id,
                "Liczby": format_number_list(d.numbers)
            })
        return rows

    def compute_number_scores(self) -> Dict[int, float]:
        """
        Wylicza łączny wynik punktowy każdej liczby.
        Wynik bazuje na:
        - częstotliwości,
        - świeżości / obecności w nowszej historii,
        - parach i trójkach,
        - rytmice,
        - lekkim bonusie za liczby 'spóźnione'.
        """
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
        """
        Waliduje kupon Lotto według rozsądnych zasad estetyczno-statystycznych.
        Nie chodzi o 'gwarancję wygranej', tylko o sensowne ograniczenie skrajnych układów.
        """
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
        """
        Ocenia jakość całego kuponu.
        Im wyższy wynik, tym kupon jest ciekawszy według naszej metody.
        """
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

    def generate_smart_tickets(self, count: int = 6) -> List[Dict]:
        """
        Generuje inteligentne kupony Lotto.
        Strategia:
        1. Szukamy historycznych rdzeni: częste czwórki, trójki i pary.
        2. Dopełniamy je najlepiej punktowanymi liczbami.
        3. Sprawdzamy walidację.
        4. Zachowujemy różnorodność kuponów.
        """
        number_scores = self.compute_number_scores()
        ranked_numbers = [n for n, _ in sorted(number_scores.items(), key=lambda x: x[1], reverse=True)]
        hot_pool = ranked_numbers[:self.config.hot_pool]

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

        for ticket_index in range(count):
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

                hot_candidates = hot_pool[:]
                self.random.shuffle(hot_candidates)

                # Dopełnianie kuponu mieszanką top liczb i lekkiej losowości
                for n in hot_candidates:
                    if len(current) >= NUMBERS_IN_DRAW:
                        break
                    current.add(n)

                if len(current) < NUMBERS_IN_DRAW:
                    remaining = [n for n in range(LOTTO_MIN, LOTTO_MAX + 1) if n not in current]
                    self.random.shuffle(remaining)
                    for n in remaining:
                        if len(current) >= NUMBERS_IN_DRAW:
                            break
                        current.add(n)

                nums = sorted(current)

                # Korekta, gdy zestaw jest niewalidny
                repair_attempts = 0
                while not self.validate_ticket(nums) and repair_attempts < 30:
                    repair_attempts += 1

                    current = set(base_nums)

                    weighted_candidates = hot_pool[:]
                    self.random.shuffle(weighted_candidates)

                    filler_count = NUMBERS_IN_DRAW - len(current)
                    for n in weighted_candidates:
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

                # Lekka kara za zbyt duże podobieństwo do już wybranych kuponów
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

            # Awaryjnie: jeśli coś poszło nie tak, generujemy prostszy kupon
            if best_ticket is None:
                fallback = []
                for n in ranked_numbers:
                    if len(fallback) < NUMBERS_IN_DRAW:
                        fallback.append(n)
                best_ticket = sorted(fallback[:NUMBERS_IN_DRAW])
                best_reason = "Awaryjny kupon z najwyżej punktowanych liczb"

            seen_tickets.add(tuple(best_ticket))

            results.append({
                "Kupon": ticket_index + 1,
                "Liczby Lotto 6/49": format_number_list(best_ticket),
                "Suma": sum(best_ticket),
                "Parzyste": count_even(best_ticket),
                "Seria kolejnych": max_consecutive_run(best_ticket),
                "Geneza": best_reason,
            })

        return results

    def get_number_analysis_table(self) -> List[Dict]:
        """
        Zwraca tabelę analizy każdej liczby od 1 do 49.
        """
        scores = self.compute_number_scores()
        rows = []

        for n in range(LOTTO_MIN, LOTTO_MAX + 1):
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
            })

        rows.sort(key=lambda x: x["Wynik AI"], reverse=True)
        return rows

    def get_top_patterns_table(self) -> Dict[str, List[Dict]]:
        """
        Zwraca najczęstsze pary, trójki i czwórki.
        """
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
    """
    Dodaje własny styl CSS, aby aplikacja wyglądała nowocześnie i czytelnie.
    """
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

        .metric-box {
            background: linear-gradient(135deg, rgba(34,197,94,0.12), rgba(59,130,246,0.10));
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
            padding: 12px;
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
    """
    Renderuje nagłówek aplikacji.
    """
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    st.markdown(
        """
        <div class="app-card">
            <div class="small-note">
                Ta aplikacja analizuje historię losowań Lotto 6/49 z pliku PDF, wyciąga częste układy,
                sprawdza rytm występowania liczb i buduje inteligentne zestawy na podstawie historii.
                <br><br>
                <b>Ważne:</b> to nie jest gwarancja wygranej. To rozbudowany generator statystyczno-historyczny,
                który tworzy sensowne, uporządkowane kupony zamiast całkowicie przypadkowych zestawów.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_sidebar() -> Tuple[int, int, AnalyzerConfig]:
    """
    Renderuje panel boczny z ustawieniami użytkownika.
    """
    st.sidebar.header("⚙️ Ustawienia")

    max_draws = st.sidebar.number_input(
        "Maksymalna liczba losowań do analizy",
        min_value=50,
        max_value=5000,
        value=MAX_DRAWS_DEFAULT,
        step=1,
        help="Im więcej losowań, tym szersza historia. Dla tego pliku zwykle będzie to maksymalnie tyle, ile odczyta parser."
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
        value=True,
        help="Dopuszcza układ 2/4, 3/3 albo 4/2."
    )

    rule_spread = st.sidebar.checkbox(
        "Wymuś rozsądny rozstrzał liczb",
        value=True,
        help="Pilnuje, aby różnica między najmniejszą a największą liczbą nie była zbyt mała."
    )

    rule_sum_range = st.sidebar.checkbox(
        "Wymuś rozsądny zakres sumy",
        value=True,
        help="Odrzuca bardzo skrajne kupony o nienaturalnie niskiej lub wysokiej sumie."
    )

    rule_avoid_last_draw_clone = st.sidebar.checkbox(
        "Nie powtarzaj dokładnie ostatniego losowania",
        value=True
    )

    st.sidebar.subheader("Silnik generatora")
    hot_pool = st.sidebar.slider(
        "Rozmiar puli najmocniejszych liczb",
        min_value=12,
        max_value=35,
        value=DEFAULT_HOT_POOL,
        step=1
    )

    generation_attempts = st.sidebar.slider(
        "Liczba prób budowy każdego kuponu",
        min_value=500,
        max_value=12000,
        value=DEFAULT_GENERATION_ATTEMPTS,
        step=500,
        help="Więcej prób = lepsza selekcja, ale dłuższe liczenie."
    )

    seed = st.sidebar.number_input(
        "Seed losowania pomocniczego",
        min_value=0,
        max_value=999999,
        value=DEFAULT_RANDOM_SEED,
        step=1
    )

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
    )

    return int(max_draws), int(tickets_count), config


def render_file_input():
    """
    Renderuje sekcję wyboru pliku PDF.
    """
    st.subheader("📄 Plik wejściowy PDF")

    uploaded = st.file_uploader(
        "Wgraj plik wyniki.pdf z historią Lotto",
        type=["pdf"],
        help="Aplikacja jest przygotowana pod plik PDF w układzie podobnym do Multipasko Lotto 6/49."
    )

    use_local_file = st.checkbox(
        "Użyj lokalnego pliku wyniki.pdf, jeśli nic nie wgrano",
        value=True
    )

    col1, col2 = st.columns(2)
    with col1:
        st.info("Format docelowy: Lotto 6/49, 6 liczb w wierszu, numery losowań poniżej na stronie.")
    with col2:
        st.info("Parser ignoruje stopki typu „www.multipasko.pl © 2004 - 2026”.")

    return uploaded, use_local_file


def resolve_pdf_source(uploaded_file, default_path: str):
    """
    Wybiera źródło PDF:
    - wgrany plik,
    - lokalny plik z dysku,
    - None, jeśli nic nie ma.
    """
    if uploaded_file is not None:
        return make_bytesio_from_upload(uploaded_file)

    if os.path.exists(default_path):
        return default_path

    return None


def render_overview(analyzer: LottoAnalyzer, diagnostics: Dict):
    """
    Zakładka przeglądowa z najważniejszymi informacjami.
    """
    st.subheader("📊 Podsumowanie analizy")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Przeanalizowane losowania", analyzer.total_draws)
    c2.metric("Najnowsze ID", analyzer.draws[0].draw_id if analyzer.draws else "-")
    c3.metric("Najstarsze ID", analyzer.draws[-1].draw_id if analyzer.draws else "-")
    c4.metric("Strony PDF", diagnostics.get("pages_total", "-"))

    st.markdown("### Ostatnie losowania")
    st.dataframe(analyzer.get_recent_draws_table(15), use_container_width=True, height=420)

    st.markdown("### Informacja o parserze")
    st.success(
        "Parser działa bez OCR, więc jest szybki i stabilny. "
        "Czyta tekst bezpośrednio z PDF i łączy wiersze z liczbami z odpowiadającymi im numerami losowań."
    )


def render_generated_tickets(analyzer: LottoAnalyzer, tickets_count: int):
    """
    Zakładka z wygenerowanymi kuponami.
    """
    st.subheader("🎟️ Inteligentne kupony Lotto 6/49")

    st.markdown(
        """
        <div class="app-card">
            <div class="small-note">
                Generator działa w kilku krokach:
                <br>• szuka par, trójek i czwórek, które historycznie lubiły wypadać razem,
                <br>• sprawdza częstotliwość i rytmikę każdej liczby,
                <br>• buduje rdzeń kuponu z układów historycznych,
                <br>• dopełnia kupon najmocniejszymi liczbami,
                <br>• odrzuca zestawy zbyt skrajne lub mało sensowne.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    tickets = analyzer.generate_smart_tickets(tickets_count)
    st.dataframe(tickets, use_container_width=True, height=420)

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
    """
    Zakładka z pełną analizą liczb 1..49.
    """
    st.subheader("🔢 Analiza liczb 1–49")

    st.markdown(
        """
        <div class="app-card">
            <div class="small-note">
                <b>Wynik AI</b> to łączna ocena liczby oparta na:
                częstotliwości, świeżości w nowszych losowaniach, parach, trójkach, rytmice i lekkim bonusie za spóźnienie.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    table = analyzer.get_number_analysis_table()
    st.dataframe(table, use_container_width=True, height=650)


def render_patterns(analyzer: LottoAnalyzer):
    """
    Zakładka z najczęstszymi układami historycznymi.
    """
    st.subheader("🧩 Najczęstsze układy historyczne")

    patterns = analyzer.get_top_patterns_table()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### Najczęstsze pary")
        st.dataframe(patterns["pairs"], use_container_width=True, height=420)

    with col2:
        st.markdown("### Najczęstsze trójki")
        st.dataframe(patterns["triples"], use_container_width=True, height=420)

    with col3:
        st.markdown("### Najczęstsze czwórki")
        st.dataframe(patterns["quads"], use_container_width=True, height=420)


def render_diagnostics(diagnostics: Dict):
    """
    Zakładka diagnostyczna pokazująca jak parser odczytał plik.
    """
    st.subheader("🛠️ Diagnostyka parsowania PDF")

    st.write("Ta sekcja pozwala szybko sprawdzić, czy plik został odczytany poprawnie.")

    col1, col2, col3 = st.columns(3)
    col1.metric("Losowania przed deduplikacją", diagnostics.get("draws_total_before_dedup", 0))
    col2.metric("Losowania po deduplikacji", diagnostics.get("draws_total_after_dedup", 0))
    col3.metric("Liczba stron", diagnostics.get("pages_total", 0))

    st.markdown("### Szczegóły stron")
    st.dataframe(diagnostics.get("pages", []), use_container_width=True, height=500)


# ============================================================
# GŁÓWNA FUNKCJA APLIKACJI
# ============================================================

def main():
    """
    Główna funkcja uruchamiająca aplikację Streamlit.
    """
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
            "🔢 Liczby 1–49",
            "🧩 Układy historyczne",
            "🛠️ Diagnostyka"
        ])

        with tabs[0]:
            render_overview(analyzer, diagnostics)

        with tabs[1]:
            render_generated_tickets(analyzer, tickets_count)

        with tabs[2]:
            render_numbers_analysis(analyzer)

        with tabs[3]:
            render_patterns(analyzer)

        with tabs[4]:
            render_diagnostics(diagnostics)

    except Exception as e:
        st.error(f"Wystąpił błąd podczas analizy: {e}")
        raise


if __name__ == "__main__":
    main()
