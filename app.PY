import streamlit as st
import pandas as pd
import sqlite3
from datetime import date
import os

# =========================
# CONFIGURAZIONE PAGINA
# =========================
st.set_page_config(page_title="Piano Bulk", page_icon="📦", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;600;700;800&display=swap');
:root {
    --merck-purple: #6A2C91; --merck-green: #2D8A5C; --merck-red: #EB3300;
    --merck-aqua: #008B8B; --bg-aqua: #E0F7FA; --merck-amber: #FFB000; --bg: #ffffff;
}
html, body, [class*="css"] { font-family: 'Syne', sans-serif; background-color: var(--bg); }
.app-title { font-size: 2.2rem; font-weight: 800; color: var(--merck-purple); border-bottom: 3px solid var(--merck-purple); padding-bottom: 0.5rem; margin-bottom: 2rem; }
.section-label { font-family: 'DM Mono', monospace; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 2px; color: var(--merck-purple); margin: 2rem 0 1rem 0; font-weight: 600; }
.kpi-row { display: flex; gap: 1rem; margin: 1.5rem 0; }
.kpi-card { flex: 1; border-radius: 8px; padding: 1.2rem; text-align: center; border: 1px solid rgba(0,0,0,0.05); box-shadow: 0 2px 4px rgba(0,0,0,0.05); border-top: 5px solid; }
.kpi-total { background-color: var(--bg-aqua); border-color: var(--merck-aqua); }
.kpi-total .kpi-number { color: var(--merck-aqua); }
.kpi-tempo { background-color: #eaf5ee; border-color: var(--merck-green); }
.kpi-tempo .kpi-number { color: var(--merck-green); }
.kpi-ritardo { background-color: #fdf2f0; border-color: var(--merck-red); }
.kpi-ritardo .kpi-number { color: var(--merck-red); }
.kpi-attesa { background-color: #fff8e6; border-color: var(--merck-amber); }
.kpi-attesa .kpi-number { color: var(--merck-amber); }
.kpi-number { font-size: 2.5rem; font-weight: 800; line-height: 1; }
.kpi-label { font-family: 'DM Mono', monospace; font-size: 0.65rem; text-transform: uppercase; color: #555; margin-top: 0.5rem; }
button[kind="primary"] { background-color: var(--merck-purple) !important; border: none !important; color: white !important; }
</style>
""", unsafe_allow_html=True)

# =========================
# DATABASE MANAGER
# =========================
class DatabaseManager:
    def __init__(self, db_path="magazzino.db"):
        self.db_path = db_path
        self._init_db()

    def get_connection(self): return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self.get_connection()
        conn.execute("CREATE TABLE IF NOT EXISTS piani_bulk (piano_id TEXT PRIMARY KEY, week INTEGER, year INTEGER, bulk_date TEXT)")
        conn.execute("""CREATE TABLE IF NOT EXISTS piano_bulk_righe (
            id INTEGER PRIMARY KEY AUTOINCREMENT, piano_id TEXT, batch_number TEXT, description TEXT, 
            site TEXT, TEMP TEXT, monitoraggio TEXT,
            delivery_date TEXT, flag_received INTEGER DEFAULT 0, flag_date TEXT,
            FOREIGN KEY (piano_id) REFERENCES piani_bulk(piano_id))""")
        conn.commit()
        conn.close()

    def salva_nuovo_piano(self, df_filtrato, week_scelta):
        anno_corrente = date.today().year
        piano_id = f"W{int(week_scelta):02d}_{anno_corrente}"
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO piani_bulk VALUES (?, ?, ?, ?)", (piano_id, int(week_scelta), anno_corrente, str(date.today())))
        cursor.execute("DELETE FROM piano_bulk_righe WHERE piano_id = ?", (piano_id,))
        for _, row in df_filtrato.iterrows():
            raw_date = row.get("DELIVERY DATE", "")
            try: d_date = pd.to_datetime(raw_date).strftime('%Y-%m-%d')
            except: d_date = str(raw_date)
            
            cursor.execute("""INSERT INTO piano_bulk_righe (piano_id, batch_number, description, site, TEMP, monitoraggio, delivery_date) 
                              VALUES (?, ?, ?, ?, ?, ?, ?)""", 
                           (piano_id, str(row.get("BATCH NUMBER", "")), str(row.get("DESCRIPTION", "")), 
                            str(row.get("SITES", "")), str(row.get("TEMP", "")), str(row.get("MONITORAGGIO", "")), d_date))
        conn.commit()
        conn.close()
        return piano_id

    def carica_piano(self, piano_id):
        conn = self.get_connection()
        df = pd.read_sql("SELECT * FROM piano_bulk_righe WHERE piano_id = ?", conn, params=[piano_id])
        conn.close()
        return df

    def salva_modifiche(self, piano_id, df_aggiornato):
        conn = self.get_connection()
        for _, row in df_aggiornato.iterrows():
            val_rec = 1 if row["Ricevuto"] else 0
            conn.execute("UPDATE piano_bulk_righe SET flag_received=?, flag_date=? WHERE piano_id=? AND batch_number=?",
                         (val_rec, row["Data Ricezione"], piano_id, str(row["Lotto"])))
        conn.commit()
        conn.close()

    def lista_piani(self):
        conn = self.get_connection()
        df = pd.read_sql("SELECT * FROM piani_bulk ORDER BY year DESC, week DESC", conn)
        conn.close()
        return df

# =========================
# APP LOGIC
# =========================
db = DatabaseManager()
today_str = str(date.today())

if "piano_attivo_id" not in st.session_state: st.session_state.piano_attivo_id = None

st.markdown('<h1 class="app-title">PIANO BULK</h1>', unsafe_allow_html=True)

# --- 01 CARICA ---
st.markdown('<div class="section-label">01 — Caricamento Excel Master</div>', unsafe_allow_html=True)
up = st.file_uploader("Trascina file Excel", type=["xlsx", "xlsm"], label_visibility="collapsed")

if up:
    df_preview = pd.read_excel(up)
    df_preview.columns = [c.upper().strip() for c in df_preview.columns]
    if "WEEK" in df_preview.columns:
        weeks_disponibili = sorted(df_preview["WEEK"].unique())
        col_sel, col_btn = st.columns([3, 1])
        with col_sel: 
            week_scelta = st.selectbox("Seleziona la WEEK da gestire da questo file:", weeks_disponibili)
        with col_btn:
            st.write("")
            if st.button("⚡ ESTRAI SETTIMANA", type="primary", use_container_width=True):
                df_filtrato = df_preview[df_preview["WEEK"] == week_scelta]
                st.session_state.piano_attivo_id = db.salva_nuovo_piano(df_filtrato, week_scelta)
                st.rerun()

# --- 02 GESTIONE ---
if st.session_state.piano_attivo_id:
    df_r = db.carica_piano(st.session_state.piano_attivo_id)
    
    def get_delivery_status(row):
        if not row["flag_received"]: return ""
        try:
            diff = (pd.to_datetime(row['flag_date']) - pd.to_datetime(row['delivery_date'])).days
            return "In Tempo" if diff <= 0 else "In Ritardo"
        except: return "Data Errata"

    df_r["Stato Consegna"] = df_r.apply(get_delivery_status, axis=1)
    
    # KPI
    tot, rec_count = len(df_r), df_r[df_r["flag_received"] == 1].shape[0]
    in_tempo = df_r[df_r["Stato Consegna"] == "In Tempo"].shape[0]
    in_ritardo = df_r[df_r["Stato Consegna"] == "In Ritardo"].shape[0]
    mancanti = tot - rec_count

    st.markdown(f'<div class="section-label">02 — Gestione Piano: {st.session_state.piano_attivo_id}</div>', unsafe_allow_html=True)
    st.markdown(f"""<div class="kpi-row">
        <div class="kpi-card kpi-total"><div class="kpi-number">{tot}</div><div class="kpi-label">Lotti Totali</div></div>
        <div class="kpi-card kpi-tempo"><div class="kpi-number">{in_tempo}</div><div class="kpi-label">Ricevuti in Tempo</div></div>
        <div class="kpi-card kpi-ritardo"><div class="kpi-number">{in_ritardo}</div><div class="kpi-label">In Ritardo</div></div>
        <div class="kpi-card kpi-attesa"><div class="kpi-number">{mancanti}</div><div class="kpi-label">Da Ricevere</div></div>
    </div>""", unsafe_allow_html=True)

    df_ed = df_r.copy()
    df_ed["Ricevuto"] = df_ed["flag_received"].astype(bool)
    df_ed = df_ed.rename(columns={"batch_number":"Lotto", "description":"Descrizione", "delivery_date":"DELIVERY DATE", "flag_date":"Data Ricezione", "monitoraggio":"Monitoraggio"})
    
    col_order = ["Ricevuto", "Lotto", "Descrizione", "Monitoraggio", "DELIVERY DATE", "Data Ricezione", "Stato Consegna", "site", "TEMP"]
    
    edited_df = st.data_editor(df_ed[col_order], use_container_width=True, hide_index=True,
                               disabled=["Lotto", "Descrizione", "Monitoraggio", "DELIVERY DATE", "site", "TEMP", "Stato Consegna"])

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 SALVA MODIFICHE", use_container_width=True, type="primary"):
            edited_df["Data Ricezione"] = edited_df.apply(lambda r: r["Data Ricezione"] if (r["Ricevuto"] and r["Data Ricezione"]) else (today_str if r["Ricevuto"] else None), axis=1)
            db.salva_modifiche(st.session_state.piano_attivo_id, edited_df)
            st.rerun()

    with col2:
        if st.button("📊 AGGIORNA STORICO POWER BI", use_container_width=True):
            csv_file = "power_bi_source.csv"
            export_df = edited_df.copy()
            export_df["Piano_ID"] = st.session_state.piano_attivo_id
            
            if os.path.exists(csv_file):
                history_df = pd.read_csv(csv_file, sep=';')
                # Rimuove versioni vecchie dello stesso piano per evitare duplicati
                history_df = history_df[history_df["Piano_ID"] != st.session_state.piano_attivo_id]
                final_df = pd.concat([history_df, export_df], ignore_index=True)
            else:
                final_df = export_df
                
            final_df.to_csv(csv_file, index=False, sep=';')
            st.success(f"Dati accodati! Lo storico ora ha {len(final_df)} righe.")

# --- 03 STORICO ---
st.markdown('<div class="section-label">03 — Archivio Rapido Piani</div>', unsafe_allow_html=True)
df_list = db.lista_piani()
if not df_list.empty:
    cols = st.columns(5)
    for i, row in df_list.iterrows():
        with cols[i % 5]:
            if st.button(f"📂 {row['piano_id']}", key=f"btn_{row['piano_id']}", use_container_width=True):
                st.session_state.piano_attivo_id = row['piano_id']
                st.rerun()
