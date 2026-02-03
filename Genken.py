import streamlit as st
import pypdf
import re
import random
import os
import pandas as pd
from collections import Counter
import time

# --- KONFIGURACJA KENO ---
st.set_page_config(
    page_title="Keno Smart System",
    page_icon="⚡",
    layout="centered"
)

# --- STYL (ZIELONY - SZYBKI) ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1f12; color: #e8f5e9; }
    .keno-ball {
        font-size: 20px; font-weight: bold; color: white;
        background: radial-gradient(circle at 30% 30%, #43a047, #1b5e20);
        border: 2px solid #66bb6a;
        border-radius: 50%;
        width: 45px; height: 45px; display: inline-flex;
        justify-content: center; align-items: center;
        margin: 4px; box-shadow: 0 0 10px rgba(76, 175, 80, 0.4);
    }
    .metric-box {
        background-color: #1b3a24; padding: 10px; border-radius: 8px;
        text-align: center; border: 1px solid #2e7d32;
        color: #a5d6a7; margin-bottom: 10px;
    }
    h1 { color: #66bb6a !important; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNKCJE DANYCH ---
@st.cache_data
def load_data(file_path):
    if not os.path.exists(file_path):
        return []
    draws = []
    try:
        reader = pypdf.PdfReader(file_path)
        for page in reader.pages:
            text = page.extract_text() or ""
            tokens = re.findall(r'\d+', text)
            i = 0
            while i < len(tokens):
                candidates = []
                offset = 0
                # Keno: losuje się 20 liczb z 70
                while len(candidates) < 20 and (i + offset) < len(tokens):
                    try:
                        val = int(tokens[i+offset])
                        # Ignorujemy duże numery ID losowania (np. 1448950)
                        if 1 <= val <= 70:
                            candidates.append(val)
                        else:
                            # Jeśli trafimy na ID losowania w środku, przerywamy zbieranie
                            if candidates: break 
                    except: break
                    offset += 1
                
                # Jeśli znaleźliśmy chociaż 15 liczb w ciągu, uznajemy to za losowanie
                # (czasem PDF dzieli wiersze)
                if len(candidates) >= 15:
                    draws.append(candidates)
                    i += offset
                else:
                    i += 1
    except:
        return []
    return draws

def get_hot_weights(draws):
    flat = [n for d in draws for n in d]
    c = Counter(flat)
    # Wagi dla liczb 1-70
    return [c.get(i, 1) for i in range(1, 71)]

# --- GENERATOR KENO SMART ---
def generate_keno_real(weights, num_picks=10):
    population = list(range(1, 71))
    
    # Próbujemy max 5000 razy znaleźć idealny układ
    for _ in range(5000):
        # 1. Losowanie ważone (Hot Numbers z pliku!)
        stronger_weights = [w**1.3 for w in weights] # Lekkie wzmocnienie trendu
        
        candidates = set()
        while len(candidates) < num_picks:
            c = random.choices(population, weights=stronger_weights, k=1)[0]
            candidates.add(c)
        
        nums = sorted(list(candidates))
        
        # --- FILTRY KENO ---
        
        # 1. Strefy (Dzielimy 70 liczb na 3 części: 1-23, 24-46, 47-70)
        # Dobry kupon Keno powinien być rozstrzelony po planszy.
        if num_picks >= 5:
            z1 = sum(1 for n in nums if n <= 23)
            z2 = sum(1 for n in nums if 23 < n <= 46)
            z3 = sum(1 for n in nums if n > 46)
            
            # Wymagamy obecności w każdej strefie przy grze na 10
            if num_picks == 10 and (z1 == 0 or z2 == 0 or z3 == 0):
                continue
        
        # 2. Parzystość (4-6 parzystych przy 10 liczbach)
        even = sum(1 for n in nums if n % 2 == 0)
        if num_picks == 10 and (even < 4 or even > 6): continue
        if num_picks == 5 and (even < 2 or even > 3): continue
            
        # 3. Ciągi (Brak schodków > 2)
        consecutive = 0
        max_cons = 0
        for i in range(len(nums)-1):
            if nums[i+1] == nums[i] + 1: consecutive += 1
            else: consecutive = 0
            max_cons = max(max_cons, consecutive)
            
        if max_cons >= 2: continue
            
        return nums, even

    return nums, 0

# --- INTERFEJS ---
def main():
    st.title("⚡ Keno Smart System")
    st.markdown("Analiza historyczna bazy PDF + Filtry strefowe.")
    
    FILE_NAME = "999los.pdf"
    draws = load_data(FILE_NAME)
    
    if not draws:
        st.warning(f"⚠️ Nie widzę pliku {FILE_NAME}. Wgraj go, aby użyć historii.")
        weights = [1] * 70
        db_info = "Tryb losowy (Brak danych)"
    else:
        weights = get_hot_weights(draws)
        db_info = f"Baza: {len(draws)} ostatnich losowań"

    st.info(f"📊 {db_info}")

    # Wybór trybu
    st.write("Wybierz strategię:")
    c1, c2 = st.columns(2)
    with c1:
        mode_10 = st.button("Gra na 10 liczb (Agresywna)", use_container_width=True)
    with c2:
        mode_5 = st.button("Gra na 5 liczb (Ostrożna)", use_container_width=True)

    # Logika
    if 'k_res' not in st.session_state:
        st.session_state['k_res'] = None
        
    if mode_10:
        with st.spinner("Analiza trendów z pliku PDF..."):
            time.sleep(0.3)
            res, ev = generate_keno_real(weights, 10)
            st.session_state['k_res'] = (res, ev, 10)
            
    if mode_5:
        with st.spinner("Szukanie pewniaków..."):
            time.sleep(0.3)
            res, ev = generate_keno_real(weights, 5)
            st.session_state['k_res'] = (res, ev, 5)

    # Wynik
    if st.session_state['k_res']:
        res, ev, picks = st.session_state['k_res']
        
        st.divider()
        st.subheader(f"Twoje liczby ({picks} z 70):")
        
        # Kule
        html = "<div style='display: flex; flex-wrap: wrap; justify-content: center;'>"
        for n in res:
            html += f"<div class='keno-ball'>{n}</div>"
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Statystyki
        m1, m2 = st.columns(2)
        m1.markdown(f"<div class='metric-box'>⚖️ Parzyste: <b>{ev}/{picks}</b></div>", unsafe_allow_html=True)
        m2.markdown(f"<div class='metric-box'>🔥 Źródło<br><small>Hot Numbers (PDF)</small></div>", unsafe_allow_html=True)
        
        st.caption("Algorytm wybrał liczby najczęściej występujące w Twoim pliku, a następnie odrzucił te, które tworzyłyby skupiska lub ciągi.")

if __name__ == "__main__":
    main()
