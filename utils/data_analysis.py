"""
Scientific Analysis Engine
pandas + scipy + statsmodels stack for automated statistical analysis.
"""

import io
import numpy as np
import pandas as pd
from scipy import stats
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional


# ── Data loading ──────────────────────────────────────────────────────────────

def load_file(file_bytes: bytes, filename: str) -> tuple:
    """Load CSV or Excel file into a DataFrame. Returns (df, error)."""
    try:
        name = filename.lower()
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
        elif name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(file_bytes))
        else:
            return None, "Unsupported format. Please upload a CSV or Excel file."
        # Basic cleanup
        df.columns = [str(c).strip() for c in df.columns]
        return df, ""
    except Exception as e:
        return None, str(e)


# ── Descriptive statistics ────────────────────────────────────────────────────

def describe_dataset(df: pd.DataFrame) -> dict:
    """Return a compact summary of the dataset structure and statistics."""
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()
    missing  = int(df.isnull().sum().sum())

    summary = {}
    if num_cols:
        desc = df[num_cols].describe().round(3)
        summary = desc.to_dict()

    return {
        "rows": len(df),
        "columns": len(df.columns),
        "numeric_columns": num_cols,
        "categorical_columns": cat_cols,
        "missing_values": missing,
        "missing_pct": round(100 * missing / max(df.size, 1), 1),
        "summary": summary,
    }


def dataset_context_for_ai(df: pd.DataFrame) -> str:
    """Build a concise text description of the dataset for the AI prompt."""
    info = describe_dataset(df)
    lines = [
        f"Rows: {info['rows']} | Columns: {info['columns']}",
        f"Numeric columns: {', '.join(info['numeric_columns']) or 'none'}",
        f"Categorical columns: {', '.join(info['categorical_columns']) or 'none'}",
        f"Missing values: {info['missing_values']} ({info['missing_pct']}%)",
    ]
    if info["summary"]:
        for col, stats_dict in list(info["summary"].items())[:4]:
            mean = stats_dict.get("mean", "?")
            std  = stats_dict.get("std", "?")
            lines.append(f"  {col}: mean={mean}, std={std}")
    return "\n".join(lines)


# ── Correlation ───────────────────────────────────────────────────────────────

def correlation_analysis(df: pd.DataFrame, cols: list) -> tuple:
    """Pearson correlation matrix + Plotly heatmap. Returns (corr_df, figure)."""
    subset = df[cols].select_dtypes(include=[np.number]).dropna()
    if len(subset.columns) < 2:
        return None, None
    corr = subset.corr().round(3)
    fig = go.Figure(go.Heatmap(
        z=corr.values,
        x=corr.columns.tolist(),
        y=corr.index.tolist(),
        colorscale="RdBu_r",
        zmid=0,
        text=corr.values.round(2),
        texttemplate="%{text}",
        colorbar=dict(title="r"),
    ))
    fig.update_layout(title="Correlation Matrix", height=420, margin=dict(l=10, r=10, t=40, b=10))
    return corr, fig


# ── Linear regression ─────────────────────────────────────────────────────────

def linear_regression(df: pd.DataFrame, target: str, features: list) -> dict:
    """OLS regression (statsmodels preferred, scipy fallback)."""
    data = df[[target] + features].dropna()
    if len(data) < 5:
        return {"error": "Not enough data points for regression (need ≥ 5)"}
    try:
        import statsmodels.api as sm
        X = sm.add_constant(data[features].astype(float))
        y = data[target].astype(float)
        model = sm.OLS(y, X).fit()
        return {
            "r_squared":     round(float(model.rsquared), 4),
            "adj_r_squared": round(float(model.rsquared_adj), 4),
            "f_statistic":   round(float(model.fvalue), 4),
            "p_value_f":     round(float(model.f_pvalue), 4),
            "coefficients":  {k: round(float(v), 4) for k, v in model.params.items()},
            "p_values":      {k: round(float(v), 4) for k, v in model.pvalues.items()},
            "n":             len(data),
        }
    except ImportError:
        pass
    # scipy fallback (single feature only)
    if len(features) == 1:
        x_vals = data[features[0]].astype(float)
        y_vals = data[target].astype(float)
        slope, intercept, r, p, se = stats.linregress(x_vals, y_vals)
        return {
            "r_squared":  round(r ** 2, 4),
            "slope":      round(float(slope), 4),
            "intercept":  round(float(intercept), 4),
            "p_value":    round(float(p), 4),
            "std_error":  round(float(se), 4),
            "n":          len(data),
        }
    return {"error": "statsmodels not installed — install it for multi-variable regression"}


def regression_scatter(df: pd.DataFrame, x: str, y: str) -> go.Figure:
    data = df[[x, y]].dropna()
    fig = px.scatter(data, x=x, y=y, trendline="ols",
                     title=f"{y} ~ {x}", height=380)
    fig.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    return fig


# ── T-test ────────────────────────────────────────────────────────────────────

