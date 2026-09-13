"""
Telco Customer Churn - Data Quality Profiling Script
创建日期：2026-09-03
用途：系统化检查数据质量，生成可复现的质量基线报告

运行方式：
    python scripts/profile_data.py

输出：
    - 控制台日志
    - reports/tables/data_quality_results.csv
    - reports/tables/data_quality_issues.csv
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
from datetime import datetime

# 配置
INPUT_PATH = "data/raw/telco_customer_churn/WA_Fn-UseC_-Telco-Customer-Churn.csv"
OUTPUT_DIR = Path("reports/tables")
RANDOM_SEED = 42

def main():
    print("=" * 80)
    print("Telco Customer Churn - Data Quality Profile")
    print("=" * 80)
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Input: {INPUT_PATH}")
    print(f"Random seed: {RANDOM_SEED}")
    print()

    # 创建输出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 读取数据
    print("[1/9] Loading data...")
    try:
        df = pd.read_csv(INPUT_PATH)
        print(f"   SUCCESS: Loaded {len(df)} rows, {len(df.columns)} columns")
    except Exception as e:
        print(f"   FAILED: {e}")
        return 1

    # 初始化结果列表
    quality_results = []
    quality_issues = []

    # 2. 结构检查
    print("\n[2/9] Structure check...")
    quality_results.append({
        'dimension': 'Structure',
        'check': 'File readable',
        'status': 'PASS',
        'value': f'{len(df)} rows, {len(df.columns)} columns',
        'severity': 'N/A'
    })

    expected_cols = 21
    if len(df.columns) != expected_cols:
        quality_issues.append({
            'dimension': 'Structure',
            'field': 'N/A',
            'rule': f'Expected {expected_cols} columns',
            'count': len(df.columns),
            'pct': 'N/A',
            'sample': str(list(df.columns)),
            'severity': 'P0',
            'impact': 'Column structure mismatch',
            'recommendation': 'Verify data source version',
            'needs_business_confirm': 'Yes'
        })

    # 3. 主键唯一性
    print("[3/9] Primary key uniqueness...")
    pk = 'customerID'
    null_count = df[pk].isna().sum()
    dup_count = df[pk].duplicated().sum()
    unique_count = df[pk].nunique()

    pk_status = 'PASS' if (null_count == 0 and dup_count == 0 and unique_count == len(df)) else 'FAIL'
    quality_results.append({
        'dimension': 'Uniqueness',
        'check': 'customerID uniqueness',
        'status': pk_status,
        'value': f'{unique_count} unique IDs, {null_count} nulls, {dup_count} duplicates',
        'severity': 'P0' if pk_status == 'FAIL' else 'N/A'
    })

    if null_count > 0:
        quality_issues.append({
            'dimension': 'Uniqueness',
            'field': pk,
            'rule': 'Primary key must not be null',
            'count': null_count,
            'pct': f'{null_count/len(df)*100:.2f}%',
            'sample': 'N/A',
            'severity': 'P0',
            'impact': 'Cannot identify analysis unit',
            'recommendation': 'Remove or investigate rows with null customerID',
            'needs_business_confirm': 'Yes'
        })

    if dup_count > 0:
        dup_ids = df[df[pk].duplicated(keep=False)][pk].head(3).tolist()
        quality_issues.append({
            'dimension': 'Uniqueness',
            'field': pk,
            'rule': 'Primary key must be unique',
            'count': dup_count,
            'pct': f'{dup_count/len(df)*100:.2f}%',
            'sample': str(dup_ids),
            'severity': 'P0',
            'impact': 'Ambiguous analysis unit',
            'recommendation': 'Investigate and deduplicate',
            'needs_business_confirm': 'Yes'
        })

    # 4. 完整性检查
    print("[4/9] Completeness check...")
    for col in df.columns:
        missing_count = df[col].isna().sum()
        missing_pct = missing_count / len(df) * 100

        quality_results.append({
            'dimension': 'Completeness',
            'check': f'{col} missing',
            'status': 'PASS' if missing_count == 0 else 'WARN',
            'value': f'{missing_count} ({missing_pct:.2f}%)',
            'severity': 'P1' if missing_pct > 5 and col in ['Churn', 'tenure', 'MonthlyCharges'] else 'P2'
        })

        if missing_count > 0:
            quality_issues.append({
                'dimension': 'Completeness',
                'field': col,
                'rule': 'Should not have missing values',
                'count': missing_count,
                'pct': f'{missing_pct:.2f}%',
                'sample': 'N/A',
                'severity': 'P1' if col in ['Churn', 'tenure', 'MonthlyCharges'] else 'P2',
                'impact': 'May affect feature engineering or modeling',
                'recommendation': 'Investigate pattern, consider imputation or flagging',
                'needs_business_confirm': 'No'
            })

    # 5. 类型和格式检查
    print("[5/9] Type and format check...")

    # TotalCharges 应该是数值但是字符串
    if df['TotalCharges'].dtype == 'object':
        blank_count = (df['TotalCharges'] == ' ').sum()
        quality_results.append({
            'dimension': 'Type',
            'check': 'TotalCharges type',
            'status': 'WARN',
            'value': f'object (expected numeric), {blank_count} blank strings',
            'severity': 'P1'
        })

        quality_issues.append({
            'dimension': 'Type',
            'field': 'TotalCharges',
            'rule': 'Should be numeric',
            'count': blank_count,
            'pct': f'{blank_count/len(df)*100:.2f}%',
            'sample': 'Blank string " "',
            'severity': 'P1',
            'impact': 'Cannot use as numeric feature',
            'recommendation': 'Convert blank to NaN, then to float; investigate why blank',
            'needs_business_confirm': 'No'
        })

    # 6. 合法范围检查
    print("[6/9] Valid range check...")

    # tenure 范围
    tenure_min, tenure_max = df['tenure'].min(), df['tenure'].max()
    tenure_neg = (df['tenure'] < 0).sum()
    quality_results.append({
        'dimension': 'Range',
        'check': 'tenure range',
        'status': 'PASS' if tenure_neg == 0 else 'FAIL',
        'value': f'{tenure_min} - {tenure_max} months, {tenure_neg} negative',
        'severity': 'P0' if tenure_neg > 0 else 'N/A'
    })

    # MonthlyCharges 范围
    mc_min, mc_max = df['MonthlyCharges'].min(), df['MonthlyCharges'].max()
    mc_neg = (df['MonthlyCharges'] < 0).sum()
    mc_zero = (df['MonthlyCharges'] == 0).sum()
    quality_results.append({
        'dimension': 'Range',
        'check': 'MonthlyCharges range',
        'status': 'PASS' if mc_neg == 0 else 'FAIL',
        'value': f'{mc_min:.2f} - {mc_max:.2f}, {mc_neg} negative, {mc_zero} zero',
        'severity': 'P0' if mc_neg > 0 else ('P2' if mc_zero > 0 else 'N/A')
    })

    if mc_zero > 0:
        quality_issues.append({
            'dimension': 'Range',
            'field': 'MonthlyCharges',
            'rule': 'Should not be zero for active customers',
            'count': mc_zero,
            'pct': f'{mc_zero/len(df)*100:.2f}%',
            'sample': 'MonthlyCharges = 0',
            'severity': 'P2',
            'impact': 'May indicate data quality issue or special customer type',
            'recommendation': 'Investigate business meaning',
            'needs_business_confirm': 'Yes'
        })

    # 7. 类别取值检查
    print("[7/9] Categorical values check...")

    categorical_expected = {
        'gender': ['Male', 'Female'],
        'SeniorCitizen': [0, 1],
        'Partner': ['Yes', 'No'],
        'Dependents': ['Yes', 'No'],
        'PhoneService': ['Yes', 'No'],
        'Contract': ['Month-to-month', 'One year', 'Two year'],
        'PaperlessBilling': ['Yes', 'No'],
        'Churn': ['Yes', 'No']
    }

    for col, expected_vals in categorical_expected.items():
        actual_vals = df[col].unique().tolist()
        unexpected = set(actual_vals) - set(expected_vals)

        status = 'PASS' if len(unexpected) == 0 else 'WARN'
        quality_results.append({
            'dimension': 'Category',
            'check': f'{col} valid values',
            'status': status,
            'value': f'{len(actual_vals)} unique, unexpected: {list(unexpected) if unexpected else "none"}',
            'severity': 'P1' if unexpected else 'N/A'
        })

        if unexpected:
            quality_issues.append({
                'dimension': 'Category',
                'field': col,
                'rule': f'Expected values: {expected_vals}',
                'count': len(unexpected),
                'pct': 'N/A',
                'sample': str(list(unexpected)),
                'severity': 'P1',
                'impact': 'May cause encoding errors',
                'recommendation': 'Verify if legitimate values or data error',
                'needs_business_confirm': 'Yes'
            })

    # 8. 业务逻辑一致性
    print("[8/9] Business logic consistency...")

    # TotalCharges vs tenure consistency (需要先清洗TotalCharges)
    # 这里只做样本检查，详细验证在W3清洗时
    quality_results.append({
        'dimension': 'Consistency',
        'check': 'TotalCharges vs tenure logic',
        'status': 'DEFER',
        'value': 'Deferred to W3 cleaning pipeline',
        'severity': 'N/A'
    })

    # 服务逻辑：无互联网服务时，增值服务应为 "No internet service"
    internet_service_cols = ['OnlineSecurity', 'OnlineBackup', 'DeviceProtection',
                             'TechSupport', 'StreamingTV', 'StreamingMovies']
    no_internet = df[df['InternetService'] == 'No']

    for col in internet_service_cols:
        invalid_count = ((df['InternetService'] == 'No') &
                         (df[col] != 'No internet service')).sum()

        if invalid_count > 0:
            quality_issues.append({
                'dimension': 'Consistency',
                'field': f'InternetService vs {col}',
                'rule': 'No internet service should have "No internet service" for add-ons',
                'count': invalid_count,
                'pct': f'{invalid_count/len(df)*100:.2f}%',
                'sample': f'{col} has invalid value when InternetService=No',
                'severity': 'P2',
                'impact': 'Logic inconsistency',
                'recommendation': 'Standardize to "No internet service" or investigate',
                'needs_business_confirm': 'No'
            })

    # 9. 标签和不平衡检查
    print("[9/9] Label quality and imbalance check...")

    churn_dist = df['Churn'].value_counts()
    churn_rate = churn_dist['Yes'] / len(df) * 100

    quality_results.append({
        'dimension': 'Label',
        'check': 'Churn distribution',
        'status': 'PASS',
        'value': f'Yes: {churn_dist["Yes"]} ({churn_rate:.2f}%), No: {churn_dist["No"]} ({100-churn_rate:.2f}%)',
        'severity': 'N/A'
    })

    quality_results.append({
        'dimension': 'Label',
        'check': 'Class imbalance',
        'status': 'WARN',
        'value': f'Minority class: {churn_rate:.2f}%',
        'severity': 'Note for W5'
    })

    # 保存结果
    print("\n" + "=" * 80)
    print("Saving results...")

    results_df = pd.DataFrame(quality_results)
    results_path = OUTPUT_DIR / "data_quality_results.csv"
    results_df.to_csv(results_path, index=False)
    print(f"   Saved: {results_path}")

    issues_df = pd.DataFrame(quality_issues)
    issues_path = OUTPUT_DIR / "data_quality_issues.csv"
    issues_df.to_csv(issues_path, index=False)
    print(f"   Saved: {issues_path}")

    # 汇总统计
    print("\n" + "=" * 80)
    print("Quality Summary:")
    print(f"   Total checks: {len(quality_results)}")
    print(f"   PASS: {(results_df['status'] == 'PASS').sum()}")
    print(f"   WARN: {(results_df['status'] == 'WARN').sum()}")
    print(f"   FAIL: {(results_df['status'] == 'FAIL').sum()}")
    print(f"   Total issues logged: {len(quality_issues)}")
    print(f"   P0 (blocking): {(issues_df['severity'] == 'P0').sum() if len(issues_df) > 0 else 0}")
    print(f"   P1 (must fix before modeling): {(issues_df['severity'] == 'P1').sum() if len(issues_df) > 0 else 0}")
    print(f"   P2 (optimize later): {(issues_df['severity'] == 'P2').sum() if len(issues_df) > 0 else 0}")

    print("\n" + "=" * 80)
    print("Quality profiling completed successfully")
    print("=" * 80)

    return 0

if __name__ == "__main__":
    sys.exit(main())
