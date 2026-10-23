"""Business names for the registered, unchanged 64 W4 logical variables."""

LABELS = {
    "tenure": "在网月数", "MonthlyCharges": "当前月费", "TotalCharges": "累计费用",
    "gender": "性别", "SeniorCitizen": "老年客户标记", "Partner": "伴侣标记",
    "Dependents": "被抚养人标记", "PhoneService": "电话服务", "MultipleLines": "多线路服务",
    "InternetService": "互联网接入类型", "OnlineSecurity": "在线安全服务",
    "OnlineBackup": "在线备份服务", "DeviceProtection": "设备保护服务",
    "TechSupport": "技术支持服务", "StreamingTV": "流媒体电视", "StreamingMovies": "流媒体电影",
    "Contract": "合约类型", "PaperlessBilling": "无纸账单", "PaymentMethod": "付款方式",
    "total_charges_missing": "累计费用缺失标记", "tenure_zero": "零在网月数标记",
    "internet_applicable": "互联网适用标记", "tenure_log1p": "在网月数对数",
    "monthly_charges_log1p": "当前月费对数", "total_charges_log1p": "累计费用对数",
    "tenure_band": "在网阶段", "monthly_charge_band": "月费档位",
    "historical_monthly_average": "历史月均费用代理",
    "current_to_historical_charge_ratio": "当前月费与历史均费比",
    "monthly_charge_gap": "当前月费与历史均费差额",
    "constant_rate_total_proxy": "当前费率累计费用场景",
    "cumulative_charge_gap": "累计费用与当前费率场景差额",
    "charge_history_available": "费用历史可计算标记",
    "historical_charge_positive": "历史费用正值标记", "household_profile": "家庭关系组合",
    "household_support_count": "家庭关系标记数量",
    "senior_without_household_support": "无家庭关系标记的老年客户",
    "phone_applicable": "电话适用标记", "internet_addon_count": "互联网附加服务数量",
    "protection_addon_count": "保护类附加服务数量", "support_security_count": "安全与支持服务数量",
    "streaming_addon_count": "流媒体附加服务数量", "internet_without_addons": "未开通附加项的互联网用户",
    "unprotected_streaming": "无保护服务的流媒体用户", "unsupported_fiber": "无技术支持的光纤用户",
    "internet_bundle_profile": "互联网服务组合", "core_service_count": "核心服务数量",
    "active_service_count": "已开通服务总数", "charge_per_active_service": "每项服务均摊月费代理",
    "contract_months": "名义合约月数", "tenure_contract_ratio": "在网时长与名义合约比",
    "nominal_contract_charge_proxy": "名义合约费用场景", "tenure_contract_phase": "在网与名义合约相对阶段",
    "automatic_payment": "自动付款标记", "billing_profile": "账单与付款组合",
    "manual_paperless": "无纸账单且人工付款", "month_to_month_manual_payment": "按月合约且人工付款",
    "fiber_month_to_month": "光纤且按月合约", "new_month_to_month": "新客且按月合约",
    "senior_manual_payment": "老年客户且人工付款", "household_long_contract": "家庭关系与年度合约组合",
    "fiber_streaming_count": "光纤与流媒体数量交互", "support_streaming_balance": "安全支持与娱乐服务数量差",
    "household_streaming": "家庭关系与流媒体组合",
}

CATEGORY_LABELS = {
    "Month-to-month": "按月", "One year": "一年", "Two year": "两年",
    "Fiber optic": "光纤", "DSL": "DSL", "Yes": "是", "No": "否",
    "No internet service": "无互联网服务", "No phone service": "无电话服务",
    "Electronic check": "电子支票", "Mailed check": "邮寄支票",
    "Bank transfer (automatic)": "银行自动扣款", "Credit card (automatic)": "信用卡自动扣款",
    "Female": "女性", "Male": "男性", "not_applicable": "不适用", "basic": "基础",
    "protection_support": "保护支持", "entertainment": "娱乐", "mixed": "混合",
    "neither": "两者均无", "partner_only": "仅伴侣", "dependents_only": "仅被抚养人", "both": "两者均有",
    "within_nominal": "名义期限内", "beyond_nominal": "超过名义期限", "zero": "零月",
    "paperless_auto": "无纸自动", "paperless_manual": "无纸人工",
    "paper_auto": "纸质自动", "paper_manual": "纸质人工",
}


def review_action(feature):
    """Investigation prompts, never an estimated causal treatment effect."""
    if feature in {"gender", "SeniorCitizen", "Partner", "Dependents", "household_profile", "household_support_count"}:
        return "仅用于检查模型偏差和服务可达性；不按人口属性自动限制服务或定价。"
    if "contract" in feature.lower() or feature == "Contract":
        return "核对客户合约、续约意向与实际到期记录；不能从名义合约长度推断到期。"
    if "tenure" in feature or feature == "new_month_to_month":
        return "核对客户所处使用阶段及上手障碍；静态在网时长不等于近期活跃度。"
    if "charge" in feature.lower() or feature in {"MonthlyCharges", "TotalCharges"}:
        return "核对账单、用量与价格体验；费用比值和差额不证明发生过涨价。"
    if "payment" in feature.lower() or "billing" in feature.lower() or feature in {"PaymentMethod", "PaperlessBilling", "manual_paperless"}:
        return "核对支付便利性、失败扣款及账单反馈；不把付款方式解释为因果。"
    if feature in {"InternetService", "PhoneService", "MultipleLines"} or "fiber" in feature:
        return "核对产品适配、连接体验和真实支持记录；不据代理数据认定网络质量问题。"
    return "核对服务是否适用、是否满足真实需求及支持体验；不因相关性自动推销附加项。"