def t_test_independent(s1: pd.Series, s2: pd.Series, label1: str = "A", label2: str = "B") -> dict:
    """Independent samples t-test."""
    a, b = s1.dropna().astype(float), s2.dropna().astype(float)
    t, p = stats.ttest_ind(a, b, equal_var=False)  # Welch's t-test
    return {
        "t_statistic": round(float(t), 4),
        "p_value":     round(float(p), 4),
        "significant": bool(p < 0.05),
        "n1":          len(a),
        "n2":          len(b),
        "mean1":       round(float(a.mean()), 4),
        "mean2":       round(float(b.mean()), 4),
        "interpretation": (
            f"Statistically significant difference between {label1} and {label2} (p={p:.4f})"
            if p < 0.05 else
            f"No significant difference between {label1} and {label2} (p={p:.4f})"
        ),
    }


# ── ANOVA ─────────────────────────────────────────────────────────────────────

def one_way_anova(df: pd.DataFrame, value_col: str, group_col: str) -> dict:
    """One-way ANOVA with group means."""
    groups_data = [g[value_col].dropna().astype(float).values
                   for _, g in df.groupby(group_col)]
    if len(groups_data) < 2:
        return {"error": "Need at least 2 groups for ANOVA"}
    f, p = stats.f_oneway(*groups_data)
    group_means = df.groupby(group_col)[value_col].mean().round(3).to_dict()
    return {
        "f_statistic":  round(float(f), 4),
        "p_value":      round(float(p), 4),
        "significant":  bool(p < 0.05),
        "groups":       len(groups_data),
        "group_means":  group_means,
        "interpretation": (
            f"Significant group differences (F={f:.3f}, p={p:.4f})" if p < 0.05
            else f"No significant group differences (F={f:.3f}, p={p:.4f})"
        ),
    }


# ── Chi-square ────────────────────────────────────────────────────────────────

def chi_square(df: pd.DataFrame, col1: str, col2: str) -> dict:
    """Chi-square test of independence for two categorical columns."""
    ct = pd.crosstab(df[col1], df[col2])
    chi2, p, dof, expected = stats.chi2_contingency(ct)
    return {
        "chi2_statistic": round(float(chi2), 4),
        "p_value":        round(float(p), 4),
        "degrees_of_freedom": int(dof),
        "significant":    bool(p < 0.05),
        "interpretation": (
            f"Significant association between {col1} and {col2} (p={p:.4f})" if p < 0.05
            else f"No significant association between {col1} and {col2} (p={p:.4f})"
        ),
    }


# ── Auto chart ────────────────────────────────────────────────────────────────

def auto_chart(df: pd.DataFrame, x: str, y: Optional[str] = None,
               hint: str = "", color: Optional[str] = None) -> go.Figure:
    """Choose the most appropriate chart type automatically."""
    is_num_x = pd.api.types.is_numeric_dtype(df[x])
    is_num_y = pd.api.types.is_numeric_dtype(df[y]) if y and y in df.columns else False

    if hint == "histogram" or not y:
        fig = px.histogram(df, x=x, title=f"Distribution — {x}", height=380)
    elif hint == "heatmap":
        corr_cols = [c for c in [x, y] if c in df.select_dtypes(include=[np.number]).columns]
        _, fig = correlation_analysis(df, corr_cols) if len(corr_cols) > 1 else (None, px.scatter(df, x=x, y=y))
    elif hint == "bar" or not is_num_x:
        grp = df.groupby(x)[y].mean().reset_index() if y else df[x].value_counts().reset_index()
        y_col = y if y else "count"
        if "count" not in grp.columns and y_col not in grp.columns:
            grp.columns = [x, y_col]
        fig = px.bar(grp, x=x, y=y_col, title=f"{y or 'Count'} by {x}", height=380)
    elif hint == "box":
        fig = px.box(df, x=color, y=x if not y else y, title=f"Distribution by group", height=380)
    elif is_num_x and is_num_y:
        fig = px.scatter(df, x=x, y=y, color=color, trendline="ols",
                         title=f"{y} vs {x}", height=380)
    else:
        fig = px.histogram(df, x=x, title=f"Distribution — {x}", height=380)

    fig.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    return fig


# ── Distribution overview ─────────────────────────────────────────────────────

def distribution_grid(df: pd.DataFrame, cols: list, max_cols: int = 3) -> go.Figure:
    """Small-multiples histogram for numeric columns."""
    import math
    from plotly.subplots import make_subplots

    n = min(len(cols), 9)
    cols = cols[:n]
    ncols = min(n, max_cols)
    nrows = math.ceil(n / ncols)

    fig = make_subplots(rows=nrows, cols=ncols, subplot_titles=cols)
    for i, col in enumerate(cols):
        r, c = divmod(i, ncols)
        data = df[col].dropna()
        fig.add_trace(go.Histogram(x=data, name=col, showlegend=False), row=r + 1, col=c + 1)

    fig.update_layout(height=260 * nrows, margin=dict(l=10, r=10, t=40, b=10),
                      title_text="Variable Distributions")
    return fig
