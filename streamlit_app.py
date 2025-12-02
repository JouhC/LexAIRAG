import streamlit as st
import pandas as pd
import requests
from config import settings

DEFAULT_API_URL = settings.DEFAULT_API_URL if hasattr(settings, "DEFAULT_API_URL") else "http://localhost:8000"

def call_search_api(query: str, k: int):
    api_url = DEFAULT_API_URL
    url = f"{api_url.rstrip('/')}/search"
    payload = {"query": query, "k": k}

    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def main():
    st.set_page_config(page_title="LexAI Vector Search", layout="wide")
    st.title("🔍 LexAI Vector Search (via API)")

    with st.sidebar:
        st.header("Settings")
        top_k_choice = st.radio(
            "Number of results",
            options=[5, 10],
            index=0,
        )
        st.caption(f"API URL: `{DEFAULT_API_URL}`")

    query = st.text_area(
        "Query",
        placeholder="e.g. liability of carrier for loss of goods...",
        height=100,
    )

    if st.button("Search"):
        if not query.strip():
            st.warning("Please enter a query.")
            return

        with st.spinner("Calling LexAI API..."):
            try:
                data = call_search_api(query.strip(), top_k_choice)
            except requests.exceptions.RequestException as e:
                st.error(f"API request failed: {e}")
                return

        results = data.get("results", [])
        if not results:
            st.info("No results returned.")
            return

        # Table view
        st.subheader("Results (Table)")
        df = pd.DataFrame(results)

        # Order columns for nicer display
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
            hide_index=True,
        )

        # Detailed view
        st.subheader("Detailed View")
        for i, row in enumerate(results, start=1):
            sim = row.get("similarity")
            sim_str = f"{sim:.3f}" if sim is not None else "N/A"
            header = (
                f"{i}. Case {row.get('case_no')} • "
                f"{row.get('section')} • Chunk #{row.get('chunk_index')} "
                f"• Similarity: {sim_str}"
            )
            with st.expander(header, expanded=(i == 1)):
                st.markdown("**Preview:**")
                st.write(row.get("preview", ""))
                st.caption(
                    f"Chunk ID: {row.get('id')} | Distance: {float(row.get('distance', 0)):.4f}"
                )


if __name__ == "__main__":
    main()
