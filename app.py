import streamlit as st
import pandas as pd
import sqlite3
from datetime import date

# =========================
# 01 - CONFIGURAZIONE E STILE
# =========================
st.set_page_config(page_title="Piano Bulk - OneDrive Sync", page_icon="📦", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;600;700;800&display=swap');
:root { --merck-purple: #6A2C91; --merck-aqua: #008B8B; --bg: #ffffff; }
html, body, [class*="css"] { font-family: 'Syne', sans-serif; }
.app-title { font-size: 2rem; font-weight: 800; color: var(--merck-purple); border-bottom: 3px solid var(--merck-purple); margin-bottom: 2rem; }
.section-label { font-family: 'DM Mono', monospace; font-size: 0.75rem; text-transform: uppercase; color: var(--merck-purple); margin-top: 2rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# =========================
# 02 - DATABASE (SQLite Locale)
# =========================
class DatabaseManager:
    def __init__(self, db_path="magazzino.db"):
        self.db_path = db_path
        self._init_db()

    def get_connection(self): return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self.get_connection()
        conn.execute("CREATE TABLE IF NOT EXISTS piani_bulk (piano_id TEXT PRIMARY KEY, week INTEGER, year INTEGER)")
        conn.execute("""CREATE TABLE IF NOT EXISTS piano_bulk_righe (
            id INTEGER PRIMARY KEY AUTOINCREMENT, piano_id TEXT, batch_number TEXT, description TEXT, 
            site TEXT, TEMP TEXT, monitoraggio TEXT, delivery_date TEXT, 
            flag_received INTEGER DEFAULT 0, flag_date TEXT,
            FOREIGN KEY (piano_id) REFERENCES piani_bulk(piano_id))""")
        conn.commit()
        conn.close()

    def salva_nuovo_piano(self, df_filtrato, week_scelta):
        anno = date.today().year
        piano_id = f"W{int(week_scelta):02d}_{anno}"
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO piani_bulk VALUES (?, ?, ?)", (piano_id, int(week_scelta), anno))
        cursor.execute("DELETE FROM piano_bulk_righe WHERE piano_id = ?", (piano_id,))
        for _, row in df_filtrato.iterrows():
            cursor.execute("""INSERT INTO piano_bulk_righe (piano_id, batch_number, description, site, TEMP, monitoraggio, delivery_date) 
                              VALUES (?, ?, ?, ?, ?, ?, ?)""", 
                           (piano_id, str(row.get("BATCH NUMBER", "")), str(row.get("DESCRIPTION", "")), 
                            str(row.get("SITES", "")), str(row.get("TEMP", "")), str(row.get("MONITORAGGIO", "")), str(row.get("DELIVERY DATE", ""))))
        conn.commit()
        conn.close()
        return piano_id

    def get_master_data(self):
        """Estrae TUTTO lo storico accumulato finora"""
        conn = self.get_connection()
        query = """
            SELECT p.piano_id, p.week, p.year, r.batch_number, r.description, 
                   r.site, r.TEMP, r.delivery_date, r.flag_received, r.flag_date
            FROM piani_bulk p
            JOIN piano_bulk_righe r ON p.piano_id = r.piano_id
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df

# =========================
# 03 - LOGICA APPLICATIVA
# =========================
db = DatabaseManager()
if "piano_attivo" not in st.session_state: st.session_state.piano_attivo = None

st.markdown('<h1 class="app-title">PIANO BULK — EXPORT SHAREPOINT</h1>', unsafe_allow_html=True)

# --- CARICAMENTO ---
st.markdown('<div class="section-label">01 — Importa Nuova Settimana</div>', unsafe_allow_html=True)
up = st.file_uploader("Trascina file Excel", type=["xlsx", "xlsm"], label_visibility="collapsed")

if up:
    df_preview = pd.read_excel(up)
    df_preview.columns = [c.upper().strip() for c in df_preview.columns]
    weeks = sorted(df_preview["WEEK"].unique())
    col_sel, col_btn = st.columns([3, 1])
    with col_sel: week_scelta = st.selectbox("Seleziona la WEEK da aggiungere:", weeks)
    with col_btn:
        st.write("")
        if st.button("⚡ AGGIUNGI AL DB", type="primary", use_container_width=True):
            st.session_state.piano_attivo = db.salva_nuovo_piano(df_preview[df_preview["WEEK"] == week_scelta], week_scelta)
            st.rerun()

# --- GESTIONE E EXPORT ---
if st.session_state.piano_attivo:
    st.markdown(f'<div class="section-label">02 — Gestione e Export (Focus: {st.session_state.piano_attivo})</div>', unsafe_allow_html=True)
    
    # Prepariamo l'export MASTER (Tutte le week)
    master_df = db.get_master_data()
    csv_master = master_df.to_csv(index=False).encode('utf-8')

    c1, c2 = st.columns(2)
    with c1:
        st.info(f"Stai lavorando sulla {st.session_state.piano_attivo}. I dati sono salvati nell'app.")
    with c2:
        # IL TASTO PER ONEDRIVE
        st.download_button(
            label="📥 AGGIORNA CSV SU ONEDRIVE",
            data=csv_master,
            file_name="DATABASE_BULK_MASTER.csv",
            mime='text/csv',
            use_container_width=True,
            help="Scarica questo file e sovrascrivi quello esistente nella cartella OneDrive sincronizzata."
        )

# --- ARCHIVIO ---
st.markdown('<div class="section-label">03 — Archivio Settimane Caricate</div>', unsafe_allow_html=True)
conn = db.get_connection()
df_list = pd.read_sql("SELECT * FROM piani_bulk ORDER BY year DESC, week DESC", conn)
conn.close()
if not df_list.empty:
    cols = st.columns(5)
    for i, row in df_list.iterrows():
        with cols[i % 5]:
            if st.button(f"📂 {row['piano_id']}", key=f"btn_{row['piano_id']}", use_container_width=True):
                st.session_state.piano_attivo = row['piano_id']
                st.rerun()
