"""Centralized configuration for Streamlit secrets and environment variables."""
import os


def get_setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value not in (None, ""):
        return str(value)
    try:
        import streamlit as st
        value = st.secrets.get(name, default)
        return str(value) if value not in (None, "") else default
    except Exception:
        return default


def has_setting(name: str) -> bool:
    return bool(get_setting(name, "").strip())
