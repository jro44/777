import streamlit as st
import requests
from bs4 import BeautifulSoup
import random
import re
from collections import Counter
from datetime import datetime

# ==============================================================================
# ⚙️ KONFIGURACJA STRONY
# ==============================================================================

st.set_page_config(
    page_title="Saloon Lotto 777",
    page_icon="🤠",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==============================================================================
# 🎨 STYL WESTERN (CSS)
# ==============================================================================
st.markdown("""
    <style>
    /* TŁO I CZCIONKI */
    .stApp {
        background-color: #2b2118;
        background-image: radial-gradient(#3d2e22 2px, transparent 2px);
        background-size: 20px 20px;
        color: #f0e6d2;
        font-family: 'Courier New', Courier, monospace;
    }
    
    /* NAGŁÓWKI */
    h1, h2, h3 {
        color: #e6b800 !important;
        text-shadow: 2px 2px 0px #000;
        font-family: 'Georgia', serif;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    
    /* OSTRZEŻENIE */
    .wanted-poster {
        background-color: #fdf5e6;
        color: #3e2723;
        border: 4px solid #3e2723;
        padding: 15px;
        border-radius: 2px;
        font-family: 'Courier New', monospace;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 5px 5px 15px rgba(0,0,0,0.5);
        background-image: url("https://www.transparenttextures.com/patterns/aged-paper.png");
    }

    /* KULE */
    .ball {
        display: inline-flex;
        justify-content: center;
        align-items: center;
        width: 50px;
        height: 50px;
        border-radius: 50%;
        background: radial-gradient(circle at 30% 30%, #ffd700, #b8860b);
        color: #2b2118;
        font-weight: bold;
        font-size: 20px;
        border: 3px solid #5c4033;
        margin: 4px;
        box-shadow: 2px 4px 8px rgba(0,0,0,0.6);
        font-family: 'Arial', sans-serif;
    }
    .ball-euro {
        background: radial-gradient(circle at 30% 30%, #cd5c5c, #8b0000);
        color: white;
        border-color: #5c4033;
    }

    /* MASZYNA */
    .slot-machine {
        background-color: #4a3525;
        border: 8px solid #8B4513;
        border-radius: 15px;
        padding: 20px;
        box-shadow: inset 0 0 20px #000;
        text-align: center;
        margin-top: 20px;
    }
    
    /* PRZYCISK */
    div.stButton > button {
        background: linear-gradient(to bottom, #d4af37 5%, #a67c00 100%);
        background-color: #d4af37;
        border-radius: 10px;
        border: 2px solid #5c4033;
        color: #2b2118;
        font-family: 'Georgia', serif;
        font-weight: bold;
        font-size: 20px;
        padding: 10px 24px;
        text-shadow: 0px 1px 0px #ffffff;
        box-shadow: 0px 4px 0px #5c4033;
        transition: all 0.1s;
        width: 100%;
    }
    div.stButton > button:active {
        transform: translateY(4px);
        box-shadow: 0px 0px 0px #5c4033;
    }
    
    /* WYNIKI */
    .result-row {
        background-color: #3d2e22;
        padding: 10px;
        margin: 5px 0;
        border-left: 5px solid #e6b800;
        border-radius: 4px;
    }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 🤠 OSTRZEŻENIE NA START
# ==============================================================================

st.markdown("""
<div class="wanted-poster">
    <h3>⚠ OSTRZEŻENIE SZERYFA ⚠</h3>
    <p>Ta maszyna używa <b>szybkiego scrapingu</b> (Multipasko dla Keno/600),
    by zdobyć wyniki niemal natychmiast po losowaniu.</p>
    <p>Mimo to, pamiętaj: <b>Dom (Kasyno) zawsze ma przewagę.</b></p>
    <p>Aplikacja stosuje matematykę do redukcji ryzyka, ale nie gwarantuje wygranej.</p>
</div>
""", unsafe_allow_html=True)

# ==============================================================================
# 🧠 KONFIGURACJA GIER I URLI (HYBRYDA)
# ==============================================================================

GAME_CONFIG = {
    "Keno": {
        "url": "https://www.multipasko.pl/wyniki-keno/",
        "source": "multipasko",
        "range": 70, "pick": 10, "sum_min": 200, "sum_max": 500, "has_bonus": False
    },
    "Szybkie 600": {
        "url": "https://www.multipasko.pl/wyniki-szybkie-600/",
        "source": "multipasko",
        "range": 32, "pick": 6, "sum_min": 75, "sum_max": 125, "has_bonus": False
    },
    "Lotto": {
        "url": "https://www.wynikilotto.net.pl/lotto/wyniki/",
        "source": "standard",
        "range": 49, "pick": 6, "sum_min": 100, "sum_max": 200, "has_bonus": False
    },
    "Lotto Plus": {
        "url": "https://www.wynikilotto.net.pl/lotto-plus/wyniki/",
        "source": "standard",
        "range": 49, "pick": 6, "sum_min": 100, "sum_max": 200, "has_bonus": False
    },
    "Mini Lotto": {
        "url": "https://www.wynikilotto.net.pl/mini-lotto/wyniki/",
        "source": "standard",
        "range": 42, "pick": 5, "sum_min": 85, "sum_max": 135, "has_bonus": False
    },
    "EuroJackpot": {
        "url": "https://www.wynikilotto.net.pl/eurojackpot/wyniki/",
        "source": "standard",
        "range": 50, "pick": 5, "sum_min": 95, "sum_max": 160, 
        "has_bonus": True, "bonus_range": 12, "bonus_pick": 2
    },
    "Multi Multi": {
        "url": "https://www.wynikilotto.net.pl/multi-multi/wyniki/",
        "source": "standard",
        "range": 80, "pick": 10, "sum_min": 250, "sum_max": 550, "has_bonus": False
    },
    "Ekstra Pensja": {
        "url": "https://www.wynikilotto.net.pl/ekstra-pensja/wyniki/",
        "source": "standard",
        "range": 35, "pick": 5, "sum_min": 60, "sum_max": 120, 
        "has_bonus": True, "bonus_range": 4, "bonus_pick": 1
    }
}

# ==============================================================================
# 🔌 SCRAPER (INTELIGENTNE POBIERANIE)
# ==============================================================================

@st.cache_data(ttl=60) 
def fetch_from_scraper(game_name):
    config = GAME_CONFIG[game_name]
    url = config["url"]
    source_type = config["source"]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        draws = []
        
        # --- PARSER DLA MULTIPASKO (Keno / 600) ---
        if source_type == "multipasko":
            tables = soup.find_all('table')
            target_table = None
            
            for tab in tables:
                if "wyniki" in str(tab).lower() or len(tab.find_all('td')) > 20:
                    target_table = tab
                    break
            
            if target_table:
                rows = target_table.find_all('tr')
                for row in rows:
                    txt = row.get_text(separator=" ").strip()
                    nums_found = [int(s) for s in re.findall(r'\b\d+\b', txt)]
                    valid = [n for n in nums_found if 1 <= n <= config["range"]]
                    
                    if len(valid) >= config["pick"]:
                        if game_name == "Keno":
                             result = list(dict.fromkeys(valid[-20:]))
                        else:
                             result = valid[-config["pick"]:]
                        
                        if len(result) >= config["pick"]:
                            time_match = re.search(r'\d{2}:\d{2}', txt)
                            date_time = time_match.group(0) if time_match else "Dziś"
                            draws.append({
                                "date": date_time,
                                "numbers": result
                            })

        # --- PARSER STANDARDOWY (Reszta gier) ---
        else:
            rows = soup.find_all('tr')
            for row in rows:
                text = row.get_text(separator=' ')
                date_match = re.search(r'\d{2}\.\d{2}\.\d{4}', text)
                date_str = date_match.group(0) if date_match else "Data"
                
                numbers = [int(n) for n in re.findall(r'\b\d+\b', text)]
                valid_nums = [n for n in numbers if 1 <= n <= config["range"]]
                
                min_req = config["pick"] + (config["bonus_pick"] if config["has_bonus"] else 0)
                
                if len(valid_nums) >= min_req:
                    total_balls = config["pick"] + (config["bonus_pick"] if config["has_bonus"] else 0)
                    result = valid_nums[-total_balls:]
                    
                    if len(result) >= config["pick"]:
                        draws.append({
                            "date": date_str,
                            "numbers": result
                        })

        return draws, None

    except Exception as e:
        return [], f"Błąd scrapowania: {str(e)}"

# ==============================================================================
# 🎰 ALGORYTM SMART
# ==============================================================================

def smart_generator(draws, game_name):
    config = GAME_CONFIG[game_name]
    population = list(range(1, config["range"] + 1))
    
    # 1. Hot Numbers
    if draws:
        all_nums = [n for d in draws for n in d['numbers']]
        counts = Counter(all_nums)
        weights = [(counts.get(i, 0) + 1)**1.5 for i in population]
    else:
        weights = [1] * len(population)

    best_set = []
    
    # 2. Monte Carlo
    for _ in range(3000):
        candidates = set()
        while len(candidates) < config["pick"]:
            c = random.choices(population, weights=weights, k=1)[0]
            candidates.add(c)
        nums = sorted(list(candidates))
        
        # Filtry
        if game_name != "Keno":
            s_sum = sum(nums)
            if not (config["sum_min"] <= s_sum <= config["sum_max"]): continue
            
        even = sum(1 for n in nums if n % 2 == 0)
        if even == 0 or even == config["pick"]: continue
            
        cons = 0
        max_cons = 0
        for i in range(len(nums)-1):
            if nums[i+1] == nums[i] + 1: cons += 1
            else: cons = 0
            max_cons = max(max_cons, cons)
        
        if max_cons >= 2: continue
        
        best_set = nums
        break
        
    if not best_set:
        best_set = sorted(random.sample(population, config["pick"]))
        
    special_set = []
    if config["has_bonus"]:
        bonus_pop = list(range(1, config["bonus_range"] + 1))
        special_set = sorted(random.sample(bonus_pop, config["bonus_pick"]))
        
    return best_set, special_set

# ==============================================================================
# 🖥️ INTERFEJS
# ==============================================================================

tab_gen, tab_res = st.tabs(["🎰 GENERATOR 777", "📜 WYNIKI LIVE"])

# --- ZAKŁADKA 1 ---
with tab_gen:
    st.markdown("<h1 style='text-align: center;'>SALOON LOTTO 777</h1>", unsafe_allow_html=True)
    
    selected_game = st.selectbox("Wybierz grę:", list(GAME_CONFIG.keys()))
    source_info = "Źródło: Multipasko (Turbo)" if GAME_CONFIG[selected_game]["source"] == "multipasko" else "Źródło: Standard"
    
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        st.markdown(f"""
        <div class="slot-machine">
            <h2 style="margin:0;">{selected_game.upper()}</h2>
            <p style="color:#aaa;">{source_info}</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("🤠 POCIĄGNIJ DŹWIGNIĘ!", use_container_width=True):
            
            with st.spinner("Pobieranie najświeższych danych..."):
                draws, error = fetch_from_scraper(selected_game)
            
            if error:
                st.error(f"Problem: {error}")
            else:
                with st.spinner("Analiza statystyczna..."):
                    main_nums, spec_nums = smart_generator(draws, selected_game)
                
                st.markdown("<div style='text-align: center; margin-top: 20px;'>", unsafe_allow_html=True)
                
                html = ""
                for n in main_nums:
                    # UŻYWAMY BEZPIECZNEGO ZAPISU POTRÓJNEGO CUDZYSŁOWU
                    html += f"""<div class='ball'>{n}</div>"""
                st.markdown(html, unsafe_allow_html=True)
                
                if spec_nums:
                    st.markdown("<h3 style='margin:10px; color:#cd5c5c;'>+ BONUS +</h3>", unsafe_allow_html=True)
                    html_spec = ""
                    for n in spec_nums:
                        # UŻYWAMY BEZPIECZNEGO ZAPISU POTRÓJNEGO CUDZYSŁOWU
                        html_spec += f"""<div class='ball ball-euro'>{n}</div>"""
                    st.markdown(html_spec, unsafe_allow_html=True)
                    
                st.markdown("</div>", unsafe_allow_html=True)
                
                st.markdown("---")
                c1, c2, c3 = st.columns(3)
                c1.metric("Baza Danych", f"{len(draws)} losowań")
                if len(draws) > 0:
                    last_draw_time = draws[0]['date']
                    c2.metric("Ostatnie Losowanie", last_draw_time)
                c3.metric("Suma", sum(main_nums))

# --- ZAKŁADKA 2 ---
with tab_res:
    st.markdown("### 📜 WYNIKI Z SIECI")
    
    res_game = st.selectbox("Pokaż wyniki dla:", list(GAME_CONFIG.keys()), key="res")
    
    if st.button("🔄 Odśwież Tabelę"):
        with st.spinner("Pobieranie..."):
            draws, error = fetch_from_scraper(res_game)
            
            if error:
                st.error(error)
            elif not draws:
                st.warning("Nie znaleziono wyników. Strona może być niedostępna.")
            else:
                for d in draws[:10]:
                    nums_str = ", ".join([str(n) for n in d['numbers']])
                    st.markdown(f"""
                    <div class="result-row">
                        <div style="color: #e6b800; font-size: 0.8em;">🕒 {d['date']}</div>
                        <div style="font-size: 1.1em; font-weight: bold;">{nums_str}</div>
                    </div>
                    """, unsafe_allow_html=True)

st.markdown("---")
st.markdown("<div style='text-align: center; color: #888; font-size: 12px;'>Saloon Lotto 777 © 2024 | Turbo Scraper Edition</div>", unsafe_allow_html=True)
    
