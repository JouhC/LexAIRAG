import streamlit as st
import pandas as pd
from sentence_transformers import SentenceTransformer
from psycopg import rows
from pgvector.psycopg import register_vector

from pipeline.db_init import create_connection, close_connection
from pipeline.similarity_search import search_chunks

@st.cache_resource
def load_model():
    # Change this to the exact name/path of the model you’re using
    # e.g. "BAAI/bge-m3" or your local fine-tuned model path
    model = SentenceTransformer("BAAI/bge-m3")
    return model


@st.cache_resource
def get_connection():
    conn = create_connection()
    # register pgvector adapter for this connection
    register_vector(conn)
    return conn

def main():
    st.set_page_config(page_title="LexAI Vector Search", layout="wide")

    st.title("🔍 LexAI Vector Search Explorer")

    with st.sidebar:
        st.header("Search Settings")
        top_k_choice = st.radio(
            "Number of results",
            options=[5, 10],
            index=0,
            help="Choose whether to show the top 5 or top 10 most similar chunks."
        )

    st.write("Enter a natural language query and search against the `decision_chunks` vector index.")

    query = st.text_area(
        "Query",
        placeholder="e.g. liability of carrier for loss of goods...",
        height=100
    )

    if st.button("Search"):
        if not query.strip():
            st.warning("Please enter a query first.")
            return

        conn = get_connection()
        model = load_model()

        with st.spinner("Running similarity search..."):
            try:
                results = search_chunks(conn, model, query, k=top_k_choice)
            except Exception as e:
                st.error(f"Error while searching: {e}")
                return

        if not results:
            st.info("No results found.")
            return

        # --------- Tabular view ----------
        st.subheader("Results (Table)")
        df = pd.DataFrame(results)

        # Ensure preview and similarity columns show nicely
        # (distance is kept for debugging/inspection)
        ordered_cols = [
            "id",
            "case_no",
            "section",
            "chunk_index",
            "similarity",
            "distance",
            "preview",
        ]
        cols_in_df = [c for c in ordered_cols if c in df.columns]
        df = df[cols_in_df]

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )

        # --------- Detailed per-result view ----------
        st.subheader("Detailed View")

        for i, row in enumerate(results, start=1):
            sim = row.get("similarity", None)
            sim_str = f"{sim:.3f}" if sim is not None else "N/A"

            header = f"{i}. Case {row['case_no']} • {row['section']} • Chunk #{row['chunk_index']} • Similarity: {sim_str}"
            with st.expander(header, expanded=(i == 1)):
                st.markdown("**Preview:**")
                st.write(row["text"])
                st.caption(
                    f"Chunk ID: {row['id']} | Distance: {float(row['distance']):.4f}"
                )

    # Optional: show connection status in sidebar
    with st.sidebar:
        try:
            conn = get_connection()
            st.success("✅ DB connected")
        except Exception as e:
            st.error(f"❌ DB connection failed: {e}")


if __name__ == "__main__":
    main()