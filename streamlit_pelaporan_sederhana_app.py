import os
import sqlite3
from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st
import io
try:
    from fpdf import FPDF  # pip install fpdf2
except Exception:
    FPDF = None  # akan dimanfaatkan untuk menampilkan pesan instalasi

DB_PATH = "reports.db"
UPLOAD_DIR = "uploads"

# ---------- Utilities ----------

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                pelapor_nama TEXT,
                pelapor_email TEXT,
                judul TEXT NOT NULL,
                kategori TEXT,
                prioritas TEXT,
                deskripsi TEXT,
                status TEXT DEFAULT 'Baru',
                lampiran_path TEXT
            )
            """
        )
        conn.commit()


def save_upload(upload) -> Optional[str]:
    """Simpan file ke folder uploads dan kembalikan path relatifnya."""
    if upload is None:
        return None
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    # Pastikan nama file aman
    filename = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{upload.name.replace(' ', '_')}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(upload.getbuffer())
    return filepath


def insert_report(row: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO reports (
                created_at, pelapor_nama, pelapor_email, judul, kategori, prioritas, deskripsi, status, lampiran_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                row.get("pelapor_nama"),
                row.get("pelapor_email"),
                row["judul"],
                row.get("kategori"),
                row.get("prioritas"),
                row.get("deskripsi"),
                row.get("status", "Baru"),
                row.get("lampiran_path"),
            ),
        )
        conn.commit()


def load_reports() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            "SELECT id, created_at, pelapor_nama, pelapor_email, judul, kategori, prioritas, deskripsi, status, lampiran_path FROM reports ORDER BY id DESC",
            conn,
        )
    return df


def update_status_bulk(updated_df: pd.DataFrame):
    with get_conn() as conn:
        for _, r in updated_df.iterrows():
            conn.execute(
                "UPDATE reports SET status=? WHERE id=?",
                (r["status"], int(r["id"]))
            )
        conn.commit()


# ---------- PDF Helpers ----------

class _PDF(FPDF):
    def header(self):
        self.set_font("Times", "B", 14)
        self.cell(0, 10, "Laporan Pelaporan", new_x="LMARGIN", new_y="NEXT", align="C")
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Times", "I", 10)
        self.cell(0, 10, f"Halaman {self.page_no()}", align="C")


def _pdf_init():
    pdf = _PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Times", size=12)
    return pdf


def pdf_report_detail(row: dict) -> bytes:
    pdf = _pdf_init()
    # Judul
    pdf.set_font("Times", "B", 16)
    pdf.cell(0, 8, txt=str(row.get("judul", "(Tanpa Judul)")), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Metadata
    pdf.set_font("Times", size=12)
    fields = [
        ("ID", row.get("id")),
        ("Tanggal", row.get("created_at")),
        ("Kategori", row.get("kategori")),
        ("Prioritas", row.get("prioritas")),
        ("Status", row.get("status")),
        ("Pelapor", row.get("pelapor_nama") or "-"),
        ("Email", row.get("pelapor_email") or "-"),
    ]
    for k, v in fields:
        pdf.set_font("Times", "B", 12)
        pdf.cell(35, 8, f"{k}")
        pdf.set_font("Times", size=12)
        pdf.multi_cell(0, 8, str(v))

    # Deskripsi
    desc = row.get("deskripsi")
    if desc:
        pdf.ln(2)
        pdf.set_font("Times", "B", 12)
        pdf.cell(0, 8, "Deskripsi", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Times", size=12)
        pdf.multi_cell(0, 7, str(desc))

    # Lampiran path info (hanya teks)
    att = row.get("lampiran_path")
    if att:
        pdf.ln(2)
        pdf.set_font("Times", "B", 12)
        pdf.cell(0, 8, "Lampiran (lokal)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Times", size=12)
        pdf.multi_cell(0, 7, str(att))

    out = pdf.output(dest="S").encode("latin-1")
    return out


def pdf_report_list(dff: pd.DataFrame) -> bytes:
    pdf = _pdf_init()
    pdf.set_font("Times", "B", 14)
    pdf.cell(0, 8, "Rekap Laporan (hasil filter)", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Times", size=12)
    pdf.multi_cell(0, 7, f"Dibuat: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    pdf.ln(2)

    # Tabel sederhana
    headers = ["ID", "Tanggal", "Judul", "Kategori", "Prioritas", "Status"]
    col_widths = [15, 36, 70, 28, 25, 22]
    pdf.set_font("Times", "B", 11)
    for h, w in zip(headers, col_widths):
        pdf.cell(w, 8, h, border=1)
    pdf.ln()

    pdf.set_font("Times", size=10)
    for _, r in dff.iterrows():
        cells = [
            str(int(r["id"])),
            str(r["created_at"])[:19],
            str(r["judul"])[:60],
            str(r["kategori"])[:18],
            str(r["prioritas"]),
            str(r["status"]),
        ]
        for c, w in zip(cells, col_widths):
            pdf.cell(w, 7, c, border=1)
        pdf.ln()

    return pdf.output(dest="S").encode("latin-1")

# ---------- UI Components ----------

st.set_page_config(page_title="Pelaporan Sederhana", page_icon="📝", layout="wide")
init_db()

st.sidebar.title("📝 Pelaporan")
menu = st.sidebar.radio("Menu", ["Buat Laporan", "Daftar Laporan", "Dashboard"], index=0)

with st.sidebar:
    st.markdown("---")
    st.caption("Built with Streamlit. Data tersimpan lokal di SQLite (reports.db).")

if menu == "Buat Laporan":
    st.header("Buat Laporan Baru")
    with st.form("form_laporan", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            pelapor_nama = st.text_input("Nama Pelapor")
        with col2:
            pelapor_email = st.text_input("Email Pelapor")

        judul = st.text_input("Judul Laporan *")
        kategori = st.selectbox(
            "Kategori",
            ["Umum", "Teknis", "Keuangan", "Sumber Daya Manusia", "Lainnya"],
            index=0,
        )
        prioritas = st.radio("Prioritas", ["Rendah", "Sedang", "Tinggi"], index=1, horizontal=True)
        deskripsi = st.text_area("Deskripsi", height=150)
        lampiran = st.file_uploader("Lampiran (opsional)", type=None)

        submitted = st.form_submit_button("Kirim Laporan")

    if submitted:
        if not judul.strip():
            st.error("Judul wajib diisi.")
        else:
            lampiran_path = save_upload(lampiran)
            insert_report(
                {
                    "pelapor_nama": pelapor_nama.strip() or None,
                    "pelapor_email": pelapor_email.strip() or None,
                    "judul": judul.strip(),
                    "kategori": kategori,
                    "prioritas": prioritas,
                    "deskripsi": deskripsi.strip() or None,
                    "status": "Baru",
                    "lampiran_path": lampiran_path,
                }
            )
            st.success("Laporan berhasil dikirim!")
            if lampiran_path:
                st.info(f"Lampiran tersimpan: {lampiran_path}")

elif menu == "Daftar Laporan":
    st.header("Daftar Laporan")

    df = load_reports()

    # Filter bar
    with st.expander("Filter", expanded=True):
        colf1, colf2, colf3 = st.columns(3)
        with colf1:
            f_kategori = st.multiselect("Kategori", sorted(df["kategori"].dropna().unique().tolist()))
        with colf2:
            f_prioritas = st.multiselect("Prioritas", sorted(df["prioritas"].dropna().unique().tolist()))
        with colf3:
            f_status = st.multiselect("Status", ["Baru", "Diproses", "Selesai"])  # allowed values

    dff = df.copy()
    if f_kategori:
        dff = dff[dff["kategori"].isin(f_kategori)]
    if f_prioritas:
        dff = dff[dff["prioritas"].isin(f_prioritas)]
    if f_status:
        dff = dff[dff["status"].isin(f_status)]

    # Tampilkan dan izinkan edit kolom status saja
    editable = dff[["id", "created_at", "judul", "kategori", "prioritas", "status"]].copy()

    st.caption("Klik pada kolom 'status' untuk mengubah: Baru / Diproses / Selesai")
    edited = st.data_editor(
        editable,
        disabled=["id", "created_at", "judul", "kategori", "prioritas"],
        key="editor",
        use_container_width=True,
        column_config={
            "status": st.column_config.SelectboxColumn(
                "status",
                help="Ubah status laporan",
                options=["Baru", "Diproses", "Selesai"],
            )
        },
    )

    colb1, colb2 = st.columns([1, 1])
    with colb1:
        if st.button("Simpan Perubahan Status", type="primary"):
            try:
                update_status_bulk(edited)
                st.success("Status laporan berhasil diperbarui.")
            except Exception as e:
                st.error(f"Gagal menyimpan: {e}")

    with colb2:
        csv = dff.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Unduh CSV (hasil filter)",
            csv,
            file_name=f"laporan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

    # Tombol ekspor PDF rekap (hasil filter)
    if FPDF is None:
        st.warning("Modul fpdf2 belum terpasang. Jalankan: pip install fpdf2")
    else:
        if st.button("Unduh PDF (rekap hasil filter)"):
            try:
                pdf_bytes = pdf_report_list(dff[["id","created_at","judul","kategori","prioritas","status"]])
                st.download_button(
                    label="Klik untuk mengunduh PDF",
                    data=pdf_bytes,
                    file_name=f"rekap_laporan_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf",
                )
            except Exception as e:
                st.error(f"Gagal membuat PDF: {e}")",
            csv,
            file_name=f"laporan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

    # Detail lampiran
    if not dff.empty:
        st.markdown("### Detail Laporan Terpilih")
        selected_id = st.number_input("Masukkan ID laporan untuk melihat detail", min_value=int(dff["id"].min()), max_value=int(dff["id"].max()), step=1)
        detail = df[df["id"] == selected_id]
        if not detail.empty:
            r = detail.iloc[0]
            st.write(
                {
                    "ID": int(r["id"]),
                    "Dibuat": r["created_at"],
                    "Judul": r["judul"],
                    "Kategori": r["kategori"],
                    "Prioritas": r["prioritas"],
                    "Status": r["status"],
                    "Pelapor": r["pelapor_nama"] or "-",
                    "Email": r["pelapor_email"] or "-",
                }
            )
            if pd.notna(r["deskripsi"]) and str(r["deskripsi"]).strip():
                st.markdown("**Deskripsi:**")
                st.write(r["deskripsi"])
            if pd.notna(r["lampiran_path"]) and r["lampiran_path"]:
                st.markdown(f"**Lampiran:** `{r['lampiran_path']}`")

            # Ekspor PDF detail laporan terpilih
            if FPDF is None:
                st.info("Untuk ekspor PDF, pasang paket: pip install fpdf2")
            else:
                if st.button("Unduh PDF (detail laporan ini)", type="primary"):
                    try:
                        pdf_bytes = pdf_report_detail(r.to_dict())
                        st.download_button(
                            label="Klik untuk mengunduh PDF",
                            data=pdf_bytes,
                            file_name=f"laporan_{int(r['id'])}.pdf",
                            mime="application/pdf",
                        )
                    except Exception as e:
                        st.error(f"Gagal membuat PDF: {e}")

elif menu == "Dashboard":
    st.header("Dashboard Ringkas")
    df = load_reports()
    if df.empty:
        st.info("Belum ada data.")
    else:
        colm1, colm2, colm3, colm4 = st.columns(4)
        with colm1:
            st.metric("Total Laporan", len(df))
        with colm2:
            st.metric("Baru", int((df["status"] == "Baru").sum()))
        with colm3:
            st.metric("Diproses", int((df["status"] == "Diproses").sum()))
        with colm4:
            st.metric("Selesai", int((df["status"] == "Selesai").sum()))

        colc1, colc2 = st.columns(2)
        with colc1:
            st.subheader("Laporan per Kategori")
            cat_counts = df["kategori"].value_counts().reset_index()
            cat_counts.columns = ["Kategori", "Jumlah"]
            st.bar_chart(cat_counts.set_index("Kategori"))
        with colc2:
            st.subheader("Laporan per Prioritas")
            pr_counts = df["prioritas"].value_counts().reset_index()
            pr_counts.columns = ["Prioritas", "Jumlah"]
            st.bar_chart(pr_counts.set_index("Prioritas"))

        st.subheader("Tren Laporan per Tanggal")
        tmp = df.copy()
        tmp["Tanggal"] = pd.to_datetime(tmp["created_at"]).dt.date
        trend = tmp.groupby("Tanggal").size().reset_index(name="Jumlah")
        st.line_chart(trend.set_index("Tanggal"))

# ---------- Footer ----------
st.markdown("---")
st.caption(
    "Tips: Jalankan dengan `streamlit run app.py`. Folder `uploads/` akan dibuat otomatis untuk menyimpan lampiran."
)
