import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests
from streamlit_searchbox import st_searchbox
from io import StringIO
from datetime import datetime, timedelta

# --- 1. DESIGN & CSS ---
st.set_page_config(page_title="Investerings Terminal", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #F3F4F6 !important; color: #111827 !important; }
    .lovable-card { 
        background-color: #FFFFFF !important; padding: 24px; border-radius: 12px; 
        border: 1px solid #D1D5DB !important; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px;
    }
    .stMarkdown, p, label, .stMetric, span { color: #111827 !important; font-weight: 500; }

    .stButton>button, .stButton>button p, .stButton>button span { 
        background-color: #111827 !important; 
        color: #FFFFFF !important; 
        font-weight: 700 !important; 
    }
    .stButton>button { border-radius: 8px; padding: 14px; width: 100%; }
    .metric-value { font-size: 32px; font-weight: 800; color: #2563EB !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #E5E7EB; border-radius: 5px 5px 0 0; padding: 10px 20px; }
    </style>
    """, unsafe_allow_html=True)


# --- 2. DATA FUNKTIONER ---

def search_tickers(search_term: str):
    if not search_term or len(search_term) < 2: return []
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={search_term}&region=SE&lang=sv-SE"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers).json()
        return [f"{quote['symbol']} ({quote.get('shortname', '')})" for quote in r.get('quotes', [])]
    except:
        return []


@st.cache_data(ttl=3600)
def fetch_insider_trades(days_back=7):
    start_date = (datetime.today() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    url = f"https://marknadssok.fi.se/Publiceringsklient/sv-SE/Search/Search?SearchFunctionType=Insyn&Publiceringsdatum.From={start_date}&button=export&exporttype=csv"

    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        csv_data = StringIO(response.content.decode('utf-16'))
        df = pd.read_csv(csv_data, sep=';')

        if df.empty: return pd.DataFrame()

        df['Volym_num'] = df['Volym'].astype(str).str.replace(' ', '').str.replace(',', '.').apply(pd.to_numeric,
                                                                                                   errors='coerce')
        df['Pris_num'] = df['Pris'].astype(str).str.replace(' ', '').str.replace(',', '.').apply(pd.to_numeric,
                                                                                                 errors='coerce')

        df['Totalvärde'] = df['Volym_num'] * df['Pris_num']

        mask_karaktar = df['Karaktär'].isin(['Förvärv', 'Avyttring'])
        mask_miljon = df['Totalvärde'] >= 1000000
        df_filtered = df[mask_karaktar & mask_miljon].copy()

        df_filtered['Totalvärde'] = df_filtered['Totalvärde'].apply(lambda x: f"{x:,.0f}".replace(',', ' '))

        if 'Instrumentnamn' in df_filtered.columns:
            df_filtered['Aktie/Bolag'] = df_filtered['Instrumentnamn']
        else:
            df_filtered['Aktie/Bolag'] = df_filtered.get('Utgivare', 'Okänt bolag')

        cols_to_keep = ['Publiceringsdatum', 'Aktie/Bolag', 'Person i ledande ställning', 'Befattning', 'Karaktär',
                        'Totalvärde', 'Valuta']
        cols = [c for c in cols_to_keep if c in df_filtered.columns]

        return df_filtered[cols].sort_values(by='Publiceringsdatum', ascending=False)

    except Exception as e:
        return None


# --- 3. SESSION STATE ---
if 'rows' not in st.session_state: st.session_state.rows = 5
if 'weights_map' not in st.session_state: st.session_state.weights_map = {}

# --- 4. NAVIGATION ---
st.title("Investerings Terminal")
t1, t2, t3, t4, t5 = st.tabs(
    ["📂 Portföljanalys", "🔮 Risk-Simulering", "🧮 Positionskalkylator", "🕵️‍♂️ Insynshandel", "📊 System-Simulator"])

# --- TAB 1: PORTFÖLJANALYS ---
with t1:
    st.markdown('<div class="lovable-card">', unsafe_allow_html=True)
    st.subheader("Portföljbyggare")
    selected_assets, active_rows = [], []

    for i in range(st.session_state.rows):
        c1, c2, c3 = st.columns([6, 1.5, 0.5])
        with c1:
            asset = st_searchbox(search_tickers, key=f"s_{i}", placeholder="Sök aktie (t.ex. VOLV-B.ST)...")
        with c2:
            val = st.session_state.weights_map.get(i, 0.0)
            weight = st.number_input("Vikt", 0.0, 100.0, float(val), step=5.0, key=f"win_{i}",
                                     label_visibility="collapsed")
            st.session_state.weights_map[i] = weight
        with c3:
            st.write("%")

        if asset and isinstance(asset, str):
            selected_assets.append(asset.split(" ")[0])
            active_rows.append(i)

    if st.button("➕ Lägg till rad"):
        st.session_state.rows += 1
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    if st.button("KÖR ANALYS", use_container_width=True) and selected_assets:
        with st.spinner("Hämtar historisk data från marknaden..."):
            try:
                weights = [st.session_state.weights_map.get(i, 0.0) / 100 for i in active_rows]
                df = yf.download(selected_assets, period="5y", progress=False)

                if df.empty:
                    st.error(
                        "⚠️ Kunde inte hämta prisdata. Yahoo Finance blockerar tillfälligt anropet från servern. Försök igen om en stund.")
                else:
                    prices = df['Adj Close'] if 'Adj Close' in df.columns else df['Close']

                    if isinstance(prices, pd.Series):
                        prices = prices.to_frame(name=selected_assets[0])

                    returns = prices.pct_change().dropna()

                    valid_assets = [a for a in selected_assets if a in returns.columns]
                    if not valid_assets:
                        st.error("⚠️ Data saknas för de valda aktierna.")
                    else:
                        port_ret = (returns[valid_assets] * weights[:len(valid_assets)]).sum(axis=1)
                        cum_port = (1 + port_ret).cumprod()
                        st.session_state.port_ret = port_ret

                        m1, m2, m3 = st.columns(3)
                        volatility = port_ret.std() * np.sqrt(252)
                        sharpe = (port_ret.mean() * 252) / volatility if volatility != 0 else 0
                        max_dd = ((cum_port / cum_port.cummax()) - 1).min()

                        m1.markdown(
                            f'<div class="lovable-card"><p>Sharpe Ratio</p><p class="metric-value">{sharpe:.2f}</p></div>',
                            unsafe_allow_html=True)
                        m2.markdown(
                            f'<div class="lovable-card"><p>Max Drawdown</p><p class="metric-value">{max_dd * 100:.1f}%</p></div>',
                            unsafe_allow_html=True)
                        m3.markdown(
                            f'<div class="lovable-card"><p>Årlig Volatilitet</p><p class="metric-value">{volatility * 100:.1f}%</p></div>',
                            unsafe_allow_html=True)

                        fig = px.line((cum_port - 1) * 100, title="Historisk Utveckling (5 år)")
                        fig.update_layout(yaxis_ticksuffix="%", plot_bgcolor="white", xaxis_title="Datum",
                                          yaxis_title="Avkastning")
                        st.plotly_chart(fig, use_container_width=True)

            except Exception as e:
                st.error(f"Ett tekniskt fel uppstod vid analysen: {e}")

# --- TAB 2: MONTE CARLO ---
with t2:
    if 'port_ret' in st.session_state:
        st.markdown('<div class="lovable-card">', unsafe_allow_html=True)
        st.subheader("Monte Carlo: Framtida Sannolikhetsmoln")
        st.write(
            "Simuleringen räknar i bakgrunden ut **10 000 möjliga scenarier** för det kommande året baserat på din historiska volatilitet. Grafen visar ett urval av 100 vägar.")

        mu, sigma = st.session_state.port_ret.mean(), st.session_state.port_ret.std()
        sim_days = 252
        num_simulations = 10000

        sim_returns = np.random.normal(mu, sigma, (num_simulations, sim_days))
        sim_paths = (1 + sim_returns).cumprod(axis=1) - 1
        sim_paths_pct = sim_paths * 100

        fig_mc = go.Figure()
        for i in range(100):
            fig_mc.add_trace(
                go.Scatter(y=sim_paths_pct[i], mode='lines', line=dict(width=1.5), opacity=0.15, line_color="#2563EB",
                           showlegend=False))

        fig_mc.add_hline(y=0, line_dash="solid", line_color="black", line_width=2)
        fig_mc.update_layout(height=600, xaxis_title="Handelsdagar framåt", yaxis_title="Avkastning (%)",
                             plot_bgcolor="white", yaxis_ticksuffix="%")
        st.plotly_chart(fig_mc, use_container_width=True)

        final_returns = sim_paths_pct[:, -1]

        c1, c2, c3 = st.columns(3)
        c1.metric("Worst Case (botten 5%)", f"{np.percentile(final_returns, 5):.1f}%")
        c2.metric("Median utfall", f"{np.median(final_returns):.1f}%")
        c3.metric("Best Case (topp 5%)", f"{np.percentile(final_returns, 95):.1f}%")

        prob_win = (len(final_returns[final_returns > 0]) / num_simulations) * 100
        st.success(f"📈 Sannolikhet att portföljen ligger på **PLUS** efter 12 månader: **{prob_win:.1f}%**")

        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info(
            "⚠️ Bygg din portfölj och klicka på 'KÖR ANALYS' under fliken Portföljanalys för att låsa upp Monte Carlo-simuleringen.")

# --- TAB 3: POSITIONSKALKYLATOR ---
with t3:
    st.markdown('<div class="lovable-card">', unsafe_allow_html=True)
    st.subheader("Positionsstorlek & Riskhantering")
    st.write("Beräkna exakt hur många aktier du kan köpa utan att riskera mer än din uppsatta portföljrisk.")

    col1, col2 = st.columns(2)
    with col1:
        acc = st.number_input("Portföljvärde (SEK)", 1000, step=1000, value=100000)
        risk = st.slider("Maximal Risk per affär (%)", 0.1, 5.0, 1.0, step=0.1)
    with col2:
        ent = st.number_input("Inköpskurs (Pris per aktie)", 0.1, value=100.0)
        sl = st.number_input("Stop Loss Kurs (Där du säljer vid förlust)", 0.0, value=95.0)

    if ent > sl:
        risk_sek = acc * (risk / 100)
        shares = int(risk_sek / (ent - sl))
        st.divider()
        m1, m2 = st.columns(2)
        m1.metric("Mål: Antal aktier att köpa", f"{shares} st")
        m2.metric("Total ordersumma", f"{shares * ent:,.0f} SEK")
        st.info(
            f"Om aktien sjunker till din Stop Loss ({sl} SEK) förlorar du exakt {risk_sek:,.0f} SEK ({risk}% av din portfölj).")
    else:
        st.error("Stop Loss måste ligga under inköpskursen.")
    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 4: INSYNSHANDEL ---
with t4:
    st.markdown('<div class="lovable-card">', unsafe_allow_html=True)
    st.subheader("Insynshandel (> 1 Miljon)")
    st.write("Visar endast stora transaktioner (Förvärv/Avyttring) där totalvärdet överstiger 1 000 000 kr.")

    col_days, _ = st.columns([1, 3])
    with col_days:
        days_back = st.number_input("Dagar bakåt", min_value=1, max_value=30, value=7)

    if st.button("Hämta Stora Transaktioner", use_container_width=True):
        with st.spinner("Ansluter till Finansinspektionen..."):
            insider_df = fetch_insider_trades(days_back)

            if insider_df is not None and not insider_df.empty:
                st.dataframe(insider_df, use_container_width=True, hide_index=True)
                st.caption("Källa: Finansinspektionen. (Cachad i 1 timme).")
            elif insider_df is not None and insider_df.empty:
                st.info("Hittade inga transaktioner över 1 miljon för den valda perioden.")
            else:
                st.error("Kunde inte nå Finansinspektionen. Deras server kan ligga nere tillfälligt.")

    st.markdown('</div>', unsafe_allow_html=True)

# --- TAB 5: SYSTEM-SIMULATOR ---
with t5:
    st.markdown('<div class="lovable-card">', unsafe_allow_html=True)
    st.subheader("📊 System-Simulator (Trade för Trade)")
    st.write(
        "Mata in din historiska (eller förväntade) trade-statistik för att simulera hur din strategi kommer prestera över ett helt år. Kalkylatorn simulerar 10 000 år av trading för att hitta dina mest troliga utfall.")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.write("💰 **Kapital & Frekvens**")
        start_cap = st.number_input("Startkapital (SEK)", 1000, value=100000, step=5000)
        trades_per_week = st.number_input("Trades per vecka", 1, 100, value=5)
    with c2:
        st.write("⚖️ **Win/Loss Ratio**")
        win_rate = st.number_input("Vinst-andel (%)", 0, 100, value=40)
        be_rate = st.number_input("Breakeven-andel (%)", 0, 100, value=20)
        loss_rate = 100 - win_rate - be_rate
        st.info(f"Förlust-andel blir då: **{loss_rate}%**")
    with c3:
        st.write("🎯 **Normala utfall**")
        avg_win = st.number_input("Genomsnittsvinst per trade (%)", 0.1, 100.0, value=2.0, step=0.1)
        avg_loss = st.number_input("Genomsnittsförlust per trade (%)", 0.1, 100.0, value=1.0, step=0.1)

    st.divider()
    st.write("🚀 **Outliers (Extrema utfall)**")
    c4, c5 = st.columns(2)
    with c4:
        max_win = st.number_input("Större än normala vinster i %", 0.1, 500.0, value=10.0, step=0.5)
        max_win_prob = st.number_input("Hur ofta sker denna jättevinst? (% av ALLA trades)", 0.0, 100.0, value=2.0,
                                       step=0.5)
    with c5:
        max_loss = st.number_input("Större än normala förluster i %", 0.1, 100.0, value=4.0, step=0.5)
        max_loss_prob = st.number_input("Hur ofta sker denna storförlust? (% av ALLA trades)", 0.0, 100.0, value=1.0,
                                        step=0.5)

    if loss_rate < 0:
        st.error("Din Vinst-andel + Breakeven-andel kan inte vara över 100%!")
    elif (max_win_prob > win_rate) or (max_loss_prob > loss_rate):
        st.error("Outlier-chansen kan inte vara större än din totala vinst/förlust-andel!")
    else:
        if st.button("KÖR SYSTEM-SIMULERING", use_container_width=True):
            with st.spinner("Simulerar 10 000 år av din strategi..."):
                total_trades = trades_per_week * 52  # 52 veckor på ett år
                num_sims = 10000

                # Datorn behöver veta exakt sannolikhet (mellan 0 och 1) för varje sak som kan hända
                normal_win_prob = (win_rate - max_win_prob) / 100
                normal_loss_prob = (loss_rate - max_loss_prob) / 100
                outlier_win_prob = max_win_prob / 100
                outlier_loss_prob = max_loss_prob / 100
                be_prob = be_rate / 100

                probs = np.array([normal_win_prob, normal_loss_prob, be_prob, outlier_win_prob, outlier_loss_prob])

                # Om det uppstår något mikroskopiskt decimal-fel, justera så det blir exakt 1.0 (100%)
                probs = probs / probs.sum()

                # Utfall för portföljen i procent (multiplikator, t.ex. 1.02 betyder +2%)
                outcomes = [
                    1 + (avg_win / 100),  # Normal vinst
                    1 - (avg_loss / 100),  # Normal förlust
                    1.0,  # Breakeven (0%)
                    1 + (max_win / 100),  # Home run vinst
                    1 - (max_loss / 100)  # Black swan förlust
                ]

                # Blixtsnabb simulering
                sim_matrix = np.random.choice(outcomes, size=(num_sims, total_trades), p=probs)
                sim_paths = start_cap * sim_matrix.cumprod(axis=1)

                fig_sys = go.Figure()
                for i in range(100):
                    fig_sys.add_trace(go.Scatter(y=sim_paths[i], mode='lines', line=dict(width=1.5), opacity=0.15,
                                                 line_color="#10B981", showlegend=False))

                fig_sys.add_hline(y=start_cap, line_dash="solid", line_color="black", line_width=2)
                fig_sys.update_layout(height=600, xaxis_title=f"Antal Trades (Total: {total_trades} st under 1 år)",
                                      yaxis_title="Portföljvärde (SEK)", plot_bgcolor="white")
                st.plotly_chart(fig_sys, use_container_width=True)

                final_vals = sim_paths[:, -1]

                st.write("### Resultat efter 12 månader")
                colA, colB, colC = st.columns(3)
                colA.metric("Worst Case (botten 5%)", f"{np.percentile(final_vals, 5):,.0f} SEK")
                colB.metric("Medianvärde (Mest troligt)", f"{np.median(final_vals):,.0f} SEK")
                colC.metric("Best Case (topp 5%)", f"{np.percentile(final_vals, 95):,.0f} SEK")

                win_prob_sys = (len(final_vals[final_vals > start_cap]) / num_sims) * 100
                ruin_prob = (len(final_vals[final_vals < start_cap * 0.5]) / num_sims) * 100

                st.divider()
                st.success(f"📈 Sannolikhet att gå med plus efter 1 år: **{win_prob_sys:.1f}%**")

                if ruin_prob > 5:
                    st.error(
                        f"⚠️ Risk of Ruin (Sannolikhet att tappa minst 50% av startkapitalet): **{ruin_prob:.1f}%**. Din risk/reward kan behöva justeras!")
                else:
                    st.info(
                        f"🛡️ Risk of Ruin (Sannolikhet att tappa minst 50% av startkapitalet): **{ruin_prob:.1f}%**")

    st.markdown('</div>', unsafe_allow_html=True)
