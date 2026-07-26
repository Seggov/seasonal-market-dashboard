"""Punto de entrada de la aplicación Streamlit de análisis financiero."""

import streamlit as st


st.set_page_config(
    page_title="Finance | Análisis de mercados",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "Análisis descriptivo de series OHLC locales, sin descargas.",
    },
)

from src.interfaz import ejecutar_aplicacion


ejecutar_aplicacion()
