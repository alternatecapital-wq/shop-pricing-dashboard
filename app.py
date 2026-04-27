import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from fpdf import FPDF
import base64

st.set_page_config(page_title="AlternateCapital Shop Pricing", page_icon="🛠️", layout="wide")

# ====================== PASSWORD FOR ADMIN ======================
ADMIN_PASSWORD = "admin123"  # ← CHANGE THIS TO YOUR OWN SECRET PASSWORD

# ====================== DATABASE SETUP ======================
DB_FILE = "shop_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS items (
                 id INTEGER PRIMARY KEY,
                 part_number TEXT,
                 description TEXT,
                 category TEXT,
                 sale_price REAL,
                 purchase_price REAL,
                 date TEXT,
                 transaction_type TEXT)''')
    conn.commit()
    conn.close()

def load_data():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM items", conn)
    conn.close()
    return df

def save_row(row):
    conn = sqlite3.connect(DB_FILE)
    pd.DataFrame([row]).to_sql('items', conn, if_exists='append', index=False)
    conn.close()

init_db()
df = load_data()

# ====================== SIDEBAR ======================
st.sidebar.image("https://i.imgur.com/5q2v2bL.png", width=180)  # replace with your logo link later
st.sidebar.title("🛠️ AlternateCapital")
st.sidebar.markdown("**Vehicle Spare Parts**")

page = st.sidebar.radio("Navigation", [
    "Dashboard", "Items & Pricing", "Quotes", "Customers", "Suppliers", "Vehicle Lookup", "Categories"
], index=1)

is_admin = False
if st.sidebar.checkbox("🔐 Admin Mode (Upload Data)"):
    pwd = st.sidebar.text_input("Enter Admin Password", type="password")
    if pwd == ADMIN_PASSWORD:
        is_admin = True
        st.sidebar.success("✅ Admin access granted")
    else:
        st.sidebar.error("❌ Wrong password")

# ====================== ITEMS & PRICING PAGE ======================
if page == "Items & Pricing":
    st.title("Items & Pricing")
    st.caption("Vehicle Spare Parts • Real-time price ranges")

    # ADMIN ONLY UPLOAD
    if is_admin:
        uploaded_file = st.file_uploader("📤 Upload CSV (sales + purchases)", type=["csv"])
        if uploaded_file:
            new_data = pd.read_csv(uploaded_file)
            new_data.columns = [col.strip().title().replace(" ", " ") for col in new_data.columns]
            for _, row in new_data.iterrows():
                save_row(row.to_dict())
            st.success(f"✅ Imported {len(new_data)} rows!")
            st.rerun()

    # Search
    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input("🔎 Search by Part Number or Description", "")
    with col2:
        categories = ["All"] + sorted(df["category"].dropna().unique().tolist())
        cat_filter = st.selectbox("Category", categories)

    # Price range summary (your most important view)
    if len(df) > 0:
        filtered = df.copy()
        if search:
            mask = (filtered["part_number"].astype(str).str.contains(search, case=False, na=False)) | \
                   (filtered["description"].astype(str).str.contains(search, case=False, na=False))
            filtered = filtered[mask]
        if cat_filter != "All":
            filtered = filtered[filtered["category"] == cat_filter]

        summary = filtered.groupby(["part_number", "description", "category"], dropna=False).agg(
            Lowest_Sold=("sale_price", "min"),
            Highest_Sold=("sale_price", "max"),
            Average_Sold=("sale_price", "mean"),
            Times_Sold=("sale_price", "count"),
            Avg_Cost=("purchase_price", "mean")
        ).round(2).reset_index()

        st.dataframe(
            summary.style.format({
                "Lowest_Sold": "${:.2f}", "Highest_Sold": "${:.2f}",
                "Average_Sold": "${:.2f}", "Avg_Cost": "${:.2f}"
            }),
            use_container_width=True, height=600
        )
    else:
        st.info("No data yet – admin, please upload your first CSV.")

# ====================== QUOTES PAGE (Professional PDF) ======================
elif page == "Quotes":
    st.title("📋 Create Customer Quote")
    st.caption("Professional quotes • A4 or A5 • Print-ready")

    # Current quote in session state
    if "quote_items" not in st.session_state:
        st.session_state.quote_items = []

    # Customer details
    with st.expander("👤 Customer & Vehicle Details", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            customer_name = st.text_input("Customer Name")
            customer_phone = st.text_input("Phone Number")
        with col2:
            vehicle = st.text_input("Vehicle / Reg Number")
            quote_date = st.date_input("Quote Date", datetime.today())

    # Add items to quote
    st.subheader("Add Items")
    search_quote = st.text_input("Search part number or description", key="quote_search")
    if search_quote and len(df) > 0:
        results = df[
            df["part_number"].astype(str).str.contains(search_quote, case=False, na=False) |
            df["description"].astype(str).str.contains(search_quote, case=False, na=False)
        ].head(10)
        for _, item in results.iterrows():
            if st.button(f"Add → {item['part_number']} | {item['description']}", key=f"add_{item['id']}"):
                st.session_state.quote_items.append({
                    "part_number": item["part_number"],
                    "description": item["description"],
                    "quantity": 1,
                    "unit_price": float(item["sale_price"]) if pd.notna(item["sale_price"]) else 0.0
                })
                st.rerun()

    # Current quote table
    if st.session_state.quote_items:
        st.subheader("Quote Items")
        quote_df = pd.DataFrame(st.session_state.quote_items)
        quote_df["total"] = quote_df["quantity"] * quote_df["unit_price"]
        
        # Editable quantities
        for i, row in quote_df.iterrows():
            col1, col2, col3 = st.columns([3, 2, 2])
            with col1:
                st.write(f"**{row['part_number']}** – {row['description']}")
            with col2:
                qty = st.number_input("Qty", min_value=1, value=int(row["quantity"]), key=f"qty_{i}")
                st.session_state.quote_items[i]["quantity"] = qty
            with col3:
                price = st.number_input("Unit Price", value=float(row["unit_price"]), key=f"price_{i}")
                st.session_state.quote_items[i]["unit_price"] = price

        total_amount = quote_df["total"].sum()
        st.info(f"**Quote Total: ${total_amount:,.2f}**")

        # Generate PDF
        format_choice = st.radio("Paper Size", ["A4", "A5"], horizontal=True)
        if st.button("📄 Generate & Download Professional Quote PDF"):
            pdf = FPDF(format=format_choice)
            pdf.add_page()
            pdf.set_font("Arial", "B", 16)
            pdf.cell(0, 10, "AlternateCapital – Vehicle Spare Parts", ln=1, align="C")
            pdf.set_font("Arial", "", 12)
            pdf.cell(0, 8, f"Quote Date: {quote_date}", ln=1, align="C")
            pdf.cell(0, 8, f"Customer: {customer_name} | Phone: {customer_phone} | Vehicle: {vehicle}", ln=1, align="C")
            pdf.ln(10)

            # Table header
            pdf.set_font("Arial", "B", 10)
            pdf.cell(30, 10, "Part #", border=1)
            pdf.cell(80, 10, "Description", border=1)
            pdf.cell(20, 10, "Qty", border=1, align="C")
            pdf.cell(30, 10, "Unit Price", border=1, align="R")
            pdf.cell(30, 10, "Total", border=1, align="R")
            pdf.ln()

            pdf.set_font("Arial", "", 10)
            for item in st.session_state.quote_items:
                pdf.cell(30, 8, str(item["part_number"]), border=1)
                pdf.cell(80, 8, item["description"][:45], border=1)
                pdf.cell(20, 8, str(item["quantity"]), border=1, align="C")
                pdf.cell(30, 8, f"${item['unit_price']:.2f}", border=1, align="R")
                pdf.cell(30, 8, f"${item['quantity']*item['unit_price']:.2f}", border=1, align="R")
                pdf.ln()

            pdf.ln(10)
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, f"Grand Total: ${total_amount:,.2f}", ln=1, align="R")
            pdf.ln(10)
            pdf.set_font("Arial", "", 10)
            pdf.cell(0, 8, "Thank you for your business! Terms: Payment on collection.", align="C")

            # Download
            pdf_bytes = pdf.output(dest="S").encode("latin-1")
            b64 = base64.b64encode(pdf_bytes).decode()
            href = f'<a href="data:application/pdf;base64,{b64}" download="Quote_{customer_name}_{datetime.today().strftime("%Y%m%d")}.pdf">📥 Download {format_choice} PDF Quote</a>'
            st.markdown(href, unsafe_allow_html=True)
            st.success("✅ Quote PDF generated!")

        if st.button("🗑️ Clear Quote"):
            st.session_state.quote_items = []
            st.rerun()

    else:
        st.info("Search and add items above to build a quote.")

# ====================== OTHER PAGES (placeholders) ======================
else:
    st.title(page)
    st.info(f"🚧 {page} page coming soon – let me know what you need here!")

st.caption("© AlternateCapital • Built for fast selling • Data saved automatically")
