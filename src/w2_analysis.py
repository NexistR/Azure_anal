"""Read-only Telco EDA for the integrated Azure churn project.

Analysis-only bins and six-service counts are never exported as customer features.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

PACKAGE = Path(__file__).resolve().parents[1]
PROJECT = PACKAGE
WORKSPACE = PROJECT.parent
REPORTS = PACKAGE / "reports"
TABLES = REPORTS / "tables"
FIGURES = REPORTS / "figures" / "w2_eda"
SEED = 42
SERVICES = ["OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies"]
TENURE_LABELS = ["[0,6)", "[6,12)", "[12,24)", "[24,48)", "[48,73)"]
CONTRACTS = ["Month-to-month", "One year", "Two year"]
LIMIT = "Telco公开代理数据；横截面关联；无事件日期；月费为价值代理，非CLV。"
COLORS = ["#176b87", "#e07a5f", "#43876d", "#b99442", "#8564a0", "#51799c"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_table(frame, name):
    TABLES.mkdir(parents=True, exist_ok=True)
    frame.to_csv(TABLES / f"{name}.csv", index=False, encoding="utf-8-sig", float_format="%.12g")
    return frame


def rate_table(frame, groups):
    """Observed customer-level rate with pointwise 95% Wilson intervals."""
    groups = [groups] if isinstance(groups, str) else groups
    result = frame.groupby(groups, observed=True, dropna=False)["churn"].agg(n="size", churned="sum").reset_index()
    n, k = result["n"].to_numpy(), result["churned"].to_numpy()
    p, z = k / n, stats.norm.ppf(0.975)
    center = (p + z*z / (2*n)) / (1 + z*z/n)
    half = z * np.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
    result["churn_rate"] = p
    result["ci_low"] = np.maximum(0, center-half)
    result["ci_high"] = np.minimum(1, center+half)
    result["small_group"] = n < 30
    return result


def load_data():
    path = PROJECT / "data/raw/telco_customer_churn/WA_Fn-UseC_-Telco-Customer-Churn.csv"
    manifest = pd.read_csv(PROJECT / "reports/tables/data_manifest.csv")
    expected = manifest.loc[manifest["relative_path"].eq(path.relative_to(PROJECT).as_posix()), "sha256"].iloc[0].lower()
    assert sha256(path) == expected, "Input hash differs from W1 manifest"
    raw = pd.read_csv(path, dtype={"TotalCharges": "string"})
    assert raw.shape == (7043, 21)
    assert raw.customerID.notna().all() and raw.customerID.is_unique
    assert set(raw.Churn.unique()) == {"Yes", "No"}
    assert raw.Churn.eq("Yes").sum() == 1869
    assert raw.tenure.between(0, 72).all() and raw.MonthlyCharges.gt(0).all()
    assert set(raw.InternetService.unique()) == {"DSL", "Fiber optic", "No"}
    for col in SERVICES:
        assert set(raw[col].unique()) == {"Yes", "No", "No internet service"}
    # Exclude TotalCharges at the analysis boundary; inspect blanks only in the quality audit.
    df = raw.drop(columns=["TotalCharges", "customerID"]).copy()
    df["churn"] = df.Churn.eq("Yes").astype(int)
    df["service_count"] = df[SERVICES].eq("Yes").sum(axis=1)
    df["tenure_band"] = pd.cut(df.tenure, [0, 6, 12, 24, 48, 73], right=False, labels=TENURE_LABELS)
    df["fee_quartile"], edges = pd.qcut(df.MonthlyCharges, 4, labels=["Q1", "Q2", "Q3", "Q4"], retbins=True)
    df["has_internet"] = df.InternetService.ne("No")
    df["fee_level"] = np.where(df.MonthlyCharges.ge(df.MonthlyCharges.median()), "High fee", "Low fee")
    df["service_level"] = np.where(df.service_count.le(2), "0-2 add-ons", "3-6 add-ons")
    df["manual_payment"] = df.PaymentMethod.isin(["Electronic check", "Mailed check"])
    df["risk_rule"] = np.where(df.Contract.eq("Month-to-month") & df.tenure.lt(6), "Rule flagged", "Other customers")
    assert df.tenure_band.notna().all() and df.service_count.between(0, 6).all()
    assert not df.loc[~df.has_internet, "service_count"].any()
    return raw, df, path, edges


def analyze():
    np.random.seed(SEED)
    raw, df, path, edges = load_data()
    source_hash_before = sha256(path)
    internet = df.loc[df.has_internet].copy()
    tables = {}
    tests = []

    def population(frame):
        internet_types = "/".join(sorted(frame.InternetService.unique()))
        high_fee_only = bool(frame.fee_level.eq("High fee").all())
        return f"InternetService={internet_types}" + ("; MonthlyCharges >= full-sample median" if high_fee_only else "")

    def table(name, frame):
        tables[name] = save_table(frame, name)
        return frame

    def chi(test_id, hypothesis, frame, column, family="primary"):
        c = pd.crosstab(frame[column], frame.churn).reindex(columns=[0, 1], fill_value=0)
        chi2, p, dof, expected = stats.chi2_contingency(c, correction=False)
        effect = np.sqrt(chi2 / (c.to_numpy().sum() * min(c.shape[0]-1, c.shape[1]-1)))
        method = "Pearson chi-square (no Yates)"
        statistic = chi2
        if expected.min() < 5 and c.shape == (2, 2):
            statistic, p = stats.fisher_exact(c)
            method = "Fisher exact (two-sided); effect remains Cramers V"
        tests.append(dict(test_id=test_id, hypothesis_id=hypothesis, family=family, method=method,
                          population=population(frame),
                          n=len(frame), statistic=statistic, p_value=p, effect_name="Cramers V", effect=effect,
                          dof=dof, min_expected=expected.min(), sparse_expected=bool(expected.min()<5)))

    def spearman(test_id, hypothesis, frame, column, family="primary"):
        result = stats.spearmanr(frame[column], frame.churn)
        tests.append(dict(test_id=test_id, hypothesis_id=hypothesis, family=family, method="Spearman (two-sided)",
                          population=population(frame),
                          n=len(frame), statistic=result.statistic, p_value=result.pvalue,
                          effect_name="Spearman rho", effect=result.statistic, dof=np.nan,
                          min_expected=np.nan, sparse_expected=False))

    table("w2_churn_distribution", df.groupby("Churn").size().rename("n").reset_index().assign(share=lambda x: x.n/len(df)))
    table("w2_contract_rates", rate_table(df, "Contract"))
    table("w2_tenure_rates", rate_table(df, "tenure_band"))
    table("w2_service_count_all", rate_table(df, "service_count"))
    table("w2_service_count_internet", rate_table(internet, "service_count"))
    table("w2_service_count_by_internet", rate_table(df, ["InternetService", "service_count"]))
    table("w2_fee_quartile_rates", rate_table(df, "fee_quartile"))
    table("w2_payment_rates", rate_table(df, "PaymentMethod"))
    table("w2_manual_payment_rates", rate_table(df, "manual_payment"))
    table("w2_contract_tenure_rates", rate_table(df, ["Contract", "tenure_band"]))
    table("w2_contract_payment_rates", rate_table(df, ["Contract", "PaymentMethod"]))
    table("w2_fee_service_rates", rate_table(internet, ["fee_level", "service_level"]))
    table("w2_fee_service_by_internet", rate_table(internet, ["InternetService", "fee_level", "service_level"]))
    risk = rate_table(df, ["risk_rule", "fee_level"])
    risk = risk.merge(df.groupby(["risk_rule", "fee_level"], observed=True).MonthlyCharges.agg(
        monthly_charge_sum="sum", monthly_charge_mean="mean").reset_index(), on=["risk_rule", "fee_level"], validate="one_to_one")
    risk["customer_share"] = risk.n / len(df)
    risk["monthly_charge_share"] = risk.monthly_charge_sum / df.MonthlyCharges.sum()
    table("w2_risk_value_prototype", risk)
    adoption = []
    service_rates = []
    for service in SERVICES:
        adoption.append(dict(service=service, n_all=len(df), adopted=int(df[service].eq("Yes").sum()),
                             adoption_all=df[service].eq("Yes").mean(), n_eligible=len(internet),
                             adoption_eligible=internet[service].eq("Yes").mean()))
        rates = rate_table(internet, service).rename(columns={service: "adoption"})
        rates.insert(0, "service", service)
        service_rates.append(rates)
        chi("service_"+service, "H4", internet, service, "six_services")
    table("w2_service_adoption", pd.DataFrame(adoption))
    table("w2_individual_service_rates", pd.concat(service_rates, ignore_index=True))
    demographics = []
    for col in ["gender", "SeniorCitizen", "Partner", "Dependents"]:
        rates = rate_table(df, col).rename(columns={col: "group"})
        rates.insert(0, "field", col)
        demographics.append(rates)
        chi("demographic_"+col, "H9", df, col, "demographics")
    table("w2_demographic_rates", pd.concat(demographics, ignore_index=True))
    table("w2_demographic_joint", rate_table(df, ["SeniorCitizen", "Partner", "Dependents"]))
    table("w2_internet_rates", rate_table(df, "InternetService"))
    combo = internet.copy()
    combo["combination"] = combo[SERVICES].eq("Yes").astype(int).astype(str).agg("".join, axis=1)
    table("w2_service_combinations", rate_table(combo, "combination").sort_values("n", ascending=False, kind="stable"))
    numeric = df[["tenure", "MonthlyCharges", "SeniorCitizen", "service_count", "churn"]].corr(method="spearman")
    table("w2_spearman_matrix", numeric.rename_axis("field").reset_index())
    table("w2_numeric_summary", df[["tenure", "MonthlyCharges"]].describe().rename_axis("statistic").reset_index())
    table("w2_schema_audit", pd.DataFrame([dict(field=c, dtype=str(raw[c].dtype),
          missing=int(raw[c].isna().sum()), unique=int(raw[c].nunique())) for c in raw]))

    chi("H1_contract_all", "H1", df, "Contract")
    spearman("H2_tenure_all", "H2", df, "tenure")
    spearman("H4_services_internet", "H4", internet, "service_count")
    chi("H5_low_services_among_high_fee_internet", "H5", internet.loc[internet.fee_level.eq("High fee")], "service_level")
    chi("H6_manual_payment_all", "H6", df, "manual_payment")
    chi("H10_fee_quartiles_all", "H10", df, "fee_quartile")
    spearman("H4_services_all_sensitivity", "H4", df, "service_count", "sensitivity")
    for kind in ["DSL", "Fiber optic"]:
        spearman("H4_services_"+kind, "H4", df.loc[df.InternetService.eq(kind)], "service_count", "sensitivity")
        subset = internet.loc[internet.fee_level.eq("High fee") & internet.InternetService.eq(kind)]
        chi("H5_high_fee_"+kind, "H5", subset, "service_level", "sensitivity")
    spearman("H2_without_tenure_zero", "H2", df.loc[df.tenure.ne(0)], "tenure", "sensitivity")
    test_frame = pd.DataFrame(tests)
    test_frame["family_size"] = test_frame.groupby("family").test_id.transform("size")
    test_frame["p_bonferroni"] = np.minimum(1, test_frame.p_value * test_frame.family_size)
    test_frame["significant_adjusted"] = test_frame.p_bonferroni < 0.05
    table("w2_statistical_tests", test_frame)

    blanks = raw.TotalCharges.str.strip().eq("")
    no_internet = raw.InternetService.eq("No")
    service_conflicts = sum(int((raw[c].eq("No internet service") != no_internet).sum()) for c in SERVICES)
    q1, q3 = df.MonthlyCharges.quantile([.25, .75])
    lower, upper = q1-1.5*(q3-q1), q3+1.5*(q3-q1)
    quality = pd.DataFrame([
        ("rows", len(raw), "W1 baseline 7043"), ("columns", len(raw.columns), "W1 baseline 21"),
        ("duplicate_customer_id", int(raw.customerID.duplicated().sum()), "Must be zero"),
        ("duplicate_rows", int(raw.duplicated().sum()), "Must be zero"),
        ("explicit_null_cells", int(raw.isna().sum().sum()), "Does not detect whitespace strings"),
        ("total_charges_whitespace", int(blanks.sum()), "Read-only audit; not converted or analyzed"),
        ("tenure_zero", int(raw.tenure.eq(0).sum()), "Retained in W2"),
        ("blank_charges_and_zero_tenure", int((blanks & raw.tenure.eq(0)).sum()), "No automatic imputation decision"),
        ("no_internet_customers", int(no_internet.sum()), "Structural ineligibility is not missingness"),
        ("addon_logic_conflicts", service_conflicts, "Across six service fields"),
        ("phone_logic_conflicts", int((raw.PhoneService.eq("No") != raw.MultipleLines.eq("No phone service")).sum()), "No phone service consistency"),
        ("monthly_charge_iqr_outliers", int((df.MonthlyCharges.lt(lower)|df.MonthlyCharges.gt(upper)).sum()), "Statistical rule only; not a cleaning decision"),
    ], columns=["check", "value", "interpretation"])
    table("w2_quality_observations", quality)
    ticket_path = PROJECT / "data/raw/customer_support_tickets/customer_support_tickets.csv"
    ticket_columns = list(pd.read_csv(ticket_path, nrows=0).columns)
    common = sorted(set(raw.columns) & set(ticket_columns))
    h7 = dict(telco_key="customerID", ticket_columns=ticket_columns, exact_common_columns=common,
              verified_customer_key=False, intersection_count=None, coverage=None,
              decision="不可验证：工单表无Telco customerID及可靠映射，Telco无快照时间；未合并。")
    (REPORTS / "w2_h7_feasibility.json").write_text(json.dumps(h7, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = dict(seed=SEED, source=path.relative_to(WORKSPACE).as_posix(), source_sha256=sha256(path),
                    rows=len(df), columns=len(raw.columns), churned=int(df.churn.sum()), churn_rate=df.churn.mean(),
                    internet_users=len(internet), six_services=SERVICES, tenure_bins=[0,6,12,24,48,73],
                    tenure_intervals="Left closed, right open", fee_quartile_edges=edges.tolist(),
                    high_fee_threshold=float(df.MonthlyCharges.median()), low_service_threshold=2,
                    risk_rule="Contract == Month-to-month AND tenure < 6; no predicted probability",
                    raw_unchanged=sha256(path)==source_hash_before,
                    python=platform.python_version(),
                    packages={p:importlib.metadata.version(p) for p in ["pandas","numpy","matplotlib","seaborn","scipy","nbformat","nbclient","nbconvert","ipykernel"]})
    # Source hash is also checked against the frozen W1 manifest again by the verification runner.
    (REPORTS / "w2_analysis_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return dict(df=df, raw=raw, tables=tables, tests=test_frame, metadata=metadata, h7=h7)


def configure_plots():
    sns.set_theme(style="whitegrid", palette=COLORS)
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    chinese = next((f for f in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC"] if f in fonts), None)
    plt.rcParams.update({"font.sans-serif": [chinese or "DejaVu Sans", "DejaVu Sans"],
                         "axes.unicode_minus": False, "axes.spines.top": False,
                         "axes.spines.right": False, "font.size": 10})
    return chinese


def plot_all(result):
    configure_plots()
    FIGURES.mkdir(parents=True, exist_ok=True)
    df, t = result["df"], result["tables"]
    charts = []

    def test_note(ax, test_id, comparison=""):
        row = result["tests"].set_index("test_id").loc[test_id]
        label = (comparison+"\n" if comparison else "")+f"{row.effect_name}={row.effect:.3f}; adjusted p={row.p_bonferroni:.2e}"
        ax.text(.5, -.23, label, transform=ax.transAxes, ha="center", fontsize=9)

    def save(fig, number, slug, title, hypothesis, kind, conclusion, action, evidence):
        fig.suptitle(f"{number:02d} | {title} | {hypothesis}", fontsize=15, fontweight="bold")
        fig.text(.015, .015, "Telco proxy | Cross-sectional association | MonthlyCharges is not CLV", fontsize=8, color="#555555")
        fig.tight_layout(rect=[0,.045,1,.94])
        filename = f"{number:02d}_{slug}.png"
        fig.savefig(FIGURES / filename, dpi=300, facecolor="white", metadata={"Software":"Week2 EDA"})
        plt.close(fig)
        charts.append(dict(chart_id=f"{number:02d}", hypothesis_id=hypothesis, category=kind, title=title,
                           conclusion=conclusion, action=action, path=f"reports/figures/w2_eda/{filename}",
                           evidence=f"reports/tables/{evidence}.csv", limitations=LIMIT))

    def rates(ax, data, group, title=None):
        data = data.reset_index(drop=True)
        x = np.arange(len(data))
        y = data.churn_rate.to_numpy()
        err = np.vstack([y-data.ci_low.to_numpy(), data.ci_high.to_numpy()-y])
        ax.bar(x, y, color=[COLORS[i%len(COLORS)] for i in x], yerr=err, capsize=3, alpha=.9)
        ax.set_xticks(x, data[group].astype(str), rotation=18 if len(data)>4 else 0, ha="center")
        ax.set_ylim(0, min(1, max(.15, float(data.ci_high.max())+.14)))
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.set_ylabel("Observed churn rate (95% Wilson CI)")
        ax.set_xlabel(group)
        for i, row in data.iterrows():
            ax.text(i, row.ci_high+.012, f"{row.churn_rate:.1%}\nn={row.n:,}"+(" *" if row.small_group else ""), ha="center", fontsize=9)
        if title:
            ax.set_title(title)

    def heat(ax, data, row, col):
        pivot = data.pivot(index=row, columns=col, values="churn_rate")
        counts = data.pivot(index=row, columns=col, values="n").reindex_like(pivot)
        labels = pivot.copy().astype(object)
        for r in pivot.index:
            for c in pivot.columns:
                value, count = pivot.loc[r,c], counts.loc[r,c]
                labels.loc[r,c] = "" if pd.isna(value) else f"{value:.1%}\nn={count:.0f}"+(" *" if count<30 else "")
        sns.heatmap(pivot, annot=labels, fmt="", cmap="YlOrRd", vmin=0, vmax=1, ax=ax,
                    cbar_kws={"label":"Observed churn rate"}, linewidths=1)
        ax.tick_params(axis="x", rotation=15)
        ax.tick_params(axis="y", rotation=0)

    fig, axes = plt.subplots(1,2,figsize=(11,5))
    counts = df.Churn.value_counts().reindex(["No","Yes"])
    axes[0].bar(counts.index, counts, color=COLORS[:2]); axes[0].set(xlabel="Churn",ylabel="Customers")
    for i,v in enumerate(counts): axes[0].text(i,v+40,f"{v:,}",ha="center")
    axes[1].pie(counts, labels=["No","Yes"], autopct="%.2f%%",colors=COLORS[:2],startangle=90)
    save(fig,1,"churn_distribution","流失标签分布","基础","分布",f"流失1,869/7,043（{df.churn.mean():.2%}）。","后续评估保留类别占比基线。","w2_churn_distribution")
    fig,ax=plt.subplots(figsize=(10,5)); sns.histplot(df.tenure,bins=np.arange(0,75,3),kde=True,ax=ax,color=COLORS[0]); ax.set(xlabel="Tenure (months)",ylabel="Customers")
    save(fig,2,"tenure_distribution","客户年限分布","H2","分布",f"tenure<6客户占{df.tenure.lt(6).mean():.2%}；0月客户11名。","新客分层使用明确的左闭右开月数区间。","w2_tenure_rates")
    fig,axes=plt.subplots(1,2,figsize=(11,5)); sns.histplot(df.MonthlyCharges,bins=30,ax=axes[0],color=COLORS[0]); sns.boxplot(y=df.MonthlyCharges,ax=axes[1],color=COLORS[0]); axes[0].set(xlabel="MonthlyCharges (dataset units)",ylabel="Customers"); axes[1].set_ylabel("MonthlyCharges (dataset units)")
    save(fig,3,"monthly_charges_distribution","月费分布","H10,H5","分布",f"月费中位数{df.MonthlyCharges.median():.2f}，范围{df.MonthlyCharges.min():.2f}–{df.MonthlyCharges.max():.2f}。","以中位数划分价值代理，货币单位不作额外推断。","w2_numeric_summary")
    for number,column,hypothesis in [(4,"Contract","H1"),(5,"PaymentMethod","H6")]:
        fig,ax=plt.subplots(figsize=(11,5)); counts=df[column].value_counts(); ax.bar(counts.index,counts,color=COLORS[:len(counts)]); ax.set(xlabel=column,ylabel="Customers"); ax.tick_params(axis="x",rotation=12)
        for i,v in enumerate(counts): ax.text(i,v+30,f"{v:,}\n{v/len(df):.1%}",ha="center",fontsize=9)
        ax.set_ylim(0,counts.max()*1.18)
        save(fig,number,column.lower()+"_distribution",column+"客户构成",hypothesis,"分布",f"最多类别为{counts.index[0]}，共{counts.iloc[0]:,}名。","结合各组样本量解读后续流失率差异。","w2_contract_rates" if number==4 else "w2_payment_rates")
    fig,ax=plt.subplots(figsize=(11,5)); adoption=t["w2_service_adoption"]; x=np.arange(6); ax.bar(x-.18,adoption.adoption_all,width=.36,label="All customers"); ax.bar(x+.18,adoption.adoption_eligible,width=.36,label="Internet users"); ax.set_xticks(x,SERVICES,rotation=15); ax.set(xlabel="Internet add-on service",ylabel="Adoption rate"); ax.yaxis.set_major_formatter(PercentFormatter(1)); ax.legend()
    save(fig,6,"service_adoption","六项互联网增值服务采用率","H4","分布","无互联网客户不具备采用六项增值服务的条件，分母会影响采用率。","服务采用报告同时标明全体与互联网客户分母。","w2_service_adoption")
    fig,ax=plt.subplots(figsize=(10,5)); ctr=t["w2_contract_rates"].set_index("Contract").loc[CONTRACTS].reset_index(); rates(ax,ctr,"Contract")
    test_note(ax,"H1_contract_all")
    con="；".join(f"{r.Contract} {r.churn_rate:.2%}" for r in ctr.itertuples())
    save(fig,7,"h1_contract_churn","合同类型与流失率","H1","关联",con+"。","将月付客户列为进一步访谈候选，年付转换效果尚需验证。","w2_contract_rates")
    fig,ax=plt.subplots(figsize=(10,5)); r=t["w2_tenure_rates"]; ax.errorbar(np.arange(len(r)),r.churn_rate,yerr=np.vstack([r.churn_rate-r.ci_low,r.ci_high-r.churn_rate]),marker="o",capsize=5); ax.set_xticks(np.arange(len(r)),r.tenure_band.astype(str)); ax.set(xlabel="Tenure intervals (months; left-closed)",ylabel="Observed churn rate (95% Wilson CI)"); ax.yaxis.set_major_formatter(PercentFormatter(1)); ax.set_ylim(0,.7)
    for i,row in r.iterrows(): ax.text(i,row.ci_high+.02,f"{row.churn_rate:.1%}\nn={row.n:,}",ha="center")
    test_note(ax,"H2_tenure_all")
    save(fig,8,"h2_tenure_churn","客户年限与流失率","H2","关联",f"[0,6)月组{r.iloc[0].churn_rate:.2%}，[48,73)月组{r.iloc[-1].churn_rate:.2%}。","优先研究上手体验；横截面不能解释为同一批客户的时间趋势。","w2_tenure_rates")
    fig,axes=plt.subplots(1,2,figsize=(13,5),sharey=True); rates(axes[0],t["w2_service_count_all"],"service_count","All customers (sensitivity)"); rates(axes[1],t["w2_service_count_internet"],"service_count","Internet users (primary)")
    test_note(axes[0],"H4_services_all_sensitivity"); test_note(axes[1],"H4_services_internet")
    save(fig,9,"h4_service_count_churn","增值服务数与流失率","H4","关联","全体0服务组混合无互联网客户；互联网客户内少服务与较高流失相关。","W3保留无互联网状态；W4再将服务计数正式工程化。","w2_service_count_internet")
    fig,axes=plt.subplots(2,3,figsize=(13,8)); sr=t["w2_individual_service_rates"]
    for ax,service in zip(axes.flat,SERVICES): rates(ax,sr.loc[sr.service.eq(service)],"adoption",service)
    for ax in axes.flat: ax.set_ylim(0,.6)
    save(fig,10,"h4_individual_services","各增值服务与流失率（互联网客户）","H4","关联","服务之间关联强度不同，安全与技术支持需重点进一步核查。","六项比较使用Bonferroni校正，不能把采用关联解读为加购效果。","w2_individual_service_rates")
    fig,ax=plt.subplots(figsize=(10,5)); rates(ax,t["w2_fee_quartile_rates"],"fee_quartile")
    test_note(ax,"H10_fee_quartiles_all")
    save(fig,11,"h10_fee_quartiles","月费四分位与流失率","H10","关联","月费组间流失率有差异，具体走势见分位表，不能假设严格单调。","价值优先级同时参考风险规则和费用，暂不计算CLV。","w2_fee_quartile_rates")
    fig,ax=plt.subplots(figsize=(11,6)); rng=np.random.default_rng(SEED); internet=df.loc[df.has_internet]; jitter=rng.uniform(-.16,.16,len(internet))
    for churn,label,color in [(0,"No churn",COLORS[0]),(1,"Churn",COLORS[1])]:
        mask=internet.churn.eq(churn).to_numpy(); ax.scatter(internet.service_count.to_numpy()[mask]+jitter[mask],internet.MonthlyCharges.to_numpy()[mask],s=10,alpha=.23,color=color,label=label,rasterized=True)
    ax.axvline(2.5,color="#333333",ls="--"); ax.axhline(df.MonthlyCharges.median(),color="#333333",ls="--"); ax.set(xlabel="Six-service count (display jitter only)",ylabel="MonthlyCharges (dataset units)"); ax.legend()
    test_note(ax,"H5_low_services_among_high_fee_internet","High-fee internet users: 0-2 vs 3-6 add-ons")
    r=t["w2_fee_service_rates"]; high=r.loc[r.fee_level.eq("High fee")].set_index("service_level")
    save(fig,12,"h5_fee_service_scatter","月费与服务数（互联网客户）","H5","关联",f"高月费0–2服务组流失{high.loc['0-2 add-ons','churn_rate']:.2%}，3–6服务组{high.loc['3-6 add-ons','churn_rate']:.2%}。","核查套餐与服务适配；价格感知和实际使用深度缺字段，尚不可验证。","w2_fee_service_rates")
    fig,ax=plt.subplots(figsize=(12,5)); rates(ax,t["w2_payment_rates"],"PaymentMethod")
    test_note(ax,"H6_manual_payment_all","Manual vs automatic payment (pooled groups)")
    save(fig,13,"h6_payment_churn","支付方式与流失率","H6","关联","Electronic check组流失率较高，手动支付组内部也有差异。","支付方式不等于支付失败或自动续费；先核查合同构成。","w2_payment_rates")
    fig,axes=plt.subplots(2,2,figsize=(12,8)); demo=t["w2_demographic_rates"]
    for ax,col in zip(axes.flat,["gender","SeniorCitizen","Partner","Dependents"]): rates(ax,demo.loc[demo.field.eq(col)],"group",col)
    save(fig,14,"h9_demographics","人口统计细分与流失率","H9","关联","并非所有人口字段都存在显著差异；性别与其他细分分别检验。","仅用于公平性与细分稳定性核查，不替代缺失的地区或行业字段。","w2_demographic_rates")
    fig,ax=plt.subplots(figsize=(12,5)); heat(ax,t["w2_contract_tenure_rates"],"Contract","tenure_band")
    save(fig,15,"contract_tenure_heatmap","合同×年限交叉流失率","H1,H2","交叉","月付与短年限组合呈较高观察流失；小样本格标*，不据此作稳定排序。","W4记录交互候选；未做正式交互显著性检验。","w2_contract_tenure_rates")
    fig,ax=plt.subplots(figsize=(9,7)); matrix=t["w2_spearman_matrix"].set_index("field"); sns.heatmap(matrix,annot=True,fmt=".2f",cmap="vlag",center=0,vmin=-1,vmax=1,ax=ax); ax.tick_params(axis="x",rotation=20)
    save(fig,16,"spearman_correlation","数值变量Spearman相关矩阵","H2,H4,H10","交叉","矩阵含Churn仅作标签关联说明；服务数与费用也存在关联。","W4排除Churn及其派生字段；本图不构成完整共线性诊断。","w2_spearman_matrix")
    fig,ax=plt.subplots(figsize=(10,6)); heat(ax,t["w2_risk_value_prototype"],"risk_rule","fee_level")
    ax.set_title(f"Rule flagged: Month-to-month & tenure < 6 | High fee: MonthlyCharges >= {df.MonthlyCharges.median():.2f}",fontsize=10)
    save(fig,17,"risk_value_prototype","风险规则×月费价值代理矩阵","H10","交叉","风险规则为月付且tenure<6，高价值为月费≥全体中位数；格内为已观察流失率。","仅展示分层雏形；W7完成验证后的风险评分才可支持后续排序。","w2_risk_value_prototype")
    fig,axes=plt.subplots(1,3,figsize=(15,5)); by=t["w2_service_count_by_internet"]
    for ax,kind in zip(axes,["No","DSL","Fiber optic"]): rates(ax,by.loc[by.InternetService.eq(kind)],"service_count",kind)
    for ax in axes: ax.set_ylim(0,.85)
    save(fig,18,"internet_service_stratification","互联网类型内的服务数对比","H4","交叉","0服务客户在不同互联网类型中基线不同；分层后再判断服务数量方向。","保留InternetService类别并对分层结果做敏感性核查。","w2_service_count_by_internet")
    fig,ax=plt.subplots(figsize=(13,5)); heat(ax,t["w2_contract_payment_rates"],"Contract","PaymentMethod")
    save(fig,19,"contract_payment_heatmap","合同×支付方式交叉流失率","H6,H1","交叉","支付方式差异需要结合合同类型解读，各格样本量并不相同。","将支付方式候选解释与合同构成共同复核。","w2_contract_payment_rates")
    fig,ax=plt.subplots(figsize=(12,5)); combos=t["w2_service_combinations"].head(10); rates(ax,combos,"combination"); ax.set_xlabel("Six-service Yes=1 / No=0, in documented order (top 10 by n)")
    save(fig,20,"service_combinations","互联网客户常见增值服务组合","H4","交叉","按样本量列出前十种组合，组合间差异是探索结果，未做独立确认检验。","用组合分布支持需求访谈，不根据本图推荐强制加购。","w2_service_combinations")
    return save_table(pd.DataFrame(charts), "w2_chart_hypothesis_mapping")


def hypothesis_results(result):
    t, tests = result["tables"], result["tests"].set_index("test_id")
    original = pd.read_csv(PROJECT / "reports/hypothesis_matrix_v1.csv").set_index("hypothesis_id")
    specifications = [
        ("H1", "通过", "H1_contract_all", "合同类型与观察流失有关，月付组高于一年期与两年期。", "月付客户访谈和上手支持候选；不声称年付转换的因果效果。"),
        ("H2", "通过", "H2_tenure_all", "年限与标签负相关；低tenure组观察流失率更高。", "核查新客体验；无事件日期，不能据此估计生存曲线。"),
        ("H3", "不可验证", None, "缺登录、资源使用量及30–90天时间序列。", "补充真实使用事件与快照日期后再验证。"),
        ("H4", "部分通过", "H4_services_internet", "互联网客户内服务数与流失负相关；全体0服务组混杂无互联网客户，非简单全局单调关系。", "保留服务适用性，采用六项互联网增值服务统一口径；使用深度不可验证。"),
        ("H5", "部分通过", "H5_low_services_among_high_fee_internet", "高月费互联网客户中少服务组流失较高；光纤内方向一致，但DSL高费少服务组样本极少、校正不显著；价格感知与使用深度不可观察。", "核查套餐适配与使用数据；不能断言客户认为性价比低或所有网络子群都成立。"),
        ("H6", "部分通过", "H6_manual_payment_all", "手动与自动支付组观察流失不同，电子支票差异突出；支付失败无数据。", "结合合同分层复核；自动支付不等于自动续费。"),
        ("H7", "不可验证", None, result["h7"]["decision"], "需稳定共同客户键、映射依据和一致观察窗口；不按姓名或行号拼接。"),
        ("H8", "不可验证", None, "沿用W1定义：自动续费与历史续约；缺自动续费标志、续约历史、到期日。", "H8不改写为支付失败；不以tenure或PaymentMethod替代证据。"),
        ("H9", "部分通过", "demographic_SeniorCitizen", "部分人口细分基线存在差异，性别无显著证据；未验证各群驱动权重差异。", "检查细分稳定性与公平性；无地区、行业、企业规模字段。"),
        ("H10", "部分通过", "H10_fee_quartiles_all", "完成月费分位关联与风险规则×价值矩阵雏形；未证明资源分配效果。", "MonthlyCharges只是价值代理；无预测概率、CLV、毛利或ROI结果。"),
    ]
    contract_rates=t["w2_contract_rates"].set_index("Contract").churn_rate
    tenure_rates=t["w2_tenure_rates"].churn_rate
    fee_service=t["w2_fee_service_rates"].query("fee_level == 'High fee'").set_index("service_level").churn_rate
    payment=t["w2_manual_payment_rates"].set_index("manual_payment").churn_rate
    direction = {
        "H1": bool(contract_rates["Month-to-month"] > contract_rates[["One year","Two year"]].max()),
        "H2": bool(tests.loc["H2_tenure_all","effect"] < 0 and tenure_rates.iloc[0] > tenure_rates.iloc[-1]),
        "H4": bool(tests.loc["H4_services_internet","effect"] < 0),
        "H5": bool(fee_service["0-2 add-ons"] > fee_service["3-6 add-ons"]),
        "H6": bool(payment[True] > payment[False]),
        "H9": None, "H10": None,
    }
    records=[]
    for hid,status,test_id,conclusion,action in specifications:
        test = tests.loc[test_id] if test_id else None
        if test is not None and not test.significant_adjusted:
            status="不通过"
            conclusion="预设比较经多重比较校正未获得显著证据；原始机制仍受数据可用性限制。"
        elif test is not None and direction[hid] is False:
            status="不通过"
            conclusion="预设比较存在统计关联，但实测方向不支持原假设。"
        records.append(dict(hypothesis_id=hid, hypothesis_statement=original.loc[hid,"hypothesis_statement"],
            status=status, analyzed=test_id is not None, direction_supported=direction.get(hid), test_id=test_id or "", n=int(test.n) if test is not None else None,
            p_value=float(test.p_value) if test is not None else None, p_bonferroni=float(test.p_bonferroni) if test is not None else None,
            effect_name=test.effect_name if test is not None else "", effect=float(test.effect) if test is not None else None,
            conclusion=conclusion, action=action, limitations=LIMIT))
    return save_table(pd.DataFrame(records), "w2_hypothesis_results")


def run_analysis():
    result = analyze()
    result["charts"] = plot_all(result)
    result["hypotheses"] = hypothesis_results(result)
    return result


if __name__ == "__main__":
    analysis = run_analysis()
    print(analysis["hypotheses"][["hypothesis_id", "status", "p_bonferroni"]].to_string(index=False))
    print(f"Saved {len(analysis['charts'])} figures to {FIGURES}")
